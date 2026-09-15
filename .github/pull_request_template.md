<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — pull request template
-->

## What and why

One paragraph: what changes and the reason for it.

## Boundary and evidence

- [ ] The change stays inside the repository boundary in `docs/adr/0001-repository-boundary.md`
      (no SC-NeuroCore code or models, no controllers or physics from other projects, no
      redistributed vendor tools or IP).
- [ ] No capability, claim, measured number or hardware statement is added without the
      measured run, manifest and hashes it requires.
- [ ] Measurement contracts changed only with the manifest, schema, protocol and validator in
      the same change.

## Gates

- [ ] `make preflight` passes (every gate in `VALIDATION.md`)
- [ ] New or changed executable code has 100 % statement and branch coverage
- [ ] Documentation changed in the same change where behaviour or contracts changed

## Notes for the reviewer

Decisions, rejected alternatives and anything else that is not obvious from the diff.
