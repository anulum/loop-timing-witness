// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — conditional-integration PID and full-state discrete LQR

// All coefficients are signed raw Q8.24 and held stable until reset. Configured
// bounds must contain zero, so reset is an admissible integral/output boundary.
// One accepted sample per edge; output_valid is registered on that edge with its
// cycle tag. Wide accumulation precedes floor scaling and boundary saturation.
module fixed_point_controller (
    input logic clock, reset_n, sample_valid, lqr_mode,
    input logic [31:0] sample_cycle,
    input logic signed [31:0] reference_value, position, velocity,
    input logic signed [31:0] kp, ki_period, derivative_decay, derivative_gain,
    input logic signed [31:0] position_gain, velocity_gain, reference_gain,
    input logic signed [31:0] output_min, output_max, integral_min, integral_max,
    output logic coefficients_valid, output_valid,
    output logic [31:0] command_cycle,
    output logic signed [31:0] command, integral_state, derivative_state,
    output logic clipped, integral_held
);
    localparam logic signed [95:0] SCALE = 96'sd16777216;
    localparam logic signed [31:0] MINIMUM = 32'sh80000000;
    localparam logic signed [31:0] MAXIMUM = 32'sh7fffffff;
    logic initialized;
    logic signed [31:0] previous_position;
    logic signed [31:0] next_derivative, proposed_integral, next_integral;
    logic signed [95:0] error, difference, derivative_raw, integral_raw;
    logic signed [95:0] proportional, provisional, final_raw;
    logic hold_integral;

    // Extend before multiplying or subtracting to preserve 33-bit differences.
    function automatic logic signed [95:0] wide(input logic signed [31:0] value);
        wide = {{64{value[31]}}, value};
    endfunction

    // Clamp only after the complete signed accumulation and floor scaling.
    function automatic logic signed [31:0] clamp(
        input logic signed [95:0] value,
        input logic signed [31:0] lower, upper
    );
        if (value < wide(lower)) clamp = lower;
        else if (value > wide(upper)) clamp = upper;
        else clamp = value[31:0];
    endfunction

    always_comb begin
        coefficients_valid = output_min <= output_max && integral_min <= integral_max &&
            output_min <= 0 && output_max >= 0 && integral_min <= 0 && integral_max >= 0 &&
            kp >= 0 && ki_period >= 0 && derivative_gain >= 0 &&
            derivative_decay >= 0 && derivative_decay <= 32'sd16777216;
        error = wide(reference_value) - wide(position);
        difference = wide(position) - wide(previous_position);
        derivative_raw = (wide(derivative_decay) * wide(derivative_state) -
                          wide(derivative_gain) * difference) >>> 24;
        next_derivative = initialized ? clamp(derivative_raw, MINIMUM, MAXIMUM) : 32'sd0;
        integral_raw = (wide(integral_state) * SCALE + wide(ki_period) * error) >>> 24;
        proposed_integral = clamp(integral_raw, integral_min, integral_max);
        proportional = wide(kp) * error;
        provisional = (proportional + wide(integral_state) * SCALE +
                       wide(next_derivative) * SCALE) >>> 24;
        hold_integral = (provisional >= wide(output_max) && error > 0) ||
                        (provisional <= wide(output_min) && error < 0);
        next_integral = hold_integral ? integral_state : proposed_integral;
        if (lqr_mode)
            final_raw = (wide(reference_gain) * wide(reference_value) -
                         wide(position_gain) * wide(position) -
                         wide(velocity_gain) * wide(velocity)) >>> 24;
        else
            final_raw = (proportional + wide(next_integral) * SCALE +
                         wide(next_derivative) * SCALE) >>> 24;
    end

    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            initialized <= 1'b0;
            previous_position <= '0;
            command_cycle <= '0;
            command <= '0;
            integral_state <= '0;
            derivative_state <= '0;
            output_valid <= 1'b0;
            clipped <= 1'b0;
            integral_held <= 1'b0;
        end else begin
            output_valid <= sample_valid && coefficients_valid;
            if (sample_valid && coefficients_valid) begin
                command_cycle <= sample_cycle;
                command <= clamp(final_raw, output_min, output_max);
                clipped <= final_raw < wide(output_min) || final_raw > wide(output_max);
                integral_held <= !lqr_mode && hold_integral;
                if (!lqr_mode) begin
                    initialized <= 1'b1;
                    previous_position <= position;
                    integral_state <= next_integral;
                    derivative_state <= next_derivative;
                end
            end
        end
    end
endmodule
