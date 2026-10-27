import numpy as np
import pytest

from satori.__main__ import main
from satori.labels import (
    Quality,
    confident_indices,
    quality_of,
    restrict,
    weights,
)
from satori.model import Split

ROWS = [
    {"name": "once", "n_measurements": "1", "spread": "0.0"},
    {"name": "twice_agreeing", "n_measurements": "2", "spread": "0.2"},
    {"name": "twice_disagreeing", "n_measurements": "2", "spread": "3.0"},
    {"name": "many_agreeing", "n_measurements": "20", "spread": "0.5"},
]


def test_quality_reads_a_row():
    assert quality_of(ROWS[3]) == Quality(20, 0.5)


def test_quality_of_a_row_without_the_columns():
    """An ordinary library CSV has no measurement counts; treat it as one."""
    assert quality_of({"name": "x"}) == Quality(1, 0.0)


@pytest.mark.parametrize(
    "row, confident",
    [
        (ROWS[0], False),  # measured only once: nothing to check it against
        (ROWS[1], True),
        (ROWS[2], False),  # measured twice, but they disagree wildly
        (ROWS[3], True),
    ],
)
def test_confidence_needs_repeats_that_agree(row, confident):
    assert quality_of(row).confident == confident


def test_thresholds_can_be_tightened():
    assert quality_of(ROWS[3]).is_confident(min_measurements=2, max_spread=0.3) is False
    assert quality_of(ROWS[3]).is_confident(min_measurements=25) is False


def test_confident_indices():
    assert confident_indices(ROWS) == [1, 3]


def test_weights_average_to_one():
    """Weighting must change the balance, not the effective amount of data."""
    for scheme in ("equal", "count", "agreement", "both"):
        assert weights(ROWS, scheme).mean() == pytest.approx(1.0)


def test_equal_weights_are_all_the_same():
    assert np.allclose(weights(ROWS, "equal"), 1.0)


def test_count_weighting_favours_repeated_measurements():
    by_count = weights(ROWS, "count")
    assert by_count[3] > by_count[1] > by_count[0]  # 20 > 2 > 1 measurements


def test_agreement_weighting_punishes_disagreement():
    by_agreement = weights(ROWS, "agreement")
    assert by_agreement[1] > by_agreement[2]  # spread 0.2 beats spread 3.0


def test_both_combines_the_two():
    assert np.allclose(
        weights(ROWS, "both"),
        (weights(ROWS, "count") * weights(ROWS, "agreement"))
        / (weights(ROWS, "count") * weights(ROWS, "agreement")).mean(),
    )


def test_unknown_weight_scheme_is_rejected():
    with pytest.raises(ValueError, match="unknown weight scheme"):
        weights(ROWS, "vibes")


def test_restrict_narrows_each_side_independently():
    split = Split("cluster", [0, 1, 2, 3], [4, 5, 6, 7], "held out")

    assert restrict(split, test_allowed={4, 6}).test == [4, 6]
    assert restrict(split, test_allowed={4, 6}).train == [0, 1, 2, 3]  # training untouched
    assert restrict(split, train_allowed={1}).train == [1]
    assert restrict(split, train_allowed={1}).test == [4, 5, 6, 7]  # test untouched

    both = restrict(split, train_allowed={1, 2}, test_allowed={5})
    assert (both.train, both.test) == ([1, 2], [5])
    assert "scored on 1 confident labels" in both.explanation


def test_restrict_with_nothing_allowed_changes_nothing():
    split = Split("cluster", [0, 1], [2, 3], "held out")
    assert restrict(split).train == [0, 1]
    assert restrict(split).test == [2, 3]


# Distinct cores, so clustering finds real series instead of one blob.
CORES = [
    "c1ccccc1",
    "c1ccncc1",
    "c1ccoc1",
    "C1CCCCC1",
    "c1ccc2ccccc2c1",
    "c1cscc1",
    "C1CCNCC1",
    "c1cnc[nH]1",
    "C1CCOC1",
    "c1ccc(F)cc1",
    "C1CCCC1",
    "c1ccsc1",
]


def write_library(path, n_confident=60, n_single=120):
    """A library where confident labels are clean and single ones are noisy."""
    rng = np.random.default_rng(0)
    lines = ["name,smiles,pchembl,n_measurements,spread"]

    def molecule(i: int, tail: str) -> str:
        return "C" * (1 + i // len(CORES)) + tail + CORES[i % len(CORES)]

    for i in range(n_confident):
        # Potency follows the core, measured cleanly.
        lines.append(f"good{i},{molecule(i, 'O')},{5.0 + (i % len(CORES)) * 0.3:.2f},3,0.2")
    for i in range(n_single):
        value = 5.0 + (i % len(CORES)) * 0.3 + rng.normal(scale=1.5)
        lines.append(f"noisy{i},{molecule(i, 'N')},{value:.2f},1,0.0")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_labels_command(tmp_path, capsys):
    csv = write_library(tmp_path / "library.csv")
    code = main(
        ["labels", str(csv), "--repeats", "2", "--cutoff", "0.3", "--model", "ridge"]
        + ["--schemes", "count", "both"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "measured once only:" in out
    assert "Experiment 1" in out and "Experiment 2" in out
    assert "scored on confident labels only" in out
    assert "all labels, weighted by count" in out
    assert "confident labels only" in out
    assert "have a label we can check" in out


def test_labels_command_needs_the_quality_columns(tmp_path, capsys):
    csv = tmp_path / "plain.csv"
    csv.write_text("name,smiles,pchembl\na,CCO,5.0\nb,CCCO,6.0\n")
    assert main(["labels", str(csv)]) == 1
    assert "no 'n_measurements' column" in capsys.readouterr().err


def test_labels_command_refuses_too_few_confident_labels(tmp_path, capsys):
    csv = write_library(tmp_path / "thin.csv", n_confident=5, n_single=60)
    assert main(["labels", str(csv)]) == 1
    assert "too few confident labels" in capsys.readouterr().err
