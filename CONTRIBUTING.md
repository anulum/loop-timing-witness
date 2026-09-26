<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — contributing
-->

# Contributing

Contributions are coordinated directly with the owner at protoscience@anulum.li; the process
below applies to every change, including the owner's.

## Ground rules

1. **Truthful evidence state.** `measurement-domain.json` declares the evidence maturity and is the
   only place it is written. No capability, claim, measured number or hardware statement enters
   the repository without the measured run, manifest and hashes it requires.
2. **Boundary.** Work stays inside [`docs/adr/0001-repository-boundary.md`](docs/adr/0001-repository-boundary.md):
   no accelerator-library code or adapters, no controllers or plant models from other projects, no
   vendor tools or licensed IP.
3. **Contracts change together.** A change to a measurement contract updates the manifest, the
   schema, the validator, the measurement protocol and the architecture document in the same
   change.
4. **Complete units.** Code arrives complete, strictly typed, documented with NumPy-style
   docstrings and tested through its real entry points, with 100 % statement and branch coverage
   of new or changed code. No placeholder interfaces, skipped tests or suppression comments.
5. **Supply chain.** A new or changed development dependency means regenerating the hashed lock
   with the recorded command and adding a reviewed licence record. Workflow actions and hook
   repositories are pinned to commit objects verified at their source.
6. **Provenance and licensing.** Every file carries the seven-line provenance header in its native
   comment syntax (inside an HTML comment in Markdown); JSON files are annotated in `REUSE.toml`.
7. **Language.** British English, descriptive names, no self-applied quality labels, no internal
   planning codes.

## Workflow

```bash
make venv       # hashed development environment
make hooks      # pre-commit, commit-message and pre-push hooks
make preflight  # every gate in VALIDATION.md
```

Commits are atomic, staged by explicit path and described in the conventional
`type(scope): summary` form. History on `main` is never rewritten.

## Security-relevant changes

Changes to the threat model, the workflow permissions, the dependency lock or the safe-state
design follow [`SECURITY.md`](SECURITY.md) and need owner review.
