// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — invalid fabric parameter elaboration

module control_parameters_tb #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter int GROUP_ADDRESS_BITS = 6
);
    control_plant_witness #(.PERIOD_TICKS(PERIOD_TICKS), .MISS_LIMIT(MISS_LIMIT),
        .GROUP_ADDRESS_BITS(GROUP_ADDRESS_BITS)) instrument ();
    initial begin #1; $finish; end
endmodule
