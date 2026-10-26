import csv
from pathlib import Path

import pytest

from satori.__main__ import main
from satori.library import load_csv, rank, save_csv, screen

EXAMPLE_CSV = Path(__file__).parent.parent / "examples" / "known_drugs.csv"


@pytest.fixture
def result():
    return screen(load_csv(EXAMPLE_CSV))


def test_load_csv_requires_columns(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("id,structure\n1,CCO\n")
    with pytest.raises(ValueError, match="missing column"):
        load_csv(path)


def test_invalid_rows_are_set_aside(result):
    assert [name for name, _ in result.invalid] == ["broken_row"]


def test_same_molecule_written_differently_is_a_duplicate(result):
    assert result.duplicates == [("aspirin_written_differently", "aspirin")]
    assert len(result.compounds) == 14


def test_rank_orders_by_qed(result):
    qeds = [c.props["qed"] for c in rank(result.compounds)]
    assert qeds == sorted(qeds, reverse=True)


def test_rank_drug_like_only_and_top(result):
    ranked = rank(result.compounds, drug_like_only=True)
    assert all(c.drug_like for c in ranked)
    assert {"atorvastatin", "cyclosporine"}.isdisjoint(c.name for c in ranked)
    assert len(rank(result.compounds, top=3)) == 3


def test_save_csv_round_trip(result, tmp_path):
    out = tmp_path / "ranked.csv"
    save_csv(rank(result.compounds, top=5), out)
    with open(out, newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["rank"] for r in rows] == ["1", "2", "3", "4", "5"]
    assert "qed" in rows[0]


def test_screen_command(tmp_path, capsys):
    out = tmp_path / "ranked.csv"
    assert main(["screen", str(EXAMPLE_CSV), "--drug-like", "--top", "5", "--out", str(out)]) == 0
    assert "skipped duplicate: aspirin_written_differently" in capsys.readouterr().out
    assert out.exists()


def test_screen_command_missing_file(capsys):
    assert main(["screen", "does-not-exist.csv"]) == 1
    assert "error:" in capsys.readouterr().err
