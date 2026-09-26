// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fixed-point and reference edge cases

`timescale 1ns/1ps
module plant_arithmetic_tb;
    logic clock = 0, reset_n = 0, sample_tick = 0;
    logic signed [31:0] x = 0, y = 0, u = 0, sum;
    logic clipped;
    logic [1:0] mode = 0;
    logic signed [31:0] amplitude = 32'sd16777216, offset = 0, ramp_increment = 32'sd16777216;
    logic [3:0] phase_increment = 1;
    logic signed [31:0] reference_value;
    logic reference_clipped;
    logic signed [31:0] saturated_output, saturated_velocity;
    logic plant_clip;
    sampled_plant #(.A00(32'sd16777216), .A01(32'sd0), .A10(32'sd0),
        .A11(32'sd16777216), .B0(32'sd16777216), .B1(32'sd16777216)) clipping_plant (
        .clock(clock), .reset_n(reset_n), .sample_tick(sample_tick), .actuator(u),
        .output_value(saturated_output), .velocity(saturated_velocity), .clipped(plant_clip)
    );
    integer index;
    fixed_point_math #(.A(32'sd16777216), .B(32'sd16777216), .C(32'sd16777216)) arithmetic (
        .x(x), .y(y), .u(u), .result(sum), .clipped(clipped)
    );
    reference_generator reference_source (
        .clock(clock), .reset_n(reset_n), .sample_tick(sample_tick), .mode(mode),
        .amplitude(amplitude), .offset(offset), .ramp_increment(ramp_increment),
        .phase_increment(phase_increment), .reference_value(reference_value), .clipped(reference_clipped)
    );
    always #5 clock = ~clock;
    task automatic sample;
        begin
            @(negedge clock); sample_tick = 1;
            @(negedge clock); sample_tick = 0;
            $display("REFERENCE mode=%0d value=%0d clipped=%0d", mode, reference_value, reference_clipped);
        end
    endtask
    task automatic restart;
        begin
            @(negedge clock); reset_n = 0;
            @(negedge clock); reset_n = 1;
        end
    endtask
    initial begin
        x = 32'sh7fffffff; y = 1; #1;
        if (sum != 32'sh7fffffff || !clipped) $fatal(1, "positive saturation failed");
        x = 32'sh80000000; y = -1; #1;
        if (sum != 32'sh80000000 || !clipped) $fatal(1, "negative saturation failed");
        x = -25; y = 12; u = 3; #1;
        if (sum != -10 || clipped) $fatal(1, "signed sum failed");
        u = 32'sh7fffffff;
        restart(); sample(); sample();
        if (saturated_output != 32'sh7fffffff || saturated_velocity != 32'sh7fffffff || !plant_clip)
            $fatal(1, "plant positive clipping not signalled");
        u = 32'sh80000000;
        restart(); sample(); sample();
        if (saturated_output != 32'sh80000000 || saturated_velocity != 32'sh80000000 || !plant_clip)
            $fatal(1, "plant negative clipping not signalled");
        u = 0;
        restart(); sample();
        mode = 2;
        restart();
        for (index = 0; index < 16; index = index + 1) sample();
        mode = 1;
        restart();
        for (index = 0; index < 4; index = index + 1) sample();
        ramp_increment = 32'sh7fffffff;
        restart(); sample(); sample(); sample();
        ramp_increment = 32'sh80000000;
        restart(); sample(); sample(); sample();
        mode = 0; amplitude = 32'sh7fffffff; offset = 1;
        restart(); sample();
        amplitude = 32'sh80000000; offset = -1;
        sample();
        mode = 3; offset = 0;
        sample();
        mode = 2; amplitude = 32'sd8388608; phase_increment = 3;
        restart(); sample(); sample(); sample(); sample();
        // Negative fractional product floors, rather than truncating to zero.
        if (reference_value != -32'sd3210182) $fatal(1, "negative fractional scaling");
        restart();
        if (reference_value || reference_clipped) $fatal(1, "reference reset failed");
        $display("ARITHMETIC_PASS");
        $finish;
    end
endmodule
