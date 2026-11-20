// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — kernel answers to one system call for native API tests

#ifndef WITNESS_TEST_SYSTEM_CALL_ANSWER_H
#define WITNESS_TEST_SYSTEM_CALL_ANSWER_H
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>

/** Make the kernel answer one system call of this process with an errno without running it.
 *
 * An errno of zero skips the call and reports success, so the state it would change stays
 * unchanged.
 */
inline void answer_system_call(long number, int error) {
    std::array<sock_filter, 4> filter{
        {BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(seccomp_data, nr)),
         BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, static_cast<std::uint32_t>(number), 0, 1),
         BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | static_cast<std::uint32_t>(error)),
         BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW)}};
    sock_fprog program{static_cast<unsigned short>(filter.size()), filter.data()};
    assert(prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0);
    assert(prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &program) == 0);
}
#endif
