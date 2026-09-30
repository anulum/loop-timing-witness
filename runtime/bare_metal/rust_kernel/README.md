<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — Rust arithmetic adapter for shared AMP firmware
-->

# Rust AMP kernel adapter

This static library implements the four functions declared in
`controllers/c/witness_controller.h` through the maintained safe `witness-controller` Rust
API. The coefficient, PID-state and command types use C representation. State is reset
through `witness_pid_reset` before its first step; rejected coefficients leave state and
output unchanged. The caller supplies aligned, live allocations and exclusive access.
Output storage may be uninitialised until a successful call writes it. Unsafe code is confined
to this pointer boundary and the panic termination call; the arithmetic crate still forbids
unsafe code and requires no allocator.

The RV64 archive uses `riscv64imac-unknown-none-elf`, an aborting panic strategy and checked
integer overflow. Its panic handler calls `witness_amp_rust_panic`, which disables interrupt
service and publishes terminal telemetry refusal cause `0x109` in the shared C firmware.
Startup assembly, interrupt service, memory ownership and telemetry are shared with that
firmware; this library implements arithmetic rather than those platform operations.

```sh
cargo build --offline --locked --release --target riscv64imac-unknown-none-elf \
  --manifest-path runtime/bare_metal/rust_kernel/Cargo.toml --target-dir build/rust-amp
cargo clippy --offline --locked --target riscv64imac-unknown-none-elf \
  --manifest-path runtime/bare_metal/rust_kernel/Cargo.toml --target-dir build/rust-amp -- -D warnings
.venv/bin/pytest -q tests/test_amp_rust_kernel.py
```

The tests link the actual archive into the original C public API test and streaming CLI,
exercise coefficient refusal and state recovery, and compare PID/LQR extremes, fractional
rounding and resets with the original C implementation. The standalone host panic entry
terminates its process with `abort`; firmware uses the telemetry refusal entry above.
The public firmware preparation command selects this arithmetic implementation with
`--rust-compiler rustc`; the generated Makefile links its actual RV64 archive with the shared
C/assembly platform. Original compiler, sources, metadata/final dependency records, target
libraries and archive bytes are retained by the image and capture receipts. See
[`docs/AMP_SIMULATION.md`](../../../docs/AMP_SIMULATION.md) for the complete preparation
and capture contract.

Registry publication is disabled. This archive alone establishes no admitted measurement,
Linux coexistence or physical board timing.
