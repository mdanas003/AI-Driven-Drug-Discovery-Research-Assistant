from pathlib import Path

import pytest

from satori.__main__ import main
from satori.similarity import (
    N_BITS,
    cluster,
    fingerprint_library,
    fingerprint_of,
    most_similar,
    similarity,
)

EXAMPLE_CSV = Path(__file__).parent.parent / "examples" / "known_drugs.csv"

GEFITINIB = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"
ERLOTINIB = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"
ETHANOL = "CCO"


def test_fingerprint_size():
    assert fingerprint_of(ETHANOL).GetNumBits() == N_BITS


def test_a_molecule_is_identical_to_itself():
    assert similarity(fingerprint_of(GEFITINIB), fingerprint_of(GEFITINIB)) == 1.0


def test_salt_form_fingerprints_the_same_as_the_drug():
    assert similarity(fingerprint_of(GEFITINIB), fingerprint_of(GEFITINIB + ".Cl")) == 1.0


def test_related_drugs_score_higher_than_unrelated_ones():
    gefitinib = fingerprint_of(GEFITINIB)
    related = similarity(gefitinib, fingerprint_of(ERLOTINIB))
    unrelated = similarity(gefitinib, fingerprint_of(ETHANOL))
    assert related > 0.3 > unrelated


def test_fingerprint_library_skips_unreadable_rows():
    rows = [
        {"name": "good", "smiles": ETHANOL},
        {"name": "bad", "smiles": "C1CC"},
    ]
    kept, fps, skipped = fingerprint_library(rows)
    assert [r["name"] for r in kept] == ["good"]
    assert len(fps) == 1
    assert skipped == ["bad"]


def test_most_similar_ranks_best_first_and_respects_limits():
    library = [fingerprint_of(s) for s in (ETHANOL, ERLOTINIB, GEFITINIB)]
    hits = most_similar(fingerprint_of(GEFITINIB), library)
    assert [h.index for h in hits] == [2, 1, 0]  # itself, the relative, the stranger
    assert hits[0].similarity == 1.0
    assert len(most_similar(fingerprint_of(GEFITINIB), library, top=2)) == 2
    assert [h.index for h in most_similar(fingerprint_of(GEFITINIB), library, minimum=0.9)] == [2]


def test_cluster_groups_the_related_and_isolates_the_stranger():
    library = [fingerprint_of(s) for s in (GEFITINIB, GEFITINIB + ".O", ETHANOL)]
    clusters = cluster(library, cutoff=0.9)
    assert [len(c) for c in clusters] == [2, 1]
    assert clusters[0].members == [0, 1]
    assert clusters[1].members == [2]


def test_cluster_order_decides_which_molecule_is_the_centre():
    library = [fingerprint_of(s) for s in (GEFITINIB, GEFITINIB + ".O")]
    assert cluster(library, cutoff=0.9)[0].centre == 0
    assert cluster(library, cutoff=0.9, order=[1, 0])[0].centre == 1


def test_similar_command_accepts_a_name_from_the_library(capsys):
    assert main(["similar", "aspirin", str(EXAMPLE_CSV), "--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "found in the library" in out
    # The query itself must not be reported as its own neighbour.
    assert "aspirin " not in out.split("rank")[1]


def test_similar_command_accepts_a_smiles_string(capsys):
    assert main(["similar", GEFITINIB, str(EXAMPLE_CSV), "--top", "2"]) == 0
    assert "erlotinib" in capsys.readouterr().out


def test_similar_command_rejects_an_unknown_query(capsys):
    assert main(["similar", "no-such-drug", str(EXAMPLE_CSV)]) == 1
    assert "neither a valid SMILES" in capsys.readouterr().err


def test_similar_command_reports_when_nothing_is_close_enough(capsys):
    assert main(["similar", "CCO", str(EXAMPLE_CSV), "--min", "0.99"]) == 0
    assert "Nothing in the library reaches" in capsys.readouterr().out


def test_cluster_command(capsys):
    assert main(["cluster", str(EXAMPLE_CSV), "--cutoff", "0.4"]) == 0
    out = capsys.readouterr().out
    assert "clusters" in out
    # The deliberately broken row in the example file is reported, not fatal.
    assert "skipped 1 unreadable structure(s): broken_row" in out


@pytest.mark.parametrize("command", ["similar", "cluster"])
def test_commands_fail_cleanly_on_a_missing_file(command, capsys):
    args = [command, "nope.csv"] if command == "cluster" else [command, "CCO", "nope.csv"]
    assert main(args) == 1
    assert "error:" in capsys.readouterr().err
