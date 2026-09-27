// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — retained event generation interrupt across clock domains

// One generation per capture edge with sample IRQ, first safe or first finish.
// Coincident sources coalesce. A64bit generation outlasts the32bit cycle run;
// Gray counter crossing needs physical skew/max-delay constraints before silicon.
// Bus0x9c reads low and snapshots generation;0xa0 reads its held upper word.
// ACK0xa4(data1, fullstrobes) consumes that snapshot, not a later generation.
// Status0xa8 bits0/1: pending/snapshotvalid. Bank common reset clears bothdomains.
module retained_interrupt (
    input logic capture_clock, capture_reset_n, bus_clock, bus_reset_n,
    input logic sample_interrupt, safe_interrupt, run_finished,
    input logic local_valid, local_write,
    input logic [7:0] local_address,
    input logic [31:0] local_write_data,
    input logic [3:0] local_write_strobes,
    output logic [31:0] local_read_data,
    output logic [1:0] local_response,
    output logic interrupt_line
);
    logic safe_seen, finished_seen, source_event, observed_valid;
    logic [63:0] generation, generation_next, generation_gray, bus_generation;
    logic [63:0] observed_generation, acknowledged_generation;
    (* ASYNC_REG = "TRUE" *) logic [63:0] gray_first, gray_second;
    assign source_event = sample_interrupt || (safe_interrupt && !safe_seen) ||
        (run_finished && !finished_seen);
    assign generation_next = generation + 64'd1;
    assign interrupt_line = bus_reset_n && bus_generation != acknowledged_generation;
    for (genvar index = 0; index < 64; index = index + 1) begin : decode_gray
        assign bus_generation[index] = ^gray_second[63:index];
    end
    always_comb begin
        local_read_data = 0;
        local_response = 2'b10;
        if (bus_reset_n) begin
            if (local_write) begin
                if (local_address == 8'ha4 && local_write_data == 1 &&
                    local_write_strobes == 4'hf && observed_valid) local_response = 0;
            end else begin
                case (local_address)
                    8'h9c: begin local_read_data = bus_generation[31:0]; local_response = 0; end
                    8'ha0: if (observed_valid) begin
                        local_read_data = observed_generation[63:32]; local_response = 0;
                    end
                    8'ha8: begin local_read_data = {30'd0, observed_valid, interrupt_line}; local_response = 0; end
                    default: begin end
                endcase
            end
        end
    end
    always_ff @(posedge capture_clock or negedge capture_reset_n) begin
        if (!capture_reset_n) begin
            generation <= 0;
            generation_gray <= 0;
            safe_seen <= 0;
            finished_seen <= 0;
        end else begin
            if (safe_interrupt) safe_seen <= 1;
            if (run_finished) finished_seen <= 1;
            if (source_event) begin
                generation <= generation_next;
                generation_gray <= (generation_next >> 1) ^ generation_next;
            end
        end
    end
    always_ff @(posedge bus_clock or negedge bus_reset_n) begin
        if (!bus_reset_n) begin
            gray_first <= 0;
            gray_second <= 0;
            observed_generation <= 0;
            acknowledged_generation <= 0;
            observed_valid <= 0;
        end else begin
            gray_first <= generation_gray;
            gray_second <= gray_first;
            if (local_valid && local_response == 0) begin
                if (!local_write && local_address == 8'h9c) begin
                    observed_generation <= bus_generation;
                    observed_valid <= 1;
                end
                if (local_write) begin
                    acknowledged_generation <= observed_generation;
                    observed_valid <= 0;
                end
            end
        end
    end
endmodule
