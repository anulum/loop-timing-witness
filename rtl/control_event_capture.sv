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
// current is a register copy of the head slot, so the selection starts from a register.
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
    logic [319:0] current, incoming;
    logic [2:0] chosen;
    logic [31:0] chosen_cycle;
    // Selection candidates {pending, code index, cycle}, 36 bits each, reduced pairwise.
    logic [287:0] candidates;
    logic [143:0] pairs;
    logic [71:0] quads;
    logic [35:0] earliest;
    logic pop_group, push_group, reject_group;
    logic [3:0] group_losses;
    logic [32:0] loss_total;
    if (GROUP_ADDRESS_BITS < 1 || GROUP_ADDRESS_BITS > 8) begin : invalid_capacity
        initial $fatal(1, "GROUP_ADDRESS_BITS must be in [1,8]");
    end
    assign incoming = {event_cycles, counter_ticks};
    assign next_head = head + 1'b1;
    // The pending candidate with the earlier cycle wins; on equal cycles the lower code index,
    // passed as low, wins. The serialization order equals a scan that keeps the last minimum
    // from index 7 down to 0, in three comparator levels instead of eight.
    function automatic logic [35:0] earlier(input logic [35:0] low, input logic [35:0] high);
        earlier = high[35] && (!low[35] || high[31:0] < low[31:0]) ? high : low;
    endfunction
    for (genvar slot = 0; slot < 8; slot = slot + 1) begin : candidate
        localparam logic [2:0] CODE_INDEX = slot;
        assign candidates[36*slot +: 36] = {remaining_mask[slot], CODE_INDEX, current[64+32*slot +: 32]};
    end
    for (genvar slot = 0; slot < 4; slot = slot + 1) begin : pair
        assign pairs[36*slot +: 36] = earlier(candidates[72*slot +: 36], candidates[72*slot+36 +: 36]);
    end
    for (genvar slot = 0; slot < 2; slot = slot + 1) begin : quad
        assign quads[36*slot +: 36] = earlier(pairs[72*slot +: 36], pairs[72*slot+36 +: 36]);
    end
    assign earliest = earlier(quads[35:0], quads[71:36]);
    assign chosen = earliest[35] ? earliest[34:32] : 3'd0;
    assign chosen_cycle = earliest[35] ? earliest[31:0] : 32'hffffffff;
    always_comb begin
        head_mask = remaining_mask;
        after_mask = head_mask;
        after_mask[chosen] = 1'b0;
        group_losses = '0;
        for (integer index = 0; index < 8; index = index + 1)
            group_losses = group_losses + {3'd0, event_mask[index]};
    end
    assign record_valid = count != 0;
    assign record = {current[63:0], chosen_cycle, 24'd0,
        (chosen == 3'd7 ? 8'd13 : {5'd0, chosen} + 8'd1)};
    // Rejected serialized records are counted and consumed, never retimed. The group pops with its
    // last pending event: after_mask is zero exactly when at most one remaining bit is set, which
    // the mask register gives without waiting for the selection.
    assign pop_group = record_valid && (remaining_mask & (remaining_mask - 8'd1)) == 8'd0;
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
            current <= '0;
        end else begin
            counter_ticks <= counter_ticks + 1'b1;
            overflow_count <= loss_total[32] ? 32'hffffffff : loss_total[31:0];
            if (record_valid) remaining_mask <= after_mask;
            // current follows groups[head]: the next slot after a pop, written through when the
            // pushed group becomes the head in the same edge.
            if (pop_group) begin
                head <= head + 1'b1;
                current <= count == 1 && push_group ? incoming : groups[next_head][319:0];
                if (count > 1) remaining_mask <= groups[next_head][327:320];
                else if (push_group) remaining_mask <= event_mask;
                else remaining_mask <= '0;
            end else if (count == 0 && push_group) begin
                remaining_mask <= event_mask;
                current <= incoming;
            end
            if (push_group) tail <= tail + 1'b1;
            case ({push_group, pop_group})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
    always_ff @(posedge clock) begin
        if (push_group) groups[tail] <= {event_mask, incoming};
    end
endmodule
