<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — governance
-->

# Governance

## Ownership and decision authority

The project is owned and maintained by Miroslav Šotek (ANULUM, Marbach SG, Switzerland; ORCID
0009-0009-3560-0851). Final authority over scope, contracts, licensing, publication, releases and
every action outside this repository rests with the owner.

The repository belongs to the SC Neuromorphic Computing Systems portfolio group, which coordinates
its boundary with the other repositories of the group, in particular SC-NeuroCore.

## Boundary control

The boundary is fixed in [`docs/adr/0001-repository-boundary.md`](docs/adr/0001-repository-boundary.md).
Changing it requires a new decision record approved by the owner, and any effect on a neighbouring
repository is agreed with that repository before this one adopts it.

## Change process

1. A change lands on `main` only after every gate in [`VALIDATION.md`](VALIDATION.md) passes and the
   complete staged diff has been reviewed.
2. Evidence maturity advances only when a measured run exists with its manifest and hashes and the
   instrument acceptance tests of the measurement protocol have passed on the same bitstream.
3. Versioned contracts (manifest schema, inventory schema, run manifest format, device-under-test
   slot interface) change only through a new schema identifier or a compatible revision, recorded
   in a decision record; never silently.
4. Creating a remote, publishing, releasing, registering with external services and adding badges
   each require separate owner approval.

## Roles

| Role | Holder | Authority |
|---|---|---|
| Owner and maintainer | Miroslav Šotek | all decisions and all actions outside the repository |
| Portfolio group | SC Neuromorphic Computing Systems | boundary coordination with neighbouring repositories |
| Reviewers | per `.github/CODEOWNERS` | review of changes inside the boundary |
