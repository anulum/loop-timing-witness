// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public-port source invariant proof wrapper

module run_configuration_registers_proof #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0,
    parameter bit THERMAL = 0
) (
    input logic capture_clock, reset_n,
    input logic capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    output logic [31:0] capture_read_data,
    output logic [1:0] capture_response,
    output logic run_enabled,
    output logic [31:0] stop_after_cycle,
    output logic [1:0] reference_mode,
    output logic signed [31:0] reference_amplitude, reference_offset, ramp_increment,
    output logic [3:0] phase_increment,
    output logic fault_arm,
    output logic [1:0] fault_kind,
    output logic [31:0] fault_cycle, fault_periods,
    input logic fault_ready, freeze_actuator, overload_request
);
run_configuration_registers #(.PERIOD_TICKS(PERIOD_TICKS),.MISS_LIMIT(MISS_LIMIT),.SAFE_VALUE(SAFE_VALUE),.THERMAL(THERMAL)) dut (.*);
always @* begin
if (reset_n && capture_valid && capture_write && capture_response == 0) assert (capture_address == 8'h38 || capture_address == 8'h3c || capture_address == 8'h44 || capture_address == 8'h48 || capture_address == 8'h4c || capture_address == 8'h50 || capture_address == 8'h54 || capture_address == 8'h58 || capture_address == 8'h5c || capture_address == 8'h60 || capture_address == 8'h64);
end
endmodule
