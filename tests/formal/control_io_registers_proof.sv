// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — public-port source invariant proof wrapper

module control_io_registers_proof (
    input logic capture_clock, reset_n,
    input logic capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    output logic [31:0] capture_read_data,
    output logic [1:0] capture_response,
    input logic run_enabled, run_finished, capture_quiescent, safe_interrupt,
    input logic [31:0] cycle_number, total_misses, overflow_count,
    input logic signed [31:0] sample_value, velocity, reference_value,
    input logic [63:0] counter_ticks,
    output logic sample_read, actuator_write,
    output logic [31:0] command_cycle,
    output logic signed [31:0] command_value
);
control_io_registers dut (.*);
always @* begin
if (reset_n && capture_valid && capture_write && capture_response == 0) assert (capture_address == 8'h28 || capture_address == 8'h2c || capture_address == 8'h30);
if (reset_n && capture_valid && !capture_write && capture_response == 0) assert (capture_address == 8'h00 || capture_address == 8'h04 || capture_address == 8'h08 || capture_address == 8'h0c || capture_address == 8'h10 || capture_address == 8'h14 || capture_address == 8'h18 || capture_address == 8'h1c || capture_address == 8'h20 || capture_address == 8'h24 || capture_address == 8'h28 || capture_address == 8'h2c || capture_address == 8'h30 || capture_address == 8'h34);
if (actuator_write) assert (capture_write_data == 1 && run_enabled && !run_finished && !safe_interrupt);
end
endmodule
