// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fabric controller integrated with plant monitor and drain stream

// Vendor-neutral fabric entry point. Register/bus adapters are separate work.
// All command and fault inputs belong to capture_clock and hold through its edge.
// enable must stay high until stop_after_cycle closes the requested final cycle.
module fabric_control_witness #(
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
    parameter logic signed [31:0] THERMAL_B = 32'sd16769,
    parameter bit LQR = 1'b0,
    parameter logic signed [31:0] KP = 32'sd33554432,
    parameter logic signed [31:0] KI_PERIOD = 32'sd16777,
    parameter logic signed [31:0] DERIVATIVE_DECAY = 32'sd8388608,
    parameter logic signed [31:0] DERIVATIVE_GAIN = 32'sd4194304,
    parameter logic signed [31:0] POSITION_GAIN = THERMAL ? 32'sd6944437 : 32'sd38822697,
    parameter logic signed [31:0] VELOCITY_GAIN = THERMAL ? 32'sd0 : 32'sd26419076,
    parameter logic signed [31:0] REFERENCE_GAIN = THERMAL ? 32'sd23721653 : 32'sd55599913,
    parameter logic signed [31:0] OUTPUT_MIN = -32'sd67108864,
    parameter logic signed [31:0] OUTPUT_MAX = 32'sd67108864,
    parameter logic signed [31:0] INTEGRAL_MIN = -32'sd33554432,
    parameter logic signed [31:0] INTEGRAL_MAX = 32'sd33554432
) (
    input logic capture_clock, drain_clock, run_reset_n, enable,
    input logic [31:0] stop_after_cycle,
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
    output logic controller_config_valid, controller_clipped, controller_integral_held,
    output logic signed [31:0] controller_integral, controller_derivative,
    output logic safe_interrupt, fault_ready, freeze_actuator, overload_request,
    output logic run_finished, capture_quiescent,
    output logic [31:0] total_misses, consecutive_misses, late_commands, overflow_count,
    output logic [63:0] counter_ticks,
    input logic drain_request,
    output logic drain_valid, drain_empty,
    output logic [127:0] drain_record
);
    logic controller_write, controller_read;
    logic [31:0] controller_cycle;
    logic signed [31:0] controller_command;
    assign controller_read = sample_valid && controller_config_valid &&
        !safe_interrupt && !freeze_actuator;
    fixed_point_controller controller (
        .clock(capture_clock), .reset_n(capture_active), .sample_valid(controller_read),
        .lqr_mode(LQR), .sample_cycle(cycle_number), .reference_value(reference_value),
        .position(sample_value), .velocity(velocity), .kp(KP), .ki_period(KI_PERIOD),
        .derivative_decay(DERIVATIVE_DECAY), .derivative_gain(DERIVATIVE_GAIN),
        .position_gain(POSITION_GAIN), .velocity_gain(VELOCITY_GAIN), .reference_gain(REFERENCE_GAIN),
        .output_min(OUTPUT_MIN), .output_max(OUTPUT_MAX),
        .integral_min(INTEGRAL_MIN), .integral_max(INTEGRAL_MAX),
        .coefficients_valid(controller_config_valid), .output_valid(controller_write),
        .command_cycle(controller_cycle), .command(controller_command),
        .integral_state(controller_integral), .derivative_state(controller_derivative),
        .clipped(controller_clipped), .integral_held(controller_integral_held)
    );
    control_plant_witness #(
        .PERIOD_TICKS(PERIOD_TICKS),
        .MISS_LIMIT(MISS_LIMIT),
        .SAFE_VALUE(SAFE_VALUE),
        .THERMAL(THERMAL),
        .ADDRESS_BITS(ADDRESS_BITS),
        .GROUP_ADDRESS_BITS(GROUP_ADDRESS_BITS),
        .A00(A00),
        .A01(A01),
        .A10(A10),
        .A11(A11),
        .B0(B0),
        .B1(B1),
        .THERMAL_A(THERMAL_A),
        .THERMAL_B(THERMAL_B)
    ) instrument (
        .capture_clock(capture_clock),
        .drain_clock(drain_clock),
        .run_reset_n(run_reset_n),
        .enable(enable),
        .stop_after_cycle(stop_after_cycle),
        .fault_arm(fault_arm),
        .fault_kind(fault_kind),
        .fault_cycle(fault_cycle),
        .fault_periods(fault_periods),
        .reference_mode(reference_mode),
        .reference_amplitude(reference_amplitude),
        .reference_offset(reference_offset),
        .ramp_increment(ramp_increment),
        .phase_increment(phase_increment),
        .buffer_full(buffer_full),
        .capture_active(capture_active),
        .sample_valid(sample_valid),
        .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt),
        .cycle_number(cycle_number),
        .delayed_cycle(delayed_cycle),
        .sample_value(sample_value),
        .velocity(velocity),
        .reference_value(reference_value),
        .actuator_value(actuator_value),
        .plant_clipped(plant_clipped),
        .reference_clipped(reference_clipped),
        .safe_interrupt(safe_interrupt),
        .fault_ready(fault_ready),
        .freeze_actuator(freeze_actuator),
        .overload_request(overload_request),
        .total_misses(total_misses),
        .consecutive_misses(consecutive_misses),
        .late_commands(late_commands),
        .overflow_count(overflow_count),
        .counter_ticks(counter_ticks),
        .drain_request(drain_request),
        .drain_valid(drain_valid),
        .drain_empty(drain_empty), .run_finished(run_finished), .capture_quiescent(capture_quiescent),
        .drain_record(drain_record),
        .sample_read(controller_read), .actuator_write(controller_write),
        .command_cycle(controller_cycle), .command_value(controller_command)
    );
endmodule
