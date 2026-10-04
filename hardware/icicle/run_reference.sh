#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — verify and run one derived Icicle reference

set -euo pipefail

if (($# != 3)); then
    printf 'usage: %s DERIVED_TREE LIBERO_EXECUTABLE MPFS250T|MPFS250T_ES\n' "$0" >&2
    exit 2
fi

script_path=$(realpath -e -- "${BASH_SOURCE[0]}")
script_dir=$(dirname -- "${script_path}")
repository_root=$(realpath -e -- "${script_dir}/../..")
derived_dir=$(realpath -e -- "$1")
device=$3

if [[ ! -d "${derived_dir}" ]]; then
    printf 'derived tree is required\n' >&2
    exit 2
fi
derived_device=$(stat -c %d -- "${derived_dir}")
repository_device=$(stat -c %d -- "${repository_root}")
if [[ "${derived_device}" != "${repository_device}" ]]; then
    printf 'derived project must run on the canonical Samsung working disk\n' >&2
    exit 2
fi
source_commit=$(git -C "${derived_dir}" rev-parse HEAD)
if [[ "${source_commit}" != 9c34320f91e8e8a144c7d87bf299527fc5f02081 ]]; then
    printf 'derived tree has the wrong official reference commit\n' >&2
    exit 2
fi

case "${device}" in
    MPFS250T) project_name=BASE_DESIGN_9C34320F ;;
    MPFS250T_ES) project_name=BASE_DESIGN_ES_9C34320F ;;
    *)
        printf 'device must match the confirmed MPFS250T or MPFS250T_ES marking\n' >&2
        exit 2
        ;;
esac
if [[ -e "${derived_dir}/${project_name}" ]]; then
    printf 'generated project already exists: %s\n' "${derived_dir}/${project_name}" >&2
    exit 2
fi

"${repository_root}/.venv/bin/python" "${repository_root}/tools/derive_icicle_reference.py" \
    --verify "${derived_dir}"

if [[ ! -x "$2" ]]; then
    printf 'an executable Libero binary is required\n' >&2
    exit 2
fi
libero_exe=$(realpath -e -- "$2")

arguments=("script:MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl")
if [[ "${device}" == MPFS250T ]]; then
    arguments+=("SCRIPT_ARGS:MPFS250T+VERIFY_TIMING")
else
    arguments+=("SCRIPT_ARGS:VERIFY_TIMING")
fi
arguments+=("logfile:MPFS_ICICLE_KIT_REFERENCE_DESIGN.log")
cd -- "${derived_dir}"
"${libero_exe}" "${arguments[@]}"
