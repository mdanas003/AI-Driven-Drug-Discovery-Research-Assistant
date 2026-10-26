from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol, Sequence

from satori.errors import ComponentBlocked, DependencyUnavailable

try:
    import torch
    from torch import Tensor, nn
    from torch.nn import functional as F
except ImportError:  # Data ingestion remains usable without the ML extra.
    torch = None  # type: ignore[assignment]
    Tensor = object  # type: ignore[assignment,misc]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]


@dataclass(slots=True)
class EvidenceGraph:
    node_features: "Tensor"
    edge_index: "Tensor"
    edge_type: "Tensor"
    edge_time_features: "Tensor"
    target_node_indices: "Tensor"
    target_ids: list[str]
    as_of: str
    edge_provenance: list[str | None]


def _as_utc(value: object) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _record_time(record: object) -> datetime:
    event_time = getattr(record, "event_time", None)
    # Retrieval time is a snapshot timestamp, not a publication timestamp.
    return _as_utc(event_time or getattr(record, "retrieved_at", "1970-01-01T00:00:00+00:00"))


def encode_evidence_graph(
    records: Sequence[object],
    *,
    device: str = "cpu",
    reference_time: datetime | None = None,
) -> tuple[EvidenceGraph, list[str]]:
    """Create a deterministic heterogeneous snapshot with time-conditioned evidence edges."""
    if torch is None:
        raise DependencyUnavailable("Evidence graph tensorization requires the [ml] extra (PyTorch).")
    if not records:
        raise ValueError("Cannot encode an empty evidence snapshot")
    normalized: list[tuple[object, str, str, str, float, datetime, str | None]] = []
    for record in records:
        disease = str(getattr(record, "disease_id", "")).strip()
        target = str(getattr(record, "target_id", "")).strip()
        source = str(getattr(record, "source", "")).strip()
        score = float(getattr(record, "score", float("nan")))
        if not disease or not target or not source:
            raise ValueError("Every graph evidence record needs disease_id, target_id, and source")
        if not math.isfinite(score):
            raise ValueError(f"Evidence score must be finite for target {target}")
        normalized.append((record, disease, target, source, score, _record_time(record),
                           getattr(record, "source_record_id", None)))
    normalized.sort(key=lambda item: (item[1], item[2], item[3], item[5].isoformat(),
                                     str(item[6] or "")))
    targets = sorted({item[2] for item in normalized})
    diseases = sorted({item[1] for item in normalized})
    sources = sorted({item[3] for item in normalized})
    nodes = ([ ("disease", item) for item in diseases]
             + [("target", item) for item in targets]
             + [("source", item) for item in sources])
    lookup = {node: index for index, node in enumerate(nodes)}
    target_lookup = {item: lookup[("target", item)] for item in targets}
    event_times = [item[5] for item in normalized]
    as_of = _as_utc(reference_time) if reference_time else max(event_times)

    # Features encode node type, strongest evidence, record count and relative age.
    feature_rows = []
    for kind, _ in nodes:
        feature_rows.append([float(kind == name) for name in ("disease", "target", "source")]
                            + [0.0, 0.0, 0.0])
    edges: list[tuple[int, int]] = []
    edge_types: list[int] = []
    edge_times: list[list[float]] = []
    edge_provenance: list[str | None] = []
    for _, disease, target, source, score, event_time, source_record_id in normalized:
        disease_idx = lookup[("disease", disease)]
        target_idx = target_lookup[target]
        source_idx = lookup[("source", source)]
        age_days = max(0.0, (as_of - event_time).total_seconds() / 86400.0)
        phase = 2.0 * math.pi * age_days / 365.25
        temporal = [score, math.log1p(age_days) / math.log1p(3650.0),
                    math.sin(phase), math.cos(phase)]
        for idx in (disease_idx, target_idx, source_idx):
            feature_rows[idx][3] = max(feature_rows[idx][3], score)
            feature_rows[idx][4] = max(feature_rows[idx][4], temporal[1])
            feature_rows[idx][5] += 1.0
        # Relation ids: disease-target, target-source, source-target; reverse edges 3-5.
        for left, right, relation in ((disease_idx, target_idx, 0), (target_idx, source_idx, 1),
                                      (source_idx, target_idx, 2)):
            edges.extend(((left, right), (right, left)))
            edge_types.extend((relation, relation + 3))
            edge_times.extend((temporal, temporal))
            edge_provenance.extend((source_record_id, source_record_id))

    edge_index = (torch.tensor(edges, dtype=torch.long, device=device).T.contiguous()
                  if edges else torch.empty((2, 0), dtype=torch.long, device=device))
    graph = EvidenceGraph(
        node_features=torch.tensor(feature_rows, dtype=torch.float32, device=device),
        edge_index=edge_index,
        edge_type=torch.tensor(edge_types, dtype=torch.long, device=device),
        edge_time_features=torch.tensor(edge_times, dtype=torch.float32, device=device),
        target_node_indices=torch.tensor([target_lookup[target] for target in targets],
                                         dtype=torch.long, device=device),
        target_ids=targets,
        as_of=as_of.isoformat(),
        edge_provenance=edge_provenance,
    )
    return graph, targets


def encode_temporal_snapshots(
    records: Sequence[object],
    cutoffs: Sequence[datetime],
    *,
    lookback: timedelta | None = None,
    device: str = "cpu",
) -> list[EvidenceGraph]:
    """Materialize chronological evidence windows; future edges never leak backward."""
    if not cutoffs:
        raise ValueError("At least one snapshot cutoff is required")
    ordered_cutoffs = [_as_utc(value) for value in cutoffs]
    if ordered_cutoffs != sorted(ordered_cutoffs) or len(set(ordered_cutoffs)) != len(ordered_cutoffs):
        raise ValueError("Snapshot cutoffs must be strictly chronological")
    dated = [(record, _record_time(record)) for record in records]
    snapshots: list[EvidenceGraph] = []
    for cutoff in ordered_cutoffs:
        start = cutoff - lookback if lookback is not None else None
        visible = [record for record, event_time in dated
                   if event_time <= cutoff and (start is None or event_time > start)]
        if visible:
            graph, _ = encode_evidence_graph(visible, device=device, reference_time=cutoff)
            snapshots.append(graph)
    if not snapshots:
        raise ValueError("No evidence records are visible at the supplied snapshot cutoffs")
    return snapshots


if nn is not None:
    class RelationalAttentionLayer(nn.Module):
        """Multi-head relation and time-conditioned message passing."""

        def __init__(self, width: int, relation_count: int, heads: int = 4, dropout: float = 0.1):
            super().__init__()
            if width % heads:
                raise ValueError("width must be divisible by heads")
            self.width, self.heads, self.head_width = width, heads, width // heads
            self.relation = nn.Embedding(relation_count, width)
            self.time_projection = nn.Linear(4, width, bias=False)
            self.query = nn.Linear(width, width, bias=False)
            self.key = nn.Linear(width, width, bias=False)
            self.value = nn.Linear(width, width, bias=False)
            self.output = nn.Linear(width, width)
            self.norm = nn.LayerNorm(width)
            self.dropout = nn.Dropout(dropout)

        def forward(self, nodes: "Tensor", edge_index: "Tensor", edge_type: "Tensor",
                    edge_time_features: "Tensor") -> "Tensor":
            source, destination = edge_index
            relation = self.relation(edge_type)
            temporal = self.time_projection(edge_time_features)
            q = self.query(nodes)[destination].view(-1, self.heads, self.head_width)
            context = relation + temporal
            k = (self.key(nodes)[source] + context).view(-1, self.heads, self.head_width)
            v = (self.value(nodes)[source] + context).view(-1, self.heads, self.head_width)
            logits = (q * k).sum(-1) / math.sqrt(self.head_width)
            max_per_node = torch.full((nodes.shape[0], self.heads), -torch.inf,
                                      device=nodes.device, dtype=logits.dtype)
            if destination.numel():
                max_per_node.scatter_reduce_(0, destination[:, None].expand_as(logits), logits,
                                             reduce="amax", include_self=True)
                weights = (logits - max_per_node[destination]).exp()
                denominator = torch.zeros_like(max_per_node)
                denominator.index_add_(0, destination, weights)
                weights = weights / denominator[destination].clamp_min(1e-12)
                messages = v * weights.unsqueeze(-1)
                aggregate = torch.zeros((nodes.shape[0], self.heads, self.head_width),
                                        device=nodes.device, dtype=nodes.dtype)
                aggregate.index_add_(0, destination, messages)
            else:
                aggregate = torch.zeros((nodes.shape[0], self.heads, self.head_width),
                                        device=nodes.device, dtype=nodes.dtype)
            aggregate = self.output(aggregate.reshape(nodes.shape[0], self.width))
            return self.norm(nodes + self.dropout(F.gelu(aggregate)))


    class RelationalGraphAttention(nn.Module):
        """Trainable temporal evidence GNN; this is not a pretrained graph foundation model."""

        architecture_id = "satori.temporal_relational_graph_attention.v2"

        def __init__(self, input_width: int = 6, hidden_width: int = 128,
                     relation_count: int = 6, depth: int = 4, heads: int = 4,
                     dropout: float = 0.1):
            super().__init__()
            self.hidden_width = hidden_width
            self.relation_count = relation_count
            self.input = nn.Linear(input_width, hidden_width)
            self.layers = nn.ModuleList(RelationalAttentionLayer(hidden_width, relation_count,
                                                                 heads, dropout) for _ in range(depth))
            self.score = nn.Sequential(nn.LayerNorm(hidden_width), nn.Linear(hidden_width, 1))

        def encode(self, graph: EvidenceGraph) -> "Tensor":
            hidden = F.gelu(self.input(graph.node_features))
            for layer in self.layers:
                hidden = layer(hidden, graph.edge_index, graph.edge_type, graph.edge_time_features)
            return hidden[graph.target_node_indices]

        def forward(self, graph: EvidenceGraph) -> "Tensor":
            return self.score(self.encode(graph)).squeeze(-1)


    class DynamicTemporalGraphRanker(nn.Module):
        """Recurrent ranker over chronological graph snapshots with time-aware graph encoders."""

        architecture_id = "satori.dynamic_temporal_graph_ranker.v1"

        def __init__(self, input_width: int = 6, hidden_width: int = 128,
                     relation_count: int = 6, depth: int = 4, heads: int = 4,
                     dropout: float = 0.1):
            super().__init__()
            self.encoder = RelationalGraphAttention(input_width, hidden_width, relation_count,
                                                    depth, heads, dropout)
            self.temporal = nn.GRU(hidden_width + 1, hidden_width, batch_first=True)
            self.score = nn.Sequential(nn.LayerNorm(hidden_width), nn.Linear(hidden_width, 1))
            self.hidden_width = hidden_width

        def forward(self, snapshots: Sequence[EvidenceGraph]) -> tuple["Tensor", list[str]]:
            if not snapshots:
                raise ValueError("DynamicTemporalGraphRanker requires at least one snapshot")
            timestamps = [_as_utc(graph.as_of) for graph in snapshots]
            if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
                raise ValueError("Graph snapshots must be ordered by distinct as_of timestamps")
            target_ids = sorted({target_id for graph in snapshots for target_id in graph.target_ids})
            target_index = {target_id: index for index, target_id in enumerate(target_ids)}
            sequence = torch.zeros((len(snapshots), len(target_ids), self.hidden_width + 1),
                                   dtype=snapshots[0].node_features.dtype,
                                   device=snapshots[0].node_features.device)
            present = torch.zeros((len(snapshots), len(target_ids)), dtype=torch.bool,
                                  device=sequence.device)
            for time_index, graph in enumerate(snapshots):
                embedding = self.encoder.encode(graph)
                destination = torch.tensor([target_index[target_id] for target_id in graph.target_ids],
                                           dtype=torch.long, device=sequence.device)
                sequence[time_index, destination, :self.hidden_width] = embedding
                sequence[time_index, destination, self.hidden_width] = 1.0
                present[time_index, destination] = True
            output, _ = self.temporal(sequence)
            last_seen = present.long().sum(dim=0).new_zeros(len(target_ids))
            for target_idx in range(len(target_ids)):
                indices = torch.nonzero(present[:, target_idx], as_tuple=False).flatten()
                last_seen[target_idx] = indices[-1]
            final = output[last_seen, torch.arange(len(target_ids), device=sequence.device)]
            return self.score(final).squeeze(-1), target_ids
else:
    class RelationalAttentionLayer:  # type: ignore[no-redef]
        def __init__(self, *_: object, **__: object):
            raise DependencyUnavailable("Target graph model requires the [ml] extra (PyTorch).")

    class RelationalGraphAttention(RelationalAttentionLayer):  # type: ignore[no-redef]
        architecture_id = "satori.temporal_relational_graph_attention.v2"

    class DynamicTemporalGraphRanker(RelationalAttentionLayer):  # type: ignore[no-redef]
        architecture_id = "satori.dynamic_temporal_graph_ranker.v1"


class GraphFoundationRanker(Protocol):
    """Contract for the approved pretrained GFM; implementations register by model ID."""

    def rank(self, graph: EvidenceGraph) -> dict[str, float]: ...


_GRAPH_FOUNDATION_ADAPTERS: dict[str, Callable[[str], GraphFoundationRanker]] = {}


def register_graph_foundation_adapter(
    model_id: str, factory: Callable[[str], GraphFoundationRanker]
) -> None:
    if not model_id.strip():
        raise ValueError("model_id must be non-empty")
    _GRAPH_FOUNDATION_ADAPTERS[model_id] = factory


def load_graph_foundation_ranker(model_id: str, checkpoint: str) -> GraphFoundationRanker:
    """Load only a registered, explicit GFM implementation; never substitute the project GNN."""
    if not model_id or not checkpoint:
        raise ComponentBlocked(
            "Graph foundation model is blocked: exact model ID and checkpoint are required; "
            "the in-repo temporal relational GNN is not a pretrained foundation model."
        )
    factory = _GRAPH_FOUNDATION_ADAPTERS.get(model_id)
    if factory is None:
        raise ComponentBlocked(
            f"Graph foundation model {model_id!r} has no registered implementation. "
            "No simpler model was substituted."
        )
    return factory(checkpoint)


def evidence_score_ranking(records: Sequence[object], *, disease_id: str) -> list[tuple[str, float]]:
    """Explicit target-prioritization baseline: maximum observed source association score."""
    scores: dict[str, float] = {}
    for record in records:
        if str(getattr(record, "disease_id", "")) != disease_id:
            continue
        target = str(getattr(record, "target_id"))
        score = float(getattr(record, "score"))
        scores[target] = max(scores.get(target, float("-inf")), score)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


def random_target_ranking(target_ids: Sequence[str], *, seed: int) -> list[str]:
    """Seeded evaluation baseline; never used as a production prioritizer."""
    ranked = list(dict.fromkeys(target_ids))
    random.Random(seed).shuffle(ranked)
    return ranked


def load_target_ranker(checkpoint: str | Path, *, map_location: str = "cpu") -> "RelationalGraphAttention":
    if torch is None:
        raise DependencyUnavailable("Target graph model requires the [ml] extra (PyTorch).")
    if not checkpoint:
        raise ValueError("A trained target-ranker checkpoint is required; no untrained scores are returned.")
    state = torch.load(checkpoint, map_location=map_location, weights_only=True)
    metadata = state.get("metadata", {})
    if metadata.get("architecture_id") != RelationalGraphAttention.architecture_id:
        raise ValueError("Checkpoint architecture_id is missing or does not match this model.")
    model = RelationalGraphAttention(
        input_width=metadata["input_width"], hidden_width=metadata["hidden_width"],
        relation_count=metadata["relation_count"], depth=metadata["depth"],
        heads=metadata["heads"], dropout=metadata.get("dropout", 0.1))
    model.load_state_dict(state["state_dict"])
    model.eval()
    return model


def pairwise_target_loss(scores: "Tensor", positive_indices: "Tensor",
                         negative_indices: "Tensor", margin: float = 1.0) -> "Tensor":
    """Sampled-pair ranking objective; callers own the recorded negative-sampling policy."""
    if torch is None:
        raise DependencyUnavailable("Target ranking loss requires the [ml] extra (PyTorch).")
    if positive_indices.numel() != negative_indices.numel() or positive_indices.numel() == 0:
        raise ValueError("Positive and negative pairs must have the same non-zero length.")
    if margin <= 0:
        raise ValueError("margin must be positive")
    return F.relu(margin - scores[positive_indices] + scores[negative_indices]).mean()


def save_target_ranker(model: "RelationalGraphAttention", path: str | Path,
                       metadata: dict[str, object]) -> None:
    if torch is None:
        raise DependencyUnavailable("Saving target ranker requires PyTorch.")
    required = {"input_width", "hidden_width", "relation_count", "depth", "heads",
                "dataset_version", "split_strategy", "seed", "dataset_hash_sha256",
                "benchmark_id", "negative_sampling_policy"}
    missing = required - metadata.keys()
    if missing:
        raise ValueError(f"Checkpoint metadata missing fields: {sorted(missing)}")
    payload = {"metadata": {**metadata, "architecture_id": model.architecture_id},
               "state_dict": model.state_dict()}
    torch.save(payload, path)
