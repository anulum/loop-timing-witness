// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dual-clock event record buffer

// Gray-pointer synchronisation follows Cummings, SNUG 2002, FIFO style 1.
// Inputs/outputs belong to their named clock domain. read_data is meaningful
// only with read_valid; a request at empty does not advance the pointer.
// Both local resets must derive from the same asynchronously asserted run reset.
module event_record_fifo #(
    parameter int ADDRESS_BITS = 14
) (
    input  logic         write_clock,
    input  logic         write_reset_n,
    input  logic         write_valid,
    input  logic [127:0] write_data,
    output logic         write_ready,
    output logic         write_full,
    input  logic         read_clock,
    input  logic         read_reset_n,
    input  logic         read_request,
    output logic         read_valid,
    output logic [127:0] read_data,
    output logic         read_empty
);
    localparam int DEPTH = 1 << ADDRESS_BITS;
    localparam logic [ADDRESS_BITS:0] FULL_MASK = {2'b11, {(ADDRESS_BITS-1){1'b0}}};

    logic [127:0] records [0:DEPTH-1];
    logic [ADDRESS_BITS:0] write_binary, write_gray;
    logic [ADDRESS_BITS:0] read_binary, read_gray;
    logic [ADDRESS_BITS:0] write_binary_next, write_gray_next;
    logic [ADDRESS_BITS:0] read_binary_next, read_gray_next;
    (* ASYNC_REG = "TRUE" *) logic [ADDRESS_BITS:0] read_gray_stage, read_gray_sync;
    (* ASYNC_REG = "TRUE" *) logic [ADDRESS_BITS:0] write_gray_stage, write_gray_sync;
    logic write_accept, read_accept;

    if (ADDRESS_BITS < 1 || ADDRESS_BITS > 14) begin : invalid_capacity
        initial $fatal(1, "ADDRESS_BITS must be in [1,14]");
    end

    assign write_ready = write_reset_n && !write_full;
    assign write_accept = write_valid && write_ready;
    assign read_accept = read_request && read_reset_n && !read_empty;
    assign write_binary_next = write_binary + {{ADDRESS_BITS{1'b0}}, write_accept};
    assign read_binary_next = read_binary + {{ADDRESS_BITS{1'b0}}, read_accept};
    assign write_gray_next = (write_binary_next >> 1) ^ write_binary_next;
    assign read_gray_next = (read_binary_next >> 1) ^ read_binary_next;

    always_ff @(posedge write_clock or negedge write_reset_n) begin
        if (!write_reset_n) begin
            write_binary <= '0;
            write_gray <= '0;
            write_full <= 1'b0;
            read_gray_stage <= '0;
            read_gray_sync <= '0;
        end else begin
            write_binary <= write_binary_next;
            write_gray <= write_gray_next;
            write_full <= write_gray_next == (read_gray_sync ^ FULL_MASK);
            read_gray_stage <= read_gray;
            read_gray_sync <= read_gray_stage;
        end
    end

    always_ff @(posedge read_clock or negedge read_reset_n) begin
        if (!read_reset_n) begin
            read_binary <= '0;
            read_gray <= '0;
            read_empty <= 1'b1;
            read_valid <= 1'b0;
            write_gray_stage <= '0;
            write_gray_sync <= '0;
        end else begin
            read_binary <= read_binary_next;
            read_gray <= read_gray_next;
            read_empty <= read_gray_next == write_gray_sync;
            read_valid <= read_accept;
            write_gray_stage <= write_gray;
            write_gray_sync <= write_gray_stage;
        end
    end

    // Separate clocked ports leave the RAM intact for vendor memory inference.
    always_ff @(posedge write_clock) begin
        if (write_accept) records[write_binary[ADDRESS_BITS-1:0]] <= write_data;
    end

    always_ff @(posedge read_clock) begin
        if (read_accept) read_data <= records[read_binary[ADDRESS_BITS-1:0]];
    end
endmodule
