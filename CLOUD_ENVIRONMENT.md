# Cloud Environment Specification

## Supported images

| Image | Base | Python / framework | Intended queues |
|---|---|---|---|
| `Dockerfile.api` | `python:3.11.11-slim-bookworm` | FastAPI 0.115.12 / Uvicorn 0.34.2 | API |
| `Dockerfile.worker.cpu` | `python:3.11.11-slim-bookworm` | NumPy 2.2.4 / RDKit 2024.9.6 | CPU |
| `Dockerfile.worker.gpu` | `python:3.11.11-slim-bookworm` | PyTorch 2.6.0+cu124 / Transformers 4.51.3 / RDKit 2024.9.6 / NumPy 2.2.4 | GPU |
| `Dockerfile.worker.etflow` | `nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04` | Python 3.10 / PyTorch 2.5.1+cu121 / NumPy 1.26.4 / matching PyG extensions / ET-Flow commit supplied at build | ET-Flow |
| `Dockerfile.worker.docking` | `python:3.11.11-slim-bookworm` | CPU / RDKit 2024.9.6 / official Vina 1.2.7 Linux x86-64 binary | Docking |

The PyTorch 2.6.0 cu124 wheel is the separate official CUDA 12.4 distribution. GPU host driver and NVIDIA Container Toolkit are installed on the VM; CUDA userspace libraries are inside the container. Do not install a host CUDA toolkit merely to run the container. The official PyTorch version matrix publishes CUDA 12.4 wheels: [PyTorch previous versions](https://pytorch.org/get-started/previous-versions/).

ET-Flow's upstream environment explicitly uses NumPy 1.26.4, PyTorch's `pytorch-cuda=12.1`, PyG and `pytorch-cluster`. The Dockerfile pins Python/CUDA/Torch/PyG package versions and refuses to build unless given an immutable 40-character ET-Flow commit. Resolve a full dependency lock and run the ET-Flow compatibility smoke in cloud before treating that worker as operational. The upstream code and checkpoint licensing/validation constraints remain separate.

The ET-Flow worker places the Satori source tree on `PYTHONPATH` rather than installing the root distribution: the project declares Python `>=3.11`, while this isolated upstream-compatible worker uses Python 3.10. Confirm Python 3.10 imports and worker startup in cloud CI before enabling that image; image build alone does not prove source compatibility.

## Dependency groups

- **API:** FastAPI/Uvicorn and standard library; no GPU framework in the API image.
- **CPU:** NumPy/RDKit; no Torch imported as a required dependency.
- **GPU:** PyTorch wheel includes CUDA runtime dependencies; no weights copied into image; use persistent `HF_HOME`/`SATORI_MODEL_CACHE_DIR`.
- **ET-Flow:** isolated environment with matched CUDA 12.1/PyTorch/PyG binary packages, due to upstream NumPy/compiled extension requirements.
- **Docking:** Vina 1.2.7 binary; independent CPU queue. Input preparation is not silently performed by Vina.
- **Cloud object artifacts:** boto3; AWS IAM role or standard credential-chain injection. Other providers need a new `ArtifactStore` backend, not pipeline changes.

Exact top-level pins are in `requirements/*.lock`. Container images and their transitive resolver output must be built in CI and stored by immutable image digest before production. The ET-Flow CUDA/PyG resolver and checkpoint are specifically unverified locally because Docker/cloud GPU are not available.

## Machine resources

Reference integration VM: Ubuntu 22.04 LTS, amd64, 4 vCPU, 16 GiB system RAM, NVIDIA A10G with 22 GiB device memory (`g5.xlarge` per the [AWS EC2 accelerator specification](https://docs.aws.amazon.com/ec2/latest/instancetypes/ac.html)). Use at least 100 GiB persistent block volume for images, caches, artifacts and logs; keep model weights in a separate persistent cache and data in object storage when it grows. This is a concrete integration size, not a training guarantee: large GFM/GraphFDM/affinity training may need larger memory/multi-GPU jobs after profiling.

ET-Flow upstream does not state a minimum VRAM guarantee. Start on one 22–24 GiB GPU with batch/sample count 1 and measure before scaling. CPU Vina does not use GPU.

## Configuration variables

`SATORI_DATA_DIR`, `SATORI_ARTIFACT_DIR`, `SATORI_STATE_DB`, `SATORI_STORAGE_URI`, `SATORI_MODEL_REGISTRY`, `SATORI_MODEL_CACHE_DIR`, `SATORI_API_HOST`, `SATORI_API_PORT`, `SATORI_WORKER_QUEUE`, `SATORI_WORKER_POLL_SECONDS`, `SATORI_DEVICE`, `SATORI_LOG_LEVEL`, `SATORI_IMAGE_DIGEST`, and `HF_HOME` are environment-driven. Example values are in `.env.example`; set the image digest from the immutable image actually deployed so worker provenance can capture it. No machine-specific Windows path is built into cloud runtime configuration.

Secrets are not placed in the registry, source, or job body. Use the provider's workload identity/secret injection for external API credentials and object storage. Never commit `.env`.
