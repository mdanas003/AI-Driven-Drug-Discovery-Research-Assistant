from __future__ import annotations

from collections.abc import Iterable

from satori.chemistry import standardize
from satori.errors import DependencyUnavailable
from satori.schemas import CandidateRecord, LigandRecord, TriageDecision


def triage_with_audit(records: Iterable[LigandRecord], *, qed_min: float = 0.0,
                      max_molecular_weight: float = 700.0, max_lipinski_violations: int = 1,
                      apply_pains: bool = True) -> list[TriageDecision]:
    """Deterministic chemistry funnel with one explicit acceptance/rejection per input record."""
    try:
        from rdkit import Chem
        from rdkit.Chem import FilterCatalog
    except ImportError as exc:
        raise DependencyUnavailable("Chemical triage requires the [chemistry] extra (RDKit).") from exc
    catalog = None
    if apply_pains:
        params = FilterCatalog.FilterCatalogParams()
        params.AddCatalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
        catalog = FilterCatalog.FilterCatalog(params)
    decisions: list[TriageDecision] = []
    seen: set[str] = set()
    for record in records:
        decision = standardize(record)
        if not decision.accepted or not decision.canonical_smiles:
            decisions.append(TriageDecision(record.molecule_id, False, decision.reason))
            continue
        if decision.inchikey in seen:
            decisions.append(TriageDecision(record.molecule_id, False, "DUPLICATE"))
            continue
        seen.add(decision.inchikey or "")
        if decision.properties.get("qed", 0) < qed_min:
            decisions.append(TriageDecision(record.molecule_id, False, "QED_BELOW_THRESHOLD"))
            continue
        if decision.properties.get("molecular_weight", 0) > max_molecular_weight:
            decisions.append(TriageDecision(record.molecule_id, False, "MOLECULAR_WEIGHT_ABOVE_THRESHOLD"))
            continue
        if decision.properties.get("lipinski_violations", 0) > max_lipinski_violations:
            decisions.append(TriageDecision(record.molecule_id, False, "LIPINSKI_VIOLATIONS_ABOVE_THRESHOLD"))
            continue
        molecule = Chem.MolFromSmiles(decision.canonical_smiles)
        if catalog is not None and catalog.HasMatch(molecule):
            decisions.append(TriageDecision(record.molecule_id, False, "PAINS_ALERT"))
            continue
        candidate = CandidateRecord(molecule_id=record.molecule_id,
            smiles=decision.canonical_smiles, target_id=record.target_id or "unassigned",
            properties=decision.properties,
            provenance={"source": record.source, "molecule_id": record.molecule_id,
                        "filters": {"qed_min": qed_min, "max_molecular_weight": max_molecular_weight,
                                    "max_lipinski_violations": max_lipinski_violations,
                                    "pains": apply_pains}})
        decisions.append(TriageDecision(record.molecule_id, True, None, candidate))
    return decisions


def triage(records: Iterable[LigandRecord], **kwargs: object) -> list[CandidateRecord]:
    """Accepted candidates convenience view; use triage_with_audit to retain rejected records."""
    return [decision.candidate for decision in triage_with_audit(records, **kwargs) if decision.candidate]
