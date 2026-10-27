"""A fair fight between models, under one protocol.

Step 5 established that a score only means something alongside its split
protocol and its run-to-run spread. This module reuses that protocol for
every model and representation, so the resulting table is a comparison
rather than a collection of separately-tuned best cases.

The rule it enforces: **identical splits, identical repeats, identical
metrics, reported together.** A model only wins if it wins by more than
the run-to-run spread.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

from satori.model import (
    DEFAULT_REPEATS,
    DEFAULT_TREES,
    RepeatedScores,
    Split,
    evaluate_repeated,
    random_forest,
)


def tanimoto_kernel(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Tanimoto similarity between every row of `a` and every row of `b`.

    For on/off fingerprints this is the same measure as Step 4, written as
    matrix arithmetic: shared bits over bits in either one.
    """
    a = (a > 0).astype(np.float32)
    b = (b > 0).astype(np.float32)
    shared = a @ b.T
    either = a.sum(1)[:, None] + b.sum(1)[None, :] - shared
    return np.divide(shared, either, out=np.zeros_like(shared), where=either > 0)


class TanimotoSVR(BaseEstimator, RegressorMixin):
    """Support vector regression using chemical similarity as its kernel.

    A long-standing strong baseline on ChEMBL-sized sets: instead of
    treating fingerprint bits as independent features, it compares whole
    molecules by the same Tanimoto measure a chemist would use.

    It holds the training set to compare against, so memory grows with the
    square of the training size. At a few thousand molecules that is fine.
    """

    def __init__(self, C: float = 10.0, epsilon: float = 0.1):
        self.C = C
        self.epsilon = epsilon

    def fit(self, x: np.ndarray, y: np.ndarray, sample_weight=None) -> "TanimotoSVR":
        self.train_x_ = np.asarray(x, dtype=np.float32)
        self.svr_ = SVR(kernel="precomputed", C=self.C, epsilon=self.epsilon)
        self.svr_.fit(
            tanimoto_kernel(self.train_x_, self.train_x_), y, sample_weight=sample_weight
        )
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        kernel = tanimoto_kernel(np.asarray(x, dtype=np.float32), self.train_x_)
        return self.svr_.predict(kernel)


def gradient_boosting(seed: int = 0, trees: int = 600):
    """Many shallow trees, each correcting the last one's mistakes.

    Usually the strongest classical model on fingerprint-shaped data, and
    the main thing a random forest should be checked against.
    """
    from lightgbm import LGBMRegressor

    return LGBMRegressor(
        n_estimators=trees,
        learning_rate=0.05,
        num_leaves=63,
        colsample_bytree=0.5,
        random_state=seed,
        n_jobs=-1,
        verbose=-1,
    )


class ScaledRidge(BaseEstimator, RegressorMixin):
    """A straight line through 2,048 dimensions, on scaled features.

    Here to keep everyone honest: if this matches the clever models, the
    clever models are not earning their complexity.

    Written out rather than assembled as a Pipeline because a pipeline will
    not pass sample weights through to its final step without scikit-learn's
    metadata routing turned on, and every model here must accept weights so
    that the label-quality experiment can treat them all alike.
    """

    def __init__(self, alpha: float = 10.0):
        self.alpha = alpha

    def fit(self, x: np.ndarray, y: np.ndarray, sample_weight=None) -> "ScaledRidge":
        # with_mean=False keeps sparse fingerprint columns sparse.
        self.scaler_ = StandardScaler(with_mean=False).fit(x)
        self.ridge_ = Ridge(alpha=self.alpha)
        self.ridge_.fit(self.scaler_.transform(x), y, sample_weight=sample_weight)
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.ridge_.predict(self.scaler_.transform(x))


def ridge(seed: int = 0) -> ScaledRidge:
    return ScaledRidge()


MODELS: dict[str, Callable[[int], object]] = {
    "random_forest": lambda seed: random_forest(DEFAULT_TREES, seed),
    "gradient_boosting": gradient_boosting,
    "tanimoto_svr": lambda seed: TanimotoSVR(),
    "ridge": ridge,
}

# What gets compared by default. Not every pairing: each row is here to
# answer one question, and every row costs minutes of training.
DEFAULT_CONTESTANTS: list[tuple[str, str]] = [
    # The Step 5 result, so the table always contains its own reference.
    ("random_forest", "ecfp4"),
    # Does counting fragments beat merely noting them?
    ("random_forest", "ecfp4_counts"),
    # Does boosting beat bagging on the same representation?
    ("gradient_boosting", "ecfp4_counts"),
    # Do whole-molecule properties add anything to fragment counts?
    ("gradient_boosting", "ecfp4_counts+descriptors"),
    # Do larger fragments help?
    ("gradient_boosting", "ecfp6_counts"),
    # Does comparing whole molecules beat treating bits as independent?
    ("tanimoto_svr", "ecfp4"),
    # Is any of this better than a straight line, or than Step 1's seven numbers?
    ("ridge", "ecfp4_counts"),
    ("gradient_boosting", "descriptors_only"),
]


@dataclass
class Result:
    model: str
    features: str
    n_features: int
    scores: RepeatedScores
    seconds: float
    error: str = ""


@dataclass
class Benchmark:
    results: list[Result] = field(default_factory=list)

    @property
    def ranked(self) -> list[Result]:
        """Best first, by the honest R2 average."""
        return sorted(
            (r for r in self.results if not r.error),
            key=lambda r: r.scores.r2.mean,
            reverse=True,
        )

    def ties_with_best(self, result: Result) -> bool:
        """True if this result is within the run-to-run spread of the winner.

        Two models that differ by less than the noise are not ranked; they
        are tied, and the simpler one should be preferred.
        """
        best = self.ranked[0]
        noise = max(best.scores.r2.sd, result.scores.r2.sd)
        return abs(best.scores.r2.mean - result.scores.r2.mean) <= noise


def run(
    feature_tables: dict[str, np.ndarray],
    y: np.ndarray,
    split_for: Callable[[int], Split],
    contestants: list[tuple[str, str]] = DEFAULT_CONTESTANTS,
    repeats: int = DEFAULT_REPEATS,
    seed: int = 0,
    on_start: Callable[[str, str], None] | None = None,
    on_finish: Callable[[Result], None] | None = None,
) -> Benchmark:
    """Measure every contestant under the same splits and repeats."""
    benchmark = Benchmark()
    for model_name, feature_name in contestants:
        if on_start:
            on_start(model_name, feature_name)
        x = feature_tables[feature_name]
        started = time.perf_counter()
        try:
            _, scores = evaluate_repeated(
                x, y, split_for, repeats=repeats, model_for=MODELS[model_name], seed=seed
            )
            result = Result(
                model_name, feature_name, x.shape[1], scores, time.perf_counter() - started
            )
        except (ValueError, MemoryError, ImportError) as err:
            result = Result(
                model_name,
                feature_name,
                x.shape[1],
                RepeatedScores(model_name, []),
                time.perf_counter() - started,
                error=str(err),
            )
        benchmark.results.append(result)
        if on_finish:
            on_finish(result)
    return benchmark
