// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — asynchronous assertion and local reset release

// Both witness domains share run_reset_n. Release waits for two local edges;
// a stopped clock stays in reset. Never reset only one FIFO pointer domain.
`timescale 1ns/1ps

module clock_reset_release_tb;
    logic clock = 0, running = 1, run_reset_n = 0, local_reset_n;
    always #5 if (running) clock = ~clock;
    clock_reset_release reset_release (.*);

    task automatic release_and_check;
        begin
            @(negedge clock);
            run_reset_n = 1;
            @(posedge clock); #1;
            if (local_reset_n !== 0) $fatal(1, "reset released on first clock edge");
            @(posedge clock); #1;
            if (local_reset_n !== 1) $fatal(1, "reset did not release on second clock edge");
        end
    endtask

    initial begin
        repeat (3) @(negedge clock);
        release_and_check();
        @(negedge clock);
        running = 0;
        #2; run_reset_n = 0;
        #1;
        if (local_reset_n !== 0) $fatal(1, "reset assertion waited for clock");
        #2; run_reset_n = 1;
        #30;
        if (local_reset_n !== 0) $fatal(1, "reset released without clock");
        running = 1;
        @(posedge clock); #1;
        if (local_reset_n !== 0) $fatal(1, "stopped-clock release too early");
        @(posedge clock); #1;
        if (local_reset_n !== 1) $fatal(1, "stopped-clock release missing");
        @(negedge clock);
        #2; run_reset_n = 0;
        #1;
        if (local_reset_n !== 0) $fatal(1, "asynchronous assertion missing");
        release_and_check();
        $display("RESET_RELEASE_PASS");
        $finish;
    end
    initial begin
        #1000;
        $fatal(1, "reset release timeout");
    end
endmodule
