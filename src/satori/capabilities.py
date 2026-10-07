"""Best-effort runtime inspection; optional frameworks never prevent CPU startup."""
from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
import shutil
import subprocess
import sys
from typing import Any


def detect_capabilities() -> dict[str, Any]:
    result: dict[str, Any] = {
        "python": sys.version.split()[0], "platform": platform.platform(),
        "machine": platform.machine(), "torch_available": False,
        "cuda_available": False, "cuda_version": None, "gpus": [],
        "optional_packages": {}, "vina": shutil.which("vina"),
    }
    for package in ("fastapi", "uvicorn", "torch", "rdkit", "transformers", "etflow", "boto3"):
        result["optional_packages"][package] = importlib.util.find_spec(package) is not None
    try:
        import torch
        result.update(torch_available=True, cuda_available=bool(torch.cuda.is_available()),
                      cuda_version=torch.version.cuda)
        if torch.cuda.is_available():
            result["gpus"] = [
                {"index": i, "name": torch.cuda.get_device_name(i),
                 "total_memory_bytes": torch.cuda.get_device_properties(i).total_memory}
                for i in range(torch.cuda.device_count())
            ]
    except (ImportError, OSError, RuntimeError):
        pass
    if not result["gpus"] and shutil.which("nvidia-smi"):
        try:
            proc = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                                   "--format=csv,noheader,nounits"], capture_output=True,
                                  text=True, timeout=5, check=True)
            result["nvidia_smi"] = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        except (OSError, subprocess.SubprocessError):
            result["nvidia_smi"] = []
    for package in ("satori-drug-discovery", "torch", "rdkit", "transformers", "etflow"):
        try:
            result.setdefault("versions", {})[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return result

