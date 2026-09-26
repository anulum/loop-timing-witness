// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — integrated plant monitor injector and event witness

// Vendor-neutral fabric entry point. Register/bus adapters are separate work.
// All command and fault inputs belong to capture_clock and hold through its edge.
// enable must stay high until stop_after_cycle closes the requested final cycle.
module control_plant_witness #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0,
    parameter bit THERMAL = 1'b0,
    parameter int ADDRESS_BITS = 14,
    parameter int GROUP_ADDRESS_BITS = 6,
    parameter logic signed [31:0] A00 = 32'sd16777208,
    parameter logic signed [31:0] A01 = 32'sd16769,
    parameter logic signed [31:0] A10 = -32'sd16769,
    parameter logic signed [31:0] A11 = 32'sd16760439,
    parameter logic signed [31:0] B0 = 32'sd8,
    parameter logic signed [31:0] B1 = 32'sd16769,
    parameter logic signed [31:0] THERMAL_A = 32'sd16760447,
    parameter logic signed [31:0] THERMAL_B = 32'sd16769
) (
    input logic capture_clock, drain_clock, run_reset_n, enable,
    input logic [31:0] stop_after_cycle,
    input logic sample_read, actuator_write,
    input logic [31:0] command_cycle,
    input logic signed [31:0] command_value,
    input logic fault_arm,
    input logic [1:0] fault_kind,
    input logic [31:0] fault_cycle, fault_periods,
    input logic [1:0] reference_mode,
    input logic signed [31:0] reference_amplitude, reference_offset, ramp_increment,
    input logic [3:0] phase_increment,
    output logic buffer_full, capture_active, sample_valid, sample_interrupt, delayed_interrupt,
    output logic [31:0] cycle_number, delayed_cycle,
    output logic signed [31:0] sample_value, velocity, reference_value, actuator_value,
    output logic plant_clipped, reference_clipped,
    output logic safe_interrupt, fault_ready, freeze_actuator, overload_request,
    output logic [31:0] total_misses, consecutive_misses, late_commands, overflow_count,
    output logic [63:0] counter_ticks,
    input logic drain_request,
    output logic drain_valid, drain_empty,
    output logic [127:0] drain_record
);
    logic reset_n, drain_reset_n, injector_ready;
    logic finished;
    logic [31:0] sample_cycle;
    logic sample_tick, deadline, trip_now, injected, timely_write;
    logic [7:0] event_mask;
    logic [255:0] event_cycles;
    logic record_valid, record_ready;
    logic [127:0] record;
    logic signed [31:0] plant_actuator;
    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(run_reset_n), .local_reset_n(reset_n)
    );
    clock_reset_release drain_reset (
        .clock(drain_clock), .run_reset_n(run_reset_n), .local_reset_n(drain_reset_n)
    );
    assign capture_active = reset_n;
    assign fault_ready = injector_ready && !safe_interrupt && !trip_now && !finished;
    control_cycle #(.PERIOD_TICKS(PERIOD_TICKS), .SAFE_VALUE(SAFE_VALUE)) cycle_registers (
        .capture_clock(capture_clock), .reset_n(reset_n), .enable(enable),
        .stop_after_cycle(stop_after_cycle), .sample_read(sample_read), .actuator_write(actuator_write),
        .command_cycle(command_cycle), .command_value(command_value), .freeze_actuator(freeze_actuator),
        .safe_interrupt(safe_interrupt), .trip_now(trip_now), .injected(injected), .finished(finished),
        .sample_tick(sample_tick), .deadline(deadline), .timely_write(timely_write),
        .sample_valid(sample_valid), .cycle_number(cycle_number), .sample_cycle(sample_cycle),
        .late_commands(late_commands), .actuator_value(actuator_value), .plant_actuator(plant_actuator),
        .event_mask(event_mask), .event_cycles(event_cycles)
    );
    deadline_monitor #(.MISS_LIMIT(MISS_LIMIT)) monitor (
        .clock(capture_clock), .reset_n(reset_n), .cycle_start(sample_tick),
        .deadline(deadline), .timely_write(timely_write), .trip_now(trip_now),
        .safe_latched(safe_interrupt), .total_misses(total_misses),
        .consecutive_misses(consecutive_misses)
    );
    fault_injector #(.PERIOD_TICKS(PERIOD_TICKS)) injector (
        .clock(capture_clock), .reset_n(reset_n), .sample_tick(sample_tick && !safe_interrupt && !trip_now),
        .sample_cycle(sample_cycle), .arm(fault_arm && fault_ready && fault_cycle <= stop_after_cycle), .kind(fault_kind),
        .target_cycle(fault_cycle), .duration_periods(fault_periods), .arm_ready(injector_ready),
        .injected(injected), .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt), .delayed_cycle(delayed_cycle),
        .freeze_actuator(freeze_actuator), .overload_request(overload_request)
    );
    sampled_plant #(.THERMAL(THERMAL), .A00(A00), .A01(A01), .A10(A10), .A11(A11),
        .B0(B0), .B1(B1), .THERMAL_A(THERMAL_A), .THERMAL_B(THERMAL_B)) plant (
        .clock(capture_clock), .reset_n(reset_n), .sample_tick(sample_tick),
        .actuator(plant_actuator), .output_value(sample_value), .velocity(velocity),
        .clipped(plant_clipped)
    );
    reference_generator reference_source (
        .clock(capture_clock), .reset_n(reset_n), .sample_tick(sample_tick),
        .mode(reference_mode), .amplitude(reference_amplitude), .offset(reference_offset),
        .ramp_increment(ramp_increment), .phase_increment(phase_increment),
        .reference_value(reference_value), .clipped(reference_clipped)
    );
    control_event_capture #(.GROUP_ADDRESS_BITS(GROUP_ADDRESS_BITS)) capture (
        .clock(capture_clock), .reset_n(reset_n), .event_mask(event_mask),
        .event_cycles(event_cycles), .counter_ticks(counter_ticks), .record_valid(record_valid),
        .record(record), .record_ready(record_ready), .overflow_count(overflow_count)
    );
    event_record_fifo #(.ADDRESS_BITS(ADDRESS_BITS)) buffer (
        .write_clock(capture_clock), .write_reset_n(reset_n), .write_valid(record_valid),
        .write_data(record), .write_ready(record_ready), .write_full(buffer_full),
        .read_clock(drain_clock), .read_reset_n(drain_reset_n), .read_request(drain_request),
        .read_valid(drain_valid), .read_data(drain_record), .read_empty(drain_empty)
    );
endmodule
