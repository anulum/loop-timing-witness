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

The repository is `architecture_only`. Its executable surfaces are the validation and host
analysis tooling under `tools/`, a timestamp-record capture module exercised in RTL simulation,
and the workflow definitions under `.github/workflows/`. There is no network service, daemon,
complete fabric instrument, processor software or path to hardware.

## Reporting a vulnerability

Write privately to **protoscience@anulum.li** with the subject `[SECURITY] Loop Timing Witness`.
Do not open a public report. Include the affected file and commit, a reproduction and the impact
you observe. You receive an acknowledgement, and disclosure is agreed with you before any public
statement. Good-faith research within the scope below is welcome.

## Scope

In scope:

- the validation and host analysis tooling and its handling of manifests, hash-bound event and
  series files, inventories, workflow definitions, lock files and repository files;
- the workflow definitions, including permissions, triggers and action pinning;
- the development dependency lock and licence record;
- any way the repository could state more than its evidence supports, for example a path that lets
  the capability inventory report a capability the manifest does not hold.

Out of scope: board measurement results and the planned full instrument (neither exists yet),
third-party services, and the vendor tools the planned instrument will use.

## Controls in place

- Every JSON reader rejects repeated member names; workflow YAML is parsed with repeated-key
  rejection; unknown schema identifiers fail.
- The host tool checks every referenced source, input and hardware artefact digest before
  reporting; run file paths stay inside the run directory. An RTL simulation report is labelled
  `simulation_only` even when its data files are internally valid.
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
fuzzing campaign and no reported vulnerability. The planned safe-state logic is a measurement
feature for an emulated plant and is not a safety function for physical machinery.
