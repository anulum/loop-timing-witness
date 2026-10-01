<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — Rust fixed-point controller crate
-->

# Witness controller

`witness-controller` implements bit-exact signed Q8.24 PID and discrete LQR arithmetic.
The library uses `no_std`, requires no allocator and forbids unsafe code. Its public surface
is `Coefficients`, `PidState`, `Command`, `InvalidCoefficients` and `lqr_step`.
Coefficient validation rejects invalid bounds before changing PID state. Products accumulate
in `i128`; negative fractional results round towards negative infinity. Output saturation,
conditional integral hold and reset semantics match the maintained C and SystemVerilog kernels.

The host `witness-controller pid|lqr` executable accepts eleven comma-separated coefficient
words followed by `cycle,reference,position,velocity` rows. A `reset` row clears PID state.
It emits `cycle,command,integral,derivative,clipped,integral_held`; malformed input exits nonzero.
The host CLI and benchmark binary use the standard library for I/O and timing.

Build with `cargo build --locked`, test with `cargo test --locked` and generate the native API
reference with `cargo doc --no-deps`. Public items deny missing documentation. The full
[controller contract](https://github.com/anulum/loop-timing-witness/blob/main/docs/CONTROLLERS.md)
defines the fixed-point equations, state transitions and cross-language protocol.

This crate provides controller arithmetic and a host streaming interface. It does not provide
a Rust RV64 boot entry, interrupt service, Linux UIO collector or physical timing guarantee.
The manually dispatched registry publisher requires completed green validation at the exact
source revision, verified package consumers and a project-bound publishing credential.
The licence is AGPL-3.0-or-later; a commercial licence is available from the owner.

The repository's `tests/test_rust_package_consumer.py` packages and verifies this crate, then
uses its extracted archive as a dependency in an independent Cargo project. That client runs
the public state/refusal tests and strict Clippy, and cross-compiles its allocator-free library
for the installed `wasm32-unknown-unknown` and `riscv64imac-unknown-none-elf` targets.
The latter's generated kernel objects are checked as little-endian RISC-V ELF64 with the
soft-float ABI used by the freestanding target. This checks package consumption without
substituting the repository source or claiming a Rust firmware boot implementation.
