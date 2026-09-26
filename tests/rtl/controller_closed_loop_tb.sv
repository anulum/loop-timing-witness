// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — long functional controller and plant feedback trajectories

module controller_closed_loop_tb #(
    parameter bit THERMAL = 1'b0,
    parameter bit LQR = 1'b0
);
    localparam integer SAMPLES = 64000;
    logic clock = 1'b0, reset_n = 1'b0, sample_tick = 1'b0, sample_valid = 1'b0;
    always #5 clock = !clock;
    logic [31:0] sample_cycle = 0, command_cycle;
    logic signed [31:0] position, velocity, actuator = 0;
    logic signed [31:0] command, integral_state, derivative_state;
    logic clipped, integral_held, plant_clipped, output_valid, coefficients_valid;
    wire signed [31:0] position_gain = THERMAL ? 32'sd6944437 : 32'sd38822697;
    wire signed [31:0] velocity_gain = THERMAL ? 32'sd0 : 32'sd26419076;
    wire signed [31:0] reference_gain = THERMAL ? 32'sd23721653 : 32'sd55599913;
    fixed_point_controller controller (
        .clock(clock), .reset_n(reset_n), .sample_valid(sample_valid), .lqr_mode(LQR),
        .sample_cycle(sample_cycle), .reference_value(32'sd16777216),
        .position(position), .velocity(velocity), .kp(32'sd33554432),
        .ki_period(32'sd16777), .derivative_decay(32'sd8388608), .derivative_gain(32'sd4194304),
        .position_gain(position_gain), .velocity_gain(velocity_gain), .reference_gain(reference_gain),
        .output_min(-32'sd67108864), .output_max(32'sd67108864),
        .integral_min(-32'sd33554432), .integral_max(32'sd33554432),
        .coefficients_valid(coefficients_valid), .output_valid(output_valid),
        .command_cycle(command_cycle), .command(command), .integral_state(integral_state),
        .derivative_state(derivative_state), .clipped(clipped), .integral_held(integral_held)
    );
    sampled_plant #(.THERMAL(THERMAL)) plant (
        .clock(clock), .reset_n(reset_n), .sample_tick(sample_tick), .actuator(actuator),
        .output_value(position), .velocity(velocity), .clipped(plant_clipped)
    );
    integer file, cycle;
    string path;
    initial begin
        if (!$value$plusargs("TRACK_FILE=%s", path)) $fatal(1, "missing tracking path");
        file = $fopen(path, "w");
        if (!file) $fatal(1, "cannot open trajectory");
        $fwrite(file, "cycle,reference,output,velocity,command,integral,derivative,clipped,held\n");
        repeat (2) @(negedge clock);
        reset_n = 1'b1;
        // These eight simulation edges represent one model interval T=1 ms.
        // No witness-clock frequency or processor latency is claimed here.
        for (cycle = 0; cycle < SAMPLES; cycle = cycle + 1) begin
            sample_cycle = 32'(cycle);
            sample_tick = 1'b1;
            @(posedge clock); #1;
            if (plant_clipped) $fatal(1, "normalized plant hit numeric saturation");
            @(negedge clock);
            sample_tick = 1'b0;
            sample_valid = 1'b1;
            @(posedge clock); #1;
            if (!coefficients_valid || !output_valid || command_cycle != sample_cycle)
                $fatal(1, "controller lost sample/tag");
            $fwrite(file, "%0d,16777216,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n", sample_cycle,
                position, velocity, command, integral_state, derivative_state, clipped, integral_held);
            @(negedge clock);
            sample_valid = 1'b0;
            actuator = command;
            repeat (6) @(negedge clock);
        end
        $fclose(file);
        $display("CLOSED_LOOP_PASS samples=%0d", SAMPLES);
        $finish;
    end
endmodule
