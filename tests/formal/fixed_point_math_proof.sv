// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public-port source invariant proof wrapper

module fixed_point_math_proof #(
    parameter logic signed [31:0] A = 32'sd0,
    parameter logic signed [31:0] B = 32'sd0,
    parameter logic signed [31:0] C = 32'sd0
) (
    input logic signed [31:0] x, y, u,
    output logic signed [31:0] result,
    output logic clipped
);
fixed_point_math #(.A(A),.B(B),.C(C)) dut (.*);
always @* begin
assert (result == 0);
assert (!clipped);
end
endmodule
