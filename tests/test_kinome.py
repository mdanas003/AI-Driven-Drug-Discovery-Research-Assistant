"""Tests for the bulk-release queries.

These build a miniature ChEMBL: the same tables and column names as the
real release, with a handful of rows. That checks the SQL is correct and
that the output lines up with Step 3, without needing the 5.76 GB file.
What it cannot check is whether the real release spells its columns the
way we assume — only the real file can settle that, so there is also a
schema check that runs against it when it is present.
"""

import os
import sqlite3
from pathlib import Path

import pytest

from satori.__main__ import main
from satori.chembl import FIELDS, aggregate, clean
from satori.kinome import (
    GROUP_CLASS_LEVEL,
    KINOME_CLASS,
    KINOME_PATH,
    TYROSINE_GROUP,
    TargetCount,
    activities_for,
    kinase_counts,
    release_of,
    shortlist,
)

GEFITINIB = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"
ERLOTINIB = "C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1"
ETHANOL = "CCO"

SCHEMA = """
CREATE TABLE version (name TEXT, creation_date TEXT);
CREATE TABLE target_dictionary (tid INTEGER PRIMARY KEY, chembl_id TEXT,
    pref_name TEXT, target_type TEXT, organism TEXT);
CREATE TABLE target_components (tid INTEGER, component_id INTEGER);
CREATE TABLE component_class (component_id INTEGER, protein_class_id INTEGER);
CREATE TABLE protein_classification (protein_class_id INTEGER PRIMARY KEY,
    parent_id INTEGER, pref_name TEXT, protein_class_desc TEXT, class_level INTEGER);
CREATE TABLE molecule_dictionary (molregno INTEGER PRIMARY KEY, chembl_id TEXT,
    pref_name TEXT);
CREATE TABLE compound_structures (molregno INTEGER, canonical_smiles TEXT);
CREATE TABLE docs (doc_id INTEGER PRIMARY KEY, year INTEGER);
CREATE TABLE variant_sequences (variant_id INTEGER PRIMARY KEY, mutation TEXT);
CREATE TABLE assays (assay_id INTEGER PRIMARY KEY, chembl_id TEXT, tid INTEGER,
    assay_type TEXT, description TEXT, variant_id INTEGER);
CREATE TABLE activities (activity_id INTEGER PRIMARY KEY, assay_id INTEGER,
    molregno INTEGER, doc_id INTEGER, standard_type TEXT, standard_relation TEXT,
    standard_value REAL, standard_units TEXT, pchembl_value REAL,
    data_validity_comment TEXT, potential_duplicate INTEGER);
"""

MOLECULES = [
    (1, "CHEMBL939", "GEFITINIB", GEFITINIB),
    (2, "CHEMBL553", "ERLOTINIB", ERLOTINIB),
    (3, "CHEMBL545", "ETHANOL", ETHANOL),
]

# Two kinases in different groups, plus a non-kinase that must never appear.
TARGETS = [
    (1, "CHEMBL203", "Epidermal growth factor receptor erbB1", 10),
    (2, "CHEMBL301", "Cyclin-dependent kinase 2", 20),
    (3, "CHEMBL204", "Thrombin", 30),
]
# The real table is a parent/child tree where each node also stores its full
# path, double-space separated. Nodes 1-3 are the shared ancestors, 4 and 5
# the two kinase groups, and 10/20/30 the leaves the targets point at.
#
# The first version of this fixture had flat l1..l4 columns, because that is
# what kinome.py assumed. Every test passed, and the real release has no
# such columns: a fixture built from the same mistaken belief as the code
# confirms the belief instead of testing it. Hence the schema checks at the
# bottom of this file, which run against the actual release.
CLASSES = [
    (1, None, "Enzyme", "enzyme", 1),
    (2, 1, "Kinase", "enzyme  kinase", 2),
    (3, 2, KINOME_CLASS, KINOME_PATH, 3),
    (4, 3, TYROSINE_GROUP, KINOME_PATH + "  tk", GROUP_CLASS_LEVEL),
    (5, 3, "CMGC protein kinase group", KINOME_PATH + "  cmgc", GROUP_CLASS_LEVEL),
    (10, 4, "Tyrosine protein kinase EGFR family", KINOME_PATH + "  tk  egfr", 5),
    (20, 5, "CMGC protein kinase CDK family", KINOME_PATH + "  cmgc  cdk", 5),
    # A non-kinase, to prove the kinome filter excludes rather than includes.
    (30, 1, "Serine protease PA clan", "enzyme  protease  serine protease  pa", 4),
]


@pytest.fixture
def db(tmp_path):
    """A miniature ChEMBL release, with the real table and column names."""
    path = tmp_path / "mini_chembl.db"
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO version VALUES ('CHEMBL_37', '2026-05-29')")
    connection.executemany(
        "INSERT INTO target_dictionary VALUES (?, ?, ?, 'SINGLE PROTEIN', 'Homo sapiens')",
        [(tid, cid, name) for tid, cid, name, _ in TARGETS],
    )
    connection.executemany(
        "INSERT INTO target_components VALUES (?, ?)",
        [(tid, component) for tid, _, _, component in TARGETS],
    )
    connection.executemany(
        "INSERT INTO component_class VALUES (?, ?)",
        [(component, component) for _, _, _, component in TARGETS],
    )
    connection.executemany(
        "INSERT INTO protein_classification VALUES (?, ?, ?, ?, ?)", CLASSES
    )
    connection.executemany("INSERT INTO molecule_dictionary VALUES (?, ?, ?)",
                           [(no, cid, name) for no, cid, name, _ in MOLECULES])
    connection.executemany("INSERT INTO compound_structures VALUES (?, ?)",
                           [(no, smiles) for no, _, _, smiles in MOLECULES])
    connection.execute("INSERT INTO docs VALUES (1, 2008)")
    connection.execute("INSERT INTO variant_sequences VALUES (1, 'T790M')")

    assays = [
        (1, "CHEMBL_A1", 1, "B", "EGFR kinase assay", None),
        (2, "CHEMBL_A2", 1, "B", "EGFR T790M assay", 1),
        (3, "CHEMBL_A3", 1, "A", "A549 cell proliferation", None),  # wrong assay type
        (4, "CHEMBL_A4", 2, "B", "CDK2 kinase assay", None),
        (5, "CHEMBL_A5", 3, "B", "Thrombin assay", None),
    ]
    connection.executemany("INSERT INTO assays VALUES (?, ?, ?, ?, ?, ?)", assays)

    #                 id, assay, mol, doc, type,   rel, value, units,  pchembl, flag, dup
    activities = [
        (1, 1, 1, 1, "IC50", "=", 33.0, "nM", 7.48, None, 0),
        (2, 1, 1, 1, "IC50", "=", 20.0, "nM", 7.70, None, 0),  # same molecule again
        (3, 1, 2, 1, "IC50", "=", 2.0, "nM", 8.70, None, 0),
        (4, 2, 1, 1, "IC50", "=", 1000.0, "nM", 6.00, None, 0),  # the T790M mutant
        (5, 3, 3, 1, "IC50", "=", 100.0, "nM", 7.00, None, 0),  # cell assay
        (6, 1, 3, 1, "IC50", ">", 10000.0, "nM", None, None, 0),  # not an exact value
        (7, 1, 3, 1, "IC50", "=", 50.0, "nM", 7.30, "Outside typical range", 0),
        (8, 1, 3, 1, "Ki", "=", 5.0, "nM", 8.30, None, 0),  # wrong measurement type
        (9, 4, 1, 1, "IC50", "=", 500.0, "nM", 6.30, None, 0),  # CDK2
        (10, 5, 2, 1, "IC50", "=", 7.0, "nM", 8.15, None, 0),  # thrombin
    ]
    connection.executemany(
        "INSERT INTO activities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", activities
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def conn(db):
    from satori.kinome import connect

    return connect(db)


def test_release_is_read_from_the_file(conn):
    assert release_of(conn) == "CHEMBL_37"


def test_the_connection_is_read_only(conn):
    """A stray write would invalidate the checksum that proves provenance."""
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM activities")


def test_counts_find_kinases_and_only_kinases(conn):
    counts = {c.chembl_id: c for c in kinase_counts(conn)}
    assert set(counts) == {"CHEMBL203", "CHEMBL301"}, "thrombin is not a kinase"
    assert counts["CHEMBL203"].is_tyrosine_kinase
    assert not counts["CHEMBL301"].is_tyrosine_kinase


def test_counts_exclude_exactly_what_step_3_would_drop(conn):
    egfr = next(c for c in kinase_counts(conn) if c.chembl_id == "CHEMBL203")
    # Usable EGFR rows: activities 1, 2 (gefitinib), 3 (erlotinib), 4 (mutant).
    # Excluded: 5 (cell assay), 6 (">"), 7 (curator flag), 8 (Ki).
    assert egfr.measurements == 4
    assert egfr.molecules == 2, "distinct compounds, not measurements"


def test_counts_are_ordered_by_molecules(conn):
    counts = kinase_counts(conn)
    assert [c.molecules for c in counts] == sorted((c.molecules for c in counts), reverse=True)


def test_activities_match_the_web_api_shape(conn):
    rows = activities_for(conn, "CHEMBL203")
    assert all(set(row) == set(FIELDS) for row in rows), "must be the API's 16 columns"
    # Unfiltered, like fetch_activities: the cell assay and the ">" row are
    # still here, because deciding about them is clean()'s job, not SQL's.
    # Seven IC50 rows against EGFR; only the Ki row is absent.
    assert len(rows) == 7
    assert any(row["assay_type"] == "A" for row in rows)
    assert any(row["standard_relation"] == ">" for row in rows)


def test_the_mutant_label_survives_the_join(conn):
    """Without this column, mutant rows would be silently mixed into wild-type."""
    rows = activities_for(conn, "CHEMBL203")
    mutations = {row["assay_variant_mutation"] for row in rows}
    assert mutations == {None, "T790M"}


def test_rows_feed_step_3s_pipeline_unchanged(conn):
    """The whole point of matching the API's shape."""
    kept, dropped = clean(activities_for(conn, "CHEMBL203"))
    assert len(kept) == 4
    # Three dropped: the cell assay, the ">" row and the curator-flagged one.
    assert sum(dropped.values()) == 3
    assert "not a binding/biochemical assay (cell assays are not comparable)" in str(dropped)
    assert "flagged by ChEMBL curators" in str(dropped)

    rows = aggregate(kept)
    by_molecule = {(r["name"], r["variant"]): r for r in rows}
    gefitinib = by_molecule[("CHEMBL939", "wild_type")]
    assert gefitinib["n_measurements"] == 2
    assert gefitinib["pchembl"] == pytest.approx(7.59, abs=0.01)  # median of 7.48, 7.70
    assert ("CHEMBL939", "T790M") in by_molecule, "the mutant must be its own row"


def test_shortlist_applies_the_floor_and_the_family():
    counts = [
        TargetCount("CHEMBL203", "EGFR", TYROSINE_GROUP, 8450, 16084),
        TargetCount("CHEMBL301", "CDK2", "CMGC protein kinase group", 4000, 9000),
        TargetCount("CHEMBL9999", "Tiny kinase", TYROSINE_GROUP, 12, 15),
    ]
    assert [c.chembl_id for c in shortlist(counts, minimum=100)] == ["CHEMBL203", "CHEMBL301"]
    assert [c.chembl_id for c in shortlist(counts, 100, tyrosine_only=True)] == ["CHEMBL203"]
    assert shortlist(counts, minimum=100_000) == []


def test_kinome_counts_command(db, capsys):
    assert main(["kinome-counts", str(db), "--minimum", "1"]) == 0
    out = capsys.readouterr().out
    assert "CHEMBL_37" in out
    assert "2 human kinases" in out
    assert "CHEMBL203" in out and "CHEMBL301" in out
    assert "CHEMBL204" not in out, "thrombin is not a kinase"
    assert "Setting B, tyrosine kinases:" in out and "1 targets" in out
    assert "Setting C, whole kinome:" in out and "2 targets" in out


def test_kinome_counts_rejects_a_file_that_is_not_a_release(tmp_path, capsys):
    """A wrong path must say so, not raise sqlite3 internals at the user."""
    empty = tmp_path / "not_chembl.db"
    sqlite3.connect(empty).close()
    assert main(["kinome-counts", str(empty)]) == 1
    assert "error:" in capsys.readouterr().err


def test_kinome_extract_writes_step_3_format(db, tmp_path, capsys):
    from satori.library import load_table

    out = tmp_path / "kinome"
    assert main(["kinome-extract", str(db), "CHEMBL203", "--out-dir", str(out),
                 "--minimum-rows", "1"]) == 0
    written = out / "CHEMBL203_IC50.csv"
    assert written.exists()

    rows = load_table(str(written))
    assert set(rows[0]) == {"name", "pref_name", "smiles", "variant", "pchembl",
                            "n_measurements", "spread", "active"}
    assert {r["variant"] for r in rows} == {"wild_type", "T790M"}


def test_kinome_extract_skips_what_is_already_on_disk(db, tmp_path, capsys):
    """A kinome-wide extract must survive being interrupted and restarted."""
    out = tmp_path / "kinome"
    shared = ["kinome-extract", str(db), "CHEMBL203", "--out-dir", str(out), "--minimum-rows", "1"]
    assert main(shared) == 0
    assert "-> CHEMBL203_IC50.csv" in capsys.readouterr().out

    assert main(shared) == 0
    second = capsys.readouterr().out
    assert "skipped 1" in second


def test_kinome_extract_skips_a_target_with_too_little_data(db, tmp_path, capsys):
    out = tmp_path / "kinome"
    assert main(["kinome-extract", str(db), "--all-kinases", "--minimum", "1",
                 "--out-dir", str(out), "--minimum-rows", "100"]) == 0
    assert "too few, skipped" in capsys.readouterr().out
    assert not list(out.glob("*.csv"))


def test_kinome_extract_needs_a_target(db, capsys):
    assert main(["kinome-extract", str(db)]) == 1
    assert "name at least one target" in capsys.readouterr().err


# --- The real release -------------------------------------------------------
#
# Everything above runs against a miniature database we built ourselves, so
# it can only prove our SQL is consistent with our own assumptions. These
# tests check those assumptions against the actual 5.76 GB release, and skip
# when it is not on disk, so the suite still runs for anyone without it.
#
#     set SATORI_CHEMBL_DB=D:\chembl_dump\extracted\chembl_37\chembl_37_sqlite\chembl_37.db

REAL_DB = os.environ.get("SATORI_CHEMBL_DB")
needs_release = pytest.mark.skipif(
    not (REAL_DB and Path(REAL_DB).exists()),
    reason="set SATORI_CHEMBL_DB to the extracted chembl_NN.db to run this",
)

# Every table and column kinome.py's SQL names. A release that renames one of
# these would otherwise fail at query time with a message about SQL, not
# about what actually changed.
EXPECTED_SCHEMA = {
    "version": {"name", "creation_date"},
    "target_dictionary": {"tid", "chembl_id", "pref_name", "target_type", "organism"},
    "target_components": {"tid", "component_id"},
    "component_class": {"component_id", "protein_class_id"},
    "protein_classification": {
        "protein_class_id", "parent_id", "pref_name", "protein_class_desc", "class_level",
    },
    "molecule_dictionary": {"molregno", "chembl_id", "pref_name"},
    "compound_structures": {"molregno", "canonical_smiles"},
    "docs": {"doc_id", "year"},
    "variant_sequences": {"variant_id", "mutation"},
    "assays": {"assay_id", "chembl_id", "tid", "assay_type", "description", "variant_id"},
    "activities": {
        "activity_id", "assay_id", "molregno", "doc_id", "standard_type",
        "standard_relation", "standard_value", "standard_units", "pchembl_value",
        "data_validity_comment", "potential_duplicate",
    },
}


@pytest.fixture(scope="module")
def real():
    """The actual release, opened once for all the tests that need it."""
    from satori.kinome import connect

    return connect(Path(REAL_DB))


@needs_release
def test_the_release_has_the_columns_we_assume(real):
    for table, columns in EXPECTED_SCHEMA.items():
        present = {row["name"] for row in real.execute(f"PRAGMA table_info({table})")}
        assert present, f"table {table} is missing from this release"
        missing = columns - present
        assert not missing, f"{table} is missing {sorted(missing)}"


@needs_release
def test_the_classification_vocabulary_is_what_we_filter_on(real):
    """Our kinome definition is two string literals and a level number.

    If a release renames any of them the queries return nothing at all,
    which reads as "no kinase has data" rather than as a broken filter.
    """
    root = real.execute(
        "SELECT pref_name, class_level FROM protein_classification"
        " WHERE protein_class_desc = ?",
        (KINOME_PATH,),
    ).fetchone()
    assert root, f"no classification node has the path {KINOME_PATH!r}"
    assert root["pref_name"] == KINOME_CLASS

    groups = {
        row["pref_name"]
        for row in real.execute(
            "SELECT pref_name FROM protein_classification"
            " WHERE class_level = ? AND protein_class_desc LIKE ? || '  %'",
            (GROUP_CLASS_LEVEL, KINOME_PATH),
        )
    }
    assert TYROSINE_GROUP in groups, f"{TYROSINE_GROUP!r} not among {sorted(groups)}"
    # The nine Manning groups. Fewer would mean we are silently dropping
    # whole branches of the kinome from Setting C.
    assert len(groups) == 9, f"expected 9 kinase groups, found {sorted(groups)}"


@needs_release
def test_egfr_is_a_tyrosine_kinase_in_this_release(real):
    """A sanity check with a known answer: if EGFR is not in our kinome
    query, the query is wrong however well-formed it looks."""
    egfr = next((c for c in kinase_counts(real) if c.chembl_id == "CHEMBL203"), None)
    assert egfr is not None, "EGFR must appear in the kinome"
    assert egfr.is_tyrosine_kinase
    assert egfr.molecules > 5_000, "EGFR is one of the best-studied kinases"


@needs_release
def test_the_dump_agrees_with_what_the_web_api_gave_us(real):
    """The strongest check available: Step 3's EGFR file came from the live
    API, this one from the bulk release. Two independent paths to the same
    data must produce the same molecules, or one of them is wrong.
    """
    from satori.library import load_table

    on_disk = Path("data/chembl/CHEMBL203_IC50_wild_type.csv")
    if not on_disk.exists():
        pytest.skip("run `satori fetch-chembl CHEMBL203` first")

    api_rows = {row["smiles"] for row in load_table(str(on_disk))}
    kept, _ = clean(activities_for(real, "CHEMBL203"))
    sql_rows = {
        row["smiles"] for row in aggregate(kept) if row["variant"] == "wild_type"
    }

    overlap = len(api_rows & sql_rows) / len(api_rows)
    assert overlap > 0.95, (
        f"only {overlap:.1%} of the API's molecules came back from the dump;"
        " the two paths disagree about what the data is"
    )
