// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — strict deadlines successful recovery and latched trip

`timescale 1ns/1ps
module deadline_monitor_tb;
    logic clock = 0, reset_n = 0, cycle_start = 0, deadline = 0, timely_write = 0;
    logic trip_now, safe_latched;
    logic [31:0] total_misses, consecutive_misses;
    deadline_monitor #(.MISS_LIMIT(32'd2)) monitor (
        .clock(clock), .reset_n(reset_n), .cycle_start(cycle_start), .deadline(deadline),
        .timely_write(timely_write), .trip_now(trip_now), .safe_latched(safe_latched),
        .total_misses(total_misses), .consecutive_misses(consecutive_misses)
    );
    always #5 clock = ~clock;
    task automatic pulse(input logic write_value, input logic deadline_value);
        begin
            @(negedge clock); timely_write = write_value; deadline = deadline_value;
            @(negedge clock); timely_write = 0; deadline = 0;
        end
    endtask
    initial begin
        repeat (2) @(negedge clock); reset_n = 1;
        pulse(0, 1);
        if (total_misses != 1 || consecutive_misses != 1 || safe_latched) $fatal(1, "first miss");
        pulse(1, 0); pulse(0, 1);
        if (total_misses != 1 || consecutive_misses || safe_latched) $fatal(1, "successful cycle not recovered");
        pulse(1, 1);
        if (total_misses != 2 || consecutive_misses != 1 || safe_latched) $fatal(1, "deadline-edge write counted timely");
        pulse(0, 1);
        if (total_misses != 3 || consecutive_misses != 2 || !safe_latched) $fatal(1, "miss limit did not trip");
        pulse(1, 0); pulse(0, 1);
        if (!safe_latched || total_misses != 3 || consecutive_misses) $fatal(1, "successful write cleared latch");
        @(negedge clock); reset_n = 0;
        #1;
        if (safe_latched || total_misses || consecutive_misses) $fatal(1, "monitor reset failed");
        $display("MONITOR_PASS");
        $finish;
    end
endmodule
