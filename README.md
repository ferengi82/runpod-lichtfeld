# LichtFeld Studio RunPod Headless Container

This repository builds a RunPod-ready headless/CLI Docker image for:

https://github.com/MrNeRF/LichtFeld-Studio

The image is built automatically by GitHub Actions and pushed to GitHub Container Registry (GHCR).

## Image

After the first successful workflow run, use this image in RunPod:

```text
ghcr.io/OWNER/lichtfeld-studio-runpod:latest
```

Replace `OWNER` with the GitHub account or organization that owns this repository.

A pinned tag is also published for every upstream LichtFeld commit:

```text
ghcr.io/OWNER/lichtfeld-studio-runpod:upstream-<sha>
```

## What the image contains

- NVIDIA CUDA 12.8 runtime image
- Portable LichtFeld Studio build installed at `/opt/lichtfeld-dist`
- Headless-friendly CMake configuration:
  - `BUILD_PORTABLE=ON`
  - `LFS_ENFORCE_LINUX_GUI_BACKENDS=OFF`
  - PTX-only CUDA build via `BUILD_CUDA_MIN_SM`
- RunPod workspace at `/workspace`

## GitHub Actions

Workflow:

```text
.github/workflows/build-runpod-image.yml
```

Triggers:

- Manual: `workflow_dispatch`
- Daily: `0 4 * * *` UTC
- Push to `main` when Docker/workflow files change

The workflow resolves the latest upstream `MrNeRF/LichtFeld-Studio` commit and uses it as Docker build arg. Docker layer caching means repeated builds are cheaper when upstream did not change.

## Run manually

In GitHub:

1. Open this repository
2. Go to `Actions`
3. Select `build-runpod-image`
4. Click `Run workflow`

Optional inputs:

- `lichtfeld_ref`: branch, tag, or SHA from upstream; default `master`
- `cuda_version`: default `12.8.0`
- `build_cuda_min_sm`: default `75`

## RunPod setup

Create a RunPod template with:

```text
Container Image: ghcr.io/OWNER/lichtfeld-studio-runpod:latest
Container Disk: 80 GB or more recommended
Volume Mount Path: /workspace
```

If the repository/package is private, RunPod needs registry credentials for GHCR. The simplest setup is a public repository or public GHCR package.

## Usage inside RunPod

Open a terminal in the pod.

Show version/help:

```bash
version
```

Run LichtFeld directly:

```bash
lichtfeld --help
```

Example training run:

```bash
train -d /workspace/data/my-dataset -o /workspace/output/my-run
```

Equivalent direct command:

```bash
/opt/lichtfeld-dist/bin/run_lichtfeld.sh -d /workspace/data/my-dataset -o /workspace/output/my-run
```

## Notes and caveats

- This is Variant A: GitHub-hosted build using GitHub Actions.
- GitHub-hosted runners do not have NVIDIA GPUs. The Dockerfile uses a portable/PTX-only build and disables the GUI-backend configure enforcement.
- If upstream starts requiring an actual GPU during build/configure, move the same workflow to a self-hosted GitHub runner on RunPod.
- Large C++/CUDA/vcpkg builds can be slow. The workflow timeout is set to 6 hours.
- GHCR packages for private repositories may not be pullable by RunPod without credentials.

## Local smoke build

If you want to test the Dockerfile locally on a machine with Docker:

```bash
docker build \
  --build-arg LICHTFELD_REF=master \
  --build-arg CUDA_VERSION=12.8.0 \
  --build-arg BUILD_CUDA_MIN_SM=75 \
  -t lichtfeld-studio-runpod:local .
```

Run:

```bash
docker run --rm --gpus all -it -v "$PWD/workspace:/workspace" lichtfeld-studio-runpod:local version
```
