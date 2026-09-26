// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — consecutive deadline misses and latched safe state

// Deadline is strict: a write on the deadline edge cannot fulfil that cycle.
// Trip and interrupt latch until common run reset. Safe application wins writes.
module deadline_monitor #(
    parameter logic [31:0] MISS_LIMIT = 32'd3
) (
    input logic clock, reset_n, cycle_start, deadline, timely_write,
    output logic trip_now, safe_latched,
    output logic [31:0] total_misses, consecutive_misses
);
    logic written;
    if (MISS_LIMIT == 0) begin : invalid_limit
        initial $fatal(1, "MISS_LIMIT must be positive");
    end
    assign trip_now = deadline && !written && !safe_latched
        && consecutive_misses >= MISS_LIMIT - 1'b1;
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            written <= 1'b0;
            safe_latched <= 1'b0;
            total_misses <= '0;
            consecutive_misses <= '0;
        end else begin
            if (timely_write) written <= 1'b1;
            if (deadline) begin
                if (!written) begin
                    if (!(&total_misses)) total_misses <= total_misses + 1'b1;
                    if (!(&consecutive_misses)) consecutive_misses <= consecutive_misses + 1'b1;
                end else consecutive_misses <= '0;
                written <= 1'b0;
            end
            if (cycle_start) written <= 1'b0;
            if (trip_now) safe_latched <= 1'b1;
        end
    end
endmodule
