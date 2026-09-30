<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — host analysis contract
-->

# Host analysis contract

`tools/analyze_run.py` accepts one versioned run manifest and writes a report directory. The
event-capture RTL and its testbench produce binary input in simulation. No board measurement or
instrument acceptance has been performed; a simulation report has `evidence_status:
simulation_only` and cannot be cited as a PolarFire SoC result.

```bash
.venv/bin/python tools/analyze_run.py path/to/manifest.json --output-dir path/to/new-report
```

The Python distribution is named `loop-timing-witness` and requires Python 3.13 or later.
Its installed command runs the same analysis implementation:

```bash
loop-timing-witness-analyze path/to/manifest.json --output-dir path/to/new-report
```

The public Python API loads and verifies the manifest before calculating a report:

```python
from pathlib import Path

from loop_timing_witness import build_report, load_run

inputs = load_run(Path("path/to/manifest.json"))
report, cycle_rows = build_report(inputs)
```

The wheel includes the analysis dependency closure, JSON contracts and `py.typed` marker.
It does not require a source checkout to analyse a retained capture. Schemas shipped inside the
package are checked against the repository contracts; each run still supplies its own hash-bound
measurement-domain snapshot. Firmware preparation, capture execution and vendor-tool projects
remain repository build surfaces. Local distribution verification does not establish publication
on PyPI or qualify a board instrument.

The output directory must not exist. The tool validates the JSON and every referenced SHA-256,
decodes the binary events, analyses the series, writes all outputs to a sibling temporary
directory and renames it into place only after every write succeeds. An invalid run can still
produce a report: `valid: false` and `invalid_reasons` retain the reason. Malformed inputs fail
without a report. The source and hardware artefacts are checked as files, not accepted merely as
hash strings. The tool accepts relative paths within the run directory only.

## Inputs

[`run-manifest.schema.json`](../run-manifest.schema.json) is the Draft 2020-12 schema for
`loop-timing-witness.run-manifest.v1`. The manifest declares the UTC start, source kind and tool,
profile, placement, controller coefficients, plant and fixed-point format, sample period, run
length and warm-up, load case, fault schedule, file paths and SHA-256 values, instrument state and
operator notes. It includes a hash-bound copy of `measurement-domain.json` in the run directory;
the host interprets event codes, rails and interval definitions from that verified copy. A board
declaration additionally requires the hashed bitstream, firmware, Linux image and controller
binary files, complete tracking and power files, an instrument floor, four
acceptance flags, room temperature and board-only supply. Those declarations cannot substitute
for actual board acceptance records; independent board qualification remains a separate gate.
A report from such a declaration is labelled `board_declaration_unverified` until external
qualification verifies the board evidence.

The 16-byte event record is little-endian: `event_type` u8, zero reserved byte u8, zero reserved
word u16, `cycle` u32 and `timebase_ticks` u64. The repository
[`measurement-domain.json`](../measurement-domain.json) defines the current event codes and
intervals; each run keeps its own verified snapshot. The decoder refuses partial records,
nonzero reserved fields, unknown or wrong-profile codes, events outside the declared
cycle range, non-monotonic cycle or tick order, and duplicate event kinds in one cycle. Its
capture-module source and Icarus simulation testbench are under [`rtl/`](../rtl/) and
[`tests/rtl/`](../tests/rtl/).

The optional tracking CSV has the exact header `cycle,reference,output` and one finite decimal
observation per analysed control cycle. `reference` and `output` have the unit named by
`plant.tracking_unit`. The optional power CSV has the exact header
`timebase_ticks,rail,voltage_v,current_a,energy_j`; energy is a cumulative joule counter, and all
four rails from the measurement-domain contract must occur at each fabric tick. Voltage, current
and energy are finite and nonnegative. The run manifest may declare either auxiliary file as
`null` for an incomplete simulation run. A board run requires both files. Missing data remains
`unavailable` in the report; it is never substituted.

## Native simulation capture

```bash
.venv/bin/python tools/capture_native_simulation.py configuration.txt \
  --output-dir path/to/new-native-run --thermal 0
```

The command freezes the Makefile, controller C sources, native runtime and production RTL,
then compiles and executes that snapshot. The complete configuration format is documented in
[`PLANT_WITNESS.md`](PLANT_WITNESS.md). `--thermal 1` compiles the thermal plant; zero selects
the mechanical plant. Each run retains the executable, compiler versions, build and native logs,
original binary events, raw controller trace and
[`native-run.schema.json`](../native-run.schema.json) metadata. The metadata records the actual
controller coefficients, reference, full fault duration, overload work and completion counters.
The producer checks event count, missed deadlines and run length against the decoded capture.
Failed runs retain their artifacts; an existing output directory is refused.
The Python `capture_simulation` API also rejects plant modes outside zero/one and FIFO
address widths outside one/fourteen before allocating a run. A native failure remains a
failure even if event, trace and metadata files were completed; only the documented FIFO
overflow exit produces an invalid report with retained observations.

Native runs declare `tracking_sampling: observed`. Their tracking rows correspond exactly to
captured `SAMPLE_READ` cycles, including the warm-up prefix. Dropped reads are never filled.
The analyzer reports observed sample count, expected cycle count, missing cycles and coverage
fraction. Partial coverage remains invalid for a complete run; its RMS and peak describe only
observed cycles and may be biased by missing samples. A header-only series is accepted only
when the capture has no sample reads, and produces no error metric. Omitting `tracking_sampling`
or declaring `complete` retains the original requirement for every analyzed cycle.

These runs remain `simulation_only` and contain no power series or hardware acceptance claims.
The command forwards optional native `--cpu N`, `--scheduler normal|fifo` and
`--priority N`. The hash-bound metadata records the actual startup policy and allowed
CPU mask; see [native scheduling](PLANT_WITNESS.md#native-linux-scheduling).
Host controller calculation does not advance model time; explicitly configured modeled overload
advances it separately. They establish native/RTL integration, not physical processor latency.

### Linux host load profiles

```bash
.venv/bin/python tools/capture_native_simulation.py configuration.txt \
  --output-dir path/to/new-loaded-run --thermal 0 \
  --load-profile memory --load-cpu 2 --load-working-set-bytes 1048576
```

Select a CPU from the launching process's actual allowed affinity. `--load-profile` and
`--load-cpu` must occur together. Worker CPU selection is independent of the native
`--cpu` option: select the same CPU for shared CPU contention, or separate allowed CPUs
for those requested placements. No automatic native CPU isolation is applied. The five profiles are `idle`, `cpu`, `memory`, `network`
and `storage`; without these options capture creates no extra worker. Buffers and working
files are bounded between 4096 and 16777216 bytes; loopback UDP datagrams are limited to
60000 bytes. CPU arithmetic and idle do not allocate the requested buffer. The worker uses
`SCHED_OTHER`, priority zero and the explicit CPU, and records kernel policy readback.
It reports readiness after one completed workload chunk, runs while the native process
executes, and is stopped and reaped before capture completes. It does not change the
launching process's scheduling or affinity.

Memory work reads and modifies one byte per 64-byte stride. Network work sends and verifies
private loopback UDP datagrams; it is not NIC traffic. Storage work writes, fsyncs and reads
back an exclusive bounded working file; this does not establish uncached block-device load.
The owned file and worker log remain in `host_load_workspace/`. Resource and native failures
retain their artifacts and remain failures. The standalone
[`linux_load.py`](../tools/linux_load.py) CLI can wrap an explicitly selected absolute native
executable with the same profiles, exclusive `--journal` and `--workspace` paths and a
bounded `--timeout`.

The launcher owns both control and readiness pipes through
[`worker_channels`](../tools/linux_load_channels.py). It closes its child-end copies after
process creation and the control writer when stopping the worker, so EOF does not depend on
garbage collection. Process groups are stopped and reaped before remaining pipe resources
are released. An already released descriptor is never closed again after its number is reused.

Readiness must be a complete UTF-8 JSON line within ten seconds and at most 4096 bytes including
its newline. The reader uses one deadline across all pipe chunks, requires Boolean `true`
and a positive integer PID, and verifies that PID against the owned worker. Partial lines,
early EOF, oversized frames, repeated JSON member names and numeric substitutes for these
fields are refused before native execution. The completed worker receipt uses the same strict
JSON decoder, including repeated-member refusal inside nested counter objects.

Loaded captures freeze the host load implementation, including the worker, configuration,
launcher, readiness reader, pipe ownership, process cleanup and shared strict JSON decoder
sources. The manifest binds `host_load.json`, the worker receipt/log and optional storage data by SHA-256. The
receipt follows [`host-load.schema.json`](../host-load.schema.json), preserves actual
native return code and PIDs, policy, operation totals and monotonic time brackets. The
analyzer rejects inconsistent counters, resource scopes, CPU binding, run profile and
native completion status. It copies the validated receipt to `report.host_load` and retains
its digest. Counters cover the entire worker span, including work before and after the
enclosed native interval. They do not establish uninterrupted activity or operation totals
restricted to that interval. Host monotonic timestamps are not fabric event timestamps;
fixed simulation clocks still establish no physical processor timing or power result.

The Python capture API accepts `CaptureOptions(fifo_address_bits=8, host_load=...)` for
build capacity and optional `LoadConfiguration`. Invalid options are rejected before output
allocation. The C/Rust/RTL controller arithmetic is unchanged; this workload lifecycle is
implemented by the host Python tools.

### Native completion and FIFO loss

Native captures declare an optional hash-bound `native_metadata` file in the run manifest.
The analyzer validates its schema, source kind, controller coefficients, plant, cycle count
and sample period against the run. `native_completion` preserves the program's final live
sample/record/miss/overflow/safe counters. Recorded event count and overflow must always agree
with the receipt. With zero overflow, full-run deadline count, misses, sample reads and safe state must
agree too. This check includes the warm-up prefix even when reported metrics exclude it. Existing
manifests without a native receipt retain their original analysis path.

With declared overflow, captured-event misses can differ from live misses: losing `ACT_WRITE`
can make an on-time command appear absent, and losing `DEADLINE` removes its observation.
The report retains both values, states this inference limit and remains invalid. The receipt
does not fill events or establish missing intervals. Malformed events, missing observed read
records, or a lost declared fault anchor can still prevent report construction; the original
artifacts remain available for diagnosis.

```bash
.venv/bin/python tools/capture_native_simulation.py configuration.txt \
  --output-dir path/to/new-overflow-run --fifo-address-bits 1
```

`--fifo-address-bits` selects the actual compiled FIFO capacity, from 2 to 16384 records;
the default is 256. The source-bound `build_parameters.json` and build log retain the selected
capacity, group queue, period and plant. The copied measurement-domain file retains the
repository architecture contract; these experimental compile parameters describe the simulated
instance. A confirmed overflow returns failure while retaining its manifest and invalid report
when the surviving records can be analyzed. A failed native run without a valid completion
receipt is not converted into a successful capture. No buffer experiment qualifies board
acceptance or advances an instrument acceptance flag.

## Calculations

Same-cycle event intervals are differences of captured fabric ticks. For `CONTROL`, a deadline
is missed when no `ACT_WRITE` precedes that cycle's `DEADLINE`; a write at the deadline is late.
Fault-detection latency is `FAULT_DETECTED − FAULT_INJECTED`. Time to safe state is measured from
the first consecutive missed deadline to `SAFE_STATE`. A fault schedule must match the captured
injection cycles. The event file is invalid for a complete run if a cycle anchor is absent or
the FIFO overflow count is nonzero.

For every interval the tool reports the sample count, observation duration in ticks, median,
p95, p99, p99.9 and maximum. Percentiles use linear interpolation at position `(n − 1) × p` in
the sorted samples. Control error is the RMS and peak absolute value of `reference − output`
after warm-up. Power uses differences of the four cumulative rail counters between consecutive
fabric-tick samples. It divides the sum by the count of cycle anchors in those windows, reporting
mean joules per cycle per rail and total, plus window and cycle counts. It makes no instantaneous
per-cycle energy claim. A power series that does not cover every analysed cycle is refused. When
warm-up cycles are discarded, the first contributing power window must start at or after the
first analysed cycle; a window spanning warm-up and analysed cycles is refused.

Every report carries the run's source kind, input hashes, timebase resolution, instrument floor,
sample counts, observation duration and stated limits. The current `valid` flag means the input
series are complete and have no declared overflow; `simulation_only` remains simulation even when
`valid` is true. Physical instrument acceptance and public measured claims require the separate
hardware gates in [`MEASUREMENT_PROTOCOL.md`](MEASUREMENT_PROTOCOL.md).

## Outputs

| File | Content |
|---|---|
| `report.json` | Canonical JSON summary with evidence status, validity, metrics and limits |
| `interval_summary.csv` | One row per interval with count, distribution and duration |
| `cycle_intervals.csv` | Individual same-cycle intervals for audit and independent recalculation |
| `interval_p99.svg` | Labelled p99 comparison of available event intervals |
| `energy_per_cycle.svg` | Rail comparison when a complete power series exists |

Each CSV row and SVG title carries the evidence status, so a detached simulation artefact retains
its provenance. The SVG charts are visual summaries. The JSON and CSV carry numeric results.

## Linux native and RV64 builds

`make uio-transport run-uio` uses host GCC/G++ and writes to `build/` by default.
The separate [Linux AMP collector](AMP_LINUX.md) is built with `make run-amp-uio`.
These targets accept `LINUX_CC`, `LINUX_CXX`, `LINUX_CPPFLAGS`, `LINUX_LDFLAGS` and
`LINUX_BUILD_DIRECTORY`. The run target compiles its controller C object in that same
directory, so a target build can keep its objects separate from native simulation artifacts.
Strict compiler warnings remain enabled for either placement.

For an RV64 Linux toolchain and its genuine target sysroot:

```bash
make uio-transport run-uio \
  LINUX_CC=/path/to/toolchain/bin/riscv64-linux-gnu-gcc \
  LINUX_CXX=/path/to/toolchain/bin/riscv64-linux-gnu-g++ \
  LINUX_CPPFLAGS="--sysroot=/path/to/target-sysroot" \
  LINUX_LDFLAGS="-L/path/to/target-sysroot/usr/lib/riscv64-linux-gnu" \
  LINUX_BUILD_DIRECTORY=build/rv64-linux
```

Supply target OpenSSL headers and `libcrypto`, including the architecture-specific generated
OpenSSL headers, in the selected sysroot. SDK layouts may require extra target include paths
in `LINUX_CPPFLAGS`. A relocated compiler may also require its own host tool libraries in its
execution environment; these are separate from the target libraries passed to the linker.
Check the resulting ELF machine, ABI, loader and dynamic dependencies with the target
`readelf`. Cross compilation establishes a target build, not execution on the board or
compatibility with an unverified board image. The board's actual libc, loader and OpenSSL
versions must be checked before deployment.

## Native PAC1934 acquisition journal

Build with `make run-uio`. The native UIO command accepts
`--power-config /path/to/power.conf --power-journal /path/to/power-journal.csv`
together, plus required `--metadata /path/to/native_metadata.json` and an explicit `--cpu` for the controller. The worker CPU must be a different CPU
within the process's original allowed affinity. The worker sets and reads back `SCHED_OTHER`
and its single CPU before collecting. Simulation rejects these physical acquisition options.

The whitespace configuration contains:

```text
pac1934-iio-mchp-v1 iio:deviceN exact_kernel_release
period_ns maximum_read_ns worker_cpu sample_rate
VDD channel shunt_microohms label_prefix
VDD25 channel shunt_microohms label_prefix
VDDA25 channel shunt_microohms label_prefix
VDDA channel shunt_microohms label_prefix
```

Replace every symbolic field with the actual board configuration. No board, shunt, rail label,
or kernel defaults are inferred. Channels 1–4 form a permutation; sample rate is 8, 64, 256 or
1024 samples/s. Polling period is 50 ms–60 s and the positive maximum frame read span cannot
exceed that period. Labels, exact `in_shunt_resistor1`–`in_shunt_resistor4` values and kernel identity are
verified against actual read-only sysfs;
accumulators must already be enabled. The logger does not configure or reset the monitor.

The selected [Microchip driver source](https://raw.githubusercontent.com/linux4microchip/linux/linux-6.18-mchp/drivers/iio/adc/pac1934.c)
exports unsigned voltage/current raw words and accumulated energy already scaled by sample
rate. Its fractional scales use nine-decimal truncation. Raw × scale yields millivolts,
milliamperes and millijoules respectively; energy must not be divided by sample rate again.
Bipolar scale configurations are refused by this unsigned acquisition contract. The exact
kernel release and these attribute semantics must be checked against the installed BSP.

Each CSV row records snapshot, rail, channel, quantity, raw/scale attribute, host nanoseconds
before/after, fabric ticks before/after, observed worker policy, configured kernel release, rail label,
shunt, sample rate and exact attribute text. Frames
are collected before START, periodically while the controller runs, and after final drain.
A frame comprises separate reads and includes identity/configuration checks before and after.
Reset/decreasing or saturated energy, changed calibration, clock reversal, excessive read span,
missed polling schedule and output failures stop the run with partial files retained. Output
paths are exclusive. Worker shutdown joins before UIO/IIO resources are released; kernel I²C
read timeouts determine the actual shutdown bound.

The driver's 50 ms cache and sequential reads prevent an atomic four-rail timing claim. This
journal is not directly accepted as a qualified analyzer power file. Physical calibration,
read/cache timing, rail mapping and interval alignment require the board. The implemented
public refusal paths and builds can be checked here; actual successful acquisition remains
unverified because no board or monitor is available.

## Native artifact receipts

Both native run executables link OpenSSL 3 `libcrypto` (development headers are required to
build). Native metadata records `crypto_library` with SHA-256 algorithm, compile-time header
version number and `OpenSSL_version_num()` from the actually loaded library; these may differ
after a shared-library update. Native controller kernels remain dependency-free; the Linux/simulation run adapter
uses the EVP SHA-256 interface for capture provenance. OpenSSL 3 is dynamically linked under
[Apache-2.0](https://raw.githubusercontent.com/openssl/openssl/openssl-3.0/LICENSE.txt); its source
is not vendored into the controller kernels. The installed host reports OpenSSL
3.0.13; this records the local library version, not a target BSP qualification.

With `--metadata`, the native receipt contains SHA-256 and exact byte counts for configuration,
events and raw tracking, plus power configuration and the completed raw journal when acquisition
is enabled. Configuration bytes are checked before/after parsing and after execution. Hashes of
closed outputs are calculated after final drain, outside the controller service loop. Files must
be stable regular files; symlinks, nonregular paths and detected replacement/modification during
hashing are refused. Failures preserve partial capture files.

If configuration bytes change during execution, the completed event and raw tracking files
remain available, but the command fails before publishing native metadata or a success summary.
The retained files alone are not a verified capture. Real simulation tests synchronize on Linux
output-creation notifications, confirm their own child is stopped, modify the actual configuration,
and resume it. They cover overwrite, inode replacement, appended whitespace and symlink
substitution for both plants; they do not substitute a hash implementation or filesystem stream.
Separate initial-hash tests observe actual Linux read notifications, stop their own child and
verify its open configuration descriptor has read some but not all bytes. Append, truncation,
path replacement and unlink then exercise refusal before any capture outputs are created.
A Linux read-error case uses `/proc/self/mem` at offset zero: the kernel returns `EIO` for the
process's own unmapped address. The native command reports the read failure before creating
outputs. This is an actual kernel error test; no memory bytes are printed or used as capture data.

The simulation importer compares native event/raw receipts against actual bytes before constructing
a manifest; raw conversion interprets the verified bytes. The configuration receipt must match a
captured source artifact. Analyzer completion validation also checks the event receipt against the
manifest and decoded byte count. A matching receipt does not establish physical power timing or
board acceptance. Metadata without artifact receipts comes from an earlier development draft and
must be regenerated before import under this schema.

Native raw conversion validates all 13 ABI columns: cycle, six signed 32-bit Q8.24 values,
three boolean flags and three unsigned 64-bit timing/work counters. Fields must be nonempty
ASCII decimal integers within their bounds. Observed cycles must be unique and increasing;
gaps remain valid observations. Header, row completeness and native sample count are checked
before writing any converted tracking file. Hash agreement does not replace these semantic checks.

Malformed CSV is reported as a validation error. Conversion uses an isolated Decimal context
with enough precision for every signed 32-bit Q8.24 value; caller precision/trap settings cannot
round an observation. Exact converted values are checked against independent rational arithmetic.

The power journal uses the same exclusive stream owner as native event and tracking outputs.
Its constructor flushes the header before starting acquisition, and its controller-thread
lifecycle refuses another start after stop or close, finish before start, and another finish after close. Worker join
precedes stream destruction. Shared stream ownership is exercised with actual RTL capture and
real files; positive PAC1934 worker lifecycle verification still requires the physical device.

Both the configuration parser and public C++ run API validate cycles, period, coefficients,
reference/phase bounds, fault schedule and overload bounds, and the nanosecond duration limit.
`configure_run` performs this validation before its first device access, so an invalid public
structure cannot reset an earlier completed run or erase its retained register state. Actual
RTL API tests retain a completed capture and register/IRQ-generation snapshot, reject each
invalid configuration, verify the snapshot is unchanged, then complete another healthy run.

The public C++ scheduling API shares option validation with the CLI parser. Invalid CPU,
scheduler or priority sentinels and incomplete FIFO/power requests are refused before reading
or changing policy. Real child-process API tests start in Linux `SCHED_BATCH`, prove refusal
preserves scheduler, priority, nice value and affinity, and exercise inherited-policy retention
and explicit normal-policy pinning. These host policy observations do not qualify real-time latency.

The public metadata writer also validates configuration before creating its exclusive file.
Malformed cycle counts or fault enums are refused before output creation and fault-name lookup.
Actual completed-run API tests prove refusal leaves the metadata path available, then write the
original completion receipt with SHA-256 and byte counts of the retained configuration, events
and raw tracking. These receipts are checked against the native metadata schema.

Power acquisition shares semantic validation between its file parser and public C++ structures.
The PAC1934 constructor validates identity syntax, polling bounds, CPU, supported sample rates,
rail order, distinct channels, positive bounded shunts and journal-safe labels before inspecting
the kernel or selecting an IIO node. The journal validates the supplied structure before creating
its exclusive output. Actual constructor refusal tests submit malformed structures without
inventing sysfs devices; positive acquisition and worker lifecycle still require a physical board.
Public raw/scale reads require the supplied rail to match the constructor's verified mapping,
including channel, label and shunt. A different caller-supplied rail is refused before attribute
access or scale arithmetic; that physical-object boundary remains unexercised without the device.
