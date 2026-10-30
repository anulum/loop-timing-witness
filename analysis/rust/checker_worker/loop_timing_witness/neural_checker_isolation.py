# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — finite source-checker process isolation

"""Apply the selected Linux x86-64 checker process resource and network boundary."""

from __future__ import annotations

import ctypes
import errno
import platform
import resource

_LOAD_WORD = 0x20
_JUMP_EQUAL = 0x15
_JUMP_GREATER_EQUAL = 0x35
_RETURN = 0x06
_AUDIT_ARCH_X86_64 = 0xC000003E
_ALLOW = 0x7FFF0000
_KILL_PROCESS = 0x80000000
_DENY = 0x00050000 | errno.EPERM
_X32_SYSCALL_BIT = 0x40000000
_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2
_NETWORK_SYSCALLS = (*range(41, 56), 288, 299, 307, 425, 426, 427)


class _Instruction(ctypes.Structure):
    """One Linux classic BPF instruction in its fixed native layout."""

    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class _Program(ctypes.Structure):
    """Linux sock_fprog pointing at the complete owned filter array."""

    _fields_ = [("length", ctypes.c_ushort), ("instructions", ctypes.POINTER(_Instruction))]


def isolate_checker() -> None:
    """Apply finite resources and deny network syscalls before checker imports.

    The filter requires Linux x86-64, rejects alternate syscall architectures
    and x32 syscall numbers, and is inherited by subsequently created threads
    and children. The parent supplies no inherited network file descriptors.

    Raises
    ------
    OSError
        If the selected platform or required kernel isolation is unavailable.
    ValueError
        If inherited resource limits cannot admit the fixed checker profile.
    """
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        message = "Source checker requires its selected Linux x86-64 platform."
        raise OSError(message)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
    instructions = [
        (_LOAD_WORD, 0, 0, 4),
        (_JUMP_EQUAL, 1, 0, _AUDIT_ARCH_X86_64),
        (_RETURN, 0, 0, _KILL_PROCESS),
        (_LOAD_WORD, 0, 0, 0),
        (_JUMP_GREATER_EQUAL, 0, 1, _X32_SYSCALL_BIT),
        (_RETURN, 0, 0, _DENY),
    ]
    for number in _NETWORK_SYSCALLS:
        instructions.extend([(_JUMP_EQUAL, 0, 1, number), (_RETURN, 0, 0, _DENY)])
    instructions.append((_RETURN, 0, 0, _ALLOW))
    array = (_Instruction * len(instructions))(*(_Instruction(*item) for item in instructions))
    program = _Program(len(instructions), array)
    library = ctypes.CDLL(None, use_errno=True)
    control = library.prctl
    control.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    control.restype = ctypes.c_int
    if (
        control(_PR_SET_NO_NEW_PRIVS, 1, None, 0, 0) != 0
        or control(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, ctypes.byref(program), 0, 0) != 0
    ):
        message = "Source checker kernel isolation is unavailable."
        raise OSError(message)
