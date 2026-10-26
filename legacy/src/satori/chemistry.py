from __future__ import annotations

from collections.abc import Iterable

from satori.errors import DependencyUnavailable
from satori.schemas import LigandRecord, MoleculeDecision, StandardizedLigandRecord


def standardize(record: LigandRecord) -> MoleculeDecision:
    """RDKit-backed deterministic standardization; never silently drops invalid input."""
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, Lipinski, QED, rdMolDescriptors
    except ImportError as exc:
        raise DependencyUnavailable("Molecule standardization requires the [chemistry] extra (RDKit).") from exc
    if not record.smiles:
        return MoleculeDecision(record.molecule_id, False, "MISSING_SMILES")
    molecule = Chem.MolFromSmiles(record.smiles, sanitize=True)
    if molecule is None:
        return MoleculeDecision(record.molecule_id, False, "INVALID_SMILES")
    molecule = Chem.RemoveHs(molecule)
    canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
    key = Chem.MolToInchiKey(molecule)
    properties = {
        "qed": float(QED.qed(molecule)),
        "molecular_weight": float(Descriptors.MolWt(molecule)),
        "logp": float(Descriptors.MolLogP(molecule)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(molecule)),
        "hbd": float(Lipinski.NumHDonors(molecule)),
        "hba": float(Lipinski.NumHAcceptors(molecule)),
        "rotatable_bonds": float(Lipinski.NumRotatableBonds(molecule)),
    }
    properties["lipinski_violations"] = float(
        (properties["molecular_weight"] > 500) + (properties["logp"] > 5) +
        (properties["hbd"] > 5) + (properties["hba"] > 10)
    )
    return MoleculeDecision(record.molecule_id, True, None, canonical, key, properties)


def standardize_many(records: Iterable[LigandRecord]) -> list[MoleculeDecision]:
    seen: set[str] = set()
    decisions: list[MoleculeDecision] = []
    for record in records:
        decision = standardize(record)
        if decision.accepted and decision.inchikey in seen:
            decision.accepted = False
            decision.reason = "DUPLICATE"
        elif decision.accepted and decision.inchikey:
            seen.add(decision.inchikey)
        decisions.append(decision)
    return decisions


def standardize_activity_records(
    records: Iterable[LigandRecord],
) -> list[StandardizedLigandRecord]:
    """Standardize assay rows without discarding repeated molecules or assay labels."""
    seen: set[str] = set()
    output: list[StandardizedLigandRecord] = []
    for record in records:
        decision = standardize(record)
        duplicate = bool(decision.accepted and decision.inchikey in seen)
        if decision.accepted and decision.inchikey:
            seen.add(decision.inchikey)
        output.append(StandardizedLigandRecord(
            source_record=record,
            accepted=decision.accepted,
            rejection_reason=decision.reason,
            canonical_smiles=decision.canonical_smiles,
            standardized_inchikey=decision.inchikey,
            duplicate_structure=duplicate,
            properties=decision.properties,
        ))
    return output
