# AutoDock Vina local executable

- Release: AutoDock Vina v1.2.7, Windows x86-64 executable
- Official source: https://github.com/ccsb-scripps/AutoDock-Vina/releases/tag/v1.2.7
- Asset: `vina_1.2.7_win.exe`
- Size: 1,233,920 bytes
- SHA-256: `e0c4b2715e0c1a74f6e92d0f3be0328ac97542eafbc111e6b1efad897a73cce5`
- Verification: `AutoDock Vina v1.2.7` from `--version`

Invoke the project adapter with the explicit executable path:

```python
from satori.docking import VinaDockingEngine

engine = VinaDockingEngine("tools/vina/vina_1.2.7_win.exe")
```

The engine only runs docking on prepared PDBQT inputs. The project does not yet
have a validated receptor/ligand preparation and binding-site protocol, so this
executable verification is not a docking result.
