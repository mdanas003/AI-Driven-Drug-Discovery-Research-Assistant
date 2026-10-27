"""Step 5: predict potency from structure, and measure it honestly.

The model is a random forest: hundreds of decision trees, each trained on
a different random slice of the data, averaging their answers. It reads a
molecule's fingerprint bits (Step 4) and predicts its pChEMBL value.

The model is the easy half. The hard half is knowing whether its score
means anything, and that depends entirely on how the data is split.

**Random split** puts 20% of molecules aside for testing. But most of our
molecules belong to a chemical series of near-identical compounds, so a
molecule in the test set usually has close relatives in the training set.
The model can score well by recognizing scaffolds it has already seen.

**Cluster split** puts whole chemical series aside instead, using the
clusters from Step 4. Nothing in the test set has a close relative in
training, so the model must generalize to chemistry it has never met.

That is the question a real project asks: *will this work on the new
series we are about to make?* Satori reports both, because the gap
between them is the honest measure of how much the easy number flatters.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from rdkit import DataStructs
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

from satori.similarity import Cluster

DEFAULT_TEST_FRACTION = 0.2
DEFAULT_TREES = 300
# One split gives one number, and that number moves depending on which
# molecules happened to land in the test set. Repeating the whole
# experiment is the only way to know how much it moves.
DEFAULT_REPEATS = 5


def features(fingerprints: list) -> np.ndarray:
    """Stack fingerprints into the numeric table scikit-learn expects."""
    rows = np.zeros((len(fingerprints), fingerprints[0].GetNumBits()), dtype=np.uint8)
    for i, fp in enumerate(fingerprints):
        DataStructs.ConvertToNumpyArray(fp, rows[i])
    return rows


@dataclass
class Split:
    """Which molecules train the model and which ones test it."""

    name: str
    train: list[int]
    test: list[int]
    explanation: str


def random_split(
    n: int, test_fraction: float = DEFAULT_TEST_FRACTION, seed: int = 0
) -> Split:
    """Hold out a random sample of molecules. The optimistic measurement."""
    order = np.random.default_rng(seed).permutation(n)
    cut = max(1, round(n * test_fraction))
    return Split(
        "random",
        sorted(order[cut:].tolist()),
        sorted(order[:cut].tolist()),
        "test molecules may have close relatives in training",
    )


def cluster_split(
    clusters: list[Cluster], test_fraction: float = DEFAULT_TEST_FRACTION, seed: int = 0
) -> Split:
    """Hold out whole chemical series. The honest measurement.

    Clusters are taken in random order until the test set is large enough,
    so no test molecule has a close relative in the training set.
    """
    total = sum(len(c) for c in clusters)
    wanted = max(1, round(total * test_fraction))
    order = np.random.default_rng(seed).permutation(len(clusters))

    test: list[int] = []
    held_out = set()
    for index in order:
        if len(test) >= wanted:
            break
        test.extend(clusters[index].members)
        held_out.add(int(index))

    train = [i for c, cluster in enumerate(clusters) if c not in held_out for i in cluster.members]
    return Split(
        "cluster",
        sorted(train),
        sorted(test),
        f"{len(held_out)} whole series held out; no test molecule has a close relative in training",
    )


@dataclass
class Scores:
    """How well a model did, with a baseline for comparison.

    r2: share of the variation explained. 1.0 is perfect, 0.0 is no better
        than always guessing the average, and negative is worse than that.
    mae: average error in pChEMBL units. 1.0 means out by tenfold potency.
    spearman: how well the *ranking* matches, which is what a project
        actually needs when choosing which molecules to make next.
    baseline_mae: the error from always predicting the training average.
        A model that cannot beat this has learned nothing.
    top_hit_rate: take the 10% of molecules the model likes best. What
        share of them are genuinely among the 10% most potent? Picking at
        random would give 0.10, so this is the number a screening decision
        actually rests on: if we make what the model recommends, how often
        is it right?
    """

    split: str
    n_train: int
    n_test: int
    r2: float
    mae: float
    rmse: float
    spearman: float
    baseline_mae: float
    top_hit_rate: float = float("nan")

    @property
    def beats_baseline(self) -> bool:
        return self.mae < self.baseline_mae


def top_hit_rate(actual: np.ndarray, predicted: np.ndarray, share: float = 0.1) -> float:
    """Of the molecules the model ranks highest, how many truly belong there?"""
    how_many = max(1, round(len(actual) * share))
    best_predicted = set(np.argsort(predicted)[-how_many:].tolist())
    truly_best = set(np.argsort(actual)[-how_many:].tolist())
    return len(best_predicted & truly_best) / how_many


def random_forest(trees: int = DEFAULT_TREES, seed: int = 0) -> RandomForestRegressor:
    """The Step 5 model, and the reference every other model must beat."""
    return RandomForestRegressor(n_estimators=trees, random_state=seed, n_jobs=-1)


def evaluate(
    x: np.ndarray,
    y: np.ndarray,
    split: Split,
    model_for: Callable[[int], object] | None = None,
    seed: int = 0,
    sample_weight: np.ndarray | None = None,
) -> tuple[object, Scores]:
    """Train on the split's training half, score on its held-out half.

    `model_for` builds the model from a seed, so any scikit-learn style
    regressor can be measured under exactly the same protocol.
    `sample_weight` lets better-measured molecules count for more; the
    held-out half is always scored unweighted, since a score has to mean
    the same thing however the model was trained.
    """
    if not split.train or not split.test:
        raise ValueError(f"The {split.name} split left one side empty.")

    model = (model_for or random_forest)(seed)
    if sample_weight is None:
        model.fit(x[split.train], y[split.train])
    else:
        model.fit(x[split.train], y[split.train], sample_weight=sample_weight[split.train])
    predicted = model.predict(x[split.test])
    actual = y[split.test]

    # The honest floor: always predict the training average.
    baseline = np.full_like(actual, y[split.train].mean())
    correlation = spearmanr(actual, predicted).statistic if len(actual) > 2 else float("nan")

    return model, Scores(
        split=split.name,
        n_train=len(split.train),
        n_test=len(split.test),
        r2=round(float(r2_score(actual, predicted)), 3),
        mae=round(float(mean_absolute_error(actual, predicted)), 3),
        rmse=round(float(root_mean_squared_error(actual, predicted)), 3),
        spearman=round(float(correlation), 3),
        baseline_mae=round(float(mean_absolute_error(actual, baseline)), 3),
        top_hit_rate=round(top_hit_rate(actual, predicted), 3),
    )


@dataclass
class Spread:
    """One metric across repeated runs: its average and how much it moved."""

    mean: float
    sd: float
    low: float
    high: float

    def __str__(self) -> str:
        return f"{self.mean:.3f} +/- {self.sd:.3f}"


def spread_of(values: list[float]) -> Spread:
    """Average and variation of one metric. numpy, not statistics, because a
    metric can legitimately be undefined (Spearman needs three points) and
    nan must pass through rather than raise."""
    numbers = np.asarray(values, dtype=float)
    if numbers.size == 0:
        return Spread(float("nan"), float("nan"), float("nan"), float("nan"))
    return Spread(
        mean=round(float(numbers.mean()), 3),
        # Sample standard deviation; a single run has no spread to report.
        sd=round(float(numbers.std(ddof=1)), 3) if numbers.size > 1 else 0.0,
        low=round(float(numbers.min()), 3),
        high=round(float(numbers.max()), 3),
    )


@dataclass
class RepeatedScores:
    """The same experiment run several times, so the score has a range."""

    split: str
    runs: list[Scores]

    @property
    def repeats(self) -> int:
        return len(self.runs)

    def _of(self, metric: str) -> Spread:
        return spread_of([getattr(run, metric) for run in self.runs])

    @property
    def r2(self) -> Spread:
        return self._of("r2")

    @property
    def mae(self) -> Spread:
        return self._of("mae")

    @property
    def spearman(self) -> Spread:
        return self._of("spearman")

    @property
    def baseline_mae(self) -> Spread:
        return self._of("baseline_mae")

    @property
    def top_hit_rate(self) -> Spread:
        return self._of("top_hit_rate")

    @property
    def beats_baseline(self) -> bool:
        """True only if every repeat beat the baseline, not just the average."""
        return all(run.beats_baseline for run in self.runs)


def evaluate_repeated(
    x: np.ndarray,
    y: np.ndarray,
    split_for: Callable[[int], Split],
    repeats: int = DEFAULT_REPEATS,
    model_for: Callable[[int], object] | None = None,
    seed: int = 0,
    on_run: Callable[[int, Scores], None] | None = None,
    sample_weight: np.ndarray | None = None,
) -> tuple[object, RepeatedScores]:
    """Run the whole experiment `repeats` times with different randomness.

    Each repeat re-draws the split *and* re-seeds the forest, so the range
    that comes out covers both sources of luck. The returned model is the
    one from the first repeat, so that saving a model stays deterministic.
    """
    if repeats < 1:
        raise ValueError("repeats must be at least 1")

    first_model, runs = None, []
    for i in range(repeats):
        model, scores = evaluate(
            x, y, split_for(seed + i), model_for, seed + i, sample_weight=sample_weight
        )
        first_model = first_model if first_model is not None else model
        runs.append(scores)
        if on_run:
            on_run(i, scores)
    return first_model, RepeatedScores(runs[0].split, runs)
