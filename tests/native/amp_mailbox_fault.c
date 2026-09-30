// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — actual target mailbox fault injection around the production IRQ handler

#include "runtime/bare_metal/amp_contract.h"

/** Select one deliberate real target corruption in an owned test ELF, never an admitted capture. */
volatile const uint32_t witness_amp_test_fault = 0;
/** GNU linker wrapping retains the complete original production trap handler. */
void __real_witness_amp_trap(uint64_t cause, uint64_t value);
/** Execute production control before corrupting actual shared RAM for logger admission tests. */
void __wrap_witness_amp_trap(uint64_t cause, uint64_t value);

void __wrap_witness_amp_trap(uint64_t cause, uint64_t value) {
    volatile witness_amp_mailbox *output =
        (volatile witness_amp_mailbox *)(uintptr_t)witness_amp_platform.shared;
    const uint32_t fault = witness_amp_test_fault;
    if (fault == 1 && cause == (UINT64_C(1) << 63 | UINT64_C(11))) {
        output->producer = output->consumer + WITNESS_AMP_CAPACITY;
        __asm__ volatile("fence iorw,iorw" ::: "memory");
    }
    __real_witness_amp_trap(cause, value);
    if (!output->samples) return;
    switch (fault) {
    case 2: output->abi = 0; break;
    case 3: output->abi = 99; break;
    case 4: output->status = 4; break;
    case 5: output->consumer += 1; break;
    case 6: output->logger_status = 0; break;
    case 7: output->reserved = 1; break;
    case 8: output->producer = output->consumer + WITNESS_AMP_CAPACITY + 1; break;
    case 9: output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].clipped = 2; break;
    case 10: output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].generation = 0; break;
    case 11: output->status = WITNESS_AMP_INITIAL; break;
    case 12:
        if (output->status == WITNESS_AMP_FINISHED) output->samples += 1;
        break;
    case 13: output->run_reserved = 1; break;
    case 14: output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].integral_held = 2; break;
    case 15: output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].submitted = 2; break;
    case 16: output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].cycle = witness_amp_run.cycles; break;
    case 17:
        if (output->samples >= 2)
            output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].cycle = 0;
        break;
    case 18:
        if (output->samples >= 2)
            output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].ticks = 0;
        break;
    case 19:
        if (output->samples >= 2)
            output->records[(output->producer - 1) & (WITNESS_AMP_CAPACITY - 1)].generation = 1;
        break;
    case 20: output->trap_cause = 1; break;
    case 21: output->trap_value = 1; break;
    case 22: output->status = WITNESS_AMP_FINISHED; break;
    default: break;
    }
    __asm__ volatile("fence iorw,iorw" ::: "memory");
}
