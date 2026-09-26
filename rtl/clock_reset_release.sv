// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — asynchronous assertion and local reset release

// Both witness domains share run_reset_n. Release waits for two local edges;
// a stopped clock stays in reset. Never reset only one FIFO pointer domain.
module clock_reset_release (
    input  logic clock,
    input  logic run_reset_n,
    output logic local_reset_n
);
    (* ASYNC_REG = "TRUE" *) logic [1:0] release_stage;

    always_ff @(posedge clock or negedge run_reset_n) begin
        if (!run_reset_n) release_stage <= 2'b00;
        else release_stage <= {release_stage[0], 1'b1};
    end

    assign local_reset_n = release_stage[1];
endmodule
