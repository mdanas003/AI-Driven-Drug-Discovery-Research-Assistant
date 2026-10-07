# Phase 0 Environment Audit

**Audited:** 2026-10-02 (local machine; Asia/Calcutta)  
**Purpose:** Establish the development/integration environment. No training, data pull, docking run, or checkpoint download was performed.

## Machine profile

| Item | Observed | Notes |
|---|---|---|
| OS | Windows 10 Home Single Language; reported NT version `10.0.26200.0` | Native Windows available. |
| Python | CPython 3.13.1; pip 24.3.1; uv 0.10.10 | Project range `>=3.11,<3.14` includes this interpreter. |
| CPU | 16 logical processors | CPU model not reliably collected. |
| RAM | 25,165,824 KiB installed (24 GiB); ~9.2 GiB was available in the earlier Windows memory snapshot | Read through Windows memory API; available amount is time-sensitive. |
| GPU | NVIDIA GeForce RTX 3050 6GB Laptop GPU; 6,144 MiB VRAM | `nvidia-smi` reports driver 581.86 and CUDA 13.0 capability/runtime. The installed CUDA toolkit/compiler was not verified; a compatible PyTorch wheel can bundle runtime libraries. |
| C: storage | 49,359,675,392 bytes free (~46.0 GiB; user budget stated as ~40 GB) | Fresh read supersedes both the obsolete 3.49 GB figure and earlier Phase 0 sample. |
| WSL | `wsl.exe` present; `wsl --status` failed with access denied while enumerating distributions | Linux userland availability is unresolved; no WSL distribution was confirmed. |
| Docker | Docker CLI 29.2.0 present; daemon/engine pipe unavailable | Docker is not currently usable. |
| Python environment | New repo-local `.venv` created | Global environment was kept clean. uv cache/managed-Python discovery had access errors; standard `venv` was used instead. |

## Disk and installation policy

The measured free space is about 46.6 GiB, so the former 3.49 GB limit no longer applies. The Phase 0 core install was limited to RDKit, NumPy, and RDKit's Pillow dependency. The downloaded Windows wheels were 25.0 MB (RDKit), 12.6 MB (NumPy), and 7.2 MB (Pillow); installed footprint is modest relative to the available space. No CUDA framework, model weights, corpus, or large dataset was installed.

PyTorch's official CUDA 13.0 wheel index contains a CPython 3.13 Windows wheel, but the full CUDA dependency closure and disk footprint were not resolved in this audit. Therefore PyTorch is listed as a candidate LOCAL-GPU group but was not installed yet. Before that group is installed, resolve a dry-run plan and total wheel size, then install and verify PyTorch alone as a separate group.

## Dependency installation result

- **LOCAL-CORE:** RDKit 2026.3.6, NumPy 2.5.3, Pillow 12.3.0 installed in `.venv` from CPython 3.13 Windows wheels.
- **Verification:** imports report NumPy 2.5.3 and RDKit 2026.03.6; parsing `CCO` succeeded. No application tests or scientific workflows were run.
- **Network:** PyPI was unreachable inside the network sandbox. The bounded install succeeded only after using the approved elevated network path.
- **No heavy components installed:** PyTorch/CUDA, Transformers, sentence-transformers, PyG extensions, ETFlow, Vina, and model checkpoints remain uninstalled.

## Operational conclusion

The machine is suitable for development, data validation, CPU chemistry preprocessing, lightweight graph experimentation, and integration. The 6 GB GPU can support carefully selected inference and small experiments, but is not the training environment for the full approved architecture. Cloud GPU remains the planned execution target for expensive model training and large-scale generation. WSL and Docker availability are blocked by local access/daemon state, not by a scientific architecture decision.

## Implementation-phase update (2026-10-02)

The earlier installation statements above are the Phase 0 snapshot. Subsequent implementation work installed and verified PyTorch 2.14.1+cu130 (CUDA available; RTX 3050 detected), Transformers 4.51.3, Safetensors 0.8.0 and Tokenizers 0.21.4. The PyTorch wheel was approximately 1,990.6 MB. The pinned GP-MoLFormer model and tokenizer were downloaded, totaling about 374 MB, and a small real CUDA generation smoke succeeded. AutoDock Vina v1.2.7 Windows binary (1,233,920 bytes) was downloaded and its version verified; its SHA-256 is in `tools/vina/README.md`.

Current C: free space measured after these installs and checkpoint downloads: 40,652,046,336 bytes (37.86 GiB). This is a point-in-time measurement. WSL and Docker status were not changed; ET-Flow remains isolated to a compatible Linux/CUDA environment.
