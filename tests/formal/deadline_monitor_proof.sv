// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — safe-state invariants of the deadline monitor

// From any state reached through a reset, with every input free: the consecutive miss count
// never exceeds the total; the safe state latches only on a missed deadline that completes
// MISS_LIMIT consecutive misses, so a latched monitor has counted at least MISS_LIMIT misses;
// and the latch holds until the next reset. NEGATIVE_CONTROL asserts that the latch never
// sets, which must yield a counterexample.
module deadline_monitor_proof #(
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic clock, reset_n, cycle_start, deadline, timely_write
);
    wire trip_now, safe_latched;
    wire [31:0] total_misses, consecutive_misses;
    logic reset_seen = 0;
    deadline_monitor #(.MISS_LIMIT(MISS_LIMIT)) dut (.*);
    always @(posedge clock) begin
        if (!reset_n) reset_seen <= 1;
        if (reset_seen && reset_n) begin
            assert (consecutive_misses <= total_misses);
            assert (!safe_latched || total_misses >= MISS_LIMIT);
            if (NEGATIVE_CONTROL) assert (!safe_latched);
        end
        if (reset_seen && reset_n && $past(reset_n) && $past(reset_seen)) begin
            if ($past(safe_latched)) assert (safe_latched);
            if (!$past(safe_latched) && safe_latched)
                assert ($past(deadline) && {1'b0, $past(consecutive_misses)} + 33'd1 >= {1'b0, MISS_LIMIT});
        end
    end
endmodule
