"""Stage 6.1: the whole kinase family, read from ChEMBL's bulk release.

**Why a local database at all.** Step 3 downloads one target over the web
API, which works well and keeps the project runnable by anyone. Stage 6
needs hundreds of targets, and the API will not do it: two attempts to
fetch merely the *row counts* for 451 targets failed, the second after
stalling for thirteen hours. A server that will not answer cannot be
retried into answering. So anything kinome-scale reads from one named
release downloaded once (`chembl_37`), and provenance improves as a side
effect: "chembl_37" is a stronger statement about which data produced a
result than a retrieval timestamp against a live API.

**Why kinases, biologically.** A kinase moves a phosphate group onto
another protein — the cell's main way of switching things on and off.
There are about 500 in humans, and they all share one feature: a pocket
that binds ATP, the cell's fuel. Most kinase drugs work by sitting in
that pocket and blocking it. Because the pocket is similar across the
whole family, a molecule shaped to block EGFR often partly blocks its
relatives too. That shared shape is the reason a measurement against
another kinase is a weak clue about EGFR rather than noise, which is the
entire hypothesis Stage 6 tests.

**How we find them, which is better than the plan assumed.** The plan was
to take UniProt's 491 reviewed human kinases and map them to ChEMBL by
accession — two web services and a mapping step. The dump makes that
unnecessary: ChEMBL ships its own protein family tree in
`protein_classification`, so the kinome, and the tyrosine-kinase branch
within it, are a local join. No API, no mapping, and the family
assignment comes from the same source as the data.

**What this module deliberately does not do.** It does no cleaning,
filtering or aggregation of its own. `activities_for` emits the same
sixteen columns, under the same names, that the web API returns, so the
rows go straight into Step 3's `clean` and `aggregate`. Re-implementing
that logic against SQL would have let Stage 6 drift away from Step 5's
definitions, and then any difference in score could have been our two
code paths disagreeing rather than a real effect.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from satori.chembl import FIELDS

# ChEMBL's protein family tree is a parent/child table, not a row of l1..l8
# columns, and every node also carries its full path as a string with
# double-space separators:
#
#     enzyme  kinase  protein kinase  tk  abl
#
# That path is what we match on. Walking parent_id in SQL would need a
# recursive CTE for no benefit, and matching the path prefix says what we
# mean directly: "at or below this node in the tree".
KINOME_PATH = "enzyme  kinase  protein kinase"
KINOME_CLASS = "Protein Kinase"

# Level 4 is where the kinome splits into its nine standard groups — TK,
# TKL, CMGC, AGC, CK1, STE, CAMK, Atypical, Other. This is the Manning
# classification, the one the kinase literature uses, so reporting a target
# by its group is a statement a biologist already knows how to read.
GROUP_CLASS_LEVEL = 4

# EGFR's own group: the tyrosine kinases. Its members have the binding
# sites most similar to EGFR's, which makes it Setting B of the plan - the
# test of whether close relatives transfer better than distant ones.
TYROSINE_GROUP = "TK protein kinase group"


def _at_or_below(column: str, path: str) -> tuple[str, list[str]]:
    """SQL for 'this classification node is `path`, or sits under it'.

    The second case needs the separator in the pattern. Without it,
    `... ck1` would also match a hypothetical `... ck10`, and the bug
    would be invisible until some release added such a node.
    """
    return f"({column} = ? OR {column} LIKE ? || '  %')", [path, path]

HUMAN = "Homo sapiens"
# One protein, not a complex or a cell line: the only target type whose
# measurements are comparable with EGFR's.
SINGLE_PROTEIN = "SINGLE PROTEIN"

# Exactly `drop_reason`'s conditions, in SQL, so a shortlist count means
# "rows that would survive Step 3's cleaning" rather than "rows that exist".
USABLE = """
    cs.canonical_smiles IS NOT NULL
    AND act.pchembl_value IS NOT NULL
    AND act.standard_relation = '='
    AND a.assay_type = 'B'
    AND act.data_validity_comment IS NULL
    AND COALESCE(act.potential_duplicate, 0) = 0
"""

# The joins every query here needs: an activity, the assay that produced it,
# the protein it was measured against, and the molecule that was tested.
_FROM = """
    FROM activities act
    JOIN assays a ON a.assay_id = act.assay_id
    JOIN target_dictionary td ON td.tid = a.tid
    JOIN compound_structures cs ON cs.molregno = act.molregno
    JOIN molecule_dictionary md ON md.molregno = act.molregno
"""

# Reaching the family tree costs three more joins: a target is made of
# components (one, for a single protein), a component carries classes, and
# the class is a node in the tree. The LEFT JOIN then walks back up to the
# level-4 ancestor, which is the group name we report. LEFT, because a
# protein classified only as "protein kinase" with no group below it should
# still count as a kinase rather than vanish from the kinome.
_CLASSIFIED = f"""
    JOIN target_components tc ON tc.tid = td.tid
    JOIN component_class cc ON cc.component_id = tc.component_id
    JOIN protein_classification pc ON pc.protein_class_id = cc.protein_class_id
    LEFT JOIN protein_classification grp
           ON grp.class_level = {GROUP_CLASS_LEVEL}
          AND (pc.protein_class_desc = grp.protein_class_desc
               OR pc.protein_class_desc LIKE grp.protein_class_desc || '  %')
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open the release read-only, so no query can alter it.

    Read-only matters beyond tidiness: the file took an hour to download
    and half an hour to unpack, and a stray write would invalidate the
    checksum that proves which release produced our numbers.
    """
    connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def release_of(connection: sqlite3.Connection) -> str:
    """Which ChEMBL release this file is, taken from the file itself."""
    row = connection.execute(
        "SELECT name FROM version ORDER BY creation_date DESC LIMIT 1"
    ).fetchone()
    return row["name"] if row else "unknown"


@dataclass
class TargetCount:
    """One candidate target and how much usable data it has."""

    chembl_id: str
    name: str
    group: str
    molecules: int
    measurements: int

    @property
    def is_tyrosine_kinase(self) -> bool:
        return self.group == TYROSINE_GROUP


def kinase_counts(
    connection: sqlite3.Connection, activity_type: str = "IC50"
) -> list[TargetCount]:
    """Every human kinase, with its count of usable measurements.

    This is the query the plan could not run: it replaces a thirteen-hour
    API failure with a few seconds of local SQL, and it is what the §4
    shortlist is drawn from. `molecules` is the distinct-compound count,
    which is the number that matters — a target with 5,000 measurements of
    200 compounds is a small dataset wearing a large one's clothes.
    """
    in_kinome, paths = _at_or_below("pc.protein_class_desc", KINOME_PATH)
    sql = f"""
        SELECT td.chembl_id AS chembl_id,
               td.pref_name AS name,
               MIN(grp.pref_name) AS kinase_group,
               COUNT(DISTINCT act.molregno) AS molecules,
               COUNT(*) AS measurements
        {_FROM}
        {_CLASSIFIED}
        WHERE td.organism = ?
          AND td.target_type = ?
          AND {in_kinome}
          AND act.standard_type = ?
          AND {USABLE}
        GROUP BY td.chembl_id, td.pref_name
        ORDER BY molecules DESC
    """
    rows = connection.execute(sql, [HUMAN, SINGLE_PROTEIN, *paths, activity_type])
    return [
        TargetCount(
            chembl_id=row["chembl_id"],
            name=row["name"] or "",
            group=row["kinase_group"] or "",
            molecules=row["molecules"],
            measurements=row["measurements"],
        )
        for row in rows
    ]


def activities_for(
    connection: sqlite3.Connection, target_id: str, activity_type: str = "IC50"
) -> list[dict]:
    """Every measurement of one type for one target, in the web API's shape.

    Unfiltered on purpose, exactly as `fetch_activities` is: the only
    condition is the target and the measurement type, and every judgement
    about what to keep stays in Step 3's `drop_reason`. Two code paths that
    both decide what counts as a good measurement will eventually disagree,
    and then a score difference tells you nothing.
    """
    sql = f"""
        SELECT act.activity_id AS activity_id,
               md.chembl_id AS molecule_chembl_id,
               md.pref_name AS molecule_pref_name,
               cs.canonical_smiles AS canonical_smiles,
               act.standard_type AS standard_type,
               act.standard_relation AS standard_relation,
               act.standard_value AS standard_value,
               act.standard_units AS standard_units,
               act.pchembl_value AS pchembl_value,
               a.chembl_id AS assay_chembl_id,
               a.description AS assay_description,
               a.assay_type AS assay_type,
               vs.mutation AS assay_variant_mutation,
               act.data_validity_comment AS data_validity_comment,
               act.potential_duplicate AS potential_duplicate,
               docs.year AS document_year
        {_FROM}
        LEFT JOIN variant_sequences vs ON vs.variant_id = a.variant_id
        LEFT JOIN docs ON docs.doc_id = act.doc_id
        WHERE td.chembl_id = ? AND act.standard_type = ?
    """
    rows = connection.execute(sql, (target_id, activity_type))
    return [{field: row[field] for field in FIELDS} for row in rows]


def shortlist(
    counts: list[TargetCount], minimum: int, tyrosine_only: bool = False
) -> list[TargetCount]:
    """The targets worth downloading, by the one criterion that matters.

    `minimum` is a floor on distinct molecules. A target with a handful of
    compounds cannot teach a model anything about chemical space, but it
    still costs a slice of the similarity filter's time and adds its own
    one-hot column, so below some size a target is pure cost. Where that
    floor sits is a judgement; the plan sets it explicitly rather than
    letting it emerge from whatever the data happened to contain.
    """
    chosen = [c for c in counts if c.molecules >= minimum]
    if tyrosine_only:
        chosen = [c for c in chosen if c.is_tyrosine_kinase]
    return chosen
