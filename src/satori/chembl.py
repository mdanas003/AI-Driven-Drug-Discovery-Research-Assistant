"""Step 3: real experimental data from ChEMBL.

ChEMBL (https://www.ebi.ac.uk/chembl/) is a free database of lab
measurements: "compound X was tested against protein Y and had potency Z".
For one target we:

1. download every measurement of one type (for example IC50),
2. clean it: drop measurements we cannot trust or compare, and
   standardize each structure (salts and hydrates removed),
3. split it by protein variant: the normal ("wild-type") protein and
   each disease mutant are different proteins and are not comparable,
4. aggregate: one row per molecule per variant, with the median potency,
5. label each molecule active or inactive by a potency threshold.

Potency is expressed as a pChEMBL value: -log10 of the molar IC50.
pChEMBL 6 means 1 micromolar, 7 means 100 nM, 9 means 1 nM.
Higher is more potent, and each +1 is ten times more potent.
"""

import csv
import json
import random
import re
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import requests

from satori.molecule import canonical_smiles, parse_smiles, strip_salts

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
    "assay_description",
    "assay_type",
    "assay_variant_mutation",
    "data_validity_comment",
    "potential_duplicate",
    "document_year",
]

# pChEMBL >= 6 (IC50 <= 1 micromolar) is a common cut-off for "active".
DEFAULT_ACTIVE_THRESHOLD = 6.0

WILD_TYPE = "wild_type"
# A mutation we can see is present but cannot name.
UNNAMED_MUTANT = "mutant_unspecified"
# ChEMBL's own labels for the same thing.
_VAGUE_LABELS = {"UNDEFINED MUTATION", "UNDEFINED", "MUTANT", "MUTATED", "UNKNOWN"}

# "T790M" means: at position 790, threonine (T) became methionine (M).
# The 20 letters are the standard amino acid codes.
_POINT_MUTATION = re.compile(r"\b([ACDEFGHIKLMNPQRSTVWY]\d{2,4}[ACDEFGHIKLMNPQRSTVWY])\b")
# Deletions and insertions, written many different ways in free text.
_OTHER_MUTATION = re.compile(
    r"\b(ex(?:on)?\s?(?:19|20)\s?(?:del|deletion|ins|insertion)\w*|del(?:19|E746)\w*"
    r"|d746-750|insertion\s+mutant|deletion\s+mutant)\b",
    re.IGNORECASE,
)
_MUTANT_WORD = re.compile(r"\bmutan|\bmutation", re.IGNORECASE)

GetJson = Callable[[str, dict | None], dict]


def get_json(url: str, params: dict | None = None, retries: int = 5) -> dict:
    """GET a JSON document, retrying on anything that a retry could fix.

    Long runs meet failures that a short one never shows. Over a few
    hundred requests this API has refused with read timeouts, reset
    connections, and responses that stop mid-body — the last of which
    arrives as ChunkedEncodingError, or as a JSON error when a truncated
    body happens to parse as far as it goes. Catching only connection and
    timeout errors leaves those to crash a job hours in, so everything
    except an HTTP 4xx is retried; a 4xx means the request itself is wrong
    and asking again will not help.
    """
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=120)
            if response.status_code < 500:
                response.raise_for_status()
                return response.json()
            error: Exception = requests.HTTPError(f"HTTP {response.status_code} for {url}")
        except requests.HTTPError:
            raise
        except (requests.RequestException, ValueError) as err:
            error = err
        if attempt < retries:
            # Back off further each time; a struggling server needs room.
            time.sleep(min(2**attempt, 30))
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


def variant(record: dict) -> str:
    """Which form of the protein was tested: WILD_TYPE or a mutation label.

    A mutation can change how tightly a drug binds by a thousandfold, so
    these are effectively different proteins. ChEMBL usually names the
    mutation in `assay_variant_mutation`, but for older assays it appears
    only in the free-text description, so we read both.
    """
    labelled = (record.get("assay_variant_mutation") or "").strip()
    if labelled:
        if labelled.upper() in _VAGUE_LABELS:
            return UNNAMED_MUTANT
        # Several mutations can be listed together, e.g. "L858R,T790M".
        return "+".join(sorted(part.strip().upper() for part in labelled.split(",") if part))

    description = record.get("assay_description") or ""
    found = sorted(set(_POINT_MUTATION.findall(description)))
    if found:
        return "+".join(found)
    if _OTHER_MUTATION.search(description) or _MUTANT_WORD.search(description):
        return UNNAMED_MUTANT
    return WILD_TYPE


def clean(records: list[dict]) -> tuple[list[dict], Counter]:
    """Keep trustworthy measurements, standardize them; count the rest.

    Each kept record gains two fields: `structure` (canonical SMILES with
    salts and hydrates removed) and `variant` (which protein form was tested).
    """
    kept, dropped = [], Counter()
    for record in records:
        reason = drop_reason(record)
        if reason:
            dropped[reason] += 1
            continue
        try:
            mol = strip_salts(parse_smiles(record["canonical_smiles"]))
        except ValueError:
            dropped["RDKit cannot read the structure"] += 1
            continue
        kept.append(record | {"structure": canonical_smiles(mol), "variant": variant(record)})
    return kept, dropped


def aggregate(
    records: list[dict], active_threshold: float = DEFAULT_ACTIVE_THRESHOLD
) -> list[dict]:
    """One row per molecule per protein variant, with the median pChEMBL.

    Grouping is by standardized structure, so a drug and its salt form count
    as one molecule even though ChEMBL gives them different IDs.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for record in records:
        groups.setdefault((record["structure"], record["variant"]), []).append(record)

    rows = []
    for (structure, protein_variant), group in groups.items():
        values = [float(r["pchembl_value"]) for r in group]
        median = round(statistics.median(values), 2)
        named = next((r["molecule_pref_name"] for r in group if r["molecule_pref_name"]), "")
        rows.append(
            {
                "name": group[0]["molecule_chembl_id"],
                "pref_name": named,
                "smiles": structure,
                "variant": protein_variant,
                "pchembl": median,
                "n_measurements": len(values),
                "spread": round(max(values) - min(values), 2),
                "active": median >= active_threshold,
            }
        )
    rows.sort(key=lambda r: r["pchembl"], reverse=True)
    return rows


def measurement_agreement(records: list[dict], seed: int = 0) -> dict | None:
    """How well two independent measurements of the same molecule agree.

    This is the resolution limit of the data. If two real measurements of
    one compound differ by 0.8 log units, then no model can predict these
    labels to better than roughly that error, however clever it is. Any
    reported accuracy beyond this number is a sign of a leaked test set,
    not of a better model. Returns None if nothing was measured twice.
    """
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for record in records:
        groups[(record["structure"], record["variant"])].append(float(record["pchembl_value"]))

    repeated = [values for values in groups.values() if len(values) > 1]
    if not repeated:
        return None

    # One random pair per molecule, so a heavily measured compound does
    # not dominate the estimate.
    rng = random.Random(seed)
    differences = [abs(a - b) for values in repeated for a, b in [rng.sample(values, 2)]]
    return {
        "molecules_measured_twice": len(repeated),
        "mean_difference": round(statistics.fmean(differences), 3),
        "median_difference": round(statistics.median(differences), 3),
        "share_over_1_log": round(sum(d > 1 for d in differences) / len(differences), 3),
    }


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

    Writes to out_dir:
      <target>_<type>_raw.csv        every downloaded measurement (a cache)
      <target>_<type>_wild_type.csv  normal protein, one row per molecule
      <target>_<type>_mutant.csv     mutant forms, with a `variant` column
      <target>_<type>.json           provenance: source, drops, variant counts
    """
    stem = f"{target_id}_{activity_type}"
    raw_path = out_dir / f"{stem}_raw.csv"
    meta_path = out_dir / f"{stem}.json"

    cached = raw_path.exists() and meta_path.exists() and not refresh
    if cached:
        raw = read_csv(raw_path)
        # A cache written by an older version lacks columns we now need.
        if raw and set(FIELDS) - set(raw[0]):
            cached = False

    if cached:
        source = json.loads(meta_path.read_text(encoding="utf-8"))["source"]
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

    wild_type = [m for m in molecules if m["variant"] == WILD_TYPE]
    mutant = [m for m in molecules if m["variant"] != WILD_TYPE]
    files = {}
    for label, rows in (("wild_type", wild_type), ("mutant", mutant)):
        if rows:
            path = out_dir / f"{stem}_{label}.csv"
            write_csv(rows, path)
            files[label] = str(path)

    summary = {
        "source": source,
        "active_threshold_pchembl": active_threshold,
        "raw_measurements": len(raw),
        "kept_measurements": len(kept),
        "dropped": dict(dropped.most_common()),
        "rows": len(molecules),
        "wild_type": {
            "molecules": len(wild_type),
            "actives": sum(m["active"] for m in wild_type),
        },
        "mutant": {
            "molecules": len(mutant),
            "actives": sum(m["active"] for m in mutant),
            "variants": dict(Counter(m["variant"] for m in mutant).most_common()),
        },
        "measurement_agreement": measurement_agreement(kept),
        "files": files,
    }
    meta_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
