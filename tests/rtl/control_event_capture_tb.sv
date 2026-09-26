// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — simultaneous capture ordering overflow and reset

`timescale 1ns/1ps
module control_event_capture_tb;
    logic clock = 0, reset_n = 0;
    logic [7:0] event_mask = 0;
    logic [255:0] event_cycles = 0;
    logic [63:0] counter_ticks;
    logic record_valid, record_ready = 1;
    logic [127:0] record;
    logic [31:0] overflow_count;
    logic [127:0] expected [0:511];
    integer written = 0, read_count = 0, group_index, index;
    logic [63:0] edge_tick;
    control_event_capture #(.GROUP_ADDRESS_BITS(2)) capture (
        .clock(clock), .reset_n(reset_n), .event_mask(event_mask), .event_cycles(event_cycles),
        .counter_ticks(counter_ticks), .record_valid(record_valid), .record(record),
        .record_ready(record_ready), .overflow_count(overflow_count)
    );
    always #5 clock = ~clock;
    always @(posedge clock) begin
        if (reset_n && record_valid && record_ready) begin
            if (record !== expected[read_count]) $fatal(1, "group record/order/timestamp mismatch at %0d", read_count);
            read_count = read_count + 1;
        end
    end
    task automatic group(input logic [7:0] mask, input integer cycle);
        begin
            @(negedge clock);
            event_mask = mask;
            edge_tick = counter_ticks;
            for (index = 0; index < 8; index = index + 1) begin
                event_cycles[index*32 +: 32] = 32'(cycle);
                if (mask[index]) begin
                    expected[written] = {edge_tick, 32'(cycle), 24'd0, (index == 7 ? 8'd13 : 8'(index+1))};
                    written = written + 1;
                end
            end
            @(negedge clock); event_mask = 0;
        end
    endtask
    initial begin
        repeat (2) @(negedge clock); reset_n = 1;
        // More than four groups forces pointer wrap; drain all between batches.
        for (group_index = 0; group_index < 12; group_index = group_index + 1) begin
            group(8'hff, group_index);
            wait (read_count == written);
        end
        if (overflow_count) $fatal(1, "loss during ordinary serialization");
        // Two cycles sharing one timestamp must sort old-cycle events first.
        @(negedge clock);
        event_mask = 8'h09;
        event_cycles[0 +: 32] = 13;
        event_cycles[96 +: 32] = 12;
        expected[written] = {counter_ticks, 32'd12, 24'd0, 8'd4}; written = written + 1;
        expected[written] = {counter_ticks, 32'd13, 24'd0, 8'd1}; written = written + 1;
        @(negedge clock); event_mask = 0;
        wait (read_count == written);
        // Downstream full counts each serialized event, without retimestamping.
        @(negedge clock); record_ready = 0; event_mask = 8'hff;
        repeat (40) @(negedge clock);
        event_mask = 0;
        repeat (40) @(negedge clock);
        // Exactly 40 groups * 8 events rejected across the two bounded queues.
        if (overflow_count != 320) $fatal(1, "combined group/record loss count=%0d", overflow_count);
        @(negedge clock); reset_n = 0;
        #1;
        if (overflow_count || record_valid || counter_ticks) $fatal(1, "queue reset failed");
        written = 0; read_count = 0;
        @(negedge clock); reset_n = 1; record_ready = 1;
        group(8'h01, 0);
        wait (read_count == 1);
        // Asserting common run reset with a live multi-event group flushes it.
        @(negedge clock); record_ready = 0; event_mask = 8'hff;
        @(negedge clock); event_mask = 0; reset_n = 0;
        #1;
        if (record_valid || overflow_count || counter_ticks) $fatal(1, "queued group survived reset");
        written = 0; read_count = 0;
        @(negedge clock); reset_n = 1; record_ready = 1;
        group(8'h01, 0);
        wait (read_count == 1);
        $display("GROUP_PASS wrapped=12 dropped=320");
        $finish;
    end
    initial begin #100000; $fatal(1, "group timeout"); end
endmodule
