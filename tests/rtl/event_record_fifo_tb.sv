// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dual-clock buffer public-port scoreboard

`timescale 1ns/1ps

module event_record_fifo_tb #(
    parameter int ADDRESS_BITS = 3,
    parameter int WRITE_HALF = 3,
    parameter int READ_HALF = 7,
    parameter int RANDOM_CYCLES = 10000
);
    localparam int DEPTH = 1 << ADDRESS_BITS;
    logic write_clock = 0, read_clock = 0, run_reset_n = 0;
    logic write_reset_n, read_reset_n;
    logic write_valid = 0, write_ready, write_full;
    logic [127:0] write_data = 0, read_data;
    logic read_request = 0, read_valid, read_empty;
    logic random_phase = 0;
    logic [31:0] write_random = 32'h73a59c17, read_random = 32'hac4862df;
    logic [127:0] expected [0:200000];
    integer accepted = 0, delivered = 0, offered = 0, round;

    always #(WRITE_HALF) write_clock = ~write_clock;
    always #(READ_HALF) read_clock = ~read_clock;

    clock_reset_release write_reset (
        .clock(write_clock), .run_reset_n(run_reset_n), .local_reset_n(write_reset_n)
    );
    clock_reset_release read_reset (
        .clock(read_clock), .run_reset_n(run_reset_n), .local_reset_n(read_reset_n)
    );
    event_record_fifo #(.ADDRESS_BITS(ADDRESS_BITS)) fifo (
        .write_clock(write_clock), .write_reset_n(write_reset_n),
        .write_valid(write_valid), .write_data(write_data), .write_ready(write_ready),
        .write_full(write_full), .read_clock(read_clock), .read_reset_n(read_reset_n),
        .read_request(read_request), .read_valid(read_valid), .read_data(read_data),
        .read_empty(read_empty)
    );

    always @(posedge write_clock) begin
        if (write_reset_n && write_valid && write_ready) begin
            expected[accepted] = write_data;
            accepted = accepted + 1;
        end
    end

    always @(posedge read_clock) begin
        #1;
        if (read_valid) begin
            if (delivered >= accepted) $fatal(1, "buffer emitted unaccepted data");
            if (read_data !== expected[delivered])
                $fatal(1, "record mismatch at %0d: %h != %h", delivered, read_data, expected[delivered]);
            delivered = delivered + 1;
        end
    end

    always @(negedge read_clock) begin
        if (random_phase) begin
            read_random = {read_random[30:0], read_random[31] ^ read_random[21] ^ read_random[1] ^ read_random[0]};
            read_request = read_random[0] | read_random[1];
        end
    end

    task automatic offer(input integer count);
        integer index;
        begin
            for (index = 0; index < count; index = index + 1) begin
                @(negedge write_clock);
                write_valid = 1;
                write_data = {32'hca97f018, 32'(offered), 32'(~offered), 32'h13579bdf};
                offered = offered + 1;
            end
            @(negedge write_clock);
            write_valid = 0;
        end
    endtask

    task automatic drain;
        begin
            @(negedge read_clock);
            read_request = 1;
            wait (delivered == accepted && read_empty);
            repeat (5) @(negedge read_clock);
            if (read_valid) $fatal(1, "read request at empty produced data");
            read_request = 0;
            repeat (5) @(negedge write_clock);
            if (write_full) $fatal(1, "full did not clear after drain");
        end
    endtask

    initial begin
        repeat (4) @(negedge write_clock);
        run_reset_n = 1;
        wait (write_reset_n && read_reset_n);
        offer(DEPTH + 3);
        if (accepted != DEPTH || !write_full) $fatal(1, "incorrect capacity %0d", accepted);
        drain();
        for (round = 0; round < 3; round = round + 1) begin
            offer(DEPTH);
            drain();
        end

        random_phase = 1;
        repeat (RANDOM_CYCLES) begin
            @(negedge write_clock);
            write_random = {write_random[30:0], write_random[31] ^ write_random[21] ^ write_random[1] ^ write_random[0]};
            write_valid = write_random[0] | write_random[1];
            write_data = {32'h87654321, 32'(offered), write_random, 32'(~offered)};
            offered = offered + 1;
        end
        @(negedge write_clock);
        write_valid = 0;
        random_phase = 0;
        drain();
        if (accepted < DEPTH * 4) $fatal(1, "pointer wrap not exercised");

        offer(DEPTH);
        @(negedge write_clock);
        run_reset_n = 0;
        #1;
        if (write_ready || read_valid || !read_empty) $fatal(1, "reset did not assert");
        accepted = 0;
        delivered = 0;
        repeat (4) @(negedge read_clock);
        run_reset_n = 1;
        wait (write_reset_n && read_reset_n);
        repeat (4) @(negedge read_clock);
        if (!read_empty) $fatal(1, "old queued data survived reset");
        offer(DEPTH);
        drain();
        if (delivered != DEPTH) $fatal(1, "reset/recovery record count");
        $display("FIFO_PASS depth=%0d write_half=%0d read_half=%0d", DEPTH, WRITE_HALF, READ_HALF);
        $finish;
    end

    initial begin
        #((RANDOM_CYCLES + 8 * DEPTH + 1000) * (WRITE_HALF + READ_HALF) * 20);
        $fatal(1, "buffer simulation timeout");
    end
endmodule
