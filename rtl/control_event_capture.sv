// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — simultaneous control event capture and serialization

// Eight simultaneous strobes retain a single original edge timestamp.
// Pack cycles in 32-bit slices indexed by code: 1..7 and ACT_LATE=13.
// Bounded group queue drops whole newest groups, counting every lost event.
// Serialization orders cycle first, then code; downstream rejection drops one.
module control_event_capture #(
    parameter int GROUP_ADDRESS_BITS = 6
) (
    input logic clock, reset_n,
    input logic [7:0] event_mask,
    input logic [255:0] event_cycles,
    output logic [63:0] counter_ticks,
    output logic record_valid,
    output logic [127:0] record,
    input logic record_ready,
    output logic [31:0] overflow_count
);
    localparam int DEPTH = 1 << GROUP_ADDRESS_BITS;
    logic [327:0] groups [0:DEPTH-1];
    logic [GROUP_ADDRESS_BITS-1:0] head, tail, next_head;
    logic [GROUP_ADDRESS_BITS:0] count;
    logic [7:0] remaining_mask;
    logic [7:0] head_mask, after_mask;
    logic [327:0] current;
    integer chosen;
    logic [31:0] chosen_cycle;
    logic pop_group, push_group, reject_group;
    logic [3:0] group_losses;
    logic [32:0] loss_total;
    if (GROUP_ADDRESS_BITS < 1 || GROUP_ADDRESS_BITS > 8) begin : invalid_capacity
        initial $fatal(1, "GROUP_ADDRESS_BITS must be in [1,8]");
    end
    assign current = groups[head];
    assign next_head = head + 1'b1;
    always_comb begin
        head_mask = remaining_mask;
        chosen = 0;
        chosen_cycle = 32'hffffffff;
        for (integer index = 7; index >= 0; index = index - 1) begin
            if (head_mask[index] && current[64+32*index +: 32] <= chosen_cycle) begin
                chosen = index;
                chosen_cycle = current[64+32*index +: 32];
            end
        end
        after_mask = head_mask;
        after_mask[chosen] = 1'b0;
        group_losses = '0;
        for (integer index = 0; index < 8; index = index + 1)
            group_losses = group_losses + {3'd0, event_mask[index]};
    end
    assign record_valid = count != 0;
    assign record = {current[63:0], chosen_cycle, 24'd0,
        (chosen == 7 ? 8'd13 : 8'(chosen+1))};
    // Rejected serialized records are counted and consumed, never retimed.
    assign pop_group = record_valid && after_mask == 0;
    assign reject_group = event_mask != 0 && count == (GROUP_ADDRESS_BITS+1)'(DEPTH)
        && !pop_group;
    assign push_group = reset_n && event_mask != 0 && !reject_group;
    assign loss_total = {1'b0, overflow_count} +
        (reject_group ? {29'd0, group_losses} : 33'd0) +
        ((record_valid && !record_ready) ? 33'd1 : 33'd0);
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            counter_ticks <= '0;
            head <= '0;
            tail <= '0;
            count <= '0;
            remaining_mask <= '0;
            overflow_count <= '0;
        end else begin
            counter_ticks <= counter_ticks + 1'b1;
            overflow_count <= loss_total[32] ? 32'hffffffff : loss_total[31:0];
            if (record_valid) remaining_mask <= after_mask;
            if (pop_group) begin
                head <= head + 1'b1;
                if (count > 1) remaining_mask <= groups[next_head][327:320];
                else if (push_group) remaining_mask <= event_mask;
                else remaining_mask <= '0;
            end else if (count == 0 && push_group) remaining_mask <= event_mask;
            if (push_group) tail <= tail + 1'b1;
            case ({push_group, pop_group})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
    always_ff @(posedge clock) begin
        if (push_group) groups[tail] <= {event_mask, event_cycles, counter_ticks};
    end
endmodule
