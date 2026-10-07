from __future__ import annotations

import os
import random

from satori.errors import DependencyUnavailable


def seed_everything(seed: int, *, deterministic: bool = True) -> dict[str, object]:
    """Seed Python/NumPy/PyTorch and return the determinism settings applied."""
    if seed < 0:
        raise ValueError("seed must be non-negative")
    random.seed(seed)
    try:
        import numpy as np
    except ImportError as exc:
        raise DependencyUnavailable("Reproducible scientific runs require NumPy.") from exc
    np.random.seed(seed)
    settings: dict[str, object] = {"seed": seed, "deterministic_requested": deterministic,
                                  "python": True, "numpy": True, "torch": False,
                                  "cuda": False, "deterministic_algorithms": False}
    try:
        import torch
    except ImportError:
        return settings
    if deterministic:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        torch.use_deterministic_algorithms(True)
        if hasattr(torch.backends, "cudnn"):
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    torch.manual_seed(seed)
    cuda_available = bool(torch.cuda.is_available())
    if cuda_available:
        torch.cuda.manual_seed_all(seed)
    settings.update({"torch": True, "cuda": cuda_available,
                     "deterministic_algorithms": deterministic,
                     "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG")})
    return settings
