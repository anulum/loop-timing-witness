// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — split multiplier identity proof

// From an unconstrained state: after a rising edge the product equals the direct
// product of that edge's operands. The same RTL is proved at reduced widths for
// every operand and, for WIDTH 32, with a constant multiplicand (CONSTANT selects
// COEFFICIENT).
// NEGATIVE_CONTROL expects the current operands, ignoring the edge of latency.
module split_multiplier_proof #(
    parameter int WIDTH = 6,
    parameter bit CONSTANT = 0,
    parameter logic signed [31:0] COEFFICIENT = 32'sd0,
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic clock,
    input logic signed [WIDTH-1:0] free_multiplicand, multiplier
);
    logic signed [WIDTH-1:0] multiplicand;
    logic signed [2*WIDTH-1:0] product, expected, direct;
    logic observed = 0;
    assign multiplicand = CONSTANT ? COEFFICIENT[WIDTH-1:0] : free_multiplicand;
    assign direct = $signed({{WIDTH{multiplicand[WIDTH-1]}}, multiplicand})
        * $signed({{WIDTH{multiplier[WIDTH-1]}}, multiplier});
    split_multiplier #(.WIDTH(WIDTH)) dut (
        .clock(clock), .reset_n(1'b1), .multiplicand(multiplicand),
        .multiplier(multiplier), .product(product)
    );
    always @(posedge clock) begin
        observed <= 1;
        expected <= direct;
    end
    always @* if (observed) assert (product == (NEGATIVE_CONTROL ? direct : expected));
endmodule
