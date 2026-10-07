from __future__ import annotations

from dataclasses import dataclass

from satori.errors import DependencyUnavailable

try:
    import torch
    from torch import Tensor, nn
    from torch.nn import functional as F
except ImportError:
    torch = None  # type: ignore[assignment]
    Tensor = object  # type: ignore[assignment,misc]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


@dataclass(slots=True)
class ProteinLigandBatch:
    """Padded residue/atom features and coordinates; masks are True for real elements."""

    protein_features: "Tensor"  # [batch, residues, protein_feature_width]
    protein_coords: "Tensor"  # [batch, residues, 3]
    protein_mask: "Tensor"  # [batch, residues]
    ligand_features: "Tensor"  # [batch, atoms, ligand_feature_width]
    ligand_coords: "Tensor"  # [batch, atoms, 3]
    ligand_mask: "Tensor"  # [batch, atoms]


if nn is not None:
    class ProteinLigandCrossAttention(nn.Module):
        """3D distance-aware cross-attention with heteroscedastic affinity uncertainty."""

        architecture_id = "satori.protein_ligand_cross_attention.v1"

        def __init__(self, protein_width: int, ligand_width: int, hidden: int = 256,
                     heads: int = 8, rbf_bins: int = 32, max_distance: float = 16.0,
                     dropout: float = 0.1):
            super().__init__()
            self.max_distance = max_distance
            self.register_buffer("rbf_centers", torch.linspace(0, max_distance, rbf_bins))
            self.rbf_gamma = rbf_bins / max_distance
            self.protein_encoder = nn.Sequential(nn.Linear(protein_width, hidden), nn.GELU(), nn.LayerNorm(hidden))
            self.ligand_encoder = nn.Sequential(nn.Linear(ligand_width, hidden), nn.GELU(), nn.LayerNorm(hidden))
            self.distance_bias = nn.Sequential(nn.Linear(rbf_bins, hidden // heads), nn.GELU(),
                                               nn.Linear(hidden // heads, heads))
            self.ligand_to_protein = nn.MultiheadAttention(hidden, heads, dropout=dropout, batch_first=True)
            self.protein_to_ligand = nn.MultiheadAttention(hidden, heads, dropout=dropout, batch_first=True)
            self.fusion = nn.Sequential(nn.Linear(hidden * 4, hidden * 2), nn.GELU(), nn.Dropout(dropout),
                                        nn.LayerNorm(hidden * 2), nn.Linear(hidden * 2, hidden), nn.GELU())
            self.mean = nn.Linear(hidden, 1)
            self.log_variance = nn.Linear(hidden, 1)

        def forward(self, batch: ProteinLigandBatch) -> tuple["Tensor", "Tensor"]:
            protein = self.protein_encoder(batch.protein_features)
            ligand = self.ligand_encoder(batch.ligand_features)
            distances = torch.cdist(batch.ligand_coords.float(), batch.protein_coords.float()).clamp(max=self.max_distance)
            rbf = torch.exp(-self.rbf_gamma * (distances.unsqueeze(-1) - self.rbf_centers) ** 2)
            bias = self.distance_bias(rbf).permute(0, 3, 1, 2)
            # Distance bias enters attention logits through additive pair-specific masks.
            batch_size, heads, ligand_len, protein_len = bias.shape
            lp_mask = bias.reshape(batch_size * heads, ligand_len, protein_len)
            protein_padding = torch.zeros_like(batch.protein_mask, dtype=lp_mask.dtype).masked_fill(
                ~batch.protein_mask, float("-inf"))
            ligand_context, _ = self.ligand_to_protein(ligand, protein, protein,
                key_padding_mask=protein_padding, attn_mask=-lp_mask)
            pl_mask = -bias.transpose(-1, -2).reshape(batch_size * heads, protein_len, ligand_len)
            ligand_padding = torch.zeros_like(batch.ligand_mask, dtype=pl_mask.dtype).masked_fill(
                ~batch.ligand_mask, float("-inf"))
            protein_context, _ = self.protein_to_ligand(protein, ligand, ligand,
                key_padding_mask=ligand_padding, attn_mask=pl_mask)
            ligand_pool = (ligand_context * batch.ligand_mask.unsqueeze(-1)).sum(1) / batch.ligand_mask.sum(1, keepdim=True).clamp_min(1)
            protein_pool = (protein_context * batch.protein_mask.unsqueeze(-1)).sum(1) / batch.protein_mask.sum(1, keepdim=True).clamp_min(1)
            fused = self.fusion(torch.cat([ligand_pool, protein_pool, ligand_pool * protein_pool,
                                           torch.abs(ligand_pool - protein_pool)], dim=-1))
            return self.mean(fused).squeeze(-1), self.log_variance(fused).squeeze(-1).clamp(-8, 8)

        @staticmethod
        def gaussian_nll(mean: "Tensor", log_variance: "Tensor", target: "Tensor") -> "Tensor":
            return 0.5 * (log_variance + (target - mean).square() * torch.exp(-log_variance)).mean()
else:
    class ProteinLigandCrossAttention:  # type: ignore[no-redef]
        architecture_id = "satori.protein_ligand_cross_attention.v1"

        def __init__(self, *_: object, **__: object):
            raise DependencyUnavailable("Affinity model requires the [affinity] extra (PyTorch).")


def load_affinity_model(checkpoint: str, **model_kwargs: object) -> "ProteinLigandCrossAttention":
    if torch is None:
        raise DependencyUnavailable("Affinity model requires the [affinity] extra (PyTorch).")
    if not checkpoint:
        raise ValueError("A trained affinity checkpoint is required; untrained outputs are not predictions.")
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    metadata = state.get("metadata", {})
    if metadata.get("architecture_id") != ProteinLigandCrossAttention.architecture_id:
        raise ValueError("Checkpoint architecture_id does not match the configured affinity model.")
    model = ProteinLigandCrossAttention(**metadata["model_config"])
    model.load_state_dict(state["state_dict"])
    model.eval()
    return model
