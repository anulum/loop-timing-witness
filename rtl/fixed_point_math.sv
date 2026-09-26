// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — saturating Q8.24 multiply-add

// Q8.24: signed 32-bit values, arithmetic floor after a wide multiply-add.
module fixed_point_math #(
    parameter logic signed [31:0] A = 32'sd0,
    parameter logic signed [31:0] B = 32'sd0,
    parameter logic signed [31:0] C = 32'sd0
) (
    input logic signed [31:0] x, y, u,
    output logic signed [31:0] result,
    output logic clipped
);
    logic signed [63:0] ax, by, cu;
    logic signed [65:0] total, scaled;
    assign ax = A * x;
    assign by = B * y;
    assign cu = C * u;
    assign total = {{2{ax[63]}}, ax} + {{2{by[63]}}, by} + {{2{cu[63]}}, cu};
    assign scaled = total >>> 24;
    always_comb begin
        clipped = 1'b1;
        if (scaled > 66'sd2147483647) result = 32'sh7fffffff;
        else if (scaled < -66'sd2147483648) result = 32'sh80000000;
        else begin
            result = scaled[31:0];
            clipped = 1'b0;
        end
    end
endmodule
