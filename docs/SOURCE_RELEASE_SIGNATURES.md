<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Commercial license available
© Concepts 1996–2026 Miroslav Šotek. All rights reserved.
© Code 2020–2026 Miroslav Šotek. All rights reserved.
ORCID: 0009-0009-3560-0851
Contact: www.anulum.li | protoscience@anulum.li
Loop Timing Witness — portable source release signature verification
-->

# Source release signatures

The manually dispatched `source-release-signatures.yml` workflow verifies and
signs the two published GitHub source assets of one release:
`loop-timing-witness-<version>.zip` and `release-provenance.json`. Its required
`release` input is a choice. The options must equal the frozen registry
`RELEASES` in `tools/source_release.py`; the workflow auditor refuses any other
trigger or option list.

| Release | Source commit | Source ZIP SHA-256 | `release-provenance.json` SHA-256 |
|---|---|---|---|
| 0.1.0 | `1d12e0342d5320f62182fef41709773f3c555b50` | `3e0c83e09be127ef3fc30c0043c377f20dcfed3df58e70a49e9ebebdd6f7880e` | `adf3bf9db02b2495f5865db54e931151f28495f6b94e1fdb0c469d421740006d` |
| 0.2.0 | `1ced8822a947a2dd7a5d5e9376187b0fa36620f6` | `40acb25fc2777b81a00e8b2b985359ce62a962f1966577067d1d8040ebe35ea8` | `24884ee3278864032d97854e1f8bdc77d4edceb8a98c4408e8e534553c6e83bb` |

The tag `v<version>` must name the registered source commit. The workflow
reconstructs the ZIP from that commit with `git archive` and requires
byte-identical SHA-256 digests for the reconstruction and both downloaded
assets. A moved tag, damaged asset, unregistered release or unqualified
workflow revision refuses signing.

The published ZIPs were created with `TZ=Europe/Zurich`. Git stores local DOS
timestamps in ZIP entries, so reconstruction must declare the same timezone:

```bash
RELEASE=0.2.0
SOURCE=1ced8822a947a2dd7a5d5e9376187b0fa36620f6
TZ=Europe/Zurich git archive --format=zip --prefix="loop-timing-witness-${RELEASE}/" \
  "$SOURCE" --output=reconstructed.zip
sha256sum reconstructed.zip
```

A UTC reconstruction has identical member contents but different ZIP timestamp
bytes; verification rejects it. Both the signing workflow and test fixture
set the release timezone explicitly instead of inheriting the host's timezone.

Verification runs with read permissions. A separate job obtains a short-lived
Sigstore certificate using GitHub OIDC and signs an in-toto statement covering
both asset digests. This job can publish attestations but cannot change release
assets. The final job verifies the certificate, signature, transparency-log
proof, both subject digests, predicate type and exact workflow identity before
attaching `source-v<version>.sigstore.json` to that release. It has no OIDC
signing permission. The `source-signatures` environment admits only `main`; all
seven source validation workflows must have succeeded at the exact workflow
revision.

The custom predicate records the tag and `artifact_source_commit` separately
from `verification_workflow_commit`. This is an authenticated verification of
existing source assets, not retrospective SLSA build provenance. The original
ZIP, manifest, tag, Zenodo files and registry packages remain unchanged. A
repeat dispatch refuses overwriting an existing signature attachment.

## Verify downloaded assets

Use a current GitHub CLI with `gh attestation verify` support:

```bash
RELEASE=0.2.0
gh release download "v${RELEASE}" --repo anulum/loop-timing-witness \
  --pattern "loop-timing-witness-${RELEASE}.zip" --pattern release-provenance.json \
  --pattern "source-v${RELEASE}.sigstore.json"

for asset in "loop-timing-witness-${RELEASE}.zip" release-provenance.json; do
  gh attestation verify "$asset" --repo anulum/loop-timing-witness \
    --bundle "source-v${RELEASE}.sigstore.json" \
    --predicate-type https://github.com/anulum/loop-timing-witness/source-release-verification/v1 \
    --signer-workflow anulum/loop-timing-witness/.github/workflows/source-release-signatures.yml \
    --source-ref refs/heads/main --deny-self-hosted-runners --format json
done
```

Check the verified statement's predicate: `tag` must be `v<version>`,
`artifact_source_commit` must be that release's source commit from the table,
and `verification_workflow_commit` must identify the reviewed signing workflow
revision. For a pinned review, also supply `--source-digest` with that workflow
revision. The certificate's source digest names the signing workflow's commit,
not the older source archive's commit. Never accept an arbitrary workflow or
repository merely because its certificate is valid.

The bundle can also verify identical files downloaded from Zenodo; the
signature sidecar is distributed through GitHub. A modified file, unrelated
signer or wrong predicate fails verification. A signature establishes artifact
integrity and issuer identity; physical timing qualification remains governed
by the measurement domain and its evidence.

## Release record notes

The 0.2.0 `release-provenance.json` records `source_archive.bytes` as the
decimal string `"4202006"`; the 0.1.0 record uses a JSON integer. The value is
correct, and the hash-bound record is not rewritten. Read the size as an
integer from either form.

## Building the release assets

`tools/release_provenance.py` makes both assets from the tagged commit. A
release specification (schema
`loop-timing-witness.source-release-specification.v1`) holds the members a
person declares: the version, the version DOI, the boundary text, the
physical evidence maturity, the unqualified items, the registry artifacts and
the software verification. `collect` fills the PyPI distributions of the
version, the listed crate publications and the hosted workflow runs of the
commit from the public APIs. A source release that builds no distribution lists
the earlier registry artifacts it keeps, complete and with their `registry`
member; `collect` keeps them unchanged and does not read PyPI for the version.
`collect` refuses while any hosted run of the commit is unfinished:

```sh
python tools/release_provenance.py collect --commit <commit> \
  --specification release-specification.json --output release-specification.json
python tools/release_provenance.py build --commit <commit> \
  --specification release-specification.json --output <asset directory>
```

`build` is offline. It writes `loop-timing-witness-<version>.zip` with
`git archive` in the Europe/Zurich time zone, and `release-provenance.json`
with the archive's size, SHA-256 and MD5 and the SHA-256 of every file of the
commit's tree computed, not declared. The tests rebuild both published records
and ZIPs from their commits; the 0.1.0 record is rebuilt byte for byte.

## Subsequent versions

Each release is registered separately after its publication: its source
commit and both published asset digests in `RELEASES`, its byte-exact
`release-provenance.json` as `tests/data/source-release-v<version>-provenance.json`
with REUSE annotation and attribution sidecar, the exact public digest lines
that the secret scanner recognises for that file, and the new workflow option.
The change passes complete validation before the dispatch. Registered entries
are never edited, and a source signature never infers a package publisher's
identity.
