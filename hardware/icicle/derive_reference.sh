#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — derive the pinned Icicle reference input

set -euo pipefail

if (( $# != 2 )); then
    printf 'usage: %s OFFICIAL_SOURCE NEW_SAMSUNG_OUTPUT\n' "$0" >&2
    exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "$script_dir/../.." && pwd)
if [[ -L "$2" ]]; then
    printf 'destination must be a new non-symlink path\n' >&2
    exit 2
fi
source_dir=$(realpath -e -- "$1")
destination_dir=$(realpath -m -- "$2")
destination_parent=$(dirname -- "$destination_dir")

if [[ ! -d "$destination_parent" || -e "$destination_dir" ]]; then
    printf 'destination parent must exist and destination must be new\n' >&2
    exit 2
fi
if [[ "$destination_dir" == "$source_dir" || "$destination_dir" == "$source_dir/"* ]]; then
    printf 'destination must be outside the official source checkout\n' >&2
    exit 2
fi
if [[ $(stat -c %d -- "$destination_parent") != $(stat -c %d -- "$repository_root") ]]; then
    printf 'destination must be on the canonical Samsung working disk\n' >&2
    exit 2
fi
if [[ $(git -C "$source_dir" rev-parse HEAD) != 9c34320f91e8e8a144c7d87bf299527fc5f02081 ]]; then
    printf 'official reference commit differs from the pinned source\n' >&2
    exit 2
fi
if [[ -n $(git -C "$source_dir" status --porcelain) ]]; then
    printf 'official reference checkout is not clean\n' >&2
    exit 2
fi

"$repository_root/.venv/bin/python" "$repository_root/tools/derive_icicle_reference.py" \
    "$source_dir" "$destination_dir"
"$repository_root/.venv/bin/python" "$repository_root/tools/derive_icicle_reference.py" \
    --verify "$destination_dir"
git -C "$destination_dir" diff --check
printf 'derived Icicle source: %s\n' "$destination_dir"
