// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public controller vector replay

module controller_parity_tb;
    logic clock = 1'b0;
    always #5 clock = !clock;
    logic reset_n = 1'b0, sample_valid = 1'b0, lqr_mode;
    logic [31:0] sample_cycle, command_cycle;
    logic signed [31:0] reference_value, position, velocity;
    logic signed [31:0] kp, ki_period, derivative_decay, derivative_gain;
    logic signed [31:0] position_gain, velocity_gain, reference_gain;
    logic signed [31:0] output_min, output_max, integral_min, integral_max;
    wire coefficients_valid, output_valid, clipped, integral_held;
    wire signed [31:0] command, integral_state, derivative_state;
    fixed_point_controller dut (.*);
    string input_path, output_path;
    integer input_file, output_file, scanned, mode;
    reg [8191:0] line;
    initial begin
        if (!$value$plusargs("INPUT=%s", input_path) ||
            !$value$plusargs("OUTPUT=%s", output_path) || !$value$plusargs("MODE=%d", mode))
            $fatal(1, "missing paths/mode");
        lqr_mode = mode != 0;
        input_file = $fopen(input_path, "r");
        output_file = $fopen(output_path, "w");
        if (!input_file || !output_file) $fatal(1, "cannot open vector files");
        scanned = $fscanf(input_file, "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\n",
            kp, ki_period, derivative_decay, derivative_gain, position_gain,
            velocity_gain, reference_gain, output_min, output_max, integral_min, integral_max);
        if (scanned != 11) $fatal(1, "invalid coefficients");
        repeat (2) @(negedge clock);
        reset_n = 1'b1;
        #1;
        if (!coefficients_valid) $fatal(1, "refused coefficients");
        while (!$feof(input_file)) begin
            scanned = $fgets(line, input_file);
            if (scanned != 0) begin
                if (line == "reset\n" || line == "reset") begin
                    reset_n = 1'b0;
                    @(negedge clock);
                    reset_n = 1'b1;
                end else begin
                    scanned = $sscanf(line, "%d,%d,%d,%d", sample_cycle,
                        reference_value, position, velocity);
                    if (scanned != 4) $fatal(1, "invalid sample");
                    sample_valid = 1'b1;
                    @(posedge clock); #1;
                    if (!output_valid) $fatal(1, "missing command");
                    $fwrite(output_file, "%0d,%0d,%0d,%0d,%0d,%0d\n", command_cycle,
                        command, integral_state, derivative_state, clipped, integral_held);
                    @(negedge clock);
                    sample_valid = 1'b0;
                    @(posedge clock); #1;
                    if (output_valid) $fatal(1, "unexpected idle command");
                    @(negedge clock);
                end
            end
        end
        $fclose(input_file);
        $fclose(output_file);
        $finish;
    end
endmodule
