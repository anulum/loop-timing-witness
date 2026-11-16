// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — invariants behind the one-edge plant and reference products

// The plant and reference register their products one edge before a sample. These
// wrappers prove, from an unconstrained state across non-reset steps, the three facts
// that make the sampled values equal to a same-cycle product. NEGATIVE_CONTROL asserts
// the opposite conclusion, which must yield a counterexample.

// Consecutive capture cycles never both sample, so the plant state, phase and ramp
// (loaded only by sample_tick) are unchanged over the edge before every sample.
module plant_spacing_proof #(
    parameter logic [31:0] PERIOD_TICKS = 32'd2,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic capture_clock, reset_n, enable,
    input logic [31:0] stop_after_cycle, command_cycle,
    input logic sample_read, actuator_write,
    input logic signed [31:0] command_value,
    input logic freeze_actuator, safe_interrupt, trip_now, injected
);
    wire finished, sample_tick, deadline, timely_write, sample_valid, actuator_accept;
    wire [31:0] cycle_number, sample_cycle, late_commands;
    wire signed [31:0] actuator_value;
    wire [7:0] event_mask;
    wire [255:0] event_cycles;
    logic observed = 0;
    control_cycle #(.PERIOD_TICKS(PERIOD_TICKS)) dut (.*);
    always @(posedge capture_clock) begin
        observed <= 1;
        if (observed && reset_n && $past(reset_n) && sample_tick)
            assert (NEGATIVE_CONTROL ? $past(sample_tick) : !$past(sample_tick));
    end
endmodule

// The plant's held actuator (loaded on actuator_accept, zero after reset) equals
// actuator_value until the safe latch sets; from then on every sample applies SAFE_VALUE.
module plant_actuator_proof #(
    parameter logic signed [31:0] SAFE_VALUE = 32'sd5,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic capture_clock, reset_n, enable,
    input logic [31:0] stop_after_cycle, command_cycle,
    input logic sample_read, actuator_write,
    input logic signed [31:0] command_value,
    input logic freeze_actuator, injected
);
    wire finished, sample_tick, deadline, timely_write, sample_valid, actuator_accept;
    wire trip_now, safe_interrupt;
    wire [31:0] cycle_number, sample_cycle, late_commands, total_misses, consecutive_misses;
    wire signed [31:0] actuator_value;
    wire [7:0] event_mask;
    wire [255:0] event_cycles;
    logic signed [31:0] held;
    logic observed = 0;
    control_cycle #(.PERIOD_TICKS(32'd2), .SAFE_VALUE(SAFE_VALUE)) cycle (.*);
    deadline_monitor monitor (
        .clock(capture_clock), .reset_n(reset_n), .cycle_start(sample_tick),
        .deadline(deadline), .timely_write(timely_write), .trip_now(trip_now),
        .safe_latched(safe_interrupt), .total_misses(total_misses),
        .consecutive_misses(consecutive_misses)
    );
    // The same next-value rule as sampled_plant's actuator_held.
    always @(posedge capture_clock or negedge reset_n) begin
        if (!reset_n) held <= '0;
        else if (actuator_accept) held <= command_value;
    end
    always @(posedge capture_clock) begin
        observed <= 1;
        if (observed && reset_n && !$past(reset_n)) assert (held == actuator_value);
        if (observed && reset_n && $past(reset_n)
            && ($past(held) == $past(actuator_value) || $past(safe_interrupt)))
            assert (NEGATIVE_CONTROL ? held != actuator_value && !safe_interrupt
                : held == actuator_value || safe_interrupt);
        if (observed && reset_n && $past(reset_n) && $past(safe_interrupt))
            assert (safe_interrupt);
    end
endmodule

// reference_mode and reference_amplitude never change over an edge into an enabled
// cycle: they are written only while disabled, and enabling is a separate write.
module plant_configuration_proof #(
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic capture_clock, reset_n, capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    input logic fault_ready, freeze_actuator, overload_request
);
    wire [31:0] capture_read_data, stop_after_cycle, fault_cycle, fault_periods;
    wire [1:0] capture_response, reference_mode, fault_kind;
    wire run_enabled, fault_arm;
    wire signed [31:0] reference_amplitude, reference_offset, ramp_increment;
    wire [3:0] phase_increment;
    logic observed = 0;
    run_configuration_registers dut (.*);
    always @(posedge capture_clock) begin
        observed <= 1;
        if (observed && reset_n && $past(reset_n) && run_enabled)
            assert (NEGATIVE_CONTROL
                ? reference_mode != $past(reference_mode)
                    || reference_amplitude != $past(reference_amplitude)
                : reference_mode == $past(reference_mode)
                    && reference_amplitude == $past(reference_amplitude));
    end
endmodule
