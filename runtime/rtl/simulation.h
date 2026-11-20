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
#include "../refusal.h"
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

/** Initial values of the model's variables, chosen before the model is built.
 *
 * Mode 0 starts every variable without an initial value at zero, as Verilator does by default;
 * mode 2 draws them from the seed, which with a model built with `--x-initial unique` and
 * `--x-assign unique` shows whether any result depends on an uninitialised value.
 */
struct SimulationOptions {
    int random_reset = 0; ///< Verilator rand-reset mode: 0 zeros, 1 all ones, 2 random.
    int seed = 0;         ///< Seed of the random values in mode 2.
};

/** Deterministic 7 ns bus and 5 ns capture half-periods, with real CDC logic. */
class Simulation {
    /** A Verilator context set up before the model it serves is built. */
    struct Context : VerilatedContext {
        /** Apply the initial-value options. */
        explicit Context(const SimulationOptions &options) {
            randReset(options.random_reset);
            randSeed(options.seed);
        }
    };
    Context context;
    Vaxi_control_witness model{&context};
    /** Whether the model was evaluated after its last input or clock change. */
    bool settled = false;

    /** Record that an input changed, so the next tick evaluates before it samples. */
    void changed() { settled = false; }

    /** The clocks that toggle at one simulated nanosecond. */
    struct Due {
        bool bus;     ///< Whether the 7 ns bus half-period ends.
        bool capture; ///< Whether the 5 ns capture half-period ends.
    };

    /** Settle changed inputs and advance simulated time by one nanosecond.
     *
     * Between clock edges a model whose inputs did not change keeps its evaluated
     * state, so it is evaluated only after an input or clock change.
     */
    Due step_time() {
        if (!settled)
            model.eval();
        context.timeInc(1);
        return {context.time() % 7 == 0, context.time() % 5 == 0};
    }

    /** Toggle the due clocks and evaluate the model after a clock change. */
    void toggle(const Due due) {
        if (due.bus)
            model.bus_clock = !model.bus_clock;
        if (due.capture)
            model.capture_clock = !model.capture_clock;
        if (due.bus || due.capture)
            model.eval();
        settled = true;
        if (context.gotFinish())
            throw witness::RuntimeRefused("RTL ended during transaction");
    }

    /** Run both clocks under the asserted reset without sampling the bus.
     *
     * Until a domain's first clock edge under the reset, its flags can still hold initial values:
     * a local reset that starts low has no falling edge to assert it asynchronously. Nothing that
     * happens before the reset has acted is a bus handshake, so it is not sampled.
     */
    void hold_reset(std::uint64_t nanoseconds) {
        for (std::uint64_t index = 0; index < nanoseconds; ++index)
            toggle(step_time());
    }

    /** Settle changed inputs, sample the bus before its edge, then evaluate changed clocks. */
    Edge tick() {
        const Due due = step_time();
        const bool bus_edge = due.bus;
        const bool rising = bus_edge && !model.bus_clock;
        const Edge edge{rising && model.awvalid && model.awready,
                        rising && model.wvalid && model.wready,
                        rising && model.arvalid && model.arready,
                        rising && model.bvalid && model.bready,
                        rising && model.rvalid && model.rready,
                        model.rvalid ? model.rresp : model.bresp,
                        model.rdata};
        toggle(due);
        return edge;
    }

  public:
    /** Assert the external common reset and release both actual clock domains.
     *
     * Every input starts idle, as an AXI master drives ARVALID, AWVALID and WVALID low during
     * reset, so no transaction depends on the model's initial values. The reset period is held
     * without sampling the bus, so no flag from before the reset meets a handshake.
     */
    explicit Simulation(const SimulationOptions &options = {}) : context(options) {
        model.bus_clock = 0;
        model.capture_clock = 0;
        model.awaddr = 0;
        model.awvalid = 0;
        model.wdata = 0;
        model.wstrb = 0;
        model.wvalid = 0;
        model.bready = 0;
        model.araddr = 0;
        model.arvalid = 0;
        model.rready = 0;
        model.run_reset_n = 0;
        model.eval();
        hold_reset(140);
        model.run_reset_n = 1;
        changed();
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
    Edge read(std::uint16_t address) {
        model.araddr = address;
        model.arvalid = 1;
        model.rready = 1;
        changed();
        for (std::uint64_t index = 0; index < transaction_limit; ++index) {
            const Edge edge = tick();
            if (edge.ar) {
                model.arvalid = 0;
                changed();
            }
            if (edge.r) {
                model.rready = 0;
                changed();
                return edge;
            }
        }
        throw witness::RuntimeRefused("AXI read timed out");
    }

    /** Submit independent AW/W channels, then retain the actual B response. */
    Edge write(std::uint16_t address, std::uint32_t data, std::uint8_t strobes) {
        model.awaddr = address;
        model.wdata = data;
        model.wstrb = strobes;
        model.awvalid = 1;
        model.wvalid = 1;
        model.bready = 1;
        changed();
        for (std::uint64_t index = 0; index < transaction_limit; ++index) {
            const Edge edge = tick();
            if (edge.aw) {
                model.awvalid = 0;
                changed();
            }
            if (edge.w) {
                model.wvalid = 0;
                changed();
            }
            if (edge.b) {
                model.bready = 0;
                changed();
                return edge;
            }
        }
        throw witness::RuntimeRefused("AXI write timed out");
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
