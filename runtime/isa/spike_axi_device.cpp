// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — architectural RISC-V MMIO to production AXI RTL

#include "abstract_device.h"
#include "dts.h"
#include "sim.h"
#include "../rtl/simulation.h"
#include "spike_amp_transport.h"
#include "../amp_logger.h"
#include <charconv>
#include <iostream>
#include <limits>
#include <sstream>

namespace {
/** Explicit simulation address, PLIC source and clock mapping, never board defaults. */
struct Settings {
    reg_t base;
    std::uint32_t interrupt;
    std::uint64_t rtc_nanoseconds;
    std::uint64_t time_limit;
    std::uint64_t shared;
    std::string run_path, event_path, tracking_path;
};

/** Admit unsigned decimal plugin parameters without whitespace, signs or suffixes. */
std::uint64_t argument(const std::string &text) {
    std::uint64_t value = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), value);
    if (text.empty() || result.ec != std::errc{} || result.ptr != text.data() + text.size())
        throw std::invalid_argument("Witness device arguments must be unsigned decimal integers");
    return value;
}

/** Require the entire functional ISA simulation contract before creating RTL state. */
Settings settings(const std::vector<std::string> &args) {
    if (args.size() != 8)
        throw std::invalid_argument("Witness device requires base, IRQ, RTC nanoseconds, time limit, mailbox, run configuration, events and tracking");
    const auto base = argument(args[0]);
    const auto interrupt = argument(args[1]);
    const auto rtc_nanoseconds = argument(args[2]);
    const auto time_limit = argument(args[3]);
    if (base == 0 || base % 256 != 0 || base > std::numeric_limits<reg_t>::max() - 255 ||
        interrupt == 0 || interrupt > std::numeric_limits<std::uint32_t>::max() ||
        rtc_nanoseconds == 0 || rtc_nanoseconds > 1000000 || time_limit < 1000000)
        throw std::invalid_argument("Witness device simulation contract outside bounds");
    const auto shared = argument(args[4]);
    if (!shared || shared % 8 || shared > UINT64_MAX - sizeof(witness_amp_mailbox) ||
        args[5].empty() || args[6].empty() || args[7].empty())
        throw std::invalid_argument("Witness AMP mailbox or run files outside bounds");
    return {base, static_cast<std::uint32_t>(interrupt), rtc_nanoseconds, time_limit,
            shared, args[5], args[6], args[7]};
}
}

/** Real AXI transactions and retained RTL IRQ routed through Spike's architectural PLIC. */
class witness_axi_t final : public abstract_device_t {
    const sim_t &simulator;
    Settings configuration;
    witness::Simulation fabric;
    witness::RunConfiguration run;
    witness::SpikeAmpTransport transport;
    witness::RunOutput output;
    witness::AmpLogger<witness::SpikeAmpTransport> logger;
    bool complete = false;

    /** Publish the actual retained IRQ level and bound functional simulation lifetime. */
    void synchronize() {
        simulator.get_intctrl()->set_interrupt_level(configuration.interrupt,
                                                     fabric.wait_interrupt(0) ? 1 : 0);
        if (fabric.time() > configuration.time_limit)
            throw std::runtime_error("Witness ISA simulation time limit exceeded");
    }

public:
    /** Start production RTL after the simulator has installed its actual PLIC. */
    witness_axi_t(const sim_t &sim, Settings supplied)
        : simulator(sim), configuration(supplied),
          run(witness::read_configuration(configuration.run_path)),
          transport(sim, fabric, configuration.shared),
          output(configuration.event_path.c_str(), configuration.tracking_path.c_str()),
          logger(transport, run, output, configuration.shared) {
        if (run.modeled_overload_ns)
            throw std::invalid_argument("AMP overload must execute actual target instructions without a synthetic time advance");
        witness::configure_run(transport, run);
        synchronize();
    }

    /** Expose only the implemented 256-byte register aperture. */
    reg_t size() override { return 256; }

    /** Translate an aligned 32-bit ISA load to an actual AR/R exchange, including refusal. */
    bool load(reg_t address, size_t length, std::uint8_t *bytes) override {
        if (length != 4 || address > 252 || address % 4 != 0) return false;
        const auto reply = fabric.read(static_cast<std::uint8_t>(address));
        synchronize();
        if (reply.response != 0) return false;
        for (unsigned index = 0; index < 4; ++index)
            bytes[index] = static_cast<std::uint8_t>(reply.data >> (index * 8));
        return true;
    }

    /** Translate an aligned full-word ISA store to actual independent AW/W and B channels. */
    bool store(reg_t address, size_t length, const std::uint8_t *bytes) override {
        if (length != 4 || address > 252 || address % 4 != 0) return false;
        std::uint32_t value = 0;
        for (unsigned index = 0; index < 4; ++index)
            value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8);
        const auto reply = fabric.write(static_cast<std::uint8_t>(address), value, 15);
        synchronize();
        return reply.response == 0;
    }

    /** Advance real RTL between instruction batches using the explicitly supplied clock map. */
    void tick(reg_t rtc_ticks) override {
        if (rtc_ticks > 10000000 / configuration.rtc_nanoseconds)
            throw std::runtime_error("Witness ISA clock advance outside bounds");
        fabric.advance(rtc_ticks * configuration.rtc_nanoseconds);
        synchronize();
        if (!complete) {
            complete = logger.poll();
            if (complete) {
                const auto result = logger.completion();
                std::cout << "WITNESS_AMP_COMPLETION {\"samples\":" << result.samples
                          << ",\"events\":" << result.records
                          << ",\"misses\":" << result.misses
                          << ",\"overflow\":" << result.overflow
                          << ",\"safe\":" << (result.safe ? "true" : "false")
                          << ",\"thermal\":"
                          << (witness::read_register(transport, 0x6c) ? "true" : "false") << "}\n";
                std::cout.flush();
                if (!std::cout) throw std::runtime_error("AMP completion receipt write failed");
            }
        }
        synchronize();
    }
};

/** Bind explicit simulation arguments to the actual parsed PLIC and existing device map. */
witness_axi_t *witness_axi_parse(const void *fdt, const sim_t *sim, reg_t *base,
                               const std::vector<std::string> &args) {
    const auto supplied = settings(args);
    reg_t plic_base = 0;
    std::uint32_t interrupts = 0;
    if (fdt_parse_plic(fdt, &plic_base, &interrupts, "riscv,plic0") != 0 ||
        supplied.interrupt > interrupts)
        throw std::invalid_argument("Witness device requires an available architectural PLIC source");
    for (const auto &entry : sim->get_bus().get_devices()) {
        const auto other_base = entry.first;
        const auto other_size = entry.second->size();
        if ((supplied.base >= other_base && supplied.base - other_base < other_size) ||
            (other_base >= supplied.base && other_base - supplied.base < 256))
            throw std::invalid_argument("Witness device overlaps an existing simulator device");
    }
    *base = supplied.base;
    return new witness_axi_t(*sim, supplied);
}

/** Describe the explicit functional MMIO aperture when Spike requests plugin device-tree text. */
std::string witness_axi_dts(const sim_t *, const std::vector<std::string> &args) {
    const auto supplied = settings(args);
    std::ostringstream text;
    text << std::hex << "    witness@" << supplied.base
         << " { compatible = \"anulum,loop-timing-witness-axi-v1\", \"anulum,witness-isa-simulation\"; reg = <0x"
         << (supplied.base >> 32) << " 0x" << (supplied.base & 0xffffffff)
         << " 0 0x100>; interrupt-parent = <&PLIC>; interrupts = <0x"
         << supplied.interrupt << ">; };\n";
    return text.str();
}

REGISTER_DEVICE(witness_axi, witness_axi_parse, witness_axi_dts)
