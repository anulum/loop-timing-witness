// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — production AXI control registers plant and event window

// AXI addresses are offsets inside an externally decoded 8 KiB aperture of two 4 KiB pages
// (register map version 2): the run page holds every register at 0x000-0x0ff except the fault
// schedule, which only the fault page reaches, at 0x1000-0x100c (kind, target cycle, duration,
// arm). A system can therefore map the run page for a controller without the fault registers.
// run_drained and drain stream belong to bus_clock; plant diagnostics belong
// to capture_clock. Raw IRQ strobes belong to capture_clock; interrupt_line is
// a retained bus-domain level. The three event mirrors belong to capture_clock and are
// registers, for board pins and an external time tagger. External reset aborts AXI; bus-local0x98 resets
// the run banks while preserving the AXI transport and its accepted responses.
module axi_control_witness #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0,
    parameter bit THERMAL = 0,
    parameter int ADDRESS_BITS = 14,
    parameter int GROUP_ADDRESS_BITS = 6,
    parameter logic signed [31:0] A00 = 32'sd16777208,
    parameter logic signed [31:0] A01 = 32'sd16769,
    parameter logic signed [31:0] A10 = -32'sd16769,
    parameter logic signed [31:0] A11 = 32'sd16760439,
    parameter logic signed [31:0] B0 = 32'sd8,
    parameter logic signed [31:0] B1 = 32'sd16769,
    parameter logic signed [31:0] THERMAL_A = 32'sd16760447,
    parameter logic signed [31:0] THERMAL_B = 32'sd16769
) (
    input logic bus_clock, capture_clock, run_reset_n,
    input logic [12:0] awaddr,
    input logic awvalid,
    output logic awready,
    input logic [31:0] wdata,
    input logic [3:0] wstrb,
    input logic wvalid,
    output logic wready,
    output logic [1:0] bresp,
    output logic bvalid,
    input logic bready,
    input logic [12:0] araddr,
    input logic arvalid,
    output logic arready,
    output logic [31:0] rdata,
    output logic [1:0] rresp,
    output logic rvalid,
    input logic rready,
    input logic pps_in,
    output logic run_drained, run_enabled, run_finished, capture_quiescent, interrupt_line,
    output logic sample_read, actuator_write,
    output logic sample_ready_mirror, actuator_write_mirror, safe_state_mirror,
    output logic buffer_full, capture_active, sample_valid, sample_interrupt, delayed_interrupt,
    output logic [31:0] cycle_number, delayed_cycle,
    output logic signed [31:0] sample_value, velocity, reference_value, actuator_value,
    output logic plant_clipped, reference_clipped,
    output logic safe_interrupt, fault_ready, freeze_actuator, overload_request,
    output logic [31:0] total_misses, consecutive_misses, late_commands, overflow_count,
    output logic [63:0] counter_ticks,
    output logic drain_valid, drain_empty,
    output logic [127:0] drain_record
);
    logic capture_reset_n, bus_reset_n, capture_valid, capture_write;
    logic [7:0] capture_address, local_address;
    logic [31:0] capture_write_data, capture_read_data, io_data, config_data;
    logic [3:0] capture_write_strobes, local_write_strobes;
    logic [1:0] capture_response, io_response, config_response, local_response;
    logic local_valid, local_write, drain_request;
    logic [31:0] local_write_data, local_read_data;
    logic [31:0] stop_after_cycle, command_cycle, fault_cycle, fault_periods;
    logic signed [31:0] command_value, reference_amplitude, reference_offset, ramp_increment;
    logic [1:0] reference_mode, fault_kind;
    logic [3:0] phase_increment;
    logic fault_arm;
    logic bank_reset_n, transport_reset_n;
    logic [31:0] window_read_data, reset_read_data;
    logic [1:0] window_response, reset_response;
    logic capture_bank_ready, capture_reset_allowed;
    logic irq_selected;
    // The page decode maps the fault page onto the internal schedule offsets 0x58-0x64, and every
    // other address, the schedule offsets of the run page included, onto the unassigned local
    // offset 0xfc, which the record window refuses with SLVERR.
    function automatic logic [7:0] register_offset(input logic [12:0] address);
        if (address[12:8] == 5'd0 && (address[7:0] < 8'h58 || address[7:0] > 8'h67))
            register_offset = address[7:0];
        else if (address[12:4] == 9'h100)
            register_offset = 8'h58 + {4'd0, address[3:0]};
        else
            register_offset = 8'hfc;
    endfunction
    wire [7:0] bus_write_offset = register_offset(awaddr);
    wire [7:0] bus_read_offset = register_offset(araddr);
    logic [31:0] irq_read_data;
    logic [1:0] irq_response;
    clock_reset_release transport_reset (
        .clock(bus_clock), .run_reset_n(run_reset_n), .local_reset_n(transport_reset_n)
    );
    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(bank_reset_n), .local_reset_n(capture_reset_n)
    );
    clock_reset_release bus_reset (
        .clock(bus_clock), .run_reset_n(bank_reset_n), .local_reset_n(bus_reset_n)
    );
    // Both cross into the bus domain through synchronisers, so each is a register:
    // the reset permission would otherwise glitch when both run flags clear together.
    always_ff @(posedge capture_clock or negedge capture_reset_n) begin
        if (!capture_reset_n) begin
            capture_bank_ready <= 0;
            capture_reset_allowed <= 1;
        end else begin
            capture_bank_ready <= 1;
            capture_reset_allowed <= !run_enabled || run_finished;
        end
    end
    assign irq_selected = local_address >= 8'h9c && local_address <= 8'ha8;
    assign local_read_data = local_address == 8'h98 ? reset_read_data :
        (irq_selected ? irq_read_data : window_read_data);
    assign local_response = local_address == 8'h98 ? reset_response :
        (irq_selected ? irq_response : window_response);
    retained_interrupt irq_control (
        .capture_clock(capture_clock), .capture_reset_n(capture_reset_n),
        .bus_clock(bus_clock), .bus_reset_n(bus_reset_n), .sample_interrupt(sample_interrupt),
        .safe_interrupt(safe_interrupt), .run_finished(run_finished),
        .local_valid(local_valid && irq_selected), .local_write(local_write), .local_address(local_address),
        .local_write_data(local_write_data), .local_write_strobes(local_write_strobes),
        .local_read_data(irq_read_data), .local_response(irq_response), .interrupt_line(interrupt_line)
    );
    run_reset_control reset_control (
        .bus_clock(bus_clock), .reset_n(transport_reset_n), .external_reset_n(run_reset_n),
        .local_valid(local_valid && local_address == 8'h98), .local_write(local_write),
        .local_write_data(local_write_data), .local_write_strobes(local_write_strobes),
        .local_read_data(reset_read_data), .local_response(reset_response),
        .capture_reset_ready(capture_bank_ready), .bus_reset_ready(bus_reset_n),
        .capture_reset_allowed(capture_reset_allowed), .bank_reset_n(bank_reset_n)
    );
    axi_lite_clock_bridge #(.ENABLE_LOCAL(1)) transport (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(bus_write_offset), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wstrb(wstrb),
        .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(bus_read_offset), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .capture_valid(capture_valid), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(capture_read_data),
        .capture_response(capture_response), .local_valid(local_valid), .local_write(local_write),
        .local_address(local_address), .local_write_data(local_write_data),
        .local_write_strobes(local_write_strobes), .local_read_data(local_read_data),
        .local_response(local_response)
    );
    assign capture_read_data = capture_address >= 8'h38 ? config_data : io_data;
    assign capture_response = capture_address >= 8'h38 ? config_response : io_response;
    control_io_registers io_registers (
        .capture_clock(capture_clock), .reset_n(capture_reset_n),
        .capture_valid(capture_valid && capture_address < 8'h38), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(io_data), .capture_response(io_response),
        .run_enabled(run_enabled), .run_finished(run_finished), .capture_quiescent(capture_quiescent),
        .safe_interrupt(safe_interrupt), .cycle_number(cycle_number), .total_misses(total_misses), .overflow_count(overflow_count),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value), .counter_ticks(counter_ticks),
        .sample_read(sample_read), .actuator_write(actuator_write), .command_cycle(command_cycle), .command_value(command_value)
    );
    run_configuration_registers #(.PERIOD_TICKS(PERIOD_TICKS), .MISS_LIMIT(MISS_LIMIT),
        .SAFE_VALUE(SAFE_VALUE), .THERMAL(THERMAL)) configuration (
        .capture_clock(capture_clock), .reset_n(capture_reset_n),
        .capture_valid(capture_valid && capture_address >= 8'h38), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(config_data), .capture_response(config_response),
        .run_enabled(run_enabled), .stop_after_cycle(stop_after_cycle), .reference_mode(reference_mode),
        .reference_amplitude(reference_amplitude), .reference_offset(reference_offset), .ramp_increment(ramp_increment),
        .phase_increment(phase_increment), .fault_arm(fault_arm), .fault_kind(fault_kind),
        .fault_cycle(fault_cycle), .fault_periods(fault_periods), .fault_ready(fault_ready),
        .freeze_actuator(freeze_actuator), .overload_request(overload_request)
    );
    control_plant_witness #(.PERIOD_TICKS(PERIOD_TICKS), .MISS_LIMIT(MISS_LIMIT),
        .SAFE_VALUE(SAFE_VALUE), .THERMAL(THERMAL), .ADDRESS_BITS(ADDRESS_BITS),
        .GROUP_ADDRESS_BITS(GROUP_ADDRESS_BITS), .A00(A00), .A01(A01), .A10(A10), .A11(A11),
        .B0(B0), .B1(B1), .THERMAL_A(THERMAL_A), .THERMAL_B(THERMAL_B)) plant (
        .capture_clock(capture_clock), .drain_clock(bus_clock), .run_reset_n(bank_reset_n),
        .enable(run_enabled), .stop_after_cycle(stop_after_cycle), .sample_read(sample_read),
        .actuator_write(actuator_write), .command_cycle(command_cycle), .command_value(command_value),
        .fault_arm(fault_arm), .fault_kind(fault_kind), .fault_cycle(fault_cycle), .fault_periods(fault_periods),
        .reference_mode(reference_mode), .reference_amplitude(reference_amplitude), .reference_offset(reference_offset),
        .ramp_increment(ramp_increment), .phase_increment(phase_increment), .pps_in(pps_in),
        .buffer_full(buffer_full),
        .capture_active(capture_active), .sample_valid(sample_valid), .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt), .cycle_number(cycle_number), .delayed_cycle(delayed_cycle),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value), .actuator_value(actuator_value),
        .plant_clipped(plant_clipped), .reference_clipped(reference_clipped), .safe_interrupt(safe_interrupt),
        .fault_ready(fault_ready), .freeze_actuator(freeze_actuator), .overload_request(overload_request),
        .total_misses(total_misses), .consecutive_misses(consecutive_misses), .late_commands(late_commands),
        .overflow_count(overflow_count), .counter_ticks(counter_ticks), .drain_request(drain_request),
        .drain_valid(drain_valid), .drain_empty(drain_empty), .drain_record(drain_record),
        .run_finished(run_finished), .capture_quiescent(capture_quiescent),
        .sample_ready_mirror(sample_ready_mirror), .actuator_write_mirror(actuator_write_mirror),
        .safe_state_mirror(safe_state_mirror)
    );
    event_record_window window (
        .bus_clock(bus_clock), .reset_n(bus_reset_n),
        .local_valid(local_valid && local_address != 8'h98 && !irq_selected), .local_write(local_write),
        .local_address(local_address), .local_write_data(local_write_data), .local_write_strobes(local_write_strobes),
        .local_read_data(window_read_data), .local_response(window_response), .drain_request(drain_request),
        .drain_valid(drain_valid), .drain_empty(drain_empty), .drain_record(drain_record),
        .capture_quiescent(capture_quiescent), .run_drained(run_drained)
    );
endmodule
