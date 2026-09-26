<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — validation
-->

# Validation

Every gate that exists in this repository, with its exact scope. No board instrument exists, so no
board measurement is validated; these gates validate repository infrastructure, the internal
consistency of the measurement contracts, the RTL-simulation-to-host-analysis path and the
truthfulness of the `architecture_only` state.

## Environment

- Python 3.13 in `.venv`, created by `make venv` from `requirements-dev.txt`, which pins every
  development package with its hashes and is installed with `pip install --require-hashes`.
- Icarus Verilog 12.0 (`iverilog` and `vvp`), Ubuntu noble package `12.0-2build2`, to compile the
  synthesizable capture and buffered witness modules and produce binary event files consumed by
  the host CLI tests. The reusable test workflow installs that exact package through Ubuntu's signed APT
  repositories and prints both tool versions. A missing simulator fails the tests; simulation
  is not evidence of board acceptance.
- `actionlint` v1.7.12 and `gitleaks` v8.30.1 built with `go install` from their module sources; the
  preflight runner reads each binary's recorded module version and checksum with
  `go version -m` and refuses any other build.
- `typos` 1.50.1, installed from the same lock and checked by its reported version.

The lock is regenerated only with the command recorded in its header, followed by a licence review
of every new or changed package in `development-dependency-licences.json`.

## Local gates

`python tools/preflight.py` runs every gate below in order and fails if any gate fails or its tool
is missing; `--only NAME` runs one gate and `--list` prints the plan.

| Gate | Command | Scope |
|---|---|---|
| `ruff-check` | `ruff check .` | every Python file; all rule groups enabled, exclusions listed with reasons in `pyproject.toml` |
| `ruff-format` | `ruff format --check .` | every Python file |
| `mypy` | `mypy` | `tools/`, `tests/` and `conftest.py` in strict mode |
| `tests` | `pytest --cov --cov-branch --cov-report=term-missing --cov-fail-under=100` | every test; 100 % statement and branch coverage of `tools/`, including subprocess runs of the host CLI against event files produced by Icarus RTL simulation |
| `measurement-domain` | `python tools/validate_measurement_domain.py` | repeated-key rejection, JSON Schema, cross-field rules, and — where the canonical project registry is present — group and project identity |
| `capability-inventory` | `python tools/generate_capability_inventory.py --check` | committed inventory byte-identical to a fresh generation from a valid manifest |
| `provenance-headers` | `python tools/check_provenance_headers.py` | seven-line provenance header in every publishable file with a comment syntax; Markdown header inside an HTML comment with rendered content after it |
| `documentation` | `python tools/check_documentation.py` | every relative link and image in publishable Markdown reaches a publishable path; every fragment names a heading |
| `dependency-licences` | `python tools/check_dependency_licences.py` | lock pins and licence records match exactly; every licence expression parses and uses allowed identifiers |
| `workflows` | `python tools/audit_workflows.py` | workflow inventory, ownership taxonomy, permissions, triggers, concurrency, timeouts, action and image pinning, checkout credentials, coordinator gate |
| `reuse` | `reuse lint` | REUSE 3.x compliance of the whole tree |
| `zizmor` | `zizmor --offline --persona pedantic --strict-collection .` | workflow, Dependabot and pre-commit configuration security analysis; one audit disabled with its reason in `.github/zizmor.yml` |
| `actionlint` | `actionlint` | every workflow file |
| `typos` | `typos` | every file except the lock, the licence record and the licence texts |
| `secrets` | `gitleaks dir` on a copy of the publishable files | tracked and non-ignored untracked files |

Dependency vulnerabilities are checked with
`pip-audit --require-hashes --disable-pip -r requirements-dev.txt` (`make security`); it needs
network access to the vulnerability database and is therefore not part of the offline preflight.

## Fabric simulation and synthesis

Dedicated RTL tests are `tests/test_clock_reset_release.py`, `tests/test_event_record_fifo.py`
`tests/test_event_witness.py`, `tests/test_control_plant_witness.py` and
`tests/test_control_faults.py`. They compile the actual modules with Icarus and check public
ports with scoreboards, including the default 16,384-record capacity, clock ratios, queued-data
reset, wrap, overflow and saturation. Buffered binary drain output reaches the host report CLI.
The CI test workflow runs these with the same pinned simulator as the capture tests.

Local RTL review also runs Verilator 5.020 strict `--lint-only --Wall`, and Yosys 0.33 preparation,
memory inference checks and post-optimisation equivalence at a four-record configuration. The
plant integration additionally runs component optimization proofs with
`rtl/check_control_equivalence.ys`; monolithic technology-mapped system equivalence remains
unqualified. The
Yosys proof normalises asynchronous resets with `async2sync` before synthesis; it does not
qualify metastability, Gray-bus physical timing or a board bitstream. See
[`docs/FABRIC_WITNESS.md`](docs/FABRIC_WITNESS.md) for ports and remaining board gates. Python
coverage measures tools, not SystemVerilog; the simulations do not provide a numeric RTL
statement/branch coverage verdict.

## Hooks

`make hooks` installs the hooks in `.pre-commit-config.yaml`:

- before each commit: upstream checks for large files, case conflicts, executable bits, JSON,
  merge markers, TOML, YAML, private keys, final newlines, line endings and trailing whitespace;
  staged secret scan; REUSE; typographical check; and the local gates through
  `tools/preflight.py --only`;
- on the commit message: `tools/check_commit_trailers.py` (conventional subject, seat and
  authorship trailers, no other trailers, no generated-by attribution, no self-applied quality
  terms);
- before each push: the complete preflight.

Upstream hook repositories are pinned to verified commit objects.

## Workflow definitions

The definitions have run on a hosted platform. This table describes their intended checks, not a
current success verdict: a workflow that has not run on the exact assessed commit is no evidence.
Every action is pinned to a verified commit object.

| Workflow | Purpose | Category |
|---|---|---|
| `ci.yml` | coordinator: calls the two reusable workflows and holds the one required gate | coordinator and required gate |
| `reusable-static-policy.yml` | lint, format, typing, manifest, inventory, headers, licences, workflow policy | static analysis and policy |
| `reusable-tests.yml` | tests with 100 % statement and branch coverage | unit and component quality |
| `pre-commit.yml` | every pre-commit stage hook on all files | static analysis and policy |
| `codeql.yml` | code scanning of Python and of the workflow definitions | security and supply chain |
| `security-audit.yml` | secret scan of the full history, vulnerability audit, licence guard, REUSE, actionlint, zizmor | security and supply chain |
| `scorecard.yml` | OpenSSF Scorecard analysis; results are not published | security and supply chain |
| `sbom.yml` | CycloneDX inventory of the development lock, kept as a 30-day artefact | security and supply chain |
| `docs.yml` | documentation links, anchors and rendered headers; no deployment | documentation |

Ownership of every job and the omitted categories are declared in
`.github/workflow-inventory.json` and enforced by the `workflows` gate.
