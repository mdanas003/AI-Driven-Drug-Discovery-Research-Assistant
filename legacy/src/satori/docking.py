from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from satori.errors import ComponentBlocked


@dataclass(slots=True)
class DockingResult:
    score_kcal_mol: float
    pose_path: str
    tool_version: str
    stdout: str


class VinaDockingEngine:
    """Local AutoDock Vina adapter; inputs must already be prepared PDBQT files."""

    def __init__(self, executable: str = "vina"):
        self.executable = shutil.which(executable)
        if not self.executable:
            raise ComponentBlocked(f"Docking blocked: Vina executable {executable!r} is not installed/on PATH.")

    def version(self) -> str:
        result = subprocess.run([self.executable, "--version"], capture_output=True, text=True, check=True)
        return (result.stdout or result.stderr).strip()

    def dock(self, receptor: str | Path, ligand: str | Path, output_pose: str | Path,
             center: tuple[float, float, float], size: tuple[float, float, float],
             *, exhaustiveness: int = 8, modes: int = 9) -> DockingResult:
        output = Path(output_pose)
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [self.executable, "--receptor", str(receptor), "--ligand", str(ligand),
                "--center_x", str(center[0]), "--center_y", str(center[1]), "--center_z", str(center[2]),
                "--size_x", str(size[0]), "--size_y", str(size[1]), "--size_z", str(size[2]),
                "--exhaustiveness", str(exhaustiveness), "--num_modes", str(modes), "--out", str(output)]
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.returncode:
            raise ComponentBlocked(f"Vina docking failed ({result.returncode}): {result.stderr[-2000:]}")
        match = re.search(r"^\s*1\s+(-?\d+(?:\.\d+)?)", result.stdout, re.MULTILINE)
        if not match:
            raise ComponentBlocked("Vina completed without a parseable top-mode affinity score.")
        return DockingResult(float(match.group(1)), str(output), self.version(), result.stdout)

