// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — invariants of the fault injector

// From any state reached through a reset, with every input free: at most one fault is injected
// per reset; an accepted arm has a nonzero duration and a target that is not in the past; an
// armed fault never falls behind the sample counter and is injected at the tick of its target
// cycle, never at another; the freeze and overload levels last exactly the duration in ticks from
// the injection edge, the delayed interrupt comes exactly that many ticks after it and carries
// the target cycle, and a dropped or delayed sample interrupt is withheld only at the injection
// tick. The cycle counter here advances with the injector's tick, as control_cycle advances
// sample_cycle until the safe state latches; after that, ticks no longer reach the injector and
// no fault is injected. The observed wires are left undriven here and connected to the
// injector's registers after flatten (connect -set, see make fault-interrupt-invariants), so that
// the strengthening invariants make the rules inductive. NEGATIVE_CONTROL asserts that no fault
// is ever injected, which must yield a counterexample.
module fault_injector_proof #(
    parameter logic [31:0] PERIOD_TICKS = 32'd3,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic clock, reset_n, sample_tick, arm,
    input logic [1:0] kind,
    input logic [31:0] target_cycle, duration_periods
);
    logic [31:0] sample_cycle;
    wire arm_ready, injected, sample_interrupt, delayed_interrupt, freeze_actuator, overload_request;
    wire [31:0] delayed_cycle;
    fault_injector #(.PERIOD_TICKS(PERIOD_TICKS)) dut (.*);

    // Injector registers, connected after flatten.
    wire observed_armed, observed_used;
    wire [1:0] observed_saved_kind, observed_active_kind;
    wire [31:0] observed_saved_target, observed_saved_duration, observed_origin;
    wire [63:0] observed_remaining;

    // The last arm request seen while the injector was ready, and what followed the injection.
    logic [1:0] request_kind, active_kind;
    logic [31:0] request_target, request_duration, request_cycle;
    logic request_tick;
    logic [1:0] injections;
    logic [63:0] since, span;
    // The fault's duration in ticks, the product of the duration the injector holds (tied to the
    // accepted request below) and the period, taken at the injection edge.
    wire [63:0] duration_ticks = 64'(observed_saved_duration) * 64'(PERIOD_TICKS);
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            sample_cycle <= '0;
            request_kind <= '0;
            request_target <= '0;
            request_duration <= '0;
            request_cycle <= '0;
            request_tick <= 1'b0;
            active_kind <= '0;
            injections <= '0;
            since <= '0;
            span <= '0;
        end else begin
            if (sample_tick) sample_cycle <= sample_cycle + 1'b1;
            if (arm && arm_ready) begin
                request_kind <= kind;
                request_target <= target_cycle;
                request_duration <= duration_periods;
                request_cycle <= sample_cycle;
                request_tick <= sample_tick;
            end
            if (injected) begin
                if (injections != 2'd3) injections <= injections + 1'b1;
                active_kind <= request_kind;
                span <= duration_ticks;
                since <= 64'd1;
            end else if (since != 64'd0 && since != '1) since <= since + 1'b1;
        end
    end
    logic reset_seen = 1'b0;
    always @(posedge clock) if (!reset_n) reset_seen <= 1'b1;

    wire waiting = !arm_ready && injections == 2'd0;
    always @* begin
        if (reset_seen && reset_n) begin
            // One fault per reset.
            assert (injections <= 2'd1);
            if (injected) assert (injections == 2'd0 && waiting);
            // An accepted arm: nonzero duration, target not in the past when it was accepted.
            if (waiting) begin
                assert (request_duration != 0);
                assert (request_target > request_cycle || (request_target == request_cycle && !request_tick));
                // Never behind the counter, injected at the target tick and only there.
                assert (request_target >= sample_cycle);
                assert (injected == (sample_tick && sample_cycle == request_target));
            end else if (injections == 2'd0) assert (!injected);
            // Actions measured from the injection edge.
            assert (freeze_actuator == (injected ? request_kind == 2'd2
                : injections != 2'd0 && active_kind == 2'd2 && since < span));
            assert (overload_request == (injected ? request_kind == 2'd3
                : injections != 2'd0 && active_kind == 2'd3 && since < span));
            assert (delayed_interrupt == (injections != 2'd0 && active_kind == 2'd1 && since == span));
            if (delayed_interrupt) assert (delayed_cycle == request_target);
            assert (sample_interrupt == (delayed_interrupt
                || (sample_tick && !(injected && request_kind <= 2'd1))));
            // Strengthening invariants over the injector's registers.
            assert (!(observed_armed && observed_used));
            assert (observed_used == (injections != 2'd0));
            assert (arm_ready == (!observed_armed && !observed_used));
            if (observed_armed || observed_used) begin
                assert (observed_saved_kind == request_kind && observed_saved_target == request_target
                        && observed_saved_duration == request_duration);
            end
            if (!observed_used) begin
                assert (observed_remaining == 64'd0);
            end else begin
                assert (since != 64'd0 && observed_active_kind == active_kind);
                assert (observed_origin == request_target);
                assert (observed_remaining == (since <= span ? span - since + 64'd1 : 64'd0));
            end
            if (NEGATIVE_CONTROL) assert (!injected);
        end
    end
endmodule
