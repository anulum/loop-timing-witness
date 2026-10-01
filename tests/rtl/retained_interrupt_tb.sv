// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — retained IRQ status and immutable acknowledgement snapshot

`timescale 1ns/1ps
module retained_interrupt_tb;
    parameter integer BUS_HALF_PERIOD = 7;
    logic capture_clock = 0, capture_reset_n = 0, bus_clock = 0, bus_reset_n = 0;
    logic sample_interrupt = 0, safe_interrupt = 0, run_finished = 0;
    logic local_valid = 0, local_write = 0;
    logic [7:0] local_address = 0;
    logic [31:0] local_write_data = 1, local_read_data;
    logic [3:0] local_write_strobes = 15;
    logic [1:0] local_response;
    logic interrupt_line;
    retained_interrupt dut (.*);
    always #5 capture_clock <= ~capture_clock;
    always #(BUS_HALF_PERIOD) bus_clock <= ~bus_clock;

    task automatic read_word(input logic [7:0] address, input logic [31:0] expected);
        @(negedge bus_clock);
        local_valid = 1; local_write = 0; local_address = address;
        #1;
        if (local_response != 0 || local_read_data != expected)
            $fatal(1, "read %h expected %h got %h response %h", address, expected, local_read_data, local_response);
        if (address == 8'ha8 && interrupt_line != expected[0]) $fatal(1, "IRQ status differs from line");
        @(negedge bus_clock); local_valid = 0;
    endtask

    task automatic sample_event;
        @(negedge capture_clock); sample_interrupt = 1;
        @(negedge capture_clock); sample_interrupt = 0;
        repeat (4) @(negedge bus_clock);
    endtask

    task automatic acknowledge(input logic [1:0] expected_response);
        @(negedge bus_clock);
        local_valid = 1; local_write = 1; local_address = 8'ha4;
        #1;
        if (local_response != expected_response) $fatal(1, "ACK response");
        @(negedge bus_clock); local_valid = 0; local_write = 0;
    endtask

    initial begin
        repeat (2) @(negedge capture_clock);
        repeat (2) @(negedge bus_clock);
        capture_reset_n = 1; bus_reset_n = 1;
        read_word(8'ha8, 0);
        sample_event();
        read_word(8'ha8, 1);
        acknowledge(2);
        read_word(8'ha8, 1);
        read_word(8'h9c, 1);
        read_word(8'ha0, 0);
        read_word(8'ha8, 3);
        sample_event();
        read_word(8'ha8, 3);
        acknowledge(0);
        read_word(8'ha8, 1);
        acknowledge(2);
        read_word(8'ha8, 1);
        read_word(8'h9c, 2);
        read_word(8'ha8, 3);
        acknowledge(0);
        read_word(8'ha8, 0);
        @(negedge capture_clock); safe_interrupt = 1; run_finished = 1;
        repeat (4) @(negedge capture_clock);
        repeat (4) @(negedge bus_clock);
        read_word(8'ha8, 1);
        read_word(8'h9c, 3);
        acknowledge(0);
        read_word(8'ha8, 0);
        sample_event();
        read_word(8'ha8, 1);
        read_word(8'h9c, 4);
        read_word(8'ha8, 3);
        @(negedge bus_clock); local_valid = 1; local_address = 8'hfc;
        #1;
        if (local_response != 2 || local_read_data != 0) $fatal(1, "unknown address refused");
        @(negedge bus_clock); local_valid = 0;
        capture_reset_n = 0; bus_reset_n = 0;
        safe_interrupt = 0; run_finished = 0;
        repeat (2) @(negedge bus_clock);
        capture_reset_n = 1; bus_reset_n = 1;
        read_word(8'ha8, 0);
        acknowledge(2);
        $display("RETAINED_STATUS_PASS generations=4");
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "retained status test timed out");
    end
endmodule
