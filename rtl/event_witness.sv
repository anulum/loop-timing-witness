// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — timestamp capture and buffered drain stream

// One event_valid/code/cycle tuple is sampled per capture-clock edge. The source
// never stalls: a full buffer drops the newest record and counts it. Capture
// status and counters stay in capture_clock; drain outputs stay in drain_clock.
// Reset flushes the entire run. Physical CDC timing/RAM qualification is separate.
module event_witness #(
    parameter int ADDRESS_BITS = 14,
    parameter int OVERFLOW_COUNTER_BITS = 32
) (
    input  logic                             capture_clock,
    input  logic                             drain_clock,
    input  logic                             run_reset_n,
    input  logic                             event_valid,
    input  logic [7:0]                       event_code,
    input  logic [31:0]                      cycle_number,
    output logic                             capture_active,
    output logic [63:0]                      counter_ticks,
    output logic                             buffer_full,
    output logic                             event_dropped,
    output logic                             overflowed,
    output logic [OVERFLOW_COUNTER_BITS-1:0] overflow_count,
    input  logic                             drain_request,
    output logic                             drain_valid,
    output logic [127:0]                     drain_record,
    output logic                             drain_empty
);
    logic capture_reset_n, drain_reset_n;
    logic record_valid, buffer_ready;
    logic [127:0] captured_record;

    if (OVERFLOW_COUNTER_BITS < 1 || OVERFLOW_COUNTER_BITS > 32) begin : invalid_counter
        initial $fatal(1, "OVERFLOW_COUNTER_BITS must be in [1,32]");
    end

    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(run_reset_n), .local_reset_n(capture_reset_n)
    );
    clock_reset_release drain_reset (
        .clock(drain_clock), .run_reset_n(run_reset_n), .local_reset_n(drain_reset_n)
    );
    assign capture_active = capture_reset_n;

    event_record_capture capture (
        .clock(capture_clock), .reset_n(capture_reset_n), .event_valid(event_valid),
        .event_code(event_code), .cycle_number(cycle_number), .record_valid(record_valid),
        .record(captured_record), .counter_ticks(counter_ticks)
    );
    event_record_fifo #(.ADDRESS_BITS(ADDRESS_BITS)) buffer (
        .write_clock(capture_clock), .write_reset_n(capture_reset_n),
        .write_valid(record_valid), .write_data(captured_record),
        .write_ready(buffer_ready), .write_full(buffer_full),
        .read_clock(drain_clock), .read_reset_n(drain_reset_n), .read_request(drain_request),
        .read_valid(drain_valid), .read_data(drain_record), .read_empty(drain_empty)
    );

    always_ff @(posedge capture_clock or negedge capture_reset_n) begin
        if (!capture_reset_n) begin
            overflow_count <= '0;
            overflowed <= 1'b0;
            event_dropped <= 1'b0;
        end else begin
            event_dropped <= record_valid && !buffer_ready;
            if (record_valid && !buffer_ready) begin
                overflowed <= 1'b1;
                if (!(&overflow_count)) overflow_count <= overflow_count + 1'b1;
            end
        end
    end
endmodule
