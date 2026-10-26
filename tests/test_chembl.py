"""ChEMBL tests run offline: a fake `fetch` stands in for the real API."""

import json

import pytest

from satori.chembl import FIELDS, aggregate, build_dataset, clean, drop_reason, fetch_activities


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


def test_aggregate_takes_median_per_molecule():
    rows = aggregate(
        [
            record(molecule_chembl_id="A", pchembl_value="5.0"),
            record(molecule_chembl_id="A", pchembl_value="6.0"),
            record(molecule_chembl_id="A", pchembl_value="9.0"),
            record(molecule_chembl_id="B", pchembl_value="5.5"),
        ]
    )
    a, b = rows  # sorted most potent first
    assert (a["name"], a["pchembl"], a["n_measurements"], a["spread"]) == ("A", 6.0, 3, 4.0)
    assert a["active"] and not b["active"]


def test_build_dataset_writes_files_and_reuses_cache(tmp_path):
    records = [record(molecule_chembl_id="A"), record(molecule_chembl_id="B", assay_type="F")]
    fake = FakeChembl(records)
    summary = build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)

    assert summary["raw_measurements"] == 2
    assert summary["molecules"] == 1
    assert summary["source"]["chembl_release"] == "ChEMBL_TEST"
    assert (tmp_path / "CHEMBL203_IC50.csv").exists()
    assert json.loads((tmp_path / "CHEMBL203_IC50.json").read_text())["actives"] == 1

    # Second run reads the raw cache instead of calling the API again.
    calls = fake.calls
    again = build_dataset("CHEMBL203", out_dir=tmp_path, fetch=fake)
    assert fake.calls == calls
    assert again["molecules"] == 1
    assert again["source"] == summary["source"]
