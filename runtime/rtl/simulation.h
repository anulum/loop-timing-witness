// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — reusable production RTL clock and AXI transport

/** @file simulation.h
 * reusable production RTL clock and AXI transport.
 */

#ifndef WITNESS_SIMULATION_H
#define WITNESS_SIMULATION_H

#include "Vaxi_control_witness.h"
#include "verilated.h"
#include <cstdint>
#include <stdexcept>

namespace witness {
/** Maximum simulated nanoseconds spent awaiting one AXI transaction. */
constexpr std::uint64_t transaction_limit = 100000;

/** Accepted bus channels and response values sampled before a rising edge. */
struct Edge {
    bool aw, w, ar, b, r;
    unsigned response;
    std::uint32_t data;
};

/** Deterministic 7 ns bus and 5 ns capture half-periods, with real CDC logic. */
class Simulation {
    VerilatedContext context;
    Vaxi_control_witness model{&context};

    /** Settle inputs, sample the bus before its edge, then evaluate changed clocks. */
    Edge tick() {
        model.eval();
        context.timeInc(1);
        const bool bus_edge = context.time() % 7 == 0;
        const bool capture_edge = context.time() % 5 == 0;
        const bool rising = bus_edge && !model.bus_clock;
        const Edge edge{rising && model.awvalid && model.awready,
                        rising && model.wvalid && model.wready,
                        rising && model.arvalid && model.arready,
                        rising && model.bvalid && model.bready,
                        rising && model.rvalid && model.rready,
                        model.rvalid ? model.rresp : model.bresp,
                        model.rdata};
        if (bus_edge)
            model.bus_clock = !model.bus_clock;
        if (capture_edge)
            model.capture_clock = !model.capture_clock;
        if (bus_edge || capture_edge)
            model.eval();
        if (context.gotFinish())
            throw std::runtime_error("RTL ended during transaction");
        return edge;
    }

  public:
    /** Assert the external common reset and release both actual clock domains. */
    Simulation() {
        model.run_reset_n = 0;
        model.eval();
        advance(140);
        model.run_reset_n = 1;
        advance(140);
    }

    /** Finalize the model before freeing the Verilator context. */
    ~Simulation() { model.final(); }

    /** Return nanoseconds elapsed in this simulation, never host wall time. */
    std::uint64_t time() const { return context.time(); }

    /** Advance both clocks while the native process has requested idle time. */
    void advance(std::uint64_t nanoseconds) {
        for (std::uint64_t index = 0; index < nanoseconds; ++index)
            tick();
    }

    /** Read through AR/R channels; return the actual destination AXI response. */
    Edge read(std::uint8_t address) {
        model.araddr = address;
        model.arvalid = 1;
        model.rready = 1;
        for (std::uint64_t index = 0; index < transaction_limit; ++index) {
            const Edge edge = tick();
            if (edge.ar)
                model.arvalid = 0;
            if (edge.r) {
                model.rready = 0;
                return edge;
            }
        }
        throw std::runtime_error("AXI read timed out");
    }

    /** Submit independent AW/W channels, then retain the actual B response. */
    Edge write(std::uint8_t address, std::uint32_t data, std::uint8_t strobes) {
        model.awaddr = address;
        model.wdata = data;
        model.wstrb = strobes;
        model.awvalid = 1;
        model.wvalid = 1;
        model.bready = 1;
        for (std::uint64_t index = 0; index < transaction_limit; ++index) {
            const Edge edge = tick();
            if (edge.aw)
                model.awvalid = 0;
            if (edge.w)
                model.wvalid = 0;
            if (edge.b) {
                model.bready = 0;
                return edge;
            }
        }
        throw std::runtime_error("AXI write timed out");
    }

    /** Advance up to a bounded wait, returning the retained bus-domain IRQ level. */
    bool wait_interrupt(std::uint64_t nanoseconds) {
        for (std::uint64_t index = 0; index < nanoseconds && !model.interrupt_line; ++index)
            tick();
        return model.interrupt_line;
    }
};

} // namespace witness

/** @var witness::Edge::aw
 * Write-address channel accepted on the sampled rising edge.
 */
/** @var witness::Edge::w
 * Write-data channel accepted on the sampled rising edge.
 */
/** @var witness::Edge::ar
 * Read-address channel accepted on the sampled rising edge.
 */
/** @var witness::Edge::b
 * Write-response channel accepted on the sampled rising edge.
 */
/** @var witness::Edge::r
 * Read-response channel accepted on the sampled rising edge.
 */
/** @var witness::Edge::response
 * Actual AXI response code selected from the active response channel.
 */
/** @var witness::Edge::data
 * Raw 32-bit read-data word sampled from the fabric.
 */

#endif
