// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — parallel event capture with one shared timebase

// Each channel samples its pre-edge tuple and the same pre-increment tick.
// Registered tuples enter independent FIFOs on the following capture edge.
module shared_event_witness #(
    parameter int CHANNEL_COUNT = 3,
    parameter int ADDRESS_BITS = 10,
    parameter int OVERFLOW_COUNTER_BITS = 32
) (
    input  logic capture_clock,
    input  logic drain_clock,
    input  logic run_reset_n,
    input  logic [CHANNEL_COUNT-1:0] event_valid,
    input  logic [CHANNEL_COUNT*8-1:0] event_code,
    input  logic [CHANNEL_COUNT*32-1:0] event_identity,
    output logic capture_active,
    output logic [63:0] counter_ticks,
    output logic [CHANNEL_COUNT-1:0] buffer_full,
    output logic [CHANNEL_COUNT-1:0] event_dropped,
    output logic [CHANNEL_COUNT-1:0] overflowed,
    output logic [CHANNEL_COUNT*OVERFLOW_COUNTER_BITS-1:0] overflow_count,
    output logic [CHANNEL_COUNT*64-1:0] attempt_count,
    output logic [CHANNEL_COUNT*64-1:0] accepted_count,
    input  logic [CHANNEL_COUNT-1:0] drain_request,
    output logic [CHANNEL_COUNT-1:0] drain_valid,
    output logic [CHANNEL_COUNT*128-1:0] drain_record,
    output logic [CHANNEL_COUNT-1:0] drain_empty
);
    logic capture_reset_n, drain_reset_n;

    if (CHANNEL_COUNT < 1 || CHANNEL_COUNT > 32) begin : invalid_channels
        initial $fatal(1, "CHANNEL_COUNT must be in [1,32]");
    end
    if (OVERFLOW_COUNTER_BITS < 1 || OVERFLOW_COUNTER_BITS > 32) begin : invalid_counter
        initial $fatal(1, "OVERFLOW_COUNTER_BITS must be in [1,32]");
    end
    if (ADDRESS_BITS < 1 || ADDRESS_BITS > 14) begin : invalid_capacity
        initial $fatal(1, "ADDRESS_BITS must be in [1,14]");
    end

    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(run_reset_n), .local_reset_n(capture_reset_n)
    );
    clock_reset_release drain_reset (
        .clock(drain_clock), .run_reset_n(run_reset_n), .local_reset_n(drain_reset_n)
    );
    assign capture_active = capture_reset_n;

    always_ff @(posedge capture_clock or negedge capture_reset_n) begin
        if (!capture_reset_n) counter_ticks <= 64'd0;
        else counter_ticks <= counter_ticks + 64'd1;
    end

    if (CHANNEL_COUNT >= 1 && CHANNEL_COUNT <= 32 &&
        OVERFLOW_COUNTER_BITS >= 1 && OVERFLOW_COUNTER_BITS <= 32 &&
        ADDRESS_BITS >= 1 && ADDRESS_BITS <= 14) begin : valid_channels
        for (genvar channel = 0; channel < CHANNEL_COUNT; channel++) begin : channels
            logic record_valid, buffer_ready;
            logic [127:0] captured_record;

            always_ff @(posedge capture_clock or negedge capture_reset_n) begin
                if (!capture_reset_n) begin
                    record_valid <= 1'b0;
                    captured_record <= 128'd0;
                    attempt_count[channel*64 +: 64] <= 64'd0;
                    accepted_count[channel*64 +: 64] <= 64'd0;
                    overflow_count[channel*OVERFLOW_COUNTER_BITS +: OVERFLOW_COUNTER_BITS] <= '0;
                    overflowed[channel] <= 1'b0;
                    event_dropped[channel] <= 1'b0;
                end else begin
                    record_valid <= event_valid[channel];
                    if (event_valid[channel]) begin
                        captured_record <= {
                            counter_ticks, event_identity[channel*32 +: 32], 24'd0, event_code[channel*8 +: 8]
                        };
                    end
                    event_dropped[channel] <= record_valid && !buffer_ready;
                    if (record_valid) begin
                        attempt_count[channel*64 +: 64] <= attempt_count[channel*64 +: 64] + 64'd1;
                        if (buffer_ready) begin
                            accepted_count[channel*64 +: 64] <= accepted_count[channel*64 +: 64] + 64'd1;
                        end else begin
                            overflowed[channel] <= 1'b1;
                            if (!(&overflow_count[channel*OVERFLOW_COUNTER_BITS +: OVERFLOW_COUNTER_BITS])) begin
                                overflow_count[channel*OVERFLOW_COUNTER_BITS +: OVERFLOW_COUNTER_BITS] <= overflow_count[channel*OVERFLOW_COUNTER_BITS +: OVERFLOW_COUNTER_BITS] + 1'b1;
                            end
                        end
                    end
                end
            end

            event_record_fifo #(.ADDRESS_BITS(ADDRESS_BITS)) buffer (
                .write_clock(capture_clock), .write_reset_n(capture_reset_n),
                .write_valid(record_valid), .write_data(captured_record),
                .write_ready(buffer_ready), .write_full(buffer_full[channel]),
                .read_clock(drain_clock), .read_reset_n(drain_reset_n),
                .read_request(drain_request[channel]), .read_valid(drain_valid[channel]),
                .read_data(drain_record[channel*128 +: 128]), .read_empty(drain_empty[channel])
            );
        end
    end
endmodule
