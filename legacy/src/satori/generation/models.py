from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from satori.errors import CheckpointUnavailable, ComponentBlocked, DependencyUnavailable


@dataclass(slots=True)
class GenerationRequest:
    target_id: str
    count: int
    seed: int
    scaffold_smiles: str | None = None
    fragment_smiles: tuple[str, ...] = ()
    protein_sequence: str | None = None
    pocket_path: str | None = None
    batch_size: int = 8
    max_length: int = 202


@dataclass(slots=True)
class GeneratedMolecule:
    smiles: str
    model_id: str
    target_conditioned: bool
    conditioning: dict[str, str | None]
    seed: int
    valid_smiles: bool
    scaffold_preserved: bool | None
    validation_reason: str | None
    provenance: dict[str, Any]


class MoleculeGenerator(Protocol):
    def generate(self, request: GenerationRequest) -> list[GeneratedMolecule]: ...


class GPMolFormerGenerator:
    """Pinned IBM GP-MoLFormer model with explicit, audited scaffold prompting."""

    model_id = "ibm-research/GP-MoLFormer-Uniq"
    model_revision = "6eca879581e2302b4e1ab07bb02908636bddb4a2"
    tokenizer_revision = "361063d0ad524ef77cf39b08469f6be770dc550f"

    def __init__(self, *, device: str | None = None, model_id: str | None = None,
                 model_revision: str | None = None, tokenizer_id: str | None = None,
                 tokenizer_revision: str | None = None):
        self._model = None
        self._tokenizer = None
        self._device = device
        self.model_id = model_id or type(self).model_id
        self.model_revision = model_revision or type(self).model_revision
        self.tokenizer_id = tokenizer_id or "ibm-research/MoLFormer-XL-both-10pct"
        self.tokenizer_revision = tokenizer_revision or type(self).tokenizer_revision

    def _load(self) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise DependencyUnavailable("GP-MoLFormer requires the [generation] extra.") from exc
        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.tokenizer_id, trust_remote_code=True, revision=self.tokenizer_revision)
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_id, trust_remote_code=True, revision=self.model_revision)
        except (OSError, ImportError, RuntimeError, ValueError) as exc:
            raise CheckpointUnavailable(f"Could not resolve GP-MoLFormer checkpoint/revision: {exc}") from exc
        device = self._device or ("cuda" if torch.cuda.is_available() else "cpu")
        if device.startswith("cuda") and not torch.cuda.is_available():
            raise DependencyUnavailable("CUDA was requested for GP-MoLFormer but is unavailable")
        self._model.to(device).eval()

    def generate(self, request: GenerationRequest) -> list[GeneratedMolecule]:
        if request.count < 1:
            return []
        if not request.target_id.strip():
            raise ValueError("target_id must be non-empty")
        if request.protein_sequence or request.pocket_path:
            raise ComponentBlocked("This GP-MoLFormer checkpoint is not protein/pocket conditioned; target conditioning requires fine-tuning.")
        if request.fragment_smiles:
            raise ComponentBlocked("GP-MoLFormer fragment constraints need a validated scaffold-conditioning policy.")
        if request.batch_size < 1 or request.max_length < 1 or request.max_length > 202:
            raise ValueError("batch_size must be positive and max_length must be in [1, 202]")
        prompt = request.scaffold_smiles or ""
        scaffold_molecule = None
        if prompt:
            try:
                from rdkit import Chem
            except ImportError as exc:
                raise DependencyUnavailable("Scaffold validation requires the [chemistry] extra (RDKit).") from exc
            scaffold_molecule = Chem.MolFromSmiles(prompt)
            if scaffold_molecule is None:
                raise ValueError("scaffold_smiles is invalid; generation was not started")
            prompt = Chem.MolToSmiles(scaffold_molecule, canonical=True, isomericSmiles=True)
        if self._model is None:
            self._load()
        import torch
        from rdkit import Chem
        from satori.reproducibility import seed_everything

        seed_settings = seed_everything(request.seed)
        device = next(self._model.parameters()).device
        inputs = self._tokenizer(prompt, return_tensors="pt") if prompt else {}
        # This tokenizer emits segment ids, but the causal generation model does
        # not consume them; Transformers rejects unused generation kwargs.
        inputs.pop("token_type_ids", None)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        strings: list[str] = []
        with torch.inference_mode():
            for offset in range(0, request.count, request.batch_size):
                batch_count = min(request.batch_size, request.count - offset)
                output = self._model.generate(**inputs, do_sample=True, top_k=None,
                                              max_length=request.max_length,
                                              num_return_sequences=batch_count)
                strings.extend(self._tokenizer.batch_decode(output, skip_special_tokens=True))
        if len(strings) != request.count:
            raise RuntimeError(f"GP-MoLFormer returned {len(strings)} strings for requested count {request.count}")
        provenance = {
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "tokenizer_id": self.tokenizer_id,
            "tokenizer_revision": self.tokenizer_revision,
            "device": str(device),
            "batch_size": request.batch_size,
            "max_length": request.max_length,
            "seed_settings": seed_settings,
        }
        generated: list[GeneratedMolecule] = []
        for raw_smiles in strings:
            molecule = Chem.MolFromSmiles(raw_smiles)
            valid = molecule is not None
            canonical = (Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True)
                         if molecule is not None else raw_smiles)
            scaffold_preserved = None
            validation_reason = None
            if not valid:
                validation_reason = "INVALID_SMILES"
            elif scaffold_molecule is not None:
                scaffold_preserved = molecule.HasSubstructMatch(scaffold_molecule)
                if not scaffold_preserved:
                    validation_reason = "SCAFFOLD_NOT_PRESERVED"
            generated.append(GeneratedMolecule(
                smiles=canonical,
                model_id=self.model_id,
                target_conditioned=False,
                conditioning={"scaffold": request.scaffold_smiles, "target_id": request.target_id},
                seed=request.seed,
                valid_smiles=valid,
                scaffold_preserved=scaffold_preserved,
                validation_reason=validation_reason,
                provenance=dict(provenance),
            ))
        return generated


class ETFlowConformerGenerator:
    """SE(3)-equivariant flow matching for conformers of a generated molecular graph."""

    model_id = "etflow:drugs-o3"

    def __init__(self):
        self._model = None

    def generate(self, smiles: list[str], *, samples: int = 1) -> dict[str, object]:
        try:
            from etflow import BaseFlow
        except ImportError as exc:
            raise DependencyUnavailable("ET-Flow conformers require installing the generation extra.") from exc
        if self._model is None:
            try:
                self._model = BaseFlow.from_default(model="drugs-o3")
            except Exception as exc:
                raise CheckpointUnavailable(f"ET-Flow drugs-o3 weights unavailable: {exc}") from exc
        return self._model.predict(smiles, num_samples=samples, as_mol=True)
