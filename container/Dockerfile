# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — development and test container

# Ubuntu 26.04 with the exact apt packages the hosted workflows pin, Python 3.15.2, Rust 1.100.0 and
# Go 1.27.4, for running the repository's builds, simulations and tests away from the hosted
# runners. Every download is checked against a recorded SHA-256; rustup verifies the toolchains it
# installs. tests/test_container_definition.py keeps the pins equal to the workflows'. Build and use
# it as VALIDATION.md describes.
FROM ubuntu:26.04@sha256:d66b366dac61b575bee2aef07e9c26e8070096fbe84a3d4d3eb0da069b5d76db

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8

RUN apt-get update && apt-get install --no-install-recommends --yes \
      gcc=4:15.2.0-5ubuntu1 g++=4:15.2.0-5ubuntu1 gcc-15=15.2.0-16ubuntu1 g++-15=15.2.0-16ubuntu1 \
      libstdc++-15-dev=15.2.0-16ubuntu1 make=4.4.1-3 cmake=4.2.3-2ubuntu2 git=1:2.53.0-1ubuntu1.1 \
      curl=8.18.0-1ubuntu2.8 ca-certificates=20260816ubuntu0.26.04.2 xz-utils=5.8.3-1ubuntu0.1 \
      zstd=1.5.7+dfsg-3 unzip=6.0-29ubuntu1 jq=1.8.1-4ubuntu2 file=1:5.46-5build2 \
      procps=2:4.0.4-9ubuntu1 perl=5.40.1-7ubuntu0.4 pkg-config=2.5.1-4 bzip2=1.0.8-6ubuntu0.1 \
      shellcheck=0.11.0-2 \
      verilator=5.032-1 iverilog=12.0-3 yosys=0.52-2 strace=6.19+ds-0ubuntu5 \
      device-tree-compiler=1.7.2-2ubuntu1 libssl-dev=3.5.5-1ubuntu3.7 libssl3t64=3.5.5-1ubuntu3.7 \
      gcc-riscv64-linux-gnu=4:15.2.0-5ubuntu1 gcc-15-riscv64-linux-gnu=15.2.0-16ubuntu1cross1 \
      binutils-riscv64-linux-gnu=2.46-3ubuntu2 \
      libboost-dev=1.90.0.1ubuntu3 libboost-regex-dev=1.90.0.1ubuntu3 libboost1.90-dev=1.90.0-6ubuntu1 \
      libboost-regex1.90-dev=1.90.0-6ubuntu1 libboost-regex1.90.0=1.90.0-6ubuntu1 \
      clang-21=1:21.1.8-6ubuntu1 libclang-rt-21-dev=1:21.1.8-6ubuntu1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL --retry 2 -o /tmp/python.tar.gz \
      https://github.com/astral-sh/python-build-standalone/releases/download/20261026/cpython-3.15.2%2B20261026-x86_64-unknown-linux-gnu-install_only.tar.gz \
    && echo "08d4ae9024a7cfbd3b70e559241afa2571cd3208d7bd5f96f88e0080dd4092aa  /tmp/python.tar.gz" \
      | sha256sum --check --strict \
    && mkdir /opt/python && tar -C /opt/python --strip-components=1 -xzf /tmp/python.tar.gz \
    && rm /tmp/python.tar.gz \
    && curl -fsSL --retry 2 -o /tmp/go.tar.gz https://go.dev/dl/go1.27.4.linux-amd64.tar.gz \
    && echo "7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840  /tmp/go.tar.gz" \
      | sha256sum --check --strict \
    && tar -C /usr/local -xzf /tmp/go.tar.gz && rm /tmp/go.tar.gz

USER ubuntu
ENV RUSTUP_HOME=/home/ubuntu/.rustup CARGO_HOME=/home/ubuntu/.cargo
ENV PATH=/home/ubuntu/.cargo/bin:/usr/local/go/bin:/opt/python/bin:$PATH

RUN curl -fsSL --retry 2 -o /tmp/rustup-init \
      https://static.rust-lang.org/rustup/archive/1.29.3/x86_64-unknown-linux-gnu/rustup-init \
    && echo "b1c8cb14e30889e7e2999e6b69e62d9e9b9ffc0f4df8180564d306d9680e6c55  /tmp/rustup-init" \
      | sha256sum --check --strict \
    && chmod +x /tmp/rustup-init \
    && /tmp/rustup-init -y --no-modify-path --profile minimal --default-toolchain none \
    && rm /tmp/rustup-init \
    && rustup toolchain install 1.100.0 --profile minimal --component rustfmt --component clippy \
      --component llvm-tools-preview --target wasm32-unknown-unknown --target riscv64imac-unknown-none-elf \
    && rustup default 1.100.0

WORKDIR /work
