// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — freestanding dedicated hart controller IRQ lifecycle

#include "amp_contract.h"

_Static_assert(sizeof(witness_amp_platform_contract) == 56, "platform ELF/host ABI changed");
_Static_assert(sizeof(witness_amp_sample) == 64, "telemetry ELF/host ABI changed");
_Static_assert(sizeof(witness_amp_mailbox) == 16496, "mailbox ELF/host ABI changed");

static witness_pid_state controller_state;
static uint32_t previous_cycle;
static bool have_previous;

/** Order real MMIO and shared-memory transfers across the processor/fabric boundary. */
static void fence(void) { __asm__ volatile("fence iorw,iorw" ::: "memory"); }

/** Read one full register word; a real access fault enters the architectural trap handler. */
static uint32_t load(uint64_t address) {
    fence();
    const uint32_t value = *(volatile uint32_t *)(uintptr_t)address;
    fence();
    return value;
}

/** Write one full register word without inventing an AXI acknowledgement unavailable to a CPU. */
static void store(uint64_t address, uint32_t value) {
    fence();
    *(volatile uint32_t *)(uintptr_t)address = value;
    fence();
}

/** Locate only the explicitly reserved, operator-mapped telemetry region. */
static volatile witness_amp_mailbox *mailbox(void) {
    return (volatile witness_amp_mailbox *)(uintptr_t)witness_amp_platform.shared;
}

/** Preserve every raw signed Q8.24 word without implementation-defined narrowing. */
static int32_t signed_word(uint32_t word) {
    if (word <= INT32_MAX)
        return (int32_t)word;
    return INT32_MIN + (int32_t)(word - UINT32_C(2147483648));
}

/** Disable this hart's interrupt service, publish the reason and retain hardware deadline safety.
 */
static _Noreturn void refuse(uint64_t cause, uint64_t value) {
    __asm__ volatile("csrw mie,zero" ::: "memory");
    if (witness_amp_platform.shared && witness_amp_platform.shared % 8 == 0) {
        volatile witness_amp_mailbox *output = mailbox();
        output->trap_cause = cause;
        output->trap_value = value;
        fence();
        output->status = WITNESS_AMP_REFUSED;
        fence();
    }
    for (;;)
        __asm__ volatile("wfi" ::: "memory");
}

void witness_amp_rust_panic(void) { refuse(UINT64_C(0x109), 0); }

/** Retain one observed sample; a stalled consumer invalidates telemetry and stops control. */
static void publish(const witness_amp_sample *sample) {
    volatile witness_amp_mailbox *output = mailbox();
    const uint32_t producer = output->producer;
    fence();
    if (producer - output->consumer >= WITNESS_AMP_CAPACITY) {
        output->telemetry_overflow = 1;
        refuse(UINT64_C(0x100), sample->cycle);
    }
    output->records[producer & (WITNESS_AMP_CAPACITY - 1)] = *sample;
    output->samples += 1;
    fence();
    output->producer = producer + 1;
    fence();
}

/** Compute with the selected public kernel from an actual coherent fabric snapshot. */
static void control_sample(uint64_t generation) {
    const uint64_t base = witness_amp_platform.mmio;
    const int32_t position = signed_word(load(base));
    const uint32_t cycle = load(base + 0x10);
    const int32_t velocity = signed_word(load(base + 0x14));
    const int32_t reference = signed_word(load(base + 0x18));
    const uint64_t low = load(base + 0x1c);
    const uint64_t ticks = low | ((uint64_t)load(base + 0x20) << 32);
    if (cycle >= witness_amp_run.cycles || (have_previous && cycle <= previous_cycle))
        refuse(UINT64_C(0x101), cycle);
    previous_cycle = cycle;
    have_previous = true;
    witness_command command;
    const bool computed = witness_amp_run.lqr != 0
                              ? witness_lqr_step(&witness_amp_run.coefficients, cycle, reference,
                                                 position, velocity, &command)
                              : witness_pid_step(&witness_amp_run.coefficients, &controller_state,
                                                 cycle, reference, position, &command);
    if (!computed)
        refuse(UINT64_C(0x102), cycle);
    uint64_t work = 0;
    if (load(base + 0x68) & 4) {
        volatile uint64_t accumulator = 0;
        for (uint32_t index = 0; index < witness_amp_run.overload_iterations; ++index)
            accumulator = accumulator + (uint64_t)index * index;
        work = accumulator;
    }
    uint32_t submitted = 0;
    if (!(load(base + 4) & 12)) {
        store(base + 0x28, cycle);
        store(base + 0x2c, (uint32_t)command.command);
        store(base + 0x30, 1);
        submitted = 1;
    }
    const witness_amp_sample sample = {ticks,
                                       generation,
                                       work,
                                       cycle,
                                       reference,
                                       position,
                                       velocity,
                                       command.command,
                                       command.integral,
                                       command.derivative,
                                       command.clipped ? 1U : 0U,
                                       command.integral_held ? 1U : 0U,
                                       submitted};
    publish(&sample);
}

void witness_amp_trap(uint64_t cause, uint64_t value) {
    if (cause != (UINT64_C(1) << 63 | UINT64_C(11)))
        refuse(cause, value);
    const uint32_t interrupt = load(witness_amp_platform.claim);
    if (!interrupt)
        return;
    if (interrupt != witness_amp_platform.interrupt)
        refuse(UINT64_C(0x103), interrupt);
    const uint64_t base = witness_amp_platform.mmio;
    const uint64_t low = load(base + 0x9c);
    const uint64_t generation = low | ((uint64_t)load(base + 0xa0) << 32);
    const uint32_t status = load(base + 4);
    if (!(status & 12))
        control_sample(generation);
    store(base + 0xa4, 1);
    store(witness_amp_platform.claim, interrupt);
    if (status & 4) {
        __asm__ volatile("csrw mie,zero" ::: "memory");
        fence();
        mailbox()->status = WITNESS_AMP_FINISHED;
        fence();
    }
}

void witness_amp_main(void) {
    const witness_amp_platform_contract *platform = &witness_amp_platform;
    if (!platform->shared || platform->shared % 8)
        refuse(UINT64_C(0x104), 5);
    const uint64_t addresses[] = {platform->mmio,      platform->priority, platform->enable_word,
                                  platform->threshold, platform->claim,    platform->shared};
    for (unsigned index = 0; index < sizeof(addresses) / sizeof(addresses[0]); ++index)
        if (!addresses[index] || addresses[index] % 4)
            refuse(UINT64_C(0x104), index);
    if (platform->hart < 1 || platform->hart > 4 || !platform->interrupt ||
        platform->interrupt >= 1024 || !witness_amp_run.cycles || !witness_amp_run.period_ticks ||
        witness_amp_run.lqr > 1 || witness_amp_run.overload_iterations > 10000000 ||
        !witness_coefficients_valid(&witness_amp_run.coefficients))
        refuse(UINT64_C(0x105), 0);
    volatile witness_amp_mailbox *output = mailbox();
    output->abi = 0;
    fence();
    output->status = WITNESS_AMP_INITIAL;
    output->producer = 0;
    output->consumer = 0;
    output->trap_cause = 0;
    output->trap_value = 0;
    output->telemetry_overflow = 0;
    output->samples = 0;
    output->logger_status = WITNESS_AMP_LOGGER_WAITING;
    output->reserved = 0;
    output->run.cycles = witness_amp_run.cycles;
    output->run.period_ticks = witness_amp_run.period_ticks;
    output->run.lqr = witness_amp_run.lqr;
    output->run.overload_iterations = witness_amp_run.overload_iterations;
    output->run.coefficients.kp = witness_amp_run.coefficients.kp;
    output->run.coefficients.ki_period = witness_amp_run.coefficients.ki_period;
    output->run.coefficients.derivative_decay = witness_amp_run.coefficients.derivative_decay;
    output->run.coefficients.derivative_gain = witness_amp_run.coefficients.derivative_gain;
    output->run.coefficients.position_gain = witness_amp_run.coefficients.position_gain;
    output->run.coefficients.velocity_gain = witness_amp_run.coefficients.velocity_gain;
    output->run.coefficients.reference_gain = witness_amp_run.coefficients.reference_gain;
    output->run.coefficients.output_min = witness_amp_run.coefficients.output_min;
    output->run.coefficients.output_max = witness_amp_run.coefficients.output_max;
    output->run.coefficients.integral_min = witness_amp_run.coefficients.integral_min;
    output->run.coefficients.integral_max = witness_amp_run.coefficients.integral_max;
    output->run_reserved = 0;
    fence();
    output->abi = WITNESS_AMP_ABI;
    fence();
    while (output->logger_status == WITNESS_AMP_LOGGER_WAITING)
        fence();
    if (output->logger_status != WITNESS_AMP_LOGGER_READY)
        refuse(UINT64_C(0x108), output->logger_status);
    if (load(platform->mmio + 0x7c) != 1 || load(platform->mmio + 0x78) != 24 ||
        load(platform->mmio + 0x40) != witness_amp_run.period_ticks ||
        load(platform->mmio + 0x3c) != witness_amp_run.cycles - 1 ||
        (load(platform->mmio + 4) & 6) || load(platform->enable_word))
        refuse(UINT64_C(0x106), 0);
    if (output->abi != WITNESS_AMP_ABI || output->status || output->producer || output->consumer ||
        output->telemetry_overflow || output->samples || output->trap_cause || output->trap_value ||
        output->logger_status != WITNESS_AMP_LOGGER_READY || output->reserved)
        refuse(UINT64_C(0x107), 0);
    witness_pid_reset(&controller_state);
    store(platform->priority, 1);
    store(platform->threshold, 0);
    store(platform->enable_word, UINT32_C(1) << (platform->interrupt % 32));
    fence();
    output->status = WITNESS_AMP_ARMED;
    fence();
    const uint64_t external_irq = UINT64_C(1) << 11;
    __asm__ volatile("csrw mie,%0\ncsrs mstatus,%1" ::"r"(external_irq), "r"(UINT64_C(8))
                     : "memory");
    while (output->status != WITNESS_AMP_FINISHED)
        __asm__ volatile("wfi" ::: "memory");
    while (output->logger_status == WITNESS_AMP_LOGGER_READY)
        fence();
    if (output->logger_status != WITNESS_AMP_LOGGER_COMPLETE)
        refuse(UINT64_C(0x108), output->logger_status);
    witness_amp_exit();
}
