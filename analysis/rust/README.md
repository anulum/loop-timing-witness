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
analysis package. The command also analyses CONTROL and COMPUTE runs, as the
Python command does, and publishes a byte-equal report directory.

Build and install locally with Rust 1.99.1 or later:

```sh
cargo install --locked --path analysis/rust
loop-timing-witness-analyze-native run.json --output-dir new-report
```

The `loop-timing-witness-campaign-native` command analyses a repeat campaign
as the Python `loop-timing-witness-campaign` command does, and publishes a
byte-equal campaign report directory:

```sh
loop-timing-witness-campaign-native campaign.json --output-dir new-report
```

It returns status 0 for a published complete campaign, 2 for a published
incomplete campaign after printing each nonconformity, and 1 with the Python
command's diagnostic when the campaign is refused or its report cannot be
written. A campaign whose repeat binds an AMP capture is refused, because the
native analysis does not complete AMP captures.

The output directory must be new and have an existing parent. Publication is
atomic and refuses to replace an existing file, directory or symlink.
A manifest with a `schema_id` member is a neural run; any other is a CONTROL or
COMPUTE run, which returns status 0 once its report is published and status 1
with the Python command's diagnostic otherwise. For a neural run,
a complete passing report returns status 0. An interpreted acquisition with
failed predicates returns status 2 and retains its complete report. Invalid
declarations, unadmitted source identities, changed required bytes or failed
publication return status 1 with an authored diagnostic. `load_neural_manifest`
refuses a declaration with the Python reader's text, for the same first defect.

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

## Control-run loading

`load_control_run(path)` and `load_control_run_bytes(path, root)` validate a
CONTROL or COMPUTE run and keep its hash-bound input bytes, available through
`ControlInputs::manifest`, `domain`, `files` and `directory`.
`decode_control_events(&inputs)` returns the run's `ControlEvent` records, and
`control_events_summary(&inputs)` returns the report's `events` block with the
`IntervalRow` table, and `control_run_report(&inputs)` the complete report with
the same rows: tracking error, observed tracking, energy per cycle, validity,
input digests, stated limits and any bound native completion and host load
receipts. Its floats equal the Python report's bit for bit. A run that binds an
AMP capture is refused until AMP completion is implemented natively.
Every refusal is the text of the Python `load_run` and `decode_events` for the
same files, and every report refusal the text of the Python `build_report`;
the parity tests run both on real RTL captures, damaged series, malformed
documents and injected read failures, and shared corpora hold the schema
locations, JSON decoding, measurement-domain rules, CSV reading, decimal values
and arithmetic, series metrics and receipt schema locations to Python's
outcomes.

## Device-tree reading

The `device_tree` module decodes an original device-tree blob and reads the
resources an AMP image binds, as the Python `device_tree_*` modules do.
`decode_device_tree(&bytes)` validates the header, block extents, memory
reservations and structure tokens, and returns a `DeviceTree` with its nodes
in document order, its reservations and its boot CPU.
`register_regions(&tree, path)` translates a node's `reg` extents through every
ancestor `ranges` mapping to root physical addresses. `single_cell`,
`string_list` and `phandle_nodes` read scalar, string-list and phandle
properties. `bind_plic(&tree, &selection)` binds one dedicated U54 hart and
device source to its PLIC machine context and returns the context's register
addresses. Every refusal is the Python reader's text for the same first
defect. Addresses are 128-bit, because a translated zero-size extent may start
exactly at the end of the RV64 address space, as it may in Python.

A shared corpus holds both implementations to the same outcomes. The Python
tests build it from real `dtc` 1.7.0 output: the repository's Spike platform,
changed sources that reach each reader rule and bound, byte changes of every
header word, structure token and string byte of a small tree, hand-built
structure blocks, and blobs at the depth, node, path and size limits.

## Firmware ELF reading

The `amp_elf` module reads an AMP firmware image as the Python `amp_elf` and
`amp_elf_symbols` modules do. `admit_elf(&bytes, reservation)` admits the load
segments of a static little-endian soft-float RV64 executable inside the
firmware reservation, with its entry backed by executable file bytes.
`read_symbols(&bytes)` returns the defined global and weak symbols of the one
symbol table, in table order. Every refusal is the Python reader's text for
the same first defect.

A shared corpus holds both implementations to the same outcomes on two real
images it carries: the small image the load tests link from one assembly
file, and a whole firmware compiled from the repository's startup, controller,
exit and contract sources. The corpus records how each was built.
It covers cut, padded and changed images, other reservations, and one-field
changes of the ELF header and of every program header, section header and
global symbol.

## Rust dependency record reading

The `amp_rust_dependencies` module reads rustc's dependency records of an AMP
image built with the Rust kernel as the Python `amp_rust_dependencies` module
does. `rust_dependency_hashes(&records, directory)` hashes every source the
records name, keyed as the records write them; each source must stay in the
image's `source` tree, and every phony rule must name a source. A failure is
`AmpFailure::Refused` with the Python reader's text, or `AmpFailure::Os` with
the text of Python's `OSError`, for the same first failure; the `amp_failure`
module holds that type for every AMP reader.

Records are read with Python's universal newlines and line boundaries and
split into words by a port of CPython's POSIX `shlex.split`. A shared corpus
holds the port to CPython on every text of up to three characters over word,
whitespace, quote, escape and non-ASCII characters and every text of four
and five characters over the quote and escape core, and the reader to the
Python reader's digests, refusals and read errors on named file trees.

## AMP snapshot checks

An AMP image or capture keeps copies of its runtime libraries and of the
firmware's preprocessing sources, indexed by original name. The
`amp_runtime_snapshot` and `amp_image_dependencies` modules check them as the
Python modules of the same names do. `validate_runtime_snapshot(output,
identities)` and `validate_image_dependency_snapshot(directory, identities)`
require the index document to equal the index Python assigns to the recorded
identities, then check every copy, in the document's order, for a path inside
the folder and the recorded digest. `image_dependency_record_count(receipt)`
reads how many preprocessing records the preparation's kernel backend has.
Failures are `AmpFailure` values with Python's texts, met in Python's order.
The identity schemas are committed beside the crate, and a test holds them
equal to the Python constants.

A shared corpus holds both implementations to the same outcomes on trees that
Python's own snapshot writers build: changed, missing, linked and escaping
copies, disagreeing and malformed indexes, invalid identities, document order
and every kernel declaration.

## AMP plugin receipts

`amp_plugin_receipt::decode_plugin_receipt(&bytes)` decodes an AMP plugin
build receipt as the Python module of the same name does: bounded JSON, the
first location that breaks the committed plugin build schema, and the
receipt's agreement with the preparation it binds (identities, every
preparation and compiler identity among its dependencies, the preparation's
canonical JSON digest and its generation record beside it).
`amp_plugin_snapshot::validate_plugin_snapshot(output, plugin_digest,
thermal)` checks a capture's `plugin_build.json` against the executed library
and observed plant, its source index against the receipt, and every copy as
the other snapshot checks do. A shared corpus, built from a reduced real
receipt, holds both to Python's outcomes.

## AMP Rust kernel images

`amp_rust_receipt::validate_rust_image_receipt(directory, image, preparation)`
checks an AMP image's Rust kernel as the Python module of the same name does.
An image whose preparation declares no backend is the C kernel and may carry
no Rust declaration. For the Rust kernel the captured `rust_preparation.json`
is held to its toolchain identity (the committed toolchain schema, which a
test holds equal to Python's), to the literal compiler vectors, the runtime
library snapshot, the crate sources, the target library snapshot (archives and
metadata paired by Python 3.15's `stem` and `suffix`) and the metadata
dependency records; then the compiled records, the static archive and the
controller library are held to the image's receipt. A corpus laid out as a
real image built on the review host holds both implementations to the same
outcomes.

## AMP platform binding

`amp_platform::bind_platform(&tree, &memory, device_path, &plic)` admits an AMP
platform's resources from a decoded device tree as the Python modules
`amp_platform`, `amp_memory`, `amp_device` and `amp_collisions` do: the
firmware and telemetry reservations (direct, enabled, unmapped, page-aligned,
each inside one RAM bank, meeting no other reservation, memory node or header
reservation), the enabled Witness AXI device with its one PLIC source and
256-byte aperture, no other consumer of that source and no other root-level
register extent meeting the aperture, and a PLIC aperture that meets no RAM or
reservation. A shared corpus compiles the repository's Spike platform with the
real `dtc`, changed per rule, and holds both implementations to the same
platform or refusal.

## AMP run configuration

`amp_run_input::read_amp_run(&content)` reads an AMP image's complete native
run configuration as the Python modules `amp_run_input` and `amp_contract` do:
ASCII fields separated by the C locale's whitespace, as the native stream
reader separates them; the controller, every field's whole decimal syntax and
bound (with any count of leading zeros); a fault schedule inside the run
without modeled latency; and the run's integer contract and controller
invariants. A shared corpus of the ISA image's configuration, changed per
rule, holds both implementations to the same run or refusal.

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

`load_neural_run` uses `NeuralRegistry::reviewed()`, the two packaged
entries. A consumer that reviews its own source policy, checker policy and
executor builds a `NeuralRegistry` keyed by `neural_key` and calls
`load_neural_run_with_registry`; an entry combines the policy bytes with an
`Installation` or an `ImageExecutor`. The Python keyword-only `registry`
argument has the same keys and checks. Each entry's factory runs before the
acquired policy copies are compared, in both languages; acquisition data never
selects a registry or an entry. `public_command::run` runs the command, with
its arguments, messages and statuses, against a registry the caller passes; the
installed command passes `NeuralRegistry::reviewed()`.
`Installation::with_embedded_workers` checks each worker body against the
descriptor and writes it to a new owned directory, removed with the installation.

The first entry's runtime binds the package initialiser that was reviewed
before the public campaign API was added. The current workers therefore refuse
that entry with "Selected checker worker or installation differs from its
reviewed runtime", as in Python; the entry is never repinned. An unreadable
operator descriptor is refused as unavailable, a directory or other special
file as not regular, and changed bytes as differing from the reviewed binding.

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
