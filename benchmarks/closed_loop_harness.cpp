// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — closed-loop benchmark data from the production plant witness

// The harness clocks the unchanged production control_plant_witness and stands in for an
// interrupt-driven service: it reads each sample and writes each command at declared,
// deterministic offsets, computing the command with the production C PID kernel. The offsets
// are a stimulus, not processor execution time. Every value comes from the command line, so the
// stimulus declaration written beside the run is the complete input.

#include "Vcontrol_plant_witness.h"
#include "verilated.h"
extern "C" {
#include "../controllers/c/witness_controller.h"
}
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <stdexcept>
#include <string>
#include <utility>

namespace {

/** Refusal whose text is the harness's whole diagnostic. */
struct Refused : std::runtime_error {
    using std::runtime_error::runtime_error;
};

/** Complete declared stimulus; every member is a required command-line value. */
struct Stimulus {
    std::uint64_t cycles, seed, period, read_min, read_span, gap_min, gap_span, skip_interval;
    std::uint64_t fault_cycle, fault_periods, drain_half, reference_mode, phase_increment;
    std::int64_t reference_amplitude;
    witness_coefficients coefficients;
};

/** Parse one decimal integer in [minimum, maximum] or refuse with the key's name. */
std::int64_t integer(const std::map<std::string, std::string> &values, const std::string &key,
                     std::int64_t minimum, std::int64_t maximum) {
    const auto found = values.find(key);
    if (found == values.end())
        throw Refused("missing stimulus value: " + key);
    const std::string &text = found->second;
    char *end = nullptr;
    errno = 0;
    const long long parsed = std::strtoll(text.c_str(), &end, 10);
    if (text.empty() || *end != '\0' || errno == ERANGE || parsed < minimum || parsed > maximum)
        throw Refused("invalid stimulus value: " + key);
    return parsed;
}

/** Read key=value arguments into a map, refusing repeated or malformed entries. */
std::map<std::string, std::string> arguments(int argc, char **argv, int first) {
    std::map<std::string, std::string> values;
    for (int index = first; index < argc; ++index) {
        const std::string item = argv[index];
        const auto split = item.find('=');
        if (split == std::string::npos || split == 0 ||
            !values.emplace(item.substr(0, split), item.substr(split + 1)).second)
            throw Refused("malformed or repeated argument: " + item);
    }
    return values;
}

/** Read the coefficient block in the controller's declared field order. */
witness_coefficients coefficients(const std::map<std::string, std::string> &values) {
    const std::int64_t low = INT32_MIN, high = INT32_MAX;
    witness_coefficients result{};
    result.kp = static_cast<std::int32_t>(integer(values, "kp", low, high));
    result.ki_period = static_cast<std::int32_t>(integer(values, "ki_period", low, high));
    result.derivative_decay =
        static_cast<std::int32_t>(integer(values, "derivative_decay", low, high));
    result.derivative_gain =
        static_cast<std::int32_t>(integer(values, "derivative_gain", low, high));
    result.position_gain = static_cast<std::int32_t>(integer(values, "position_gain", low, high));
    result.velocity_gain = static_cast<std::int32_t>(integer(values, "velocity_gain", low, high));
    result.reference_gain = static_cast<std::int32_t>(integer(values, "reference_gain", low, high));
    result.output_min = static_cast<std::int32_t>(integer(values, "output_min", low, high));
    result.output_max = static_cast<std::int32_t>(integer(values, "output_max", low, high));
    result.integral_min = static_cast<std::int32_t>(integer(values, "integral_min", low, high));
    result.integral_max = static_cast<std::int32_t>(integer(values, "integral_max", low, high));
    if (!witness_coefficients_valid(&result))
        throw Refused("controller coefficients are invalid");
    return result;
}

/** Build and cross-check the declared stimulus; the key set must be exactly the declared one. */
Stimulus stimulus(const std::map<std::string, std::string> &values) {
    const std::int64_t wide = INT64_MAX;
    Stimulus result{};
    result.cycles = static_cast<std::uint64_t>(integer(values, "cycles", 16, UINT32_MAX));
    result.seed = static_cast<std::uint64_t>(integer(values, "seed", 0, wide));
    result.period = static_cast<std::uint64_t>(integer(values, "period", 1, UINT32_MAX));
    result.read_min = static_cast<std::uint64_t>(integer(values, "read_min", 1, wide));
    result.read_span = static_cast<std::uint64_t>(integer(values, "read_span", 1, wide));
    result.gap_min = static_cast<std::uint64_t>(integer(values, "gap_min", 1, wide));
    result.gap_span = static_cast<std::uint64_t>(integer(values, "gap_span", 1, wide));
    result.skip_interval = static_cast<std::uint64_t>(integer(values, "skip_interval", 0, wide));
    result.fault_cycle = static_cast<std::uint64_t>(integer(values, "fault_cycle", 0, wide));
    result.fault_periods = static_cast<std::uint64_t>(integer(values, "fault_periods", 0, 1000));
    result.drain_half = static_cast<std::uint64_t>(integer(values, "drain_half", 1, 64));
    result.reference_mode = static_cast<std::uint64_t>(integer(values, "reference_mode", 0, 2));
    result.phase_increment = static_cast<std::uint64_t>(integer(values, "phase_increment", 0, 15));
    result.reference_amplitude = integer(values, "reference_amplitude", INT32_MIN, INT32_MAX);
    result.coefficients = coefficients(values);
    if (values.size() != 25)
        throw Refused("unknown stimulus argument");
    if (result.read_min + result.read_span + result.gap_min + result.gap_span >= result.period)
        throw Refused("service offsets do not end before the deadline");
    if (result.fault_periods && (result.fault_cycle < 4 || result.fault_cycle >= result.cycles))
        throw Refused("fault cycle is outside the run");
    return result;
}

/** SplitMix64: a declared, portable sequence for the service offsets. */
class Sequence {
    std::uint64_t state;

  public:
    explicit Sequence(std::uint64_t seed) : state(seed) {}
    std::uint64_t next() {
        std::uint64_t value = (state += 0x9e3779b97f4a7c15ULL);
        value = (value ^ (value >> 30)) * 0xbf58476d1ce4e5b9ULL;
        value = (value ^ (value >> 27)) * 0x94d049bb133111ebULL;
        return value ^ (value >> 31);
    }
};

/** Observable totals printed as the harness summary. */
struct Totals {
    std::uint64_t records = 0, skipped = 0, rows = 0;
    bool buffer_full = false;
};

/** The simulated service and the open output files of one run. */
class Harness {
    const Stimulus &declared;
    Vcontrol_plant_witness &model;
    Sequence offsets;
    std::FILE *events, *trajectory;
    witness_pid_state pid{};
    std::uint64_t first = UINT64_MAX, read_tick = 0, write_tick = 0, served = 0;
    std::int32_t command = 0;
    bool active = false, read_done = false, skip = false, waiting = false;

    /** Begin service of the cycle whose interrupt was sampled at tick. */
    void begin(std::uint64_t tick) {
        served = first == UINT64_MAX ? 0 : (tick - first) / declared.period;
        if (first != UINT64_MAX && tick != first + served * declared.period)
            throw Refused("sample interrupt is off the declared period");
        read_tick = tick + declared.read_min + offsets.next() % declared.read_span;
        write_tick = read_tick + declared.gap_min + offsets.next() % declared.gap_span;
        skip =
            declared.skip_interval && served % declared.skip_interval == declared.skip_interval - 1;
        if (declared.fault_periods && served + 3 >= declared.fault_cycle)
            skip = false;
        active = true;
        read_done = false;
    }

    /** Drive the service inputs for the tick that follows a falling capture edge. */
    void service() {
        model.sample_read = 0;
        model.actuator_write = 0;
        model.command_cycle = model.cycle_number;
        if (!active)
            return;
        const std::uint64_t tick = model.counter_ticks;
        if (!read_done && tick == read_tick) {
            witness_command result{};
            const auto reference = static_cast<std::int32_t>(model.reference_value);
            const auto position = static_cast<std::int32_t>(model.sample_value);
            if (!witness_pid_step(&declared.coefficients, &pid, static_cast<std::uint32_t>(served),
                                  reference, position, &result))
                throw Refused("controller refused validated coefficients");
            command = result.command;
            model.sample_read = 1;
            read_done = true;
        } else if (read_done && tick == write_tick) {
            if (skip)
                ++totals.skipped;
            else {
                model.actuator_write = 1;
                model.command_cycle = static_cast<std::uint32_t>(served);
                model.command_value = static_cast<std::uint32_t>(command);
            }
            active = false;
        }
    }

    /** Sample the interrupt before a rising edge, as the interrupt controller would. */
    void interrupt(std::uint64_t tick) {
        if (!model.sample_interrupt || !model.capture_active || !model.enable)
            return;
        if (model.delayed_interrupt) {
            if (model.delayed_cycle != declared.fault_cycle)
                throw Refused("delayed interrupt lost its origin cycle");
            waiting = false;
        }
        if (!waiting)
            begin(tick);
    }

    /** Append one drained 16-byte record, least significant byte first. */
    void record() {
        unsigned char bytes[16];
        for (unsigned index = 0; index < 16; ++index)
            bytes[index] =
                static_cast<unsigned char>(model.drain_record[index / 4] >> (8 * (index % 4)));
        if (std::fwrite(bytes, 1, sizeof(bytes), events) != sizeof(bytes))
            throw Refused("cannot write the event file");
        ++totals.records;
    }

    /** Evaluate one half capture period; the drain clock toggles on its declared half-period. */
    void half_step(std::uint64_t half) {
        const bool toggled = half % declared.drain_half == 0;
        if (toggled)
            model.drain_clock = !model.drain_clock;
        model.eval();
        if (toggled && model.drain_clock && model.drain_valid)
            record();
        if (model.buffer_full)
            totals.buffer_full = true;
    }

    /** Record the sampled plant state after a rising edge. */
    void observe(std::uint64_t tick, std::int32_t actuator) {
        if (model.sample_valid) {
            if (model.cycle_number == 0 && first == UINT64_MAX)
                first = tick;
            const std::int32_t applied = model.safe_interrupt ? 0 : actuator;
            std::fprintf(trajectory, "%u,%d,%d,%d,%d,%llu\n", model.cycle_number,
                         static_cast<std::int32_t>(model.reference_value),
                         static_cast<std::int32_t>(model.sample_value),
                         static_cast<std::int32_t>(model.velocity), applied,
                         static_cast<unsigned long long>(tick));
            ++totals.rows;
        }
        if (model.safe_interrupt && model.actuator_value != 0)
            throw Refused("safe value not held");
    }

  public:
    Totals totals;

    Harness(const Stimulus &stimulus, Vcontrol_plant_witness &top, std::FILE *event_file,
            std::FILE *trajectory_file)
        : declared(stimulus), model(top), offsets(stimulus.seed), events(event_file),
          trajectory(trajectory_file) {
        witness_pid_reset(&pid);
    }

    /** Advance one capture period: falling edge with service inputs, then rising edge. */
    void period(std::uint64_t step) {
        model.capture_clock = 0;
        service();
        half_step(2 * step);
        const std::uint64_t tick = model.counter_ticks;
        const auto actuator = static_cast<std::int32_t>(model.actuator_value);
        interrupt(tick);
        if (declared.fault_periods && first != UINT64_MAX &&
            tick == first + declared.fault_cycle * declared.period)
            waiting = true;
        model.capture_clock = 1;
        half_step(2 * step + 1);
        observe(tick, actuator);
    }
};

/** Release reset, arm the declared fault and enable the run, as the integrated testbench does. */
std::uint64_t start(Harness &harness, Vcontrol_plant_witness &model, const Stimulus &declared) {
    model.capture_clock = 0;
    model.drain_clock = 0;
    model.run_reset_n = 0;
    model.enable = 0;
    model.fault_arm = 0;
    model.pps_in = 0; // no reference pulse: the harness records control events only
    model.reference_offset = 0;
    model.ramp_increment = 0;
    model.command_value = 0;
    model.stop_after_cycle = static_cast<std::uint32_t>(declared.cycles - 1);
    model.drain_request = 1;
    model.reference_mode = static_cast<std::uint8_t>(declared.reference_mode);
    model.reference_amplitude = static_cast<std::uint32_t>(declared.reference_amplitude);
    model.phase_increment = static_cast<std::uint8_t>(declared.phase_increment);
    model.fault_kind = 1; // delay: the service blocks until the delayed interrupt arrives
    model.fault_cycle = static_cast<std::uint32_t>(declared.fault_cycle);
    model.fault_periods = static_cast<std::uint32_t>(declared.fault_periods);
    std::uint64_t step = 0;
    for (; step < 4; ++step)
        harness.period(step);
    model.run_reset_n = 1;
    while (!model.capture_active) {
        harness.period(step++);
        if (step > 64)
            throw Refused("capture domain did not leave reset");
    }
    model.fault_arm = declared.fault_periods != 0;
    harness.period(step++);
    model.fault_arm = 0;
    model.enable = 1;
    return step;
}

/** Run every declared cycle and drain until quiescent; return the JSON summary line. */
std::string run(const Stimulus &declared, std::FILE *events, std::FILE *trajectory) {
    VerilatedContext context;
    Vcontrol_plant_witness model{&context};
    Harness harness(declared, model, events, trajectory);
    std::uint64_t step = start(harness, model, declared), settled = 0;
    const std::uint64_t limit = (declared.cycles + 16) * declared.period;
    while (settled < 64) {
        harness.period(step++);
        settled =
            model.run_finished && model.capture_quiescent && model.drain_empty ? settled + 1 : 0;
        if (model.counter_ticks > limit)
            throw Refused("run did not finish within its declared duration");
    }
    if (model.overflow_count || harness.totals.buffer_full)
        throw Refused("event FIFO lost records");
    if (harness.totals.rows != declared.cycles)
        throw Refused("trajectory does not hold one row per cycle");
    const std::string summary = "{\"cycles\": " + std::to_string(declared.cycles) +
                                ", \"records\": " + std::to_string(harness.totals.records) +
                                ", \"misses\": " + std::to_string(model.total_misses) +
                                ", \"late_commands\": " + std::to_string(model.late_commands) +
                                ", \"skipped_writes\": " + std::to_string(harness.totals.skipped) +
                                ", \"overflow\": " + std::to_string(model.overflow_count) +
                                ", \"safe\": " + (model.safe_interrupt ? "true" : "false") +
                                ", \"ticks\": " + std::to_string(model.counter_ticks) + "}\n";
    model.final();
    return summary;
}

} // namespace

/** Write events.bin and the raw trajectory for one declared closed-loop run. */
int main(int argc, char **argv) {
    if (argc < 3) {
        std::fputs("usage: closed_loop_harness events.bin trajectory.csv key=value...\n", stderr);
        return 1;
    }
    std::FILE *events = nullptr, *trajectory = nullptr;
    try {
        const Stimulus declared = stimulus(arguments(argc, argv, 3));
        events = std::fopen(argv[1], "wb");
        trajectory = std::fopen(argv[2], "w");
        if (!events || !trajectory)
            throw Refused("cannot open the output files");
        std::fputs("cycle,reference,output,velocity,actuator,ticks\n", trajectory);
        const std::string summary = run(declared, events, trajectory);
        const bool closed = std::fclose(events) == 0;
        events = nullptr;
        if (!closed || std::fclose(std::exchange(trajectory, nullptr)) != 0)
            throw Refused("cannot close the output files");
        // The summary is printed only once both outputs are complete on disk.
        if (std::fputs(summary.c_str(), stdout) == EOF || std::fflush(stdout) != 0)
            throw Refused("cannot write the summary");
        return 0;
    } catch (const Refused &error) {
        if (events)
            std::fclose(events);
        if (trajectory)
            std::fclose(trajectory);
        std::fprintf(stderr, "%s\n", error.what());
        return 1;
    }
}
