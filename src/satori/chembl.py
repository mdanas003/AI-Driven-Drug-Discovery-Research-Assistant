"""Step 3: real experimental data from ChEMBL.

ChEMBL (https://www.ebi.ac.uk/chembl/) is a free database of lab
measurements: "compound X was tested against protein Y and had potency Z".
For one target we:

1. download every measurement of one type (for example IC50),
2. clean it: drop measurements we cannot trust or compare,
3. aggregate: one row per molecule, with the median potency,
4. label each molecule active or inactive by a potency threshold.

Potency is expressed as a pChEMBL value: -log10 of the molar IC50.
pChEMBL 6 means 1 micromolar, 7 means 100 nM, 9 means 1 nM.
Higher is more potent, and each +1 is ten times more potent.
"""

import csv
import json
import statistics
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://www.ebi.ac.uk"
API_URL = BASE_URL + "/chembl/api/data"

# Only the columns we use, which keeps each downloaded page small.
FIELDS = [
    "activity_id",
    "molecule_chembl_id",
    "molecule_pref_name",
    "canonical_smiles",
    "standard_type",
    "standard_relation",
    "standard_value",
    "standard_units",
    "pchembl_value",
    "assay_chembl_id",
    "assay_type",
    "data_validity_comment",
    "potential_duplicate",
    "document_year",
]

# pChEMBL >= 6 (IC50 <= 1 micromolar) is a common cut-off for "active".
DEFAULT_ACTIVE_THRESHOLD = 6.0

GetJson = Callable[[str, dict | None], dict]


def get_json(url: str, params: dict | None = None, retries: int = 3) -> dict:
    """GET a JSON document, retrying a few times on network or server errors."""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=60)
            if response.status_code < 500:
                response.raise_for_status()
                return response.json()
            error: Exception = requests.HTTPError(f"HTTP {response.status_code} for {url}")
        except (requests.ConnectionError, requests.Timeout) as err:
            error = err
        if attempt < retries:
            time.sleep(2**attempt)
    raise RuntimeError(f"ChEMBL request failed after {retries} attempts: {error}")


def chembl_release(fetch: GetJson = get_json) -> str:
    """Which ChEMBL release the API is serving, for example 'ChEMBL_37'."""
    return fetch(f"{API_URL}/status.json", None)["chembl_db_version"]


def target_name(target_id: str, fetch: GetJson = get_json) -> str:
    return fetch(f"{API_URL}/target/{target_id}.json", None)["pref_name"]


def fetch_activities(
    target_id: str,
    activity_type: str = "IC50",
    fetch: GetJson = get_json,
    page_size: int = 1000,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Download every activity of one type for one target, page by page."""
    url = f"{API_URL}/activity.json"
    params: dict | None = {
        "target_chembl_id": target_id,
        "standard_type": activity_type,
        "only": ",".join(FIELDS),
        "limit": page_size,
    }
    records: list[dict] = []
    while url:
        page = fetch(url, params)
        records.extend({k: r.get(k) for k in FIELDS} for r in page["activities"])
        meta = page["page_meta"]
        if progress:
            progress(len(records), meta["total_count"])
        # The API tells us where the next page is; it already has the params.
        url = BASE_URL + meta["next"] if meta["next"] else None
        params = None
    return records


def drop_reason(record: dict) -> str | None:
    """Why a measurement should not be used, or None if it is fine."""
    if not record["canonical_smiles"]:
        return "no structure"
    if not record["pchembl_value"]:
        return "no pChEMBL value (inactive text, odd units, or not standardized)"
    if record["standard_relation"] != "=":
        return "not an exact value (e.g. '>10000 nM')"
    if record["assay_type"] != "B":
        return "not a binding/biochemical assay (cell assays are not comparable)"
    if record["data_validity_comment"]:
        return "flagged by ChEMBL curators"
    if str(record["potential_duplicate"]) in ("1", "True"):
        return "potential duplicate of another measurement"
    return None


def clean(records: list[dict]) -> tuple[list[dict], Counter]:
    """Keep trustworthy measurements; count why the others were dropped."""
    kept, dropped = [], Counter()
    for record in records:
        reason = drop_reason(record)
        if reason:
            dropped[reason] += 1
        else:
            kept.append(record)
    return kept, dropped


def aggregate(
    records: list[dict], active_threshold: float = DEFAULT_ACTIVE_THRESHOLD
) -> list[dict]:
    """One row per molecule: median pChEMBL over all its measurements."""
    by_molecule: dict[str, list[dict]] = {}
    for record in records:
        by_molecule.setdefault(record["molecule_chembl_id"], []).append(record)

    rows = []
    for chembl_id, group in by_molecule.items():
        values = [float(r["pchembl_value"]) for r in group]
        median = round(statistics.median(values), 2)
        rows.append(
            {
                "name": chembl_id,
                "pref_name": group[0]["molecule_pref_name"] or "",
                "smiles": group[0]["canonical_smiles"],
                "pchembl": median,
                "n_measurements": len(values),
                "spread": round(max(values) - min(values), 2),
                "active": median >= active_threshold,
            }
        )
    rows.sort(key=lambda r: r["pchembl"], reverse=True)
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def build_dataset(
    target_id: str,
    activity_type: str = "IC50",
    out_dir: Path = Path("data/chembl"),
    active_threshold: float = DEFAULT_ACTIVE_THRESHOLD,
    refresh: bool = False,
    fetch: GetJson = get_json,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Download (or reuse) raw data, clean and aggregate it, save everything.

    Writes three files to out_dir:
      <target>_<type>_raw.csv   every downloaded measurement (a cache)
      <target>_<type>.csv       one row per molecule, ready for `screen`
      <target>_<type>.json      where the data came from and what was dropped
    """
    stem = f"{target_id}_{activity_type}"
    raw_path = out_dir / f"{stem}_raw.csv"
    meta_path = out_dir / f"{stem}.json"

    if raw_path.exists() and meta_path.exists() and not refresh:
        raw = read_csv(raw_path)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        source = meta["source"]
    else:
        source = {
            "target_chembl_id": target_id,
            "target_name": target_name(target_id, fetch),
            "activity_type": activity_type,
            "chembl_release": chembl_release(fetch),
            "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "api": API_URL,
        }
        raw = fetch_activities(target_id, activity_type, fetch, progress=progress)
        if not raw:
            raise ValueError(f"ChEMBL has no {activity_type} data for {target_id}")
        write_csv(raw, raw_path)

    kept, dropped = clean(raw)
    molecules = aggregate(kept, active_threshold)
    if not molecules:
        raise ValueError("No measurements survived cleaning.")
    write_csv(molecules, out_dir / f"{stem}.csv")

    summary = {
        "source": source,
        "active_threshold_pchembl": active_threshold,
        "raw_measurements": len(raw),
        "kept_measurements": len(kept),
        "dropped": dict(dropped.most_common()),
        "molecules": len(molecules),
        "actives": sum(m["active"] for m in molecules),
    }
    meta_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
