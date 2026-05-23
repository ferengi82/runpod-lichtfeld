# syntax=docker/dockerfile:1.7

ARG CUDA_VERSION=12.8.0
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build

ARG LICHTFELD_REPO=https://github.com/MrNeRF/LichtFeld-Studio.git
ARG LICHTFELD_REF=master
ARG BUILD_CUDA_MIN_SM=75
ARG CMAKE_VERSION=4.0.3

ENV DEBIAN_FRONTEND=noninteractive \
    VCPKG_ROOT=/opt/vcpkg \
    PATH=/opt/vcpkg:/usr/local/bin:$PATH \
    CMAKE_BUILD_PARALLEL_LEVEL=2 \
    VCPKG_MAX_CONCURRENCY=2

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates curl wget git unzip zip tar pkg-config \
      build-essential gcc-14 g++-14 gfortran-14 \
      python3 python3-dev python3-pip python3-full \
      ninja-build \
      libxinerama-dev libxcursor-dev xorg-dev libglu1-mesa-dev \
      libwayland-dev libxkbcommon-dev libegl-dev libdecor-0-dev \
      libibus-1.0-dev libdbus-1-dev libsystemd-dev \
      nasm autoconf autoconf-archive automake libtool \
      ccache && \
    update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-14 60 && \
    update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-14 60 && \
    update-alternatives --install /usr/bin/gfortran gfortran /usr/bin/gfortran-14 60 && \
    rm -rf /var/lib/apt/lists/*

RUN ARCH="$(uname -m)" && \
    wget -q "https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-${ARCH}.sh" -O /tmp/cmake.sh && \
    chmod +x /tmp/cmake.sh && \
    /tmp/cmake.sh --skip-license --prefix=/usr/local && \
    rm /tmp/cmake.sh

RUN git clone https://github.com/microsoft/vcpkg.git "$VCPKG_ROOT" && \
    "$VCPKG_ROOT/bootstrap-vcpkg.sh" -disableMetrics

WORKDIR /opt
RUN git clone --depth=1 "$LICHTFELD_REPO" LichtFeld-Studio && \
    cd LichtFeld-Studio && \
    git fetch --depth=1 origin "$LICHTFELD_REF" || true && \
    git checkout "$LICHTFELD_REF" && \
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
      -DBUILD_PORTABLE=ON \
      -DBUILD_CUDA_MIN_SM=${BUILD_CUDA_MIN_SM} \
      -DLFS_ENFORCE_LINUX_GUI_BACKENDS=OFF && \
    cmake --build build --parallel "${CMAKE_BUILD_PARALLEL_LEVEL}" && \
    cmake --install build --prefix /opt/lichtfeld-dist

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04 AS runtime

ARG LICHTFELD_REF=master
ARG BUILD_CUDA_MIN_SM=75

LABEL org.opencontainers.image.title="LichtFeld Studio RunPod Headless" \
      org.opencontainers.image.description="Headless/CLI LichtFeld Studio image for RunPod" \
      org.opencontainers.image.source="https://github.com/MrNeRF/LichtFeld-Studio" \
      org.opencontainers.image.licenses="GPL-3.0"

ENV DEBIAN_FRONTEND=noninteractive \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    PATH=/opt/lichtfeld-dist/bin:$PATH \
    LICHTFELD_HOME=/opt/lichtfeld-dist \
    LICHTFELD_REF=${LICHTFELD_REF} \
    BUILD_CUDA_MIN_SM=${BUILD_CUDA_MIN_SM}

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates bash git python3 python3-pip \
      libxinerama1 libxcursor1 libx11-6 libxext6 libxi6 libxrandr2 libxrender1 \
      libwayland-client0 libwayland-cursor0 libwayland-egl1 libxkbcommon0 \
      libegl1 libdecor-0-0 libibus-1.0-5 libdbus-1-3 libsystemd0 \
      libglu1-mesa libgl1 libvulkan1 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/lichtfeld-dist /opt/lichtfeld-dist
COPY --from=build /opt/lichtfeld-upstream-revision.txt /opt/lichtfeld-upstream-revision.txt
COPY runpod-start.sh /usr/local/bin/runpod-start.sh
RUN chmod +x /usr/local/bin/runpod-start.sh && \
    mkdir -p /workspace/data /workspace/output

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/runpod-start.sh"]
CMD ["bash"]
