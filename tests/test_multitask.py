import numpy as np
import pytest

from satori.__main__ import main
from satori.model import Split
from satori.multitask import (
    arms_for,
    audit,
    build_pool,
    honest_training_set,
    max_similarity_to,
    too_close,
    with_task_feature,
)
from satori.similarity import fingerprint_of

GEFITINIB = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"
ERLOTINIB = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"
ETHANOL = "CCO"

PRIMARY = [
    {"name": "a", "smiles": GEFITINIB, "pchembl": "7.5", "variant": "wild_type"},
    {"name": "b", "smiles": ERLOTINIB, "pchembl": "7.4", "variant": "wild_type"},
    {"name": "c", "smiles": ETHANOL, "pchembl": "4.0", "variant": "wild_type"},
]
# The same molecules, measured against mutant forms of the protein.
AUXILIARY = [
    {"name": "a", "smiles": GEFITINIB, "pchembl": "5.9", "variant": "T790M"},
    {"name": "d", "smiles": "CCCO", "pchembl": "4.2", "variant": "T790M"},
    {"name": "e", "smiles": "CCCCO", "pchembl": "4.3", "variant": "L858R"},
]


@pytest.fixture
def pool():
    return build_pool({"wt": PRIMARY, "mut": AUXILIARY}, primary="wild_type")


@pytest.fixture
def fps(pool):
    return [fingerprint_of(s) for s in pool.smiles]


def test_pool_splits_rows_by_protein_variant(pool):
    assert pool.task_names == ["wild_type", "T790M", "L858R"]
    assert len(pool) == 6
    assert pool.indices_of("wild_type") == [0, 1, 2]
    assert pool.is_primary.sum() == 3


def test_pool_falls_back_to_the_file_label_without_a_variant_column():
    rows = [{"name": "a", "smiles": ETHANOL, "pchembl": "5.0"}]
    pool = build_pool({"CHEMBL203": rows}, primary="CHEMBL203")
    assert pool.task_names == ["CHEMBL203"]


def test_pool_rejects_an_unknown_primary():
    with pytest.raises(ValueError, match="not among"):
        build_pool({"wt": PRIMARY}, primary="CHEMBL999")


def test_max_similarity_of_nothing_held_out_is_zero(fps):
    assert list(max_similarity_to(fps, [])) == [0.0] * len(fps)


def test_a_molecule_is_too_close_to_itself(fps):
    assert too_close([fps[0]], [fps[0]], cutoff=0.6)[0]
    assert not too_close([fps[2]], [fps[0]], cutoff=0.6)[0]  # ethanol vs gefitinib


def test_honest_training_set_drops_the_same_molecule_under_another_protein(pool, fps):
    """The leak this whole module exists to stop."""
    # Row 0 is gefitinib against wild-type; row 3 is gefitinib against T790M.
    kept = honest_training_set(fps, test=[0], cutoff=0.6)
    assert 0 not in kept  # the test molecule itself
    assert 3 not in kept  # the same molecule, different protein
    assert 2 in kept  # ethanol is unrelated, so it may stay


def test_honest_training_set_drops_close_relatives_too(fps):
    """Not just identical molecules: near neighbours leak as well."""
    propanol, butanol = fps[4], fps[5]
    # Near neighbours but not identical: 0.58 similar, so a 0.5 cut-off catches
    # them while the 0.6 default would not. The cut-off is a real choice.
    similarity = max_similarity_to([butanol], [propanol])[0]
    assert 0.5 <= similarity < 0.6, "fixture must be near neighbours, not twins"
    assert 5 not in honest_training_set(fps, test=[4], cutoff=0.5)
    assert 5 in honest_training_set(fps, test=[4], cutoff=0.6)


def test_honest_training_set_can_be_limited_to_one_protein(pool, fps):
    primary_only = honest_training_set(fps, test=[0], cutoff=0.6, candidates=[0, 1, 2])
    assert set(primary_only) <= {1, 2}


def test_audit_passes_a_clean_split(fps):
    assert audit(fps, train=[2], test=[0], cutoff=0.6).clean


def test_audit_catches_leakage_that_slipped_through(fps):
    """The guard must be seen to fail, or it cannot be trusted when it passes."""
    report = audit(fps, train=[0, 3], test=[0], cutoff=0.6)
    assert not report.clean
    assert report.offenders == 2
    assert report.worst_similarity == 1.0


def test_task_feature_says_which_protein_each_row_is(pool):
    molecule_features = np.ones((len(pool), 4), dtype=np.uint8)
    combined = with_task_feature(molecule_features, pool)

    assert combined.shape == (6, 4 + 3)  # 4 structural + one column per protein
    assert list(combined[0, 4:]) == [1, 0, 0]  # wild_type
    assert list(combined[3, 4:]) == [0, 1, 0]  # T790M
    assert combined[:, 4:].sum() == len(pool)  # exactly one protein per row


def test_arms_share_the_test_set_and_the_filter(pool, fps):
    primary_split = Split("primary", [0, 1], [2], "held out")
    single, multi = arms_for(pool, fps, primary_split, cutoff=0.6)

    assert single.test == multi.test == [2], "both arms must be judged on the same molecules"
    assert set(single.train) <= set(pool.indices_of("wild_type"))
    assert set(single.train) <= set(multi.train), "multi-task sees everything single-task does"
    assert audit(fps, multi.train, multi.test, 0.6).clean


def library(path, name, cores, variant, offset=0.0):
    rows = [f"name,smiles,pchembl,variant"]
    for i, core in enumerate(cores):
        rows.append(f"{name}{i},{core},{5.0 + (i % 7) * 0.3 + offset:.2f},{variant}")
    path.write_text("\n".join(rows) + "\n")
    return path


RINGS = (
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
)

# Distinct ring systems with varied linkers, so clustering finds real series.
# Every candidate is parsed before use: a fixture of invalid SMILES would make
# the test fail for a reason that has nothing to do with what it checks.
CORES = [
    smiles
    for linker in ("", "O", "N", "CC", "OC")
    for ring in RINGS
    for smiles in ["C" + linker + ring]
    if fingerprint_of(smiles)
]


def test_multitask_command(tmp_path, capsys):
    primary = library(tmp_path / "wild_type.csv", "wt", CORES, "wild_type")
    extra = library(tmp_path / "mutant.csv", "mu", CORES[:20], "T790M", offset=-1.0)

    code = main(
        ["multitask", str(primary), "--also", str(extra), "--repeats", "2"]
        + ["--cutoff", "0.4", "--test-fraction", "0.3", "--model", "ridge"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "judged on this" in out
    assert "saying which protein" in out
    assert "Leakage audit passed" in out
    assert "single_task" in out and "multi_task" in out
    assert "inside the noise" in out or "beyond the noise" in out


def test_multitask_command_rejects_an_unknown_primary(tmp_path, capsys):
    primary = library(tmp_path / "wild_type.csv", "wt", CORES[:12], "wild_type")
    assert main(["multitask", str(primary), "--primary", "CHEMBL999"]) == 1
    assert "not among" in capsys.readouterr().err


def test_multitask_command_reports_a_missing_file(capsys):
    assert main(["multitask", "nope.csv"]) == 1
    assert "error:" in capsys.readouterr().err
