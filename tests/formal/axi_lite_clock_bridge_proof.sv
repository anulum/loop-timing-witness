// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public-port source invariant proof wrapper

module axi_lite_clock_bridge_proof #(
    parameter bit ENABLE_LOCAL = 0
) (
    input logic bus_clock, capture_clock, run_reset_n,
    input logic [7:0] awaddr,
    input logic awvalid,
    output logic awready,
    input logic [31:0] wdata,
    input logic [3:0] wstrb,
    input logic wvalid,
    output logic wready,
    output logic [1:0] bresp,
    output logic bvalid,
    input logic bready,
    input logic [7:0] araddr,
    input logic arvalid,
    output logic arready,
    output logic [31:0] rdata,
    output logic [1:0] rresp,
    output logic rvalid,
    input logic rready,
    output logic capture_valid, capture_write,
    output logic [7:0] capture_address,
    output logic [31:0] capture_write_data,
    output logic [3:0] capture_write_strobes,
    input logic [31:0] capture_read_data,
    input logic [1:0] capture_response,
    output logic local_valid, local_write,
    output logic [7:0] local_address,
    output logic [31:0] local_write_data,
    output logic [3:0] local_write_strobes,
    input logic [31:0] local_read_data,
    input logic [1:0] local_response
);
axi_lite_clock_bridge #(.ENABLE_LOCAL(ENABLE_LOCAL)) dut (.*);
always @* begin
assert (!local_valid);
end
endmodule
