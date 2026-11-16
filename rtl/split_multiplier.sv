// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — signed product with registered half-width partial products

// product is multiplicand * multiplier at the latest rising edge, and zero after
// reset. Each operand splits into a signed high half and an unsigned low half;
// the four half products are the registers (17 x 17 bits at WIDTH 32, one math block
// each), and their shifted sum follows the edge. The exact product fits 2*WIDTH
// signed bits, so the wrapped sum of the sign-extended terms is exact.
module split_multiplier #(
    parameter int WIDTH = 32
) (
    input logic clock, reset_n,
    input logic signed [WIDTH-1:0] multiplicand, multiplier,
    output logic signed [2*WIDTH-1:0] product
);
    localparam int HALF = WIDTH / 2;
    if (WIDTH < 4 || WIDTH % 2 != 0) begin : invalid_width
        initial $fatal(1, "WIDTH must be even and at least four");
    end
    logic signed [HALF:0] multiplicand_high, multiplicand_low, multiplier_high, multiplier_low;
    logic signed [WIDTH+1:0] high_high, high_low, low_high, low_low;
    assign multiplicand_high = {multiplicand[WIDTH-1], multiplicand[WIDTH-1:HALF]};
    assign multiplicand_low = {1'b0, multiplicand[HALF-1:0]};
    assign multiplier_high = {multiplier[WIDTH-1], multiplier[WIDTH-1:HALF]};
    assign multiplier_low = {1'b0, multiplier[HALF-1:0]};
    always_ff @(posedge clock or negedge reset_n) begin
        if (!reset_n) begin
            high_high <= '0;
            high_low <= '0;
            low_high <= '0;
            low_low <= '0;
        end else begin
            high_high <= multiplicand_high * multiplier_high;
            high_low <= multiplicand_high * multiplier_low;
            low_high <= multiplicand_low * multiplier_high;
            low_low <= multiplicand_low * multiplier_low;
        end
    end
    logic signed [2*WIDTH-1:0] high_term, middle_term, low_term;
    assign high_term = {{(WIDTH-2){high_high[WIDTH+1]}}, high_high} << WIDTH;
    assign middle_term = ({{(WIDTH-2){high_low[WIDTH+1]}}, high_low}
        + {{(WIDTH-2){low_high[WIDTH+1]}}, low_high}) << HALF;
    assign low_term = {{(WIDTH-2){low_low[WIDTH+1]}}, low_low};
    assign product = high_term + middle_term + low_term;
endmodule
