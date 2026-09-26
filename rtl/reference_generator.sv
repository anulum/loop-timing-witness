// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — step ramp and sampled sine reference

// mode: 0 step, 1 ramp, 2 sine; unsupported modes report zero amplitude.
// First sample uses phase zero / ramp zero, then advances once per sample.
module reference_generator (
    input logic clock, reset_n, sample_tick,
    input logic [1:0] mode,
    input logic signed [31:0] amplitude, offset, ramp_increment,
    input logic [3:0] phase_increment,
    output logic signed [31:0] reference_value,
    output logic clipped
);
    logic [3:0] phase;
    logic signed [31:0] ramp, waveform, sine_value;
    logic signed [32:0] ramp_next;
    logic signed [31:0] generated;
    logic generated_clip;
    always_comb begin
        case (phase)
            4'd0: sine_value = 32'sd0;
            4'd1: sine_value = 32'sd6420363;
            4'd2: sine_value = 32'sd11863283;
            4'd3: sine_value = 32'sd15500126;
            4'd4: sine_value = 32'sd16777216;
            4'd5: sine_value = 32'sd15500126;
            4'd6: sine_value = 32'sd11863283;
            4'd7: sine_value = 32'sd6420363;
            4'd8: sine_value = 32'sd0;
            4'd9: sine_value = -32'sd6420363;
            4'd10: sine_value = -32'sd11863283;
            4'd11: sine_value = -32'sd15500126;
            4'd12: sine_value = -32'sd16777216;
            4'd13: sine_value = -32'sd15500126;
            4'd14: sine_value = -32'sd11863283;
            4'd15: sine_value = -32'sd6420363;
        endcase
        case (mode)
            2'd0: waveform = 32'sd16777216;
            2'd1: waveform = ramp;
            2'd2: waveform = sine_value;
            default: waveform = '0;
        endcase
    end
    // Dynamic amplitude uses the same wide, floor-and-saturate convention.
    logic signed [63:0] product;
    logic signed [64:0] product_scaled, shifted;
    assign product = waveform * amplitude;
    assign product_scaled = $signed({product[63], product}) >>> 24;
    assign shifted = product_scaled + $signed({{33{offset[31]}}, offset});
    always_comb begin
        generated_clip = 1'b1;
        if (shifted > 65'sd2147483647) generated = 32'sh7fffffff;
        else if (shifted < -65'sd2147483648) generated = 32'sh80000000;
        else begin
            generated = shifted[31:0];
            generated_clip = 1'b0;
        end
    end
    assign ramp_next = {ramp[31], ramp} + {ramp_increment[31], ramp_increment};
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            phase <= '0;
            ramp <= '0;
            reference_value <= '0;
            clipped <= 1'b0;
        end else if (sample_tick) begin
            reference_value <= generated;
            clipped <= generated_clip;
            phase <= phase + phase_increment;
            if (ramp_next > 33'sd2147483647) ramp <= 32'sh7fffffff;
            else if (ramp_next < -33'sd2147483648) ramp <= 32'sh80000000;
            else ramp <= ramp_next[31:0];
        end
    end
endmodule
