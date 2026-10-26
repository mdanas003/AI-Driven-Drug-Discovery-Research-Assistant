"""ChEMBL tests run offline: a fake `fetch` stands in for the real API."""

import csv
import json

import pytest

from satori.chembl import (
    FIELDS,
    UNNAMED_MUTANT,
    WILD_TYPE,
    aggregate,
    build_dataset,
    clean,
    drop_reason,
    fetch_activities,
    variant,
)


def record(**overrides):
    base = {field: None for field in FIELDS}
    base.update(
        molecule_chembl_id="CHEMBL1",
        canonical_smiles="CCO",
        standard_relation="=",
        pchembl_value="7.0",
        assay_type="B",
        potential_duplicate=0,
    )
    base.update(overrides)
    return base


class FakeChembl:
    """Serves activity records in pages, like the real API."""

    def __init__(self, records, page_size=2):
        self.records, self.page_size, self.calls = records, page_size, 0

    def __call__(self, url, params=None):
        self.calls += 1
        if url.endswith("/status.json"):
            return {"chembl_db_version": "ChEMBL_TEST"}
        if "/target/" in url:
            return {"pref_name": "Test kinase"}
        offset = int(url.split("offset=")[1]) if "offset=" in url else 0
        end = offset + self.page_size
        next_url = f"/chembl/api/data/activity.json?offset={end}" if end < len(self.records) else None
        return {
            "activities": self.records[offset:end],
            "page_meta": {"next": next_url, "total_count": len(self.records)},
        }


def test_fetch_follows_every_page():
    records = [record(molecule_chembl_id=f"CHEMBL{i}") for i in range(5)]
    fetched = fetch_activities("CHEMBL203", fetch=FakeChembl(records))
    assert [r["molecule_chembl_id"] for r in fetched] == [f"CHEMBL{i}" for i in range(5)]


@pytest.mark.parametrize(
    "overrides, reason_start",
    [
        ({"canonical_smiles": None}, "no structure"),
        ({"pchembl_value": None}, "no pChEMBL"),
        ({"standard_relation": ">"}, "not an exact value"),
        ({"assay_type": "F"}, "not a binding"),
        ({"data_validity_comment": "Outside typical range"}, "flagged"),
        ({"potential_duplicate": 1}, "potential duplicate"),
    ],
)
def test_drop_reasons(overrides, reason_start):
    assert drop_reason(record(**overrides)).startswith(reason_start)


def test_clean_keeps_good_records_and_counts_the_rest():
    kept, dropped = clean([record(), record(assay_type="F"), record(assay_type="F")])
    assert len(kept) == 1
    assert sum(dropped.values()) == 2


def test_clean_strips_salts_and_counts_unreadable_structures():
    kept, dropped = clean(
        [record(canonical_smiles="CCO.Cl"), record(canonical_smiles="C1CC")]
    )
    assert [r["structure"] for r in kept] == ["CCO"]
    assert dropped["RDKit cannot read the structure"] == 1


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({}, WILD_TYPE),
        ({"assay_description": "Inhibition of EGFR"}, WILD_TYPE),
        ({"assay_variant_mutation": "L858R"}, "L858R"),
        ({"assay_variant_mutation": "T790M,L858R"}, "L858R+T790M"),
        ({"assay_description": "Inhibition of EGFR T790M mutant"}, "T790M"),
        # ChEMBL's own label for "mutated, but we are not saying how".
        ({"assay_variant_mutation": "UNDEFINED MUTATION"}, UNNAMED_MUTANT),
        ({"assay_description": "against EGFR exon 19 deletion"}, UNNAMED_MUTANT),
        ({"assay_description": "Inhibition of mutant EGFR kinase"}, UNNAMED_MUTANT),
        # The labelled field wins over whatever the description says.
        ({"assay_variant_mutation": "T790M", "assay_description": "wild type"}, "T790M"),
    ],
)
def test_variant_detection(overrides, expected):
    assert variant(record(**overrides)) == expected


def test_aggregate_takes_median_per_molecule():
    rows = aggregate(
        clean(
            [
                record(molecule_chembl_id="A", pchembl_value="5.0"),
                record(molecule_chembl_id="A", pchembl_value="6.0"),
                record(molecule_chembl_id="A", pchembl_value="9.0"),
                record(molecule_chembl_id="B", canonical_smiles="CCC", pchembl_value="5.5"),
            ]
        )[0]
    )
    a, b = rows  # sorted most potent first
    assert (a["name"], a["pchembl"], a["n_measurements"], a["spread"]) == ("A", 6.0, 3, 4.0)
    assert a["active"] and not b["active"]


def test_aggregate_keeps_variants_apart():
    rows = aggregate(
        clean(
            [
                record(pchembl_value="9.0", assay_variant_mutation="T790M"),
                record(pchembl_value="5.0"),
            ]
        )[0]
    )
    assert [(r["variant"], r["pchembl"]) for r in rows] == [("T790M", 9.0), (WILD_TYPE, 5.0)]


def test_aggregate_merges_a_drug_with_its_salt_form():
    """Same drug, two ChEMBL IDs, one stored as a hydrochloride salt."""
    rows = aggregate(
        clean(
            [
                record(molecule_chembl_id="A", canonical_smiles="CCN", pchembl_value="7.0"),
                record(molecule_chembl_id="B", canonical_smiles="CCN.Cl", pchembl_value="8.0"),
            ]
        )[0]
    )
    assert len(rows) == 1
    assert rows[0]["n_measurements"] == 2


def test_build_dataset_writes_a_file_per_variant_and_reuses_cache(tmp_path):
    records = [
        record(molecule_chembl_id="A"),
        record(molecule_chembl_id="B", canonical_smiles="CCC", assay_variant_mutation="T790M"),
        record(molecule_chembl_id="C", assay_type="F"),  # dropped
    ]
    fake = FakeChembl(records)
    summary = build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)

    assert summary["raw_measurements"] == 3
    assert summary["kept_measurements"] == 2
    assert summary["wild_type"] == {"molecules": 1, "actives": 1}
    assert summary["mutant"]["variants"] == {"T790M": 1}
    assert summary["source"]["chembl_release"] == "ChEMBL_TEST"
    assert (tmp_path / "CHEMBL203_IC50_wild_type.csv").exists()
    assert (tmp_path / "CHEMBL203_IC50_mutant.csv").exists()
    assert json.loads((tmp_path / "CHEMBL203_IC50.json").read_text())["rows"] == 2

    # Second run reads the raw cache instead of calling the API again.
    calls = fake.calls
    again = build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)
    assert fake.calls == calls
    assert again["source"] == summary["source"]


def test_build_dataset_redownloads_a_cache_missing_new_columns(tmp_path):
    fake = FakeChembl([record()])
    build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)

    # Simulate a cache written before `variant` existed.
    raw_path = tmp_path / "CHEMBL203_IC50_raw.csv"
    rows = list(csv.DictReader(raw_path.open(newline="")))
    old_fields = [f for f in FIELDS if f != "assay_variant_mutation"]
    with raw_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=old_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    calls = fake.calls
    build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)
    assert fake.calls > calls
