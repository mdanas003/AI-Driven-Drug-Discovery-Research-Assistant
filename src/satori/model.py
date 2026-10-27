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

from dataclasses import dataclass

import numpy as np
from rdkit import DataStructs
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error

from satori.similarity import Cluster

DEFAULT_TEST_FRACTION = 0.2
DEFAULT_TREES = 300


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
    """

    split: str
    n_train: int
    n_test: int
    r2: float
    mae: float
    rmse: float
    spearman: float
    baseline_mae: float

    @property
    def beats_baseline(self) -> bool:
        return self.mae < self.baseline_mae


def train(
    x: np.ndarray, y: np.ndarray, trees: int = DEFAULT_TREES, seed: int = 0
) -> RandomForestRegressor:
    forest = RandomForestRegressor(n_estimators=trees, random_state=seed, n_jobs=-1)
    forest.fit(x, y)
    return forest


def evaluate(
    x: np.ndarray,
    y: np.ndarray,
    split: Split,
    trees: int = DEFAULT_TREES,
    seed: int = 0,
) -> tuple[RandomForestRegressor, Scores]:
    """Train on the split's training half, score on its held-out half."""
    if not split.train or not split.test:
        raise ValueError(f"The {split.name} split left one side empty.")

    forest = train(x[split.train], y[split.train], trees, seed)
    predicted = forest.predict(x[split.test])
    actual = y[split.test]

    # The honest floor: always predict the training average.
    baseline = np.full_like(actual, y[split.train].mean())
    correlation = spearmanr(actual, predicted).statistic if len(actual) > 2 else float("nan")

    return forest, Scores(
        split=split.name,
        n_train=len(split.train),
        n_test=len(split.test),
        r2=round(float(r2_score(actual, predicted)), 3),
        mae=round(float(mean_absolute_error(actual, predicted)), 3),
        rmse=round(float(root_mean_squared_error(actual, predicted)), 3),
        spearman=round(float(correlation), 3),
        baseline_mae=round(float(mean_absolute_error(actual, baseline)), 3),
    )
