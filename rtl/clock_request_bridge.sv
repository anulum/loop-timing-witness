// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — coherent request and response across clock domains

// One request is outstanding. Source payload remains held until its response;
// capture_response is latched on the edge where capture_valid is observed.
// The source consumes response_data only when response_valid && response_ready.
// Common asynchronous reset abandons the transaction in both domains; separate
// reset release is synchronised locally. No independent-domain reset is allowed.
// Bundled-data CDC requires physical max-delay constraints and board validation.
module clock_request_bridge #(
    parameter int REQUEST_BITS = 65,
    parameter int RESPONSE_BITS = 256
) (
    input logic bus_clock, capture_clock, run_reset_n,
    input logic request_valid,
    output logic request_ready,
    input logic [REQUEST_BITS-1:0] request_data,
    output logic response_valid,
    input logic response_ready,
    output logic [RESPONSE_BITS-1:0] response_data,
    output logic capture_valid,
    output logic [REQUEST_BITS-1:0] capture_data,
    input logic [RESPONSE_BITS-1:0] capture_response
);
    logic bus_reset_n, capture_reset_n;
    logic request_toggle, acknowledge_toggle, busy;
    (* ASYNC_REG = "TRUE" *) logic request_sync_first, request_sync_second;
    (* ASYNC_REG = "TRUE" *) logic acknowledge_sync_first, acknowledge_sync_second;
    logic [RESPONSE_BITS-1:0] held_response;
    if (REQUEST_BITS < 1 || RESPONSE_BITS < 1) begin : invalid_width
        initial $fatal(1, "bridge payload widths must be positive");
    end
    clock_reset_release bus_reset (
        .clock(bus_clock), .run_reset_n(run_reset_n), .local_reset_n(bus_reset_n)
    );
    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(run_reset_n), .local_reset_n(capture_reset_n)
    );
    assign request_ready = bus_reset_n && !busy && !response_valid;
    assign capture_valid = capture_reset_n && request_sync_second != acknowledge_toggle;
    always_ff @(posedge bus_clock or negedge bus_reset_n) begin
        if (!bus_reset_n) begin
            request_toggle <= 1'b0;
            acknowledge_sync_first <= 1'b0;
            acknowledge_sync_second <= 1'b0;
            busy <= 1'b0;
            capture_data <= '0;
            response_valid <= 1'b0;
            response_data <= '0;
        end else begin
            acknowledge_sync_first <= acknowledge_toggle;
            acknowledge_sync_second <= acknowledge_sync_first;
            if (response_valid && response_ready) response_valid <= 1'b0;
            if (request_valid && request_ready) begin
                capture_data <= request_data;
                request_toggle <= !request_toggle;
                busy <= 1'b1;
            end
            if (busy && acknowledge_sync_second == request_toggle) begin
                response_data <= held_response;
                response_valid <= 1'b1;
                busy <= 1'b0;
            end
        end
    end
    always_ff @(posedge capture_clock or negedge capture_reset_n) begin
        if (!capture_reset_n) begin
            request_sync_first <= 1'b0;
            request_sync_second <= 1'b0;
            acknowledge_toggle <= 1'b0;
            held_response <= '0;
        end else begin
            request_sync_first <= request_toggle;
            request_sync_second <= request_sync_first;
            if (capture_valid) begin
                held_response <= capture_response;
                acknowledge_toggle <= request_sync_second;
            end
        end
    end
endmodule
