// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fabric timestamp record capture

module event_record_capture (
    input  logic         clock,
    input  logic         reset_n,
    input  logic         event_valid,
    input  logic [7:0]   event_code,
    input  logic [31:0]  cycle_number,
    output logic         record_valid,
    output logic [127:0] record,
    output logic [63:0]  counter_ticks
);
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            counter_ticks <= 64'd0;
            record_valid <= 1'b0;
            record <= 128'd0;
        end else begin
            counter_ticks <= counter_ticks + 64'd1;
            record_valid <= event_valid;
            if (event_valid) begin
                record <= {counter_ticks, cycle_number, 16'd0, 8'd0, event_code};
            end
        end
    end
endmodule
