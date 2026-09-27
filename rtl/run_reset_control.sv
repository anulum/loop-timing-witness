// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bus run reset without resetting AXI transport

// Bus-domain0x98: write0 to assert the common bank reset, write1 to release.
// Assert is permitted only when capture says the run is disabled or finished;
// it cannot erase active deadlines. Read bits: enabled, capture ready, bus ready,
// assert permitted. AXI/mailbox state is outside this bank and retains responses.
module run_reset_control (
    input logic bus_clock, reset_n, external_reset_n,
    input logic local_valid, local_write,
    input logic [31:0] local_write_data,
    input logic [3:0] local_write_strobes,
    output logic [31:0] local_read_data,
    output logic [1:0] local_response,
    input logic capture_reset_ready, bus_reset_ready, capture_reset_allowed,
    output logic bank_reset_n
);
    logic enabled, assert_allowed;
    (* ASYNC_REG = "TRUE" *) logic [1:0] capture_ready_sync, reset_allowed_sync;
    assign bank_reset_n = external_reset_n && enabled;
    assign assert_allowed = !enabled || reset_allowed_sync[1];
    always_comb begin
        local_read_data = {28'd0, assert_allowed, bus_reset_ready,
            enabled && capture_ready_sync[1], enabled};
        local_response = 2'b10;
        if (reset_n) begin
            if (!local_write) local_response = 0;
            else if (local_write_strobes == 4'hf &&
                ((local_write_data == 0 && assert_allowed) || (local_write_data == 1 && !enabled)))
                local_response = 0;
        end
    end
    always_ff @(posedge bus_clock or negedge reset_n) begin
        if (!reset_n) begin
            enabled <= 1;
            capture_ready_sync <= 0;
            reset_allowed_sync <= 0;
        end else begin
            capture_ready_sync <= {capture_ready_sync[0], capture_reset_ready};
            reset_allowed_sync <= {reset_allowed_sync[0], capture_reset_allowed};
            if (local_valid && local_write && local_response == 0) enabled <= local_write_data[0];
        end
    end
endmodule
