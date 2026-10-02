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
signs the two existing GitHub `v0.1.0` source assets. It reconstructs the ZIP
from source commit `1d12e0342d5320f62182fef41709773f3c555b50` using `git archive`
and requires byte-identical SHA-256 digests for the archive and the original
`release-provenance.json`. A different tag target, damaged asset or unqualified
workflow revision refuses signing.

The original ZIP was created with `TZ=Europe/Zurich`. Git stores local DOS
timestamps in ZIP entries, so reconstruction must declare the same timezone:

```bash
TZ=Europe/Zurich git archive --format=zip --prefix=loop-timing-witness-0.1.0/ \
  1d12e0342d5320f62182fef41709773f3c555b50 --output=reconstructed.zip
sha256sum reconstructed.zip
```

The expected digest is
`3e0c83e09be127ef3fc30c0043c377f20dcfed3df58e70a49e9ebebdd6f7880e`.
A UTC reconstruction has identical member contents but different ZIP timestamp
bytes; verification rejects it. Both the signing workflow and test fixture
set the release timezone explicitly instead of inheriting the host's timezone.

Verification runs with read permissions. A separate job obtains a short-lived
Sigstore certificate using GitHub OIDC and signs an in-toto statement covering
both asset digests. This job can publish attestations but cannot change release
assets. The final job verifies the certificate, signature, transparency-log
proof, both subject digests, predicate type and exact workflow identity before
attaching `source-v0.1.0.sigstore.json`. It has no OIDC signing permission.
The `source-signatures` environment admits only `main`; all seven source
validation workflows must have succeeded at the exact workflow revision.

The custom predicate records `artifact_source_commit` separately from
`verification_workflow_commit`. This is an authenticated verification of
existing source assets, not retrospective SLSA build provenance. The original
ZIP, manifest, tag, Zenodo files and registry packages remain unchanged. A
repeat dispatch refuses overwriting an existing signature attachment.

## Verify downloaded assets

Use a current GitHub CLI with `gh attestation verify` support:

```bash
gh release download v0.1.0 --repo anulum/loop-timing-witness \
  --pattern loop-timing-witness-0.1.0.zip --pattern release-provenance.json \
  --pattern source-v0.1.0.sigstore.json

for asset in loop-timing-witness-0.1.0.zip release-provenance.json; do
  gh attestation verify "$asset" --repo anulum/loop-timing-witness \
    --bundle source-v0.1.0.sigstore.json \
    --predicate-type https://github.com/anulum/loop-timing-witness/source-release-verification/v1 \
    --signer-workflow anulum/loop-timing-witness/.github/workflows/source-release-signatures.yml \
    --source-ref refs/heads/main --deny-self-hosted-runners --format json
done
```

Check the verified statement's predicate: `artifact_source_commit` must be
`1d12e0342d5320f62182fef41709773f3c555b50`, and
`verification_workflow_commit` must identify the reviewed signing workflow
revision. For a pinned review, also supply `--source-digest` with that workflow
revision. The certificate's source digest names the signing workflow's commit,
not the older source archive's commit. Never accept an arbitrary workflow or
repository merely because its certificate is valid.

The bundle can also verify identical files downloaded from Zenodo; the
signature sidecar is distributed through GitHub. A modified file, unrelated
signer or wrong predicate fails verification. A signature establishes artifact
integrity and issuer identity; physical timing qualification remains governed
by the measurement domain and its evidence.

## Subsequent versions

This workflow is deliberately bound to the original `v0.1.0` assets. A new
source version requires separately reviewed artifact digests, a new source
identity, complete validation and its own signature. It cannot replace existing
versions or infer a package publisher's identity from the source signature.
