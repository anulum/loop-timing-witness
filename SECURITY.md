<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — security policy
-->

# Security policy

## Supported states

| State | Supported |
|---|---|
| `main` at its current commit | yes — the only supported state |
| Released versions | none exist |

The measurement-domain maturity remains `architecture_only`. Executable surfaces include
validation and host analysis tools, C/Rust/RTL controllers, the simulated plants and event
witness, the native Linux controller, UIO/IIO adapters, owned host workload processes and
workflow definitions. Linux adapters contain hardware access code, but successful MMIO, IRQ
handling and power acquisition remain unverified without a board. There is no qualified board
instrument or measured platform result. The workload's UDP traffic uses a private loopback
socket; no remotely accessible service is provided.

## Reporting a vulnerability

Write privately to **protoscience@anulum.li** with the subject `[SECURITY] Loop Timing Witness`.
Do not open a public report. Include the affected file and commit, a reproduction and the impact
you observe. You receive an acknowledgement, and disclosure is agreed with you before any public
statement. Good-faith research within the scope below is welcome.

## Scope

In scope:

- the validation and host analysis tooling and its handling of manifests, hash-bound event and
  series files, inventories, workflow definitions, lock files and repository files;
- controller configuration and run lifecycle, source snapshots, native metadata, tracking
  conversion and completion receipts;
- UIO/IIO identity checks, exclusive output and the power journal's resource ownership;
- workload configuration, bounded readiness, completed receipts, owned process and pipe cleanup;
- the workflow definitions, including permissions, triggers and action pinning;
- the development dependency lock and licence record;
- any way the repository could state more than its evidence supports, for example a path that lets
  the capability inventory report a capability the manifest does not hold.

Out of scope: unavailable board measurement results, third-party services, vendor tools and
kernel drivers maintained by their suppliers. Adapter code in this repository remains in scope
even though its successful hardware paths are unqualified.

## Controls in place

- Every JSON reader rejects repeated member names; workflow YAML is parsed with repeated-key
  rejection; unknown schema identifiers fail.
- The host tool checks every referenced source, input and hardware artefact digest before
  reporting; run file paths stay inside the run directory. An RTL simulation report is labelled
  `simulation_only` even when its data files are internally valid.
- Worker readiness uses one bounded deadline, a 4096-byte UTF-8 frame, strict JSON member
  uniqueness, exact field types and an owned PID check before native execution. Completed
  receipts also reject repeated members and must enclose the actual native interval.
- Workloads have explicit CPU/resource/lifetime bounds; the launcher stops and reaps its owned
  process groups and closes each owned descriptor once. These controls provide resource
  ownership, not a sandbox for untrusted operator-selected executables.
- Native outputs use exclusive creation. Device access checks the actual kernel UIO/IIO
  identities; actual missing-device refusals and source-bound simulation exercise the software
  path. Positive hardware behaviour is not inferred from those checks.
- Development dependencies are pinned with hashes and installed with `--require-hashes`; every
  pinned package has a reviewed licence record.
- Workflows have empty top-level permissions, per-job least privilege, commit-pinned actions,
  no persisted checkout credentials, bounded timeouts and no privileged triggers.
- Secret scanning runs on the publishable files locally and on the complete history in the
  security-audit workflow; a private-key hook runs before each commit.
- The threat model, including the controls planned for the instrument, is in
  [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Non-claims

This policy is not a certification. The repository has had no external security review, no
fuzzing campaign and no reported vulnerability. The simulated safe-state logic is a measurement
feature for an emulated plant and is not a safety function for physical machinery.
