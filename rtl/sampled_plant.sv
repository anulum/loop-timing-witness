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
module sampled_plant #(
    parameter bit THERMAL = 1'b0,
    parameter logic signed [31:0] A00 = 32'sd16777208,
    parameter logic signed [31:0] A01 = 32'sd16769,
    parameter logic signed [31:0] A10 = -32'sd16769,
    parameter logic signed [31:0] A11 = 32'sd16760439,
    parameter logic signed [31:0] B0 = 32'sd8,
    parameter logic signed [31:0] B1 = 32'sd16769,
    parameter logic signed [31:0] THERMAL_A = 32'sd16760447,
    parameter logic signed [31:0] THERMAL_B = 32'sd16769
) (
    input logic clock, reset_n, sample_tick,
    input logic signed [31:0] actuator,
    output logic signed [31:0] output_value, velocity,
    output logic clipped
);
    logic signed [31:0] next_output, next_velocity;
    logic clip_output, clip_velocity;
    fixed_point_math #(.A(THERMAL ? THERMAL_A : A00),
        .B(THERMAL ? 32'sd0 : A01), .C(THERMAL ? THERMAL_B : B0)) position_step (
        .x(output_value), .y(velocity), .u(actuator), .result(next_output), .clipped(clip_output)
    );
    fixed_point_math #(.A(THERMAL ? 32'sd0 : A10), .B(THERMAL ? 32'sd0 : A11),
        .C(THERMAL ? 32'sd0 : B1)) velocity_step (
        .x(output_value), .y(velocity), .u(actuator), .result(next_velocity), .clipped(clip_velocity)
    );
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            output_value <= '0;
            velocity <= '0;
            clipped <= 1'b0;
        end else if (sample_tick) begin
            output_value <= next_output;
            velocity <= next_velocity;
            clipped <= clip_output || clip_velocity;
        end
    end
endmodule
