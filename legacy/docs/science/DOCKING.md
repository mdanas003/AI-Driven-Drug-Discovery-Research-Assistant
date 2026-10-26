# Docking

Satori’s AutoDock Vina adapter executes only on prepared PDBQT receptor and ligand files with an explicit search box. The Vina score is a docking hypothesis, not measured affinity.

The Windows Vina binary is not vendored in this repository. Install a compatible official [AutoDock Vina release](https://github.com/ccsb-scripps/AutoDock-Vina/releases) separately and provide its executable through configuration or `PATH`. Record the version and binary checksum in each reproducible run.

## Validation status

Vina invocation and result capture have test coverage, but receptor/ligand preparation, binding-site selection, and the scientific docking protocol have not passed validation. No docking result should be described as validated until those gates and a retrospective benchmark pass.
