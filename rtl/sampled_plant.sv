// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — mechanical and thermal sampled plants

// Default ZOH coefficients: m=c=k=tau=gain=1; sample period 1 ms.
// THERMAL selects theta[k+1]=THERMAL_A*theta[k]+THERMAL_B*u[k].
// Mechanical updates both old states together. Reset starts at rest.
// The applied actuator u is the actuator_command of the latest edge with
// actuator_load (zero after reset), or SAFE_VALUE in a cycle with actuator_safe.
// Products of the state and of the held actuator are registered one edge ahead:
// sample_tick must never be high in two consecutive cycles.
module sampled_plant #(
    parameter bit THERMAL = 1'b0,
    parameter logic signed [31:0] A00 = 32'sd16777208,
    parameter logic signed [31:0] A01 = 32'sd16769,
    parameter logic signed [31:0] A10 = -32'sd16769,
    parameter logic signed [31:0] A11 = 32'sd16760439,
    parameter logic signed [31:0] B0 = 32'sd8,
    parameter logic signed [31:0] B1 = 32'sd16769,
    parameter logic signed [31:0] THERMAL_A = 32'sd16760447,
    parameter logic signed [31:0] THERMAL_B = 32'sd16769,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0
) (
    input logic clock, reset_n, sample_tick,
    input logic actuator_load, actuator_safe,
    input logic signed [31:0] actuator_command,
    output logic signed [31:0] output_value, velocity,
    output logic clipped
);
    localparam logic signed [31:0] POSITION_A = THERMAL ? THERMAL_A : A00;
    localparam logic signed [31:0] POSITION_B = THERMAL ? 32'sd0 : A01;
    localparam logic signed [31:0] POSITION_C = THERMAL ? THERMAL_B : B0;
    localparam logic signed [31:0] VELOCITY_A = THERMAL ? 32'sd0 : A10;
    localparam logic signed [31:0] VELOCITY_B = THERMAL ? 32'sd0 : A11;
    localparam logic signed [31:0] VELOCITY_C = THERMAL ? 32'sd0 : B1;
    // Signed operands widen to the 64-bit context; the exact products fit.
    localparam logic signed [63:0] POSITION_SAFE = POSITION_C * SAFE_VALUE;
    localparam logic signed [63:0] VELOCITY_SAFE = VELOCITY_C * SAFE_VALUE;
    logic signed [63:0] position_ax, position_by, position_cu, position_applied;
    logic signed [63:0] velocity_ax, velocity_by, velocity_cu, velocity_applied;
    logic signed [31:0] next_output, next_velocity, actuator_held, actuator_next;
    logic clip_output, clip_velocity;
    // The actuator products load the value held after this edge, so a command loaded in
    // the cycle before a sample reaches that sample.
    assign actuator_next = actuator_load ? actuator_command : actuator_held;
    split_multiplier position_x (
        .clock(clock), .reset_n(reset_n), .multiplicand(POSITION_A),
        .multiplier(output_value), .product(position_ax)
    );
    split_multiplier position_y (
        .clock(clock), .reset_n(reset_n), .multiplicand(POSITION_B),
        .multiplier(velocity), .product(position_by)
    );
    split_multiplier position_u (
        .clock(clock), .reset_n(reset_n), .multiplicand(POSITION_C),
        .multiplier(actuator_next), .product(position_cu)
    );
    split_multiplier velocity_x (
        .clock(clock), .reset_n(reset_n), .multiplicand(VELOCITY_A),
        .multiplier(output_value), .product(velocity_ax)
    );
    split_multiplier velocity_y (
        .clock(clock), .reset_n(reset_n), .multiplicand(VELOCITY_B),
        .multiplier(velocity), .product(velocity_by)
    );
    split_multiplier velocity_u (
        .clock(clock), .reset_n(reset_n), .multiplicand(VELOCITY_C),
        .multiplier(actuator_next), .product(velocity_cu)
    );
    assign position_applied = actuator_safe ? POSITION_SAFE : position_cu;
    assign velocity_applied = actuator_safe ? VELOCITY_SAFE : velocity_cu;
    fixed_point_math position_step (
        .ax(position_ax), .by(position_by), .cu(position_applied),
        .result(next_output), .clipped(clip_output)
    );
    fixed_point_math velocity_step (
        .ax(velocity_ax), .by(velocity_by), .cu(velocity_applied),
        .result(next_velocity), .clipped(clip_velocity)
    );
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            output_value <= '0;
            velocity <= '0;
            clipped <= 1'b0;
            actuator_held <= '0;
        end else begin
            actuator_held <= actuator_next;
            if (sample_tick) begin
                output_value <= next_output;
                velocity <= next_velocity;
                clipped <= clip_output || clip_velocity;
            end
        end
    end
endmodule
