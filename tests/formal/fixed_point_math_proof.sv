// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public-port source invariant proof wrapper

// The plant step binding: split multipliers of the state and of the next actuator
// feed fixed_point_math; a safe cycle applies C * SAFE_VALUE. With the thermal
// velocity coefficients A=B=C=0 every product register has a constant zero input,
// so after optimisation the step can neither clamp nor clip from any state.
module fixed_point_math_proof #(
    parameter logic signed [31:0] A = 32'sd0,
    parameter logic signed [31:0] B = 32'sd0,
    parameter logic signed [31:0] C = 32'sd0,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0
) (
    input logic clock, reset_n, actuator_safe,
    input logic signed [31:0] x, y, u,
    output logic signed [31:0] result,
    output logic clipped
);
    localparam logic signed [63:0] SAFE_PRODUCT = C * SAFE_VALUE;
    logic signed [63:0] ax, by, cu;
    split_multiplier x_product (
        .clock(clock), .reset_n(reset_n), .multiplicand(A), .multiplier(x), .product(ax)
    );
    split_multiplier y_product (
        .clock(clock), .reset_n(reset_n), .multiplicand(B), .multiplier(y), .product(by)
    );
    split_multiplier u_product (
        .clock(clock), .reset_n(reset_n), .multiplicand(C), .multiplier(u), .product(cu)
    );
    fixed_point_math dut (
        .ax(ax), .by(by), .cu(actuator_safe ? SAFE_PRODUCT : cu), .result(result),
        .clipped(clipped)
    );
    always @* begin
        assert (result == 0);
        assert (!clipped);
    end
endmodule
