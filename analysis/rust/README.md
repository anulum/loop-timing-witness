<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — native source-bound analysis
-->

# Witness analysis

The `witness-analysis` library and `loop-timing-witness-analyze-native` command
verify complete simulated neural acquisitions. They implement the same
`loop-timing-witness.neural-step-run.v1` input and
`loop-timing-witness.neural-step-analysis-report.v1` output as the Python
analysis package.

Build and install locally with Rust 1.99.0 or later:

```sh
cargo install --locked --path analysis/rust
loop-timing-witness-analyze-native run.json --output-dir new-report
```

The output directory must be new and have an existing parent. Publication is
atomic and refuses to replace an existing file, directory or symlink.
A complete passing report returns status 0. An interpreted acquisition with
failed predicates returns status 2 and retains its complete report. Invalid
declarations, unadmitted source identities, changed required bytes or failed
publication return status 1 with an authored diagnostic.

Use the library through its root API:

```rust,no_run
use std::path::Path;
use witness_analysis::{load_neural_run, build_neural_run_report};

fn inspect() -> Result<(), String> {
    let inputs = load_neural_run(Path::new("run.json"))?;
    let report = build_neural_run_report(&inputs);
    println!("{}", report["verification"]);
    Ok(())
}
```

The loader binds all original source, compiled artifact, data, capture, reset
and execution receipt bytes before interpreting the run. It executes fresh
fixed generation and comparison operations from the exact admitted SC source
closure. Returned inputs are an immutable completed-verification snapshot;
building a report neither rereads the acquisition nor reruns the checker.
Rust snapshot fields are private. The Python counterpart refuses direct
construction and `dataclasses.replace`; an unchanged shallow copy retains its
verified result. Mutating a returned report changes neither snapshot. These
API boundaries do not authenticate hostile code running in the consumer process.

`files::read_expected` binds a consumer-owned complete body before hashing the
acquired file. Source, checker and runtime policies use their existing refusal
messages for byte differences. Matching the expected body still requires a
valid reference, safe descriptor, exact length and SHA-256; `files::read_bound`
retains its digest-bound interface.

Integer fields interpret the complete JSON integer token `-0` as zero, matching
the Python reader. Decimal and exponent forms are refused for integer fields.
Original bytes remain the input to file binding; integer-token handling preserves
strings and duplicate-field checks.

Original neural text rows use ASCII signed 64-bit decimals, single spaces and
LF terminators. Both readers reject CRLF, other control separators, blank rows
and out-of-range integers with authored diagnostics. Empty service traces
remain available for independent population analysis. Source findings retain
the same trace, historical receipt and fresh checker order in both languages.
Contradictory checker, completion, channel, clock and reset fields produce
separate findings naming each field. Completion compares root declarations,
actual counts and tail quiescence in that order. Reset compares abandoned
trace observations before receipt predicates. Historical checker metadata
does not substitute for fresh source execution.

Source binding, capture integrity, numerical equality, completion and clock
findings remain independent. The whole verdict is their conjunction.
Numerically equal output does not override missing records, invalid phases,
inconsistent sources or failed producer publication.

## Selected installation

The compiled registry admits source contract
`ec1236a69fc9e16a4eff1dfa7bdad8aa8b6088fc4ebceb8d8c43d33517199304`
for cohort `sc-neurocore-neural-step-1n1b16t.v1` and the bundled schema digest.
Its complete population contains 57 sources, including the 38-file checker
closure. The consumer selects its interpreter, tracer and import roots from
the installation descriptor named by `LOOP_TIMING_WITNESS_CHECKER_INSTALLATION`;
the descriptor names host files, is not packaged, and must match its pinned
digest. An acquisition's argv, paths or copied policy
cannot install another trusted source or executable.

The selected finite process baseline is Linux x86-64, kernel
`7.0.0-34-generic`, with 354 runtime files and three exact embedded worker
sources. Runtime bytes are reverified before and after fixed checker
operations. Unsupported hosts and changed selected files refuse.
Worker and runtime roles must have distinct logical names and physical
installation paths.
The workers run the source-owned SC reference; no Python analysis backend
substitutes for the native verifier.

A second compiled entry admits source contract
`5ff959e55f59ca3b1d1993bbc2ed9028c49e08feb6ff15a0fd5af156959d5488` and
runs the checker in the source owner's immutable executor image. The operator
selects the extracted image with `LOOP_TIMING_WITNESS_CHECKER_IMAGE` and the
reviewed executor binding with `LOOP_TIMING_WITNESS_CHECKER_IMAGE_BINDING`; the
binding is not packaged and must match its pinned digest. It fixes the launcher command, environment, deadline,
host launcher files, required absences and the complete image inventory; all of
them are verified before and after each operation. Only the image root, the
owned working directory and the fixed operation are substituted. Python and
Rust share the same binding bytes, refusals and closure findings.

Reports preserve actual checker argv, timing, native status, observed modules
and file identities. The checker uses a closed environment, finite CPU,
address-space, file and wall-time limits, no Python site initialisation or
bytecode writes, an empty bytecode read prefix, observed file opens and a
Linux x86-64 network syscall filter. This selected boundary does not seal a
whole operating system or authenticate a remote producer.

Capture ticks are simulated shared-counter edges. A passing report does not
establish calibrated physical time, device qualification or model-family
acceptance.

See the repository's [host analysis contract](../../docs/HOST_ANALYSIS.md)
and [contributing rules](../../CONTRIBUTING.md). Licence: AGPL-3.0-or-later;
commercial licensing is available from the owner.

## Verification fixtures

Default tests exercise the exact recorded public declaration and require refusal
when its original acquisition files are absent. This is an input-integrity
control, not numerical or timing acceptance. Full selected-installation tests
require the complete immutable acquisition and the actual Python report:

```sh
PUBLIC_NEURAL_MANIFEST=/absolute/acquisition/run.json \
PUBLIC_NEURAL_PYTHON_REPORT=/absolute/report.json \
cargo test --locked --test public_api_consumer public_source_admission_and_snapshot -- --exact
```

That mode invokes both real source-checker operations, compares every original
observation to the supplied Python report and verifies snapshot isolation.
The selected kernel and all runtime bindings must be available; an unsupported
installation fails instead of skipping or substituting a checker.
