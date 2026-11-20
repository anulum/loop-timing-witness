// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dual-clock event record buffer, checked at its ports

// The write and read clocks are free inputs, so after clk2fflogic every interleaving of their
// edges is explored; both local resets come from one asynchronous run reset, as the buffer
// requires. Shadow counters of accepted writes and reads give the true occupancy. From a reset,
// the buffer never accepts a write when it holds DEPTH records and never accepts a read when it
// holds none, and a watched record, chosen freely by its write index, is read back unchanged and
// in order (CHECK_DATA; without it the data path drops out of the model, so the pointer and
// occupancy rules are proven alone). The record memory writes and reads whole words at one
// address, so every data bit takes the same path: data bit 0 stands for each of them, and the
// other bits, unused by the assertions, drop out of the model. NEGATIVE_CONTROL asserts that the
// buffer never fills, which must yield a counterexample.
module event_record_fifo_proof #(
    parameter int ADDRESS_BITS = 2,
    parameter bit CHECK_DATA = 1,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic write_clock, read_clock, reset_n,
    input logic write_valid, read_request,
    input logic [127:0] write_data
);
    localparam int DEPTH = 1 << ADDRESS_BITS;
    wire write_ready, write_full, read_valid, read_empty;
    wire [127:0] read_data;
    event_record_fifo #(.ADDRESS_BITS(ADDRESS_BITS)) dut (
        .write_clock(write_clock), .write_reset_n(reset_n), .write_valid(write_valid),
        .write_data(write_data), .write_ready(write_ready), .write_full(write_full),
        .read_clock(read_clock), .read_reset_n(reset_n), .read_request(read_request),
        .read_valid(read_valid), .read_data(read_data), .read_empty(read_empty)
    );
    // The watched write index is free but fixed for the whole trace.
    (* anyconst *) logic [ADDRESS_BITS:0] watch_index;
    logic [ADDRESS_BITS:0] writes, reads, last_read;
    logic [127:0] watched;
    logic pending;
    wire write_accept = write_valid && write_ready;
    wire read_accept = read_request && reset_n && !read_empty;
    wire [ADDRESS_BITS:0] occupancy = writes - reads;
    always_ff @(posedge write_clock or negedge reset_n) begin
        if (!reset_n) begin
            writes <= '0;
            pending <= 1'b0;
        end else if (write_accept) begin
            writes <= writes + 1'b1;
            if (writes == watch_index) begin
                watched <= write_data;
                pending <= 1'b1;
            end
        end
    end
    always_ff @(posedge read_clock or negedge reset_n) begin
        if (!reset_n) begin
            reads <= '0;
            last_read <= '0;
        end else if (read_accept) begin
            reads <= reads + 1'b1;
            last_read <= reads;
        end
    end
    logic reset_seen = 1'b0;
    always_ff @(posedge write_clock) if (!reset_n) reset_seen <= 1'b1;
    always @* begin
        if (reset_seen && reset_n) begin
            assert (occupancy <= DEPTH);
            if (write_accept) assert (occupancy < DEPTH);
            if (read_accept) assert (occupancy != 0);
            if (CHECK_DATA && read_valid && last_read == watch_index && pending)
                assert (read_data[0] == watched[0]);
            if (NEGATIVE_CONTROL) assert (occupancy != DEPTH);
        end
    end
endmodule
