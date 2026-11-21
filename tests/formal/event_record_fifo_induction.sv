// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — dual-clock event record buffer, strengthening invariants for induction

// The port checker event_record_fifo_proof states the buffer's rules; from an arbitrary state
// they are not inductive, because the pointers, their Gray copies and the two synchroniser stages
// of each domain can disagree. This module states how they agree in every reachable state, so
// that temporal induction proves the port rules for every reachable state, not only for a
// bounded trace. Yosys has no hierarchical references: the observed wires below are left
// undriven here and the proof flow connects each to the register of the same name inside the
// flattened checker and buffer (connect -set, see make fifo-invariants).
//
// All pointer arithmetic is modulo 2 * DEPTH. In every reachable state the read pointer copies of
// the write domain lag the read pointer (stage, then synchronised copy), the write pointer copies
// of the read domain lag the write pointer, no copy is more than DEPTH behind the pointer it
// follows, a clear full flag leaves room for one more record and a clear empty flag means a
// record is visible to the reader. The watched record stays in its slot while it is unread, and
// a read of its index returns it.
module event_record_fifo_induction #(
    parameter int ADDRESS_BITS = 1
) (
    input logic write_clock, read_clock, reset_n,
    input logic write_valid, read_request,
    input logic [127:0] write_data
);
    localparam int DEPTH = 1 << ADDRESS_BITS;
    localparam int POINTER_BITS = ADDRESS_BITS + 1;
    event_record_fifo_proof #(.ADDRESS_BITS(ADDRESS_BITS), .CHECK_DATA(1)) proof (
        .write_clock(write_clock), .read_clock(read_clock), .reset_n(reset_n),
        .write_valid(write_valid), .read_request(read_request), .write_data(write_data)
    );

    // Checker registers.
    wire [POINTER_BITS-1:0] writes, reads, last_read, watch_index;
    wire pending, watched_bit, reset_seen;
    // Buffer registers and ports.
    wire [POINTER_BITS-1:0] write_binary, write_gray, read_binary, read_gray;
    wire [POINTER_BITS-1:0] read_gray_stage, read_gray_sync, write_gray_stage, write_gray_sync;
    wire write_full, read_empty, read_valid, read_data_bit;
    wire [DEPTH-1:0] record_bits;

    function automatic [POINTER_BITS-1:0] gray(input [POINTER_BITS-1:0] value);
        gray = (value >> 1) ^ value;
    endfunction
    function automatic [POINTER_BITS-1:0] binary(input [POINTER_BITS-1:0] code);
        integer bit_index;
        for (bit_index = 0; bit_index < POINTER_BITS; bit_index = bit_index + 1)
            binary[bit_index] = ^(code >> bit_index);
    endfunction

    wire [POINTER_BITS-1:0] occupancy = write_binary - read_binary;
    wire [POINTER_BITS-1:0] write_lead_on_stage = write_binary - binary(read_gray_stage);
    wire [POINTER_BITS-1:0] write_lead_on_sync = write_binary - binary(read_gray_sync);
    wire [POINTER_BITS-1:0] sync_lead_on_read = binary(write_gray_sync) - read_binary;
    wire [POINTER_BITS-1:0] stage_lead_on_read = binary(write_gray_stage) - read_binary;
    wire [POINTER_BITS-1:0] watch_offset = watch_index - read_binary;
    wire [ADDRESS_BITS-1:0] watch_slot = watch_index[ADDRESS_BITS-1:0];

    always @* begin
        if (reset_seen) begin
            assert (writes == write_binary && reads == read_binary);
            assert (write_gray == gray(write_binary) && read_gray == gray(read_binary));
            assert (occupancy <= write_lead_on_stage && write_lead_on_stage <= write_lead_on_sync
                    && write_lead_on_sync <= DEPTH);
            assert (sync_lead_on_read <= stage_lead_on_read && stage_lead_on_read <= occupancy);
            if (!write_full) assert (write_lead_on_sync < DEPTH);
            if (!read_empty) assert (sync_lead_on_read != 0);
            if (read_valid) assert (last_read == read_binary - 1'b1);
            if (pending && watch_offset < occupancy)
                assert (record_bits[watch_slot] == watched_bit);
            if (read_valid && pending && last_read == watch_index)
                assert (read_data_bit == watched_bit);
        end
    end
endmodule
