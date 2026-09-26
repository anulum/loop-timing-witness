<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — native controller coverage reproduction
-->

# Native controller coverage

[`controller_coverage.json`](../benchmarks/controller_coverage.json) binds source hashes
to GCC and LLVM coverage reports. Both controller kernels and their streaming CLIs have
100% executable line and branch coverage. These counts exclude benchmark harnesses and
SystemVerilog. They establish host execution coverage, not board qualification.

Production Rust builds use 1.98.1. Stable LLVM coverage additionally reports complete line,
region and function coverage for the library and CLI, but does not instrument branches.
The separate branch analysis uses `nightly-2026-08-21`, with `llvm-tools-preview`, without
changing the production compiler or disabling any branch. GCC 13.3.0 uses `--coverage`.
Build outputs and raw reports remain under ignored `build/` and the crate's `target/`.

## Compile instrumented public interfaces

Run from the repository root with its development environment installed. Use a fresh
output directory so profiles from a different source revision cannot be merged.

```bash
mkdir -p build/controller-coverage
gcc -std=gnu11 -O0 --coverage -Icontrollers/c -c \
  controllers/c/witness_controller.c -o build/controller-coverage/kernel.o
gcc -std=gnu11 -O0 --coverage -Icontrollers/c build/controller-coverage/kernel.o \
  controllers/c/controller_cli.c -o build/controller-coverage/controller_cli
gcc -std=gnu11 -O0 --coverage -Icontrollers/c build/controller-coverage/kernel.o \
  tests/native/controller_api_test.c -o build/controller-coverage/controller_api_test
build/controller-coverage/controller_api_test
rustup component add --toolchain nightly-2026-08-21 llvm-tools-preview
export RUSTUP_TOOLCHAIN=nightly-2026-08-21
export RUSTFLAGS='-C instrument-coverage -Z coverage-options=branch -C opt-level=0'
export LLVM_PROFILE_FILE="$PWD/build/controller-coverage/rust-%p-%m.profraw"
export CARGO_TARGET_DIR="$PWD/controllers/rust/target/controller-coverage"
cargo test --offline --locked --manifest-path controllers/rust/Cargo.toml
cargo build --offline --locked --bins --manifest-path controllers/rust/Cargo.toml
```

## Execute the existing behavioral corpus

This calls the same parameterized tests against the instrumented executables. The RTL
runner still invokes Icarus; the read, write, pipe and device tests still use real OS
interfaces. It does not replace a controller, plant or simulator with a mock.

```python
import importlib
import inspect
import itertools
import os
from pathlib import Path
import sys

root = Path.cwd()
sys.path.insert(0, str(root / "tests"))
import conftest

work = root / "build/controller-coverage"
programs = (
    work / "controller_cli",
    Path(os.environ["CARGO_TARGET_DIR"]) / "debug/witness-controller",
)
fixtures = {
    "native_controllers": programs,
    "tmp_path": work,
    "run_rtl": conftest.run_rtl.__wrapped__(work),
}
for module_name in ("test_controller_inputs", "test_controller_parity"):
    module = importlib.import_module(module_name)
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        marks = [m for m in getattr(function, "pytestmark", []) if m.name == "parametrize"]
        for values in itertools.product(*(m.args[1] for m in marks)):
            parameters = dict(zip((m.args[0] for m in marks), values, strict=True))
            parameters.update(
                {
                    key: fixtures[key]
                    for key in inspect.signature(function).parameters
                    if key in fixtures
                }
            )
            function(**parameters)
```

Save or execute the Python block with `.venv/bin/python` from the repository root.
The corpus includes full-range default/maximal coefficients, deterministic random states,
negative fractions, reset, integrator rail recovery, malformed input, LF/CRLF, streaming
before EOF, `/dev/full`, invalid encoding and an actual nonblocking-pipe read failure.

## Export and inspect every outcome

Run `gcov -b -c -j build/controller-coverage/kernel.gcno` and
`gcov -b -c -j build/controller-coverage/controller_cli-controller_cli.gcno`.
For each production C file, every executable line and every branch must have a positive
execution count in the resulting JSON report. A percentage rounded to 100 is insufficient.

Resolve the pinned toolchain's `llvm-profdata` and `llvm-cov` below
`rustc --print sysroot`, in `lib/rustlib/x86_64-unknown-linux-gnu/bin/`.
Merge all `build/controller-coverage/*.profraw` with `llvm-profdata merge -sparse`.
Use `llvm-cov export --instr-profile=<merged.profdata>` with the CLI ELF and `-object`
for every actual `controller_api-*` ELF below the coverage target directory; exclude
dependency metadata files. Inspect the `lib.rs` and `main.rs` file summaries: line,
region, function and branch covered counts must equal their totals. Preserve source hashes,
compiler versions, flags and report hashes with the result. Reset the coverage environment
variables before ordinary production builds or benchmarks.
