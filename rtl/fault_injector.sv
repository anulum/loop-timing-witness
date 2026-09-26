// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — clock-exact drop delay freeze and overload injection

// One fault per reset/run. kind: 0 drop IRQ, 1 delay IRQ, 2 freeze writes,
// 3 request software overload. Zero-duration and past-cycle arms are refused.
// A delayed pulse retains its origin cycle; coincident normal IRQs coalesce.
module fault_injector #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000
) (
    input logic clock, reset_n, sample_tick,
    input logic [31:0] sample_cycle,
    input logic arm,
    input logic [1:0] kind,
    input logic [31:0] target_cycle, duration_periods,
    output logic arm_ready, injected, sample_interrupt, delayed_interrupt,
    output logic [31:0] delayed_cycle,
    output logic freeze_actuator, overload_request
);
    logic armed, used;
    logic [1:0] saved_kind;
    logic [31:0] saved_target, saved_duration;
    logic [63:0] remaining;
    logic [1:0] active_kind;
    logic [31:0] origin;
    logic [63:0] duration_ticks;
    assign duration_ticks = 64'(saved_duration) * 64'(PERIOD_TICKS);
    assign arm_ready = !armed && !used;
    assign injected = sample_tick && armed && sample_cycle == saved_target;
    assign delayed_interrupt = remaining == 64'd1 && active_kind == 2'd1;
    assign delayed_cycle = origin;
    assign sample_interrupt = delayed_interrupt ||
        (sample_tick && !(injected && (saved_kind == 2'd0 || saved_kind == 2'd1)));
    assign freeze_actuator = (remaining > 1 && active_kind == 2'd2)
        || (injected && saved_kind == 2'd2);
    assign overload_request = (remaining > 1 && active_kind == 2'd3)
        || (injected && saved_kind == 2'd3);
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            armed <= 1'b0;
            used <= 1'b0;
            saved_kind <= '0;
            saved_target <= '0;
            saved_duration <= '0;
            remaining <= '0;
            active_kind <= '0;
            origin <= '0;
        end else begin
            if (arm && arm_ready && duration_periods != 0 &&
                (target_cycle > sample_cycle || (target_cycle == sample_cycle && !sample_tick))) begin
                armed <= 1'b1;
                saved_kind <= kind;
                saved_target <= target_cycle;
                saved_duration <= duration_periods;
            end
            if (remaining != 0) remaining <= remaining - 1'b1;
            if (injected) begin
                armed <= 1'b0;
                used <= 1'b1;
                active_kind <= saved_kind;
                origin <= sample_cycle;
                // At t+D the old remaining value is one, giving exactly D ticks.
                remaining <= duration_ticks;
            end
        end
    end
endmodule
