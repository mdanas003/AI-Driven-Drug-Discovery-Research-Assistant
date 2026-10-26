from __future__ import annotations

import hashlib
from typing import Any

from satori.errors import ExternalSourceError
from satori.schemas import TargetContext, TargetRecord


def _accessions(results: list[dict[str, Any]]) -> list[str]:
    return sorted({str(result["primaryAccession"]) for result in results
                   if result.get("primaryAccession")})


def resolve_target_context(
    target: TargetRecord,
    *,
    uniprot_client: Any,
    chembl_client: Any,
    rcsb_client: Any,
) -> TargetContext:
    """Resolve identifiers and protein/structure context while retaining partial failures."""
    context = TargetContext(
        disease_id=target.disease_id or "unassigned",
        target_id=target.target_id,
        gene_symbol=target.gene_symbol,
        uniprot_id=target.uniprot_id,
    )
    accession = target.uniprot_id
    if accession is None:
        try:
            accession_results = uniprot_client.search_ensembl(target.target_id)
            matches = _accessions(accession_results)
            if len(matches) == 1:
                accession = matches[0]
                context.uniprot_id = accession
                context.provenance["uniprot_mapping"] = {
                    "method": "UniProt Ensembl cross-reference",
                    "result_count": len(accession_results),
                }
            elif not matches:
                context.sequence_status = "blocked_unmapped"
                context.blockers.append(f"No UniProt accession resolved for target {target.target_id}")
            else:
                context.sequence_status = "blocked_ambiguous"
                context.blockers.append(
                    f"Multiple UniProt accessions map to {target.target_id}: {matches}; explicit canonical choice required"
                )
        except ExternalSourceError as exc:
            context.sequence_status = "failed"
            context.blockers.append(f"UniProt identifier lookup failed: {exc}")

    if accession:
        try:
            enriched = uniprot_client.enrich(target, accession)
            sequence = "".join((enriched.sequence or "").split()).upper() or None
            if sequence and set(sequence) - set("ACDEFGHIKLMNPQRSTVWYBXZJUO"):
                context.sequence_status = "invalid_sequence"
                context.blockers.append(f"UniProt entry {accession} contains unexpected sequence symbols")
                sequence = None
            context.sequence = sequence
            if sequence:
                context.sequence_sha256 = hashlib.sha256(sequence.encode("ascii")).hexdigest()
                context.sequence_status = "ready"
                context.provenance["uniprot"] = enriched.metadata.get("uniprot", {})
            elif context.sequence_status != "invalid_sequence":
                context.sequence_status = "missing_sequence"
                context.blockers.append(f"UniProt entry {accession} has no sequence")
        except ExternalSourceError as exc:
            context.sequence_status = "failed"
            context.blockers.append(f"UniProt sequence retrieval failed: {exc}")

        try:
            context.chembl_target_id = chembl_client.target_id_for_uniprot(accession)
            context.provenance["chembl_target_mapping"] = getattr(
                chembl_client, "last_target_mapping", None)
            if context.chembl_target_id:
                context.ligand_data_status = "target_linked"
            else:
                context.ligand_data_status = "no_exact_chembl_target"
                context.blockers.append(f"No exact ChEMBL target mapping for UniProt {accession}")
        except ExternalSourceError as exc:
            context.ligand_data_status = "failed"
            context.blockers.append(f"ChEMBL target lookup failed: {exc}")

        try:
            context.structure_ids = rcsb_client.search_uniprot(accession)
            context.structure_status = "structures_found" if context.structure_ids else "no_structures_found"
            if not context.structure_ids:
                context.blockers.append(f"No RCSB structures found for UniProt {accession}")
            context.provenance["rcsb_search"] = {"uniprot_id": accession,
                                                   "structure_ids": context.structure_ids}
        except ExternalSourceError as exc:
            context.structure_status = "failed"
            context.blockers.append(f"RCSB structure lookup failed: {exc}")

    # A sequence and database ID are not a resolved pocket or prepared docking receptor.
    context.affinity_ready = False
    context.docking_ready = False
    context.blockers.append("Binding-site/chain mapping and structure preparation are not yet complete")
    return context
