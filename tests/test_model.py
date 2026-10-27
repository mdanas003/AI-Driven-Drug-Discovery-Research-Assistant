from pathlib import Path

import numpy as np
import pytest

from satori.__main__ import main
from satori.model import (
    Split,
    cluster_split,
    evaluate,
    features,
    random_split,
)
from satori.similarity import Cluster, cluster, fingerprint_of

EXAMPLE_CSV = Path(__file__).parent.parent / "examples" / "known_drugs.csv"

# Two families: short alkanes and benzene-like rings. A model that has seen
# one member of a family should do well on the others.
ALKANES = ["CCC", "CCCC", "CCCCC", "CCCCCC", "CCCCCCC", "CCCCCCCC"]
AROMATICS = ["c1ccccc1", "Cc1ccccc1", "CCc1ccccc1", "CCCc1ccccc1", "Oc1ccccc1", "Nc1ccccc1"]


@pytest.fixture
def library():
    smiles = ALKANES + AROMATICS
    fps = [fingerprint_of(s) for s in smiles]
    # Alkanes are weak, aromatics are potent: a pattern a model can learn.
    values = np.array([5.0] * len(ALKANES) + [8.0] * len(AROMATICS))
    return fps, values


def test_features_are_fingerprint_bits(library):
    fps, _ = library
    x = features(fps)
    assert x.shape == (len(fps), 2048)
    assert set(np.unique(x)) <= {0, 1}


def test_random_split_covers_every_molecule_exactly_once():
    split = random_split(100, test_fraction=0.2, seed=0)
    assert len(split.test) == 20
    assert len(split.train) == 80
    assert sorted(split.train + split.test) == list(range(100))


def test_random_split_is_repeatable_with_a_seed():
    assert random_split(100, seed=7).test == random_split(100, seed=7).test
    assert random_split(100, seed=7).test != random_split(100, seed=8).test


def test_cluster_split_never_breaks_a_cluster_apart():
    clusters = [Cluster(i * 10, list(range(i * 10, i * 10 + 10))) for i in range(10)]
    split = cluster_split(clusters, test_fraction=0.3, seed=0)

    assert sorted(split.train + split.test) == list(range(100))
    test = set(split.test)
    for group in clusters:
        members = set(group.members)
        # Every cluster is wholly in training or wholly in test, never split.
        assert members <= test or not (members & test)


def test_cluster_split_holds_out_roughly_the_requested_share():
    clusters = [Cluster(i, [i]) for i in range(100)]
    assert len(cluster_split(clusters, test_fraction=0.25, seed=0).test) == 25


def test_a_model_learns_a_real_pattern(library):
    fps, values = library
    x = features(fps)
    split = random_split(len(fps), test_fraction=0.34, seed=1)
    _, scores = evaluate(x, values, split, trees=30, seed=0)
    assert scores.beats_baseline
    assert scores.n_train + scores.n_test == len(fps)


def test_a_model_cannot_learn_noise(library):
    """Random targets must not produce a good score. A guard against leakage."""
    fps, _ = library
    noise = np.random.default_rng(0).normal(size=len(fps))
    _, scores = evaluate(
        features(fps), noise, random_split(len(fps), test_fraction=0.34, seed=1), trees=30
    )
    assert scores.r2 < 0.5


def test_the_cluster_split_is_the_harder_test(library):
    """The honest split should not flatter the model more than the easy one."""
    fps, values = library
    x = features(fps)
    clusters = cluster(fps, cutoff=0.5)
    assert len(clusters) >= 2, "the fixture must contain separable families"

    _, optimistic = evaluate(x, values, random_split(len(fps), 0.34, seed=1), trees=30)
    _, honest = evaluate(x, values, cluster_split(clusters, 0.34, seed=1), trees=30)
    assert honest.mae >= optimistic.mae


def test_random_split_always_leaves_both_sides_usable():
    """Asking for nothing, or everything, must not produce an empty side."""
    assert random_split(10, test_fraction=0.0).test
    assert random_split(10, test_fraction=1.0).test


def test_evaluate_rejects_an_empty_side(library):
    fps, values = library
    empty = Split("broken", list(range(len(fps))), [], "nothing held out")
    with pytest.raises(ValueError, match="left one side empty"):
        evaluate(features(fps), values, empty, trees=5)


def test_train_command_reports_both_splits_and_saves(tmp_path, capsys):
    model = tmp_path / "egfr.joblib"
    code = main(
        [
            "train",
            str(EXAMPLE_CSV),
            "--column",
            "molecular_weight_placeholder",
        ]
    )
    assert code == 1
    assert "no 'molecular_weight_placeholder' column" in capsys.readouterr().err

    # The example library has no potency column, so build a tiny one.
    library_csv = tmp_path / "tiny.csv"
    rows = ["name,smiles,pchembl"]
    rows += [f"alkane{i},{s},5.0" for i, s in enumerate(ALKANES)]
    rows += [f"arene{i},{s},8.0" for i, s in enumerate(AROMATICS)]
    library_csv.write_text("\n".join(rows) + "\n")

    assert main(["train", str(library_csv), "--trees", "20", "--save", str(model)]) == 0
    out = capsys.readouterr().out
    assert "random split" in out and "cluster split" in out
    assert "flatters this model by" in out
    assert model.exists()

    # A saved model carries its honest scores and can predict.
    assert main(["predict", str(model), "CCCCCCCCC"]) == 0
    out = capsys.readouterr().out
    assert "on unseen chemical series it was out by" in out
    assert "predicted pchembl" in out


def test_predict_reports_a_bad_smiles_without_crashing(tmp_path, capsys):
    library_csv = tmp_path / "tiny.csv"
    library_csv.write_text(
        "name,smiles,pchembl\n" + "\n".join(f"m{i},{s},5.0" for i, s in enumerate(ALKANES)) + "\n"
    )
    model = tmp_path / "m.joblib"
    main(["train", str(library_csv), "--trees", "10", "--save", str(model)])
    capsys.readouterr()

    assert main(["predict", str(model), "C1CC"]) == 1
    assert "Not a valid SMILES" in capsys.readouterr().out


def test_predict_reports_a_missing_model(capsys):
    assert main(["predict", "nope.joblib", "CCO"]) == 1
    assert "cannot read model" in capsys.readouterr().err
