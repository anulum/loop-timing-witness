<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — dedicated-hart ISA capture contract
-->


# Dedicated-hart ISA capture

The public `tools/capture_amp_simulation.py` command executes an admitted RV64 firmware
image on actual Spike harts against the production AXI RTL plugin. The selected hart runs
the selected C or Rust fixed-point controller and publishes observations to its reserved telemetry ring.
Other original harts park in firmware. The host logger drains that ring and the actual
fabric event FIFO separately. This verifies functional execution; it does not run Linux
on the parked harts or establish physical U54 instruction timing.

## Original firmware inputs

`tools/prepare_amp_image.py` requires an original complete DTB, native configuration,
actual RV64 compiler and explicit resource selections. It copies the admitted source
and generates a strict freestanding compiler Makefile. Run that Makefile to compile,
link and verify the firmware. `--isa` selects the target HTIF exit after logger acknowledgement;
without it the target parks, and the ISA capture command refuses that completion mode.
The default arithmetic backend is C. Add `--rust-compiler rustc` to select the original
installed Rust compiler and the RV64 Rust arithmetic archive. Both selections use the same
startup assembly, interrupt service, reserved memory, telemetry ring and target completion.

The same resource arguments are required by preparation, image verification and capture:

| Argument | Meaning |
|---|---|
| `--ram-node` | Original RAM node containing both reserved regions |
| `--firmware-node` | Dedicated reserved firmware region |
| `--telemetry-node` | Disjoint reserved shared telemetry region |
| `--device-node` | Original versioned Witness AXI device |
| `--plic-node`, `--plic-layout` | Original interrupt controller and concrete context layout |
| `--hart`, `--interrupt` | Dedicated original hart and retained interrupt source |
| `--stack-bytes` | Explicit reserved firmware stack size |

Paths, memory ranges, hart topology and interrupt ownership must agree with the original
DTB and linked firmware. The native configuration contains all 24 fields, including reference
and fault settings. A modeled controller latency is refused: the target executes instructions.
Each firmware or telemetry reservation must fit one selected RAM bank without overlapping
another declared RAM node, including a partial alias.
The Spike command explicitly allocates every enabled original DTB RAM bank with `-m`.
Banks must have page-aligned addresses and lengths and must not overlap; the command
refuses absent or disabled memory instead of inheriting the simulator default allocation.
Prepared sources, configuration, platform, compiler and actual compiler dependencies are
hash-bound by the verified image. The image also retains its actual compiler frontend, collect2,
assembler and linker identities and driver version, frozen before compilation and reconciled
again during verification. Each actual compiler program's ELF interpreter resolves its native
runtime libraries before preparation. Their paths, hashes and copied bytes are retained in
`runtime_source_index.json` and `runtime_sources/` inside the prepared image. Verification
requires the original live compiler/library identities and the captured library bytes to agree.
When a cross-toolchain is installed in a private prefix, its actual host library directory
must be available to the dynamic loader for preparation and capture (for example through
`LD_LIBRARY_PATH`). A compiler executable on `PATH` alone is insufficient if its assembler
cannot load the matching shared `libopcodes` and `libbfd` libraries.
The generated verifier retains the selected Python environment's executable path.
Preparation also copies the original `loop_timing_witness` Python modules, JSON contracts and
typing marker into `source/tools/loop_timing_witness/`. The preparation receipt hashes those
files alongside the standalone verifier commands. The captured verifier therefore imports its
captured implementation rather than the current checkout's installed package. Changing any
captured module, schema or typing marker makes `verify-inputs` refuse the build.
Subprogram, version or library drift is refused. Altered originals require a fresh preparation
and build.

Preparation also runs the actual compiler's `-M` preprocessing for all five C-backend translation units
(or all four platform translation units with explicit Rust arithmetic)
with their original strict compile flags before any object exists. `precompile/` retains the
actual GCC dependency records and diagnostics. `compiler_sources/` and
`compiler_source_index.json` preserve the complete source/header bytes, including external
compiler headers. Image-local names are relative, allowing byte-preserving image relocation;
external header identities remain absolute. `build_commands.json` retains exact compile,
link, verification and original-input check vectors.

The generated Makefile runs the public `tools/verify_amp_preparation.py` admission before any
object or link recipe. Changed original records, sources, headers or captured indexes refuse
before objects are created. Final image verification requires post-compilation GCC records to
match the entire original preprocessing closure; new, omitted or changed dependencies refuse.

The Rust selection additionally captures the original safe-core and ABI-adapter source files,
Cargo metadata, paired installed target `.rlib` archives and `.rmeta` metadata files, and
native compiler runtime libraries. Fixed direct
`rustc` vectors bind the original sysroot, RV64IMAC target, external core library, release flags
and strict diagnostics. Ambient Cargo configuration does not select the firmware compiler.
Each original Rust source must be a regular file contained in the selected checkout;
symlinked source paths that escape it are refused before a build receipt is created.
Actual metadata compilation precedes objects; both metadata dependency records and source
closure are frozen in `rust_preparation.json`. Final compilation must reproduce that closure.
The image receipt binds the actual safe-core Rlib, ABI static archive and both compiler records.
Capture preserves these outputs as well as the original sources and library snapshots; offline
analysis reconciles their captured bytes without needing the former host compiler installation.
Transient Make jobserver descriptors are excluded from compiler identity queries. Make retains
valid descriptors for actual Rust compilation. Source, compiler, target-library or archive drift
requires a fresh preparation; it cannot be admitted by changing the declared backend.
The Rust toolchain test links an isolated Rustup home to an owned copy of the real compiler
and its host libraries. It verifies refusal when Cargo is absent, when the RV64 target
libraries are absent, and when their metadata partners are missing. The portable receipt
also requires both members of every target-library pair. Owned symlink cases verify that
neither a target file nor the target directory can escape the selected compiler sysroot.
The test also changes an owned archive during actual metadata compilation and requires
refusal before a preparation receipt is written. It leaves the installed toolchain unchanged.

`tests/test_amp_rust_snapshot_drift.py` changes an owned original source or an owned
installed target archive exactly at its second real filesystem read, after hashing and
before snapshot copying. Its test-only native interposer forwards opens to the kernel;
it does not replace Rust source data, hash functions or compiler output with a mock.
Preparation must refuse the changed bytes before writing a receipt. The global Rustup
installation and canonical checkout remain unchanged.

## CI simulator setup

The reusable test workflow installs pinned RV64 GCC, device-tree compiler and Boost packages.
It fetches Spike commit `7ab2efd6785e847c6d13d810c0b25b7c9c26bd21` and builds the actual
simulator and generated SDK headers. That source needs `socketif.h` included before
`decode_macros.h` in `riscv/interactive.cc`: the latter defines `yield()`, which conflicts with
Boost's `yield(unsigned)` declaration. The workflow verifies the complete file's SHA-256
before and after this include-order change. The existing source receipts retain the Git
revision and patch, so the change is part of capture provenance.

CI compiles `tests/platforms/spike_multihart.dts`, prepares and verifies the dedicated-hart
firmware, and builds the mechanical and thermal plugins through `make amp-spike-plugin`.
The test job exports their original paths through `WITNESS_RV64_CC`, `WITNESS_SPIKE_SOURCE`,
`WITNESS_SPIKE_BUILD`, `WITNESS_SPIKE`, `WITNESS_SPIKE_PLUGIN`,
`WITNESS_SPIKE_THERMAL_PLUGIN` and `WITNESS_AMP_IMAGE`. The source build and tests have a
90-minute job limit. These artifacts support functional ISA and RTL tests; they retain the
`simulation_only` evidence status.

## Production plugin build

Build against the source and generated headers matching the actual Spike executable. Supply
both directories explicitly; absent original headers are refused before compilation.

```sh
make amp-spike-plugin AMP_SPIKE_SOURCE="$SPIKE_SOURCE" AMP_SPIKE_BUILD="$SPIKE_BUILD" \
  SIMULATION_THERMAL=0
```

The target compiles the production RTL, the current C controller, native configuration parser,
actual Spike AXI adapter and Verilator runtime. Its output is
`build/amp_spike_0/witness_spike_axi.so`. Use `SIMULATION_THERMAL=1` for the thermal plant and
`build/amp_spike_1/witness_spike_axi.so`. `AMP_PLUGIN_DIRECTORY` selects an explicit build directory.
The handwritten C and C++ inputs use `-O2` with strict warnings. The Verilator runtime
objects also use `-O2`, with matching dependency-preparation and compilation flags. Host compiler optimisation
keeps long functional captures within their wall-clock budget; it does not change the RTL sample
period or establish physical processor latency. Native coverage variants retain their explicit
compiler flags and are reported separately from the admitted production capture.
Before Verilator generation, the target writes an exclusive `generation.json` with original
RTL, handwritten code, SDK source/header hashes, Git revision and tracked patch. It records
the actual compiler frontend, collect2, assembler and linker, Verilator wrapper and native
backend, runtime root, Make, archive tool and interpreter hashes and versions. The
native executables must be dynamically linked little-endian Linux ELF64 programs. Each
executable's own ELF interpreter resolves its libraries with a bounded `--list` invocation
under the actual build environment. Original interpreter and resolved filesystem library
hashes are retained in `runtime_libraries` and in the captured dependency closure. This covers
the C/C++ drivers and subprograms, native Verilator backend, Make, archive tool, Python and
Perl. Kernel-provided vDSO mappings have no filesystem bytes and are excluded.
The compiled
plant and FIFO address width are explicit; `SIMULATION_FIFO_ADDRESS_BITS` accepts the RTL's
range of 1–14. Ambient `VERILATOR_ROOT` or `VERILATOR_BIN` substitutions are refused.

The generated model uses the explicitly selected `LINUX_CXX`. Actual compiler preprocessing
then records all native/model dependencies, including system headers, before any object is
compiled. `compilation.json` freezes those hashes and the generated build files. Successful
compilation must preserve the original generation inputs and match the entire preprocessor
source/header closure. Loader-resolved library paths and bytes must also remain unchanged
through both preparation stages and final receipt creation. The model build uses `-MD`
without `-MMD`, retaining system headers.

The final exclusive `plugin.json` binds both original stages, compiler records, sources,
link-input hashes and the actual library. Existing generation or final receipts stop Make
before generation; select a fresh directory. A preparation attempted after objects, archives
or a library exist is refused. Generation also requires an empty directory: existing compiler
records, hidden files, nested contents and symbolic directory aliases are preserved and refused.
An explicitly selected `AMP_VERILATOR_ROOT` must match the actual generator's runtime root.
`make amp-spike-plugin-prepare` exposes the same generation and
preprocessor stages without compiling native objects. These identities do not authenticate
a compromised build host or establish physical performance.

The plugin is tied to the selected Spike API and ABI; rebuilding against a different SDK does
not establish compatibility with an older executable. Capture records the actual executed
executable/plugin hashes; retain the original build log and matching SDK separately.

## Public capture arguments

Pass `--image` for the verified image directory, `--dtb` and `--configuration` for that image's
retained originals, and the complete resource arguments above. Select the actual installed
`--spike` executable and `--plugin` library explicitly. `--output` must be a new directory
outside the image. Existing output is preserved and refused.

`--rtc-nanoseconds` maps Spike RTC progress to the functional RTL clock. `--time-limit` bounds
simulated nanoseconds; `--timeout` bounds the host process in seconds. Neither bound is a
physical execution-time measurement. The production plugin's compiled thermal parameter,
read through the real RTL register, determines the declared plant.

The selected library must have its original `plugin.json` beside it, conforming to the
[plugin build schema](../amp-plugin-build.schema.json). Capture requires all actual native/model
build roles and checks original preparation, source/header, compiler-record, link-object and
tool and build-library hashes. Declared final identities must agree with the original
pre-compilation receipt. It also
reconciles the declared dependency set with the original compiler records, refusing omissions.
Original build inputs must remain available for acquisition; an old receipt whose inputs changed
requires a fresh build.

The command snapshots the verified inputs before execution and rejects input or tool byte
drift after execution. Spike's actual version header comes from its supported `--help` output.
The simulator's own ELF interpreter lists the libraries selected for both Spike and the admitted
plugin under the actual execution environment. The capture freezes their paths, hashes and
bytes separately from the plugin's original build libraries. After execution it repeats version
and loader resolution, checks the captured copies and refuses drift. Failure retains acquired
raw files and simulator diagnostics. Success
writes a capture receipt, the normal public run manifest and the normal analysis report.

| Artifact | Contract |
|---|---|
| `image/` | Snapshot of original verified firmware, platform, configuration and sources |
| `image/precompile/`, `image/compiler_sources/`, `image/compiler_source_index.json` | Original GCC records and exact pre-compilation source/header bytes |
| `image/build_commands.json` | Original complete compiler, linker and verification vectors |
| `command.json` | Exact executed argument vector, simulator/plugin SHA-256 and actual runtime identity |
| `runtime_source_index.json`, `runtime_sources/` | Original simulator/plugin loader libraries and captured bytes |
| `plugin_build.json` | Original admitted native build receipt |
| `plugin_source_index.json` | Original absolute source/header names mapped to stable local path/hash pairs |
| `plugin_sources/` | Exact copied compiler/source/header bytes under portable numerical paths |
| `spike.log` | Actual target diagnostics and one final logger completion receipt |
| `events.bin` | Original 16-byte fabric event records |
| `tracking_raw.csv` | Original native integer controller observations |
| `capture.json` | [AMP capture schema](../amp-capture.schema.json), artifact hashes and final counters |
| `tracking.csv` | Exact Q8.24 conversion of observed reference/output rows |
| `manifest.json` | [Public run schema](../run-manifest.schema.json), placement `bare_metal_amp` |
| `reports/` | Standard report JSON, interval CSVs and plot |

## Analysis and limits

The same telemetry ABI 2 startup is used by the [Linux collector](AMP_LINUX.md). Firmware
initialises and publishes the complete mailbox and its actual run constants before waiting for
logger readiness. The logger checks all fifteen published run words before releasing firmware
startup; the fabric starts only after the dedicated hart arms. The producer does not assume that
Linux has already configured the fabric when firmware boots. Final acknowledgement still follows
complete stream drain and close.

`tests/test_amp_architectural_refusals.py` deliberately damages constants in owned copies of
the actual cross-compiled ELF and executes those copies directly in Spike. These copies are
outside the admitted capture workflow: they exercise native defence in depth and never produce
a completed capture. The logger observes exact native refusal causes for invalid resources and
run bounds, plus real load-access-fault causes and addresses for unmapped MMIO and PLIC accesses.
An invalid compiled hart owner never enters C: the unchanged startup assembly parks every
simulated hart, and the bounded run expires without publishing mailbox or stream data.
`tests/test_amp_logger_api.py` links public API calls into the actual Spike adapter, retaining
the production RTL and native objects after verifying their hashes. It exercises both plants'
arming waits, delayed consumer batches, acquisition callbacks and lifecycle/address/contract
refusals, transport ownership and alignment, public AXI loads and stores, and the SDK
device-factory tree interface. Public Spike RAM stores damage actual initial and arming fields
for admission checks.
An owned ELF copy selects its real LQR kernel with a matching configuration and retained hashes. The transport and firmware remain unchanged. Successful diagnostic executions retain
ten samples and forty events; these clients do not publish capture or measurement manifests.
`tests/test_amp_spike_runtime.py` executes original production plugins with actual native
argument, memory and device-tree failures. Both plants also complete a run backed by a real
1 MiB DTB RAM allocation. Device-tree checks compare properties after an actual dtc round trip;
they do not infer a factory callback from the SDK dump command. A missing PLIC is refused by
the pinned SDK assertion, and an actual UART overlapping the Witness aperture is refused
by the adapter. These diagnostics do not publish admitted captures.
`tests/test_amp_consumer_fault.py` links a diagnostic Spike plugin from the hash-verified
production RTL and native objects, but makes its real logger violate one consumer-owned
transition. The unchanged RV64 firmware refuses an invalid startup status with cause `0x108`,
refuses READY-state reserved-field corruption with cause `0x107`, and refuses an invalid final
acknowledgement with cause `0x108`. Startup faults occur before a sample or completion receipt.
The final-acknowledgement fault occurs after the logger has drained both streams, but the failed
process still prevents a capture or manifest. These diagnostic plugins are fault-injection
evidence and are never admitted as production captures.
`tests/test_amp_cycle_fault.py` preserves each actual AXI register transaction but changes the
cycle word returned to the CPU in a source-anchored diagnostic plugin. The unchanged firmware
refuses a first cycle equal to the configured run length and a repeated second cycle with cause
`0x101`. Raw output retains only events and telemetry observed before refusal; neither case can
publish completion or enter capture admission.
`tests/test_amp_kernel_fault.py` releases validated startup through the real logger and then
changes the actual first coefficient word in target RAM before the first interrupt. The unchanged
firmware kernel revalidates its input, refuses with cause `0x102`, and retains only the fabric
event observed before computation. The diagnostic RAM write is outside capture admission.
`tests/test_amp_interrupt_fault.py` waits until the firmware has armed real PLIC source 2, then
changes only the expected source word in target RAM to 3. The unchanged trap handler claims the
actual source 2 and refuses the mismatch with cause `0x103`. The diagnostic run retains the one
pre-refusal fabric event and cannot enter capture admission.
`tests/test_amp_spurious_claim.py` links a source-bound RV64 prelude around the original firmware
entry. It calls the unchanged machine-external trap handler before startup, when the actual PLIC
claim is zero, and requires the handler to return before the complete original ten-cycle run.
This covers the non-terminal empty-claim path through the real PLIC rather than a substituted
claim value.
`tests/test_amp_startup_admission_fault.py` releases the unchanged target through the real logger,
then changes one CPU observation at a time. Its source-anchored diagnostic plugin retains the
production RTL and Spike objects. The mechanical/thermal matrix covers every startup MMIO
short circuit, every firmware-owned mailbox word, the command-submission guard and a
zero-iteration real overload. A source-bound post-entry wrapper changes the already admitted
hart word before calling the unchanged C main function, so the C range guard is exercised without
bypassing the assembly owner gate. Refusal cases retain empty pre-start streams and cannot publish
a capture or manifest; command blocking completes only after the independent hardware safe state.
With an unserviced interrupt, the real fabric records every sample and deadline and enters the
safe state on the third consecutive miss. The run times out without a target completion;
its actual drained raw events remain available. These checks establish functional architectural
behaviour, not Linux/HSS/PMP isolation or physical timing.

`tests/test_amp_rust_capture_parity.py` builds current Rust firmware and both production
plant plugins, then runs the public capture command for C and Rust on each plant. It requires
ten completed samples, 40 events and exact event/tracking stream equality per plant. It also
compares interval rows after excluding the capture-specific run identifier. This establishes
functional simulator parity, not physical timing or board acceptance.

`tests/test_amp_rust_panic.py` builds a separate source-bound RV64 image with a deliberate
panic at the public Rust PID reset entry point. Both production plant plugins execute the
image through the public capture command. The original Rust panic handler calls the shared
firmware refusal path; the logger observes cause `0x109` before any sample and no completion,
manifest or report is admitted. The fault is confined to the test-owned source copy; the
production Rust adapter is unchanged.

`tests/test_amp_rust_branch_coverage.py` separately instruments the unchanged host
safe core and C ABI adapter. Real C API/PID/LQR clients, public Rust core tests and a
test-owned genuine panic producer must cover every reported source line and branch.
That host profile does not substitute for the target refusal or physical coverage.

`tests/test_amp_consumer_stall.py` exercises actual telemetry starvation with a diagnostic
scheduling variant built by `tests/amp_stall_plugin.py` from the current original Spike plugin.
The fixture verifies the production plugin, original C++ compiler and every original link
input against the selected build receipt before compiling its exclusive diagnostic source.
It uses the normal `WITNESS_SPIKE_PLUGIN` and `WITNESS_SPIKE_THERMAL_PLUGIN` inputs and records
the actual compile/link commands, source hashes and raw build output. After the first real
sample is consumed, that variant suspends logger polling while continuing actual fabric event
draining, target instruction execution and interrupt delivery. It never writes firmware-owned
RAM. The unchanged firmware fills all 256 retained slots, then refuses the next publication
with cause `0x100` and the attempted cycle. The test checks the actual RAM dump, every retained
cycle and IRQ generation, the unchanged consumer position and the withheld final acknowledgement.
Both mechanical and thermal variants are built and exercised by the parametrized fixture.
These diagnostic plugins and altered run images remain
outside capture admission. This test is distinct from forcing the full-ring arithmetic predicate
through deliberate target RAM corruption.

The optional hash-bound `amp_capture` run field is distinct from `native_metadata`. It requires
CONTROL, `bare_metal_amp` and `rtl_simulation` and forbids `native_metadata` in the same run.
Capture repeats live build admission after execution and refuses receipt changes. Reanalysis
requires the captured original build receipt and source index, including every original dependency.
It verifies library identity, original captured bytes and the plant parameter read from the running
RTL. Reanalysis uses the captured closure and does not require the original installed SDK/toolchain.
It also verifies both image/compiler and execution/runtime library indexes against their original
receipts, checks captured library bytes and reconciles the image's original preparation hash.
Captured compiler metadata must include the original driver, all selected C subprograms,
version and runtime libraries. Missing or incomplete metadata is refused before library lookup.
Original preparation input hashes and preprocessing record hashes must agree with captured
artifacts. The firmware compiler source index and captured bytes must still match the original
preprocessing identities, even if outer capture and manifest hashes are recomputed.
Offline analysis decodes the original verification argument vector without executing it,
rebinds the captured DTB resource selection and re-admits the captured ELF contract and HTIF
channel. The declared platform, run constants, stack, load segments, source inputs, compiler
driver and simulation mode must agree with those original inputs. Rehashing contradictory
image declarations does not make them admissible.

The analysis verifies the original receipt and artifacts, agrees with the executed tool and
verified firmware identities, and reconciles controller coefficients, period, fault schedule,
plant and exact converted tracking with the original run. Actual final sample, record, miss,
overflow and safe-state counts must agree with the full event history, including warm-up.
The logger acknowledges completion only after both streams drain and output closes.

Reports remain `simulation_only`. Board acceptance flags are false; there is no physical
power series. Missing power keeps the normal validity gate false. Missing sample observations
remain missing and can additionally invalidate tracking coverage. No interpolation or
completion counter repairs a lost event. Reanalysis uses the normal command:

```sh
python tools/analyze_run.py capture/manifest.json --output-dir capture/reanalysis
```

The captured directory must remain intact. SHA-256 establishes byte identity, not trust in
a compromised simulator, compiler, plugin or host. Physical deployment additionally needs
verified Linux/HSS/PMP ownership, hardware acquisition and the same-bitstream acceptance
procedure in [the measurement protocol](MEASUREMENT_PROTOCOL.md).
