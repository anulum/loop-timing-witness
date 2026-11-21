<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — ADR 0002 source-bound neural analysis
-->

# ADR 0002 — Source-bound neural analysis in the host analysis

**Status:** proposed, 2026-11-21

**Decider:** project owner, Miroslav Šotek

## Context

Since 2026-10-30 the host analysis, in the Python package and in the Rust crate, verifies
`COMPUTE` records of one external consumer, the neural-step cohort
`sc-neurocore-neural-step-1n1b16t.v1`: it reads the closed carrier
`loop-timing-witness.neural-step-run.v1`, binds the original sources, compiled artefacts,
traces and receipts by digest, and runs the source owner's checker in child processes
([host analysis](../HOST_ANALYSIS.md#source-bound-neural-analysis)). The packaged registry
admits two source contracts of that cohort; they pin, next to the consumer's files, the copies
of three RTL files and two runtime headers of this repository that the acquisition used.

[ADR 0001](0001-repository-boundary.md) keeps consumer source code, generated peripherals,
models and adapters out of the repository and expects consumers to obtain measurements through
the `COMPUTE` profile. It does not say whether verifying one consumer's records belongs here. An
external review read the consumer-named data files as a breach of that boundary.

## Decision

1. The host analysis owns a source-bound verifier for `COMPUTE` records that does not depend on
   any one consumer: the carrier schema and its readers, the binding of sources, artefacts,
   traces and receipts by digest, the capture, clock, completion, numerical and source-binding
   findings, the report, and the isolated worker that runs a source owner's checker.
2. A consumer enters only as data in a reviewed registry entry: the schema digest, a cohort
   identifier, a source-contract digest, a checker policy and a runtime descriptor. An entry is
   added by a reviewed change to this repository, or passed by a caller that reviews its own
   entries; acquisition data never adds or selects one.
3. No consumer source code, generated peripheral, model, compiled artefact or adapter is
   committed. Committed neural files are schemas, policies, descriptors, run records and test
   fixtures of digests and counts. A checker's source comes from the run bundle and runs only
   after it matches the digests of an admitted entry.
4. The consumer installation descriptor and the executor image binding name host files. The
   operator selects them; the package pins their digests and does not ship them.
5. A neural result is simulation evidence of the cohort's timing and numerics. It establishes
   neither physical calibration nor acceptance of a model family.

## Alternatives considered

- **Move the verifier into the consumer's repository.** Not chosen: the verifier holds records
  to this instrument's event format, capture and clock rules and report, and the consumer's
  results would then be judged by the consumer's own copy of those rules.
- **Load consumer verification as a plugin or behind an optional feature.** Not chosen now: a
  second loading path would need its own controls, while the registry already confines which
  code runs, and both analyses expose the verifier in their public interfaces.

## Consequences

- A new cohort needs a reviewed registry change or a caller-reviewed registry; a structurally
  valid carrier, a copied policy or a private acquisition cannot add one.
- The [threat model](../THREAT_MODEL.md) treats the checker workers as a surface: admitted
  checker code is trusted code that runs with the analysis user's privileges.
- The repository's files pinned in an admitted contract are the copies the acquisition used. A
  later change to those files does not alter the admitted evidence; a new acquisition needs a new
  contract and registry entry.
