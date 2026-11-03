# syntax=docker/dockerfile:1.7

# Zephyr 4.5 needs Python 3.12 or later; Debian bookworm ships 3.11.
FROM --platform=linux/amd64 python:3.12.15-slim-bookworm@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d

ARG DEBIAN_FRONTEND=noninteractive

# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------

ARG WEST_VERSION=1.5.0
ARG ZEPHYR_SDK_VERSION=1.0.1
ARG JSONSCHEMA_VERSION=4.26.0
ARG CMAKE_VERSION=3.30.5
ARG PYELFTOOLS_VERSION=0.33

# sha256.sum of the SDK release
ARG ZEPHYR_SDK_MINIMAL_SHA256=ca9bc0ff66fafca1dac9d592a36d953cf16d096a9d09b1c0357f021cf9f6a7eb
ARG ZEPHYR_ARM_TOOLCHAIN_SHA256=21b85981cb5a1818d9bc53d82af80f208946ec038b982ff1907287572ed3a634

ENV \
    ZEPHYR_SDK_INSTALL_DIR=/opt/zephyr-sdk \
    ZEPHYR_TOOLCHAIN_VARIANT=zephyr \
    ZEPHYR_BOARD=m2s_hello_fpga_kit/m2s010 \
    VIRTUAL_ENV=/opt/venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    CCACHE_DIR=/ccache \
    PATH=/opt/venv/bin:/opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin:${PATH}

# ---------------------------------------------------------------------------
# OS dependencies
# ---------------------------------------------------------------------------

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ccache \
        device-tree-compiler \
        file \
        g++ \
        gcc \
        git \
        gperf \
        make \
        ninja-build \
        wget \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python environment
#
# west, plus the packages the Zephyr 4.5 build needs (manifest and module
# validation with jsonschema, ELF post-processing with pyelftools). CMake
# comes from pip because Zephyr follows recent CMake releases.
# ---------------------------------------------------------------------------

RUN python3 -m venv "${VIRTUAL_ENV}" \
    && "${VIRTUAL_ENV}/bin/pip" install \
        --no-cache-dir \
        "west==${WEST_VERSION}" \
        "jsonschema==${JSONSCHEMA_VERSION}" \
        "cmake==${CMAKE_VERSION}" \
        "pyelftools==${PYELFTOOLS_VERSION}"

# ---------------------------------------------------------------------------
# Zephyr SDK - minimal bundle plus ONLY the ARM Cortex-M toolchain
#
# From SDK 1.0 the GNU toolchains are separate archives named
# toolchain_gnu_<host>_<target> and live under <sdk>/gnu/.
# ---------------------------------------------------------------------------

RUN set -eux; \
    base="https://github.com/zephyrproject-rtos/sdk-ng/releases/download/v${ZEPHYR_SDK_VERSION}"; \
    mkdir -p "${ZEPHYR_SDK_INSTALL_DIR}/gnu"; \
    wget -q "${base}/zephyr-sdk-${ZEPHYR_SDK_VERSION}_linux-x86_64_minimal.tar.xz" \
        -O /tmp/zephyr-sdk-minimal.tar.xz; \
    echo "${ZEPHYR_SDK_MINIMAL_SHA256}  /tmp/zephyr-sdk-minimal.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/zephyr-sdk-minimal.tar.xz --strip-components=1 -C "${ZEPHYR_SDK_INSTALL_DIR}"; \
    wget -q "${base}/toolchain_gnu_linux-x86_64_arm-zephyr-eabi.tar.xz" \
        -O /tmp/zephyr-arm-toolchain.tar.xz; \
    echo "${ZEPHYR_ARM_TOOLCHAIN_SHA256}  /tmp/zephyr-arm-toolchain.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/zephyr-arm-toolchain.tar.xz -C "${ZEPHYR_SDK_INSTALL_DIR}/gnu"; \
    rm -f /tmp/zephyr-sdk-minimal.tar.xz /tmp/zephyr-arm-toolchain.tar.xz

# ---------------------------------------------------------------------------
# Register SDK (CMake package registry)
# ---------------------------------------------------------------------------

RUN "${ZEPHYR_SDK_INSTALL_DIR}/setup.sh" -h -c

# ---------------------------------------------------------------------------
# ccache
# ---------------------------------------------------------------------------

RUN mkdir -p /ccache \
    && ccache --set-config=max_size=2G \
    && ccache --set-config=compression=true

# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

WORKDIR /workspace

# Do not copy project sources into the image.
# The workspace is mounted at runtime.

CMD ["/bin/bash"]
