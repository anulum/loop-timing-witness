// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Icicle AXI4-Lite fabric boundary

// The FIC0 interconnect must select this target at 0x60020000..0x600200ff.
// The low eight address bits are the complete witness register aperture.
module icicle_witness #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter bit THERMAL = 0
) (
    input logic bus_clock, capture_clock, run_reset_n,
    input logic [37:0] awaddr,
    input logic awvalid,
    output logic awready,
    input logic [31:0] wdata,
    input logic [3:0] wstrb,
    input logic wvalid,
    output logic wready,
    output logic [1:0] bresp,
    output logic bvalid,
    input logic bready,
    input logic [37:0] araddr,
    input logic arvalid,
    output logic arready,
    output logic [31:0] rdata,
    output logic [1:0] rresp,
    output logic rvalid,
    input logic rready,
    output logic interrupt_line
);
    wire [29:0] unused_awaddr_high = awaddr[37:8];
    wire [29:0] unused_araddr_high = araddr[37:8];
    wire unused_run_drained, unused_run_enabled, unused_run_finished;
    wire unused_capture_quiescent, unused_sample_read, unused_actuator_write;
    wire unused_buffer_full, unused_capture_active, unused_sample_valid;
    wire unused_sample_interrupt, unused_delayed_interrupt, unused_plant_clipped;
    wire unused_reference_clipped, unused_safe_interrupt, unused_fault_ready;
    wire unused_freeze_actuator, unused_overload_request, unused_drain_valid;
    wire unused_drain_empty;
    wire [31:0] unused_cycle_number, unused_delayed_cycle, unused_sample_value;
    wire [31:0] unused_velocity, unused_reference_value, unused_actuator_value;
    wire [31:0] unused_total_misses, unused_consecutive_misses, unused_late_commands;
    wire [31:0] unused_overflow_count;
    wire [63:0] unused_counter_ticks;
    wire [127:0] unused_drain_record;
    axi_control_witness #(.PERIOD_TICKS(PERIOD_TICKS), .THERMAL(THERMAL)) witness (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(awaddr[7:0]), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr[7:0]), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .interrupt_line(interrupt_line),
        .run_drained(unused_run_drained), .run_enabled(unused_run_enabled), .run_finished(unused_run_finished), .capture_quiescent(unused_capture_quiescent),
        .sample_read(unused_sample_read), .actuator_write(unused_actuator_write), .buffer_full(unused_buffer_full), .capture_active(unused_capture_active),
        .sample_valid(unused_sample_valid), .sample_interrupt(unused_sample_interrupt), .delayed_interrupt(unused_delayed_interrupt), .cycle_number(unused_cycle_number),
        .delayed_cycle(unused_delayed_cycle), .sample_value(unused_sample_value), .velocity(unused_velocity), .reference_value(unused_reference_value),
        .actuator_value(unused_actuator_value), .plant_clipped(unused_plant_clipped), .reference_clipped(unused_reference_clipped), .safe_interrupt(unused_safe_interrupt),
        .fault_ready(unused_fault_ready), .freeze_actuator(unused_freeze_actuator), .overload_request(unused_overload_request), .total_misses(unused_total_misses),
        .consecutive_misses(unused_consecutive_misses), .late_commands(unused_late_commands), .overflow_count(unused_overflow_count), .counter_ticks(unused_counter_ticks),
        .drain_valid(unused_drain_valid), .drain_empty(unused_drain_empty), .drain_record(unused_drain_record)
    );
endmodule
