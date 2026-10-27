import numpy as np
import pytest

from satori import benchmark as bench
from satori.__main__ import main
from satori.features import FEATURIZERS, featurize
from satori.model import Split, random_split, top_hit_rate
from satori.molecule import parse_smiles
from satori.similarity import fingerprint_of

ALKANES = ["CCC", "CCCC", "CCCCC", "CCCCCC", "CCCCCCC", "CCCCCCCC"]
AROMATICS = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "CCCc1ccccc1", "Oc1ccccc1", "Nc1ccccc1"]


@pytest.fixture
def mols():
    return [parse_smiles(s) for s in ALKANES + AROMATICS]


@pytest.fixture
def library_csv(tmp_path):
    path = tmp_path / "tiny.csv"
    rows = ["name,smiles,pchembl"]
    rows += [f"alkane{i},{s},5.0" for i, s in enumerate(ALKANES)]
    rows += [f"arene{i},{s},8.0" for i, s in enumerate(AROMATICS)]
    path.write_text("\n".join(rows) + "\n")
    return path


@pytest.mark.parametrize("name", list(FEATURIZERS))
def test_every_featurizer_returns_one_row_per_molecule(name, mols):
    table = featurize(name, mols)
    assert table.shape[0] == len(mols)
    assert table.shape[1] > 0
    assert np.isfinite(table).all()


def test_counts_differ_from_on_off_bits(mols):
    """A molecule with a fragment twice should differ from one with it once."""
    binary = featurize("ecfp4", mols)
    counts = featurize("ecfp4_counts", mols)
    assert counts.max() > 1
    assert binary.max() == 1
    assert not np.array_equal(binary, (counts > 0).astype(binary.dtype)) is False


def test_descriptors_add_columns_to_fingerprints(mols):
    assert (
        featurize("ecfp4_counts+descriptors", mols).shape[1]
        == featurize("ecfp4_counts", mols).shape[1] + featurize("descriptors_only", mols).shape[1]
    )


def test_unknown_featurizer_is_rejected(mols):
    with pytest.raises(ValueError, match="unknown featurizer"):
        featurize("magic", mols)


def test_tanimoto_kernel_matches_step_4_similarity():
    smiles = ["CCO", "CCCO", "c1ccccc1"]
    table = featurize("ecfp4", [parse_smiles(s) for s in smiles])
    kernel = bench.tanimoto_kernel(table, table)

    assert np.allclose(np.diag(kernel), 1.0)  # identical to itself
    assert np.allclose(kernel, kernel.T)  # symmetric
    # Same numbers the Step 4 code gives.
    from satori.similarity import similarity

    expected = similarity(fingerprint_of(smiles[0]), fingerprint_of(smiles[1]))
    assert kernel[0, 1] == pytest.approx(expected, abs=1e-6)


def test_tanimoto_kernel_handles_an_empty_fingerprint():
    """An all-zero row must give 0 similarity, not a divide-by-zero."""
    table = np.array([[0, 0, 0], [1, 1, 0]], dtype=np.uint8)
    assert bench.tanimoto_kernel(table, table)[0, 0] == 0.0


def test_top_hit_rate_rewards_correct_ranking():
    actual = np.arange(100.0)
    assert top_hit_rate(actual, actual) == 1.0  # perfect ranking
    assert top_hit_rate(actual, -actual) == 0.0  # exactly backwards


def test_top_hit_rate_of_random_guessing_is_near_the_share():
    rng = np.random.default_rng(0)
    actual = rng.normal(size=2000)
    rates = [top_hit_rate(actual, rng.normal(size=2000)) for _ in range(5)]
    assert 0.02 < float(np.mean(rates)) < 0.2  # around 0.10


@pytest.mark.parametrize("name", list(bench.MODELS))
def test_every_model_can_train_and_predict(name, mols):
    x = featurize("ecfp4", mols)
    y = np.array([5.0] * len(ALKANES) + [8.0] * len(AROMATICS))
    model = bench.MODELS[name](0)
    model.fit(x, y)
    predictions = model.predict(x)
    assert predictions.shape == y.shape
    assert np.isfinite(predictions).all()


@pytest.mark.parametrize("name", list(bench.MODELS))
def test_every_model_accepts_sample_weights(name, mols):
    """The label-quality experiment weights molecules, so all models must."""
    x = featurize("ecfp4", mols)
    y = np.array([5.0] * len(ALKANES) + [8.0] * len(AROMATICS))
    weights = np.linspace(0.5, 1.5, len(y))
    predictions = bench.MODELS[name](0).fit(x, y, sample_weight=weights).predict(x)
    assert np.isfinite(predictions).all()


def test_run_measures_every_contestant_under_the_same_split(mols):
    x = {"ecfp4": featurize("ecfp4", mols)}
    y = np.array([5.0] * len(ALKANES) + [8.0] * len(AROMATICS))
    contestants = [("ridge", "ecfp4"), ("tanimoto_svr", "ecfp4")]
    results = bench.run(
        x, y, lambda seed: random_split(len(mols), 0.34, seed), contestants, repeats=2
    )
    assert len(results.results) == 2
    assert all(r.scores.repeats == 2 for r in results.results)
    assert all(r.seconds >= 0 for r in results.results)


def test_ranked_puts_the_best_r2_first():
    def result(name, r2):
        from satori.model import RepeatedScores, Scores

        runs = [Scores(name, 10, 5, r2, 0.5, 0.6, 0.7, 1.0) for _ in range(2)]
        return bench.Result(name, "ecfp4", 2048, RepeatedScores(name, runs), 1.0)

    results = bench.Benchmark([result("worse", 0.2), result("better", 0.6)])
    assert [r.model for r in results.ranked] == ["better", "worse"]
    # Identical scores have no spread, so a 0.4 gap cannot be a tie.
    assert not results.ties_with_best(results.ranked[1])


def test_a_failing_contestant_is_reported_not_fatal(mols):
    x = {"ecfp4": featurize("ecfp4", mols)}
    y = np.array([5.0] * len(mols))
    # A split holding nothing back cannot be scored, so evaluate raises.
    broken = Split("cluster", list(range(len(mols))), [], "nothing held out")
    results = bench.run(x, y, lambda seed: broken, [("ridge", "ecfp4")], repeats=1)

    assert "left one side empty" in results.results[0].error
    assert not results.ranked  # a failure must not be ranked as a result


def test_benchmark_command(library_csv, capsys):
    code = main(
        ["benchmark", str(library_csv), "--repeats", "2", "--test-fraction", "0.34"]
        + ["--only", "ridge", "gradient_boosting"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "chemical series among 12 molecules" in out
    assert "Best honest R2" in out
    assert "top 10%" in out


def test_benchmark_command_rejects_a_missing_column(library_csv, capsys):
    assert main(["benchmark", str(library_csv), "--column", "nope"]) == 1
    assert "no 'nope' column" in capsys.readouterr().err


def test_benchmark_command_rejects_unknown_contestants(library_csv, capsys):
    assert main(["benchmark", str(library_csv), "--only", "neural_net"]) == 1
    assert "no contestants named" in capsys.readouterr().err
