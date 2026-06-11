# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.0
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build

ARG LICHTFELD_REPO=https://github.com/MrNeRF/LichtFeld-Studio.git
ARG LICHTFELD_REF=master
ARG BUILD_CUDA_MIN_SM=75
ARG CMAKE_VERSION=4.0.3
ARG FILEBROWSER_VERSION=v2.63.5

ENV DEBIAN_FRONTEND=noninteractive \
    VCPKG_ROOT=/opt/vcpkg \
    PATH=/opt/vcpkg:/usr/local/bin:$PATH \
    LD_LIBRARY_PATH=/usr/local/cuda/targets/x86_64-linux/lib/stubs:/usr/local/cuda/lib64/stubs:$LD_LIBRARY_PATH \
    CMAKE_BUILD_PARALLEL_LEVEL=1 \
    VCPKG_MAX_CONCURRENCY=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl wget git unzip zip tar pkg-config \
      build-essential gcc-14 g++-14 gfortran-14 \
      python3 python3-dev python3-pip python3-full \
      ninja-build \
      libxinerama-dev libxcursor-dev xorg-dev libglu1-mesa-dev \
      libgtk-3-dev \
      libwayland-dev libxkbcommon-dev libegl-dev libdecor-0-dev \
      libibus-1.0-dev libdbus-1-dev libsystemd-dev \
      nasm autoconf autoconf-archive automake libtool \
      cuda-driver-dev-12-8 \
      ccache && \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 60 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-14 60 && \
    update-alternatives --install /usr/bin/gfortran gfortran /usr/bin/gfortran-14 60 && \
    CUDA_STUB="$(find /usr/local/cuda /usr/local/cuda-* /usr/lib -path "*/stubs/libcuda.so" 2>/dev/null | head -n1)" && \
    test -n "$CUDA_STUB" && \
    ln -sf "$CUDA_STUB" /usr/lib/x86_64-linux-gnu/libcuda.so && \
    ln -sf "$CUDA_STUB" /usr/lib/x86_64-linux-gnu/libcuda.so.1 && \
    ldconfig && \
    rm -rf /var/lib/apt/lists/*

RUN ARCH="$(uname -m)" && \
    wget -q "https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-${ARCH}.sh" -O /tmp/cmake.sh && \
    chmod +x /tmp/cmake.sh && \
    /tmp/cmake.sh --skip-license --prefix=/usr/local && \
    rm /tmp/cmake.sh

RUN git clone https://github.com/microsoft/vcpkg.git "$VCPKG_ROOT" && \
    "$VCPKG_ROOT/bootstrap-vcpkg.sh" -disableMetrics

COPY docker/vcpkg-triplets /opt/vcpkg-triplets

WORKDIR /opt
RUN git clone --depth=1 --recurse-submodules --shallow-submodules "$LICHTFELD_REPO" LichtFeld-Studio && \
    cd LichtFeld-Studio && \
    git fetch --depth=1 origin "$LICHTFELD_REF" || true && \
    git checkout "$LICHTFELD_REF" && \
    git submodule update --init --recursive --depth=1 && \
    git rev-parse HEAD > /opt/lichtfeld-upstream-revision.txt

WORKDIR /opt/LichtFeld-Studio
RUN --mount=type=cache,target=/root/.cache/vcpkg \
    --mount=type=cache,target=/root/.cache/ccache \
    cmake -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_C_COMPILER=gcc-14 \
      -DCMAKE_CXX_COMPILER=g++-14 \
      -DCMAKE_CUDA_HOST_COMPILER=g++-14 \
      -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
      -DCMAKE_CUDA_COMPILER_LAUNCHER=ccache \
      -DVCPKG_TARGET_TRIPLET=x64-linux-release \
      -DVCPKG_HOST_TRIPLET=x64-linux-release \
      -DVCPKG_OVERLAY_TRIPLETS=/opt/vcpkg-triplets \
      -DCMAKE_INSTALL_BINDIR=bin \
      -DCMAKE_INSTALL_LIBDIR=lib \
      -DCMAKE_INSTALL_DATADIR=share \
      -DBUILD_PORTABLE=ON \
      -DBUILD_CUDA_MIN_SM=${BUILD_CUDA_MIN_SM} \
      -DLFS_ENFORCE_LINUX_GUI_BACKENDS=OFF \
      -DBUILD_PYTHON_STUBS=OFF && \
    cmake --build build --parallel "${CMAKE_BUILD_PARALLEL_LEVEL}" && \
    cmake --install build --prefix /opt/lichtfeld-dist

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04 AS runtime

ARG FILEBROWSER_VERSION=v2.63.5
ARG LICHTFELD_REF=master
ARG BUILD_CUDA_MIN_SM=75

LABEL org.opencontainers.image.title="LichtFeld Studio RunPod Headless" \
      org.opencontainers.image.description="Headless/CLI LichtFeld Studio image for RunPod" \
      org.opencontainers.image.source="https://github.com/MrNeRF/LichtFeld-Studio" \
      org.opencontainers.image.licenses="GPL-3.0"

ENV DEBIAN_FRONTEND=noninteractive \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    PATH=$PATH:/opt/lichtfeld-dist/bin \
    LD_LIBRARY_PATH=/opt/lichtfeld-dist/lib:/opt/lichtfeld-dist/bin:$LD_LIBRARY_PATH \
    LICHTFELD_HOME=/opt/lichtfeld-dist \
    LICHTFELD_REF=${LICHTFELD_REF} \
    BUILD_CUDA_MIN_SM=${BUILD_CUDA_MIN_SM} \
    RUNPOD_ENABLE_FILEBROWSER=1 \
    RUNPOD_FILEBROWSER_PORT=8080 \
    RUNPOD_FILEBROWSER_ROOT=/workspace \
    RUNPOD_FILEBROWSER_NOAUTH=1 \
    RUNPOD_ENABLE_TTYD=1 \
    RUNPOD_TTYD_PORT=7681 \
    RUNPOD_ENABLE_SSHD=1 \
    RUNPOD_ENABLE_GPU_MONITOR=1 \
    RUNPOD_GPU_MONITOR_INTERVAL=30 \
    RUNPOD_ENABLE_LICHTFELD_WEBUI=1 \
    RUNPOD_LICHTFELD_WEBUI_PORT=7860 \
    RUNPOD_LOG_DIR=/workspace/logs

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates bash curl wget git python3 python3-pip \
      openssh-server ttyd tini procps htop jq less nano vim-tiny \
      iproute2 net-tools lsof rsync openssl \
      libxinerama1 libxcursor1 libx11-6 libxext6 libxi6 libxrandr2 libxrender1 \
      libwayland-client0 libwayland-cursor0 libwayland-egl1 libxkbcommon0 \
      libegl1 libdecor-0-0 libibus-1.0-5 libdbus-1-3 libsystemd0 \
      libgtk-3-0 \
      libglu1-mesa libgl1 libvulkan1 libgomp1 && \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "$(uname -m)" in \
      x86_64) FILEBROWSER_ARCH=amd64 ;; \
      aarch64|arm64) FILEBROWSER_ARCH=arm64 ;; \
      *) echo "Unsupported File Browser arch: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    FILEBROWSER_URL="https://github.com/filebrowser/filebrowser/releases/download/${FILEBROWSER_VERSION}/linux-${FILEBROWSER_ARCH}-filebrowser.tar.gz"; \
    curl -fsSL "$FILEBROWSER_URL" -o /tmp/filebrowser.tar.gz; \
    tar -xzf /tmp/filebrowser.tar.gz -C /usr/local/bin filebrowser; \
    chmod +x /usr/local/bin/filebrowser; \
    rm /tmp/filebrowser.tar.gz; \
    filebrowser version

COPY --from=build /opt/lichtfeld-dist /opt/lichtfeld-dist
COPY --from=build /opt/lichtfeld-upstream-revision.txt /opt/lichtfeld-upstream-revision.txt
RUN printf '%s\n' /opt/lichtfeld-dist/lib /opt/lichtfeld-dist/bin > /etc/ld.so.conf.d/lichtfeld.conf && \
    ldconfig && \
    ldd /opt/lichtfeld-dist/bin/LichtFeld-Studio | awk '/not found/ && $1 != "libcuda.so.1" { bad=1; print } END { exit bad }'
COPY webui /opt/lichtfeld-webui
RUN /usr/bin/python3 -m pip install --break-system-packages --no-cache-dir -r /opt/lichtfeld-webui/backend/requirements.txt && \
    PYTHONPATH=/opt/lichtfeld-webui/backend /usr/bin/python3 -c "import fastapi, uvicorn, lichtfeld_webui.app"
COPY runpod-start.sh /usr/local/bin/runpod-start.sh
RUN chmod +x /usr/local/bin/runpod-start.sh && \
    mkdir -p /workspace/data /workspace/output /workspace/logs /run/sshd

EXPOSE 22 8080 7681 7860
WORKDIR /workspace
ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/runpod-start.sh"]
CMD ["services"]
