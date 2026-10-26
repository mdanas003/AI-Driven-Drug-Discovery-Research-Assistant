from __future__ import annotations

from pathlib import Path
from typing import Sequence

from satori.errors import CheckpointUnavailable, DependencyUnavailable
from satori.provenance import write_json_atomic


class XGBoostMorganBaseline:
    """Ligand-only per-target baseline; never a substitute for protein–ligand cross-attention."""

    model_id = "baseline.xgboost_morgan_per_target.v1"

    def __init__(self, *, radius: int = 2, bits: int = 2048, estimators: int = 700,
                 max_depth: int = 8, learning_rate: float = 0.04, seed: int = 17):
        self.radius, self.bits = radius, bits
        self.estimators, self.max_depth = estimators, max_depth
        self.learning_rate, self.seed = learning_rate, seed
        self._model = None

    def _features(self, smiles: Sequence[str]):
        try:
            import numpy as np
            from rdkit import Chem, DataStructs
            from rdkit.Chem import rdFingerprintGenerator
        except ImportError as exc:
            raise DependencyUnavailable("XGBoost affinity baseline requires the [baseline] extra.") from exc
        generator = rdFingerprintGenerator.GetMorganGenerator(radius=self.radius, fpSize=self.bits)
        matrix = np.zeros((len(smiles), self.bits), dtype=np.float32)
        for index, value in enumerate(smiles):
            molecule = Chem.MolFromSmiles(value)
            if molecule is None:
                raise ValueError(f"Invalid SMILES at row {index}; baseline never drops records silently.")
            DataStructs.ConvertToNumpyArray(generator.GetFingerprint(molecule), matrix[index])
        return matrix

    def fit(self, smiles: Sequence[str], affinity: Sequence[float]) -> "XGBoostMorganBaseline":
        try:
            from xgboost import XGBRegressor
        except ImportError as exc:
            raise DependencyUnavailable("XGBoost affinity baseline requires the [baseline] extra.") from exc
        if len(smiles) != len(affinity) or len(smiles) < 2:
            raise ValueError("Training requires matching SMILES/affinity arrays with at least two records.")
        self._model = XGBRegressor(n_estimators=self.estimators, max_depth=self.max_depth,
            learning_rate=self.learning_rate, objective="reg:squarederror", tree_method="hist",
            random_state=self.seed, n_jobs=-1)
        self._model.fit(self._features(smiles), affinity)
        return self

    def predict(self, smiles: Sequence[str]) -> list[float]:
        if self._model is None:
            raise CheckpointUnavailable("XGBoost baseline is not fitted; provide a training split first.")
        return [float(value) for value in self._model.predict(self._features(smiles))]

    def save(self, path: str | Path, *, dataset_version: str, split_strategy: str) -> None:
        if self._model is None:
            raise CheckpointUnavailable("Cannot save an unfitted baseline.")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._model.save_model(destination)
        write_json_atomic(destination.with_suffix(destination.suffix + ".metadata.json"), {
            "model_id": self.model_id, "dataset_version": dataset_version,
            "split_strategy": split_strategy,
            "parameters": {"radius": self.radius, "bits": self.bits,
                           "estimators": self.estimators, "max_depth": self.max_depth,
                           "learning_rate": self.learning_rate, "seed": self.seed},
        })
