// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — capture register transactions through AXI and actual plant

`timescale 1ns/1ps
module control_io_registers_tb #(
    parameter int BUS_HALF_PERIOD = 7,
    parameter bit THERMAL = 0,
    parameter bit CONFIGURATION_ONLY = 0,
    parameter int FAULT_KIND = 0,
    parameter int REFERENCE_MODE = 0,
    parameter logic [31:0] PERIOD_TICKS = CONFIGURATION_ONLY ? 256 : 32768,
    parameter logic [31:0] MISS_LIMIT = CONFIGURATION_ONLY ? 3 : 1
);
    logic bus_clock = 0, capture_clock = 0, run_reset_n = 0, enable, reset_n;
    logic [7:0] awaddr = 0, araddr = 0, capture_address;
    logic awvalid = 0, awready, wvalid = 0, wready, arvalid = 0, arready;
    logic bvalid, bready = 0, rvalid, rready = 0;
    logic [31:0] wdata = 0, rdata, capture_write_data, capture_read_data;
    logic [3:0] wstrb = 0, capture_write_strobes;
    logic [1:0] bresp, rresp, capture_response;
    logic capture_valid, capture_write, sample_read, actuator_write, sample_valid;
    logic run_finished, capture_quiescent, safe_interrupt;
    logic [31:0] cycle_number, total_misses, command_cycle, overflow_count;
    logic signed [31:0] sample_value, velocity, reference_value, actuator_value, command_value;
    logic [63:0] counter_ticks, expected_ticks, observed_ticks;
    logic [31:0] expected_sample, expected_cycle, expected_velocity, expected_reference, expected_misses;
    logic [31:0] value;
    logic [31:0] io_read_data, config_read_data, stop_after_cycle, fault_cycle, fault_periods;
    logic [1:0] io_response, config_response, reference_mode, fault_kind;
    logic signed [31:0] reference_amplitude, reference_offset, ramp_increment;
    logic [3:0] phase_increment;
    logic fault_arm, fault_ready, freeze_actuator, overload_request;
    logic drain_valid, drain_empty;
    logic [127:0] drain_record;
    integer reads = 0, writes = 0, deadlines = 0;
    integer samples = 0, interrupts = 0, delayed = 0;
    logic freeze_seen = 0, overload_seen = 0;
    logic [31:0] expected_reference_sample;
    always #(BUS_HALF_PERIOD) bus_clock = ~bus_clock;
    always #5 capture_clock = ~capture_clock;
    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(run_reset_n), .local_reset_n(reset_n)
    );
    axi_lite_clock_bridge transport (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wstrb(wstrb),
        .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .capture_valid(capture_valid), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(capture_read_data),
        .capture_response(capture_response), .local_valid(), .local_write(), .local_address(),
        .local_write_data(), .local_write_strobes(), .local_read_data(32'd0), .local_response(2'd0)
    );
    control_io_registers registers (
        .capture_clock(capture_clock), .reset_n(reset_n), .capture_valid(capture_valid && capture_address < 8'h38),
        .capture_write(capture_write), .capture_address(capture_address),
        .capture_write_data(capture_write_data), .capture_write_strobes(capture_write_strobes),
        .capture_read_data(io_read_data), .capture_response(io_response),
        .run_enabled(enable), .run_finished(run_finished), .capture_quiescent(capture_quiescent),
        .safe_interrupt(safe_interrupt), .cycle_number(cycle_number), .total_misses(total_misses), .overflow_count(overflow_count),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value),
        .counter_ticks(counter_ticks), .sample_read(sample_read), .actuator_write(actuator_write),
        .command_cycle(command_cycle), .command_value(command_value)
    );
    assign capture_read_data = capture_address >= 8'h38 ? config_read_data : io_read_data;
    assign capture_response = capture_address >= 8'h38 ? config_response : io_response;
    run_configuration_registers #(.PERIOD_TICKS(PERIOD_TICKS), .MISS_LIMIT(MISS_LIMIT), .THERMAL(THERMAL)) configuration (
        .capture_clock(capture_clock), .reset_n(reset_n),
        .capture_valid(capture_valid && capture_address >= 8'h38), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(config_read_data),
        .capture_response(config_response), .run_enabled(enable), .stop_after_cycle(stop_after_cycle),
        .reference_mode(reference_mode), .reference_amplitude(reference_amplitude),
        .reference_offset(reference_offset), .ramp_increment(ramp_increment), .phase_increment(phase_increment),
        .fault_arm(fault_arm), .fault_kind(fault_kind), .fault_cycle(fault_cycle), .fault_periods(fault_periods),
        .fault_ready(fault_ready), .freeze_actuator(freeze_actuator), .overload_request(overload_request)
    );
    logic sample_interrupt, delayed_interrupt;
    logic [31:0] delayed_cycle;
    control_plant_witness #(.PERIOD_TICKS(PERIOD_TICKS), .MISS_LIMIT(MISS_LIMIT), .THERMAL(THERMAL), .ADDRESS_BITS(6)) plant (
        .capture_clock(capture_clock), .drain_clock(bus_clock), .run_reset_n(run_reset_n),
        .enable(enable), .stop_after_cycle(stop_after_cycle), .sample_read(sample_read), .actuator_write(actuator_write),
        .command_cycle(command_cycle), .command_value(command_value), .fault_arm(fault_arm),
        .fault_kind(fault_kind), .fault_cycle(fault_cycle), .fault_periods(fault_periods), .reference_mode(reference_mode),
        .reference_amplitude(reference_amplitude), .reference_offset(reference_offset), .ramp_increment(ramp_increment),
        .phase_increment(phase_increment), .sample_valid(sample_valid), .cycle_number(cycle_number),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value),
        .actuator_value(actuator_value), .safe_interrupt(safe_interrupt), .total_misses(total_misses),
        .overflow_count(overflow_count), .counter_ticks(counter_ticks), .run_finished(run_finished),
        .capture_quiescent(capture_quiescent), .drain_request(1'b1), .drain_valid(drain_valid),
        .drain_record(drain_record), .drain_empty(drain_empty), .buffer_full(), .capture_active(),
        .sample_interrupt(sample_interrupt), .delayed_interrupt(delayed_interrupt), .delayed_cycle(delayed_cycle), .plant_clipped(),
        .reference_clipped(), .fault_ready(fault_ready), .freeze_actuator(freeze_actuator), .overload_request(overload_request),
        .consecutive_misses(), .late_commands()
    );
    always @(posedge capture_clock) begin
        if (CONFIGURATION_ONLY && reset_n) begin
            if (sample_interrupt) interrupts = interrupts + 1;
            if (delayed_interrupt) begin
                delayed = delayed + 1;
                if (delayed_cycle != 0) $fatal(1, "delayed origin changed through configuration");
            end
            if (freeze_actuator) freeze_seen = 1;
            if (overload_request) overload_seen = 1;
        end
    end
    always @(negedge capture_clock) begin
        if (CONFIGURATION_ONLY && sample_valid) begin
            samples = samples + 1;
            case (REFERENCE_MODE)
                0: expected_reference_sample = 41943040;
                1: expected_reference_sample = 8388608 + 8388608 * cycle_number;
                2: expected_reference_sample = cycle_number == 1 ? 41943040 : 8388608;
                default: $fatal(1, "unsupported test reference mode");
            endcase
            if (reference_value != expected_reference_sample)
                $fatal(1, "configured reference does not match actual waveform");
        end
    end
    always @(posedge capture_clock) begin
        if (sample_read) begin
            expected_sample = sample_value;
            expected_cycle = cycle_number;
            expected_velocity = velocity;
            expected_reference = reference_value;
            expected_ticks = counter_ticks;
            expected_misses = total_misses;
        end
        if (capture_valid && !capture_write && capture_address == 8'h08)
            observed_ticks = counter_ticks;
        if (capture_quiescent && !run_finished) $fatal(1, "quiescent before final deadline");
    end
    always @(posedge bus_clock) begin
        #1;
        if (drain_valid) begin
            case (drain_record[7:0])
                2: begin
                    reads = reads + 1;
                    if (drain_record[127:64] != expected_ticks)
                        $fatal(1, "read event and snapshot edge differ");
                end
                3: writes = writes + 1;
                4: deadlines = deadlines + 1;
                default: begin end
            endcase
        end
    end
    task automatic read_register(input logic [7:0] address, input logic [1:0] response,
        output logic [31:0] result);
        @(negedge bus_clock);
        wait (arready);
        araddr = address;
        arvalid = 1;
        @(negedge bus_clock);
        arvalid = 0;
        wait (rvalid);
        @(negedge bus_clock);
        result = rdata;
        repeat (3) begin
            @(negedge bus_clock);
            if (!rvalid || rresp !== response || rdata !== result)
                $fatal(1, "capture register response differs or changed under stall");
        end
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
    endtask
    task automatic write_register(input logic [7:0] address, input logic [31:0] data,
        input logic [3:0] strobes, input logic [1:0] response);
        @(negedge bus_clock);
        wait (awready && wready);
        awaddr = address;
        awvalid = 1;
        wdata = data;
        wstrb = strobes;
        wvalid = 1;
        @(negedge bus_clock);
        awvalid = 0;
        wvalid = 0;
        wait (bvalid);
        @(negedge bus_clock);
        if (bresp !== response) $fatal(1, "capture register write response differs");
        bready = 1;
        @(negedge bus_clock);
        bready = 0;
    endtask
    task automatic check_snapshot;
        read_register(8'h10, 0, value);
        if (value != expected_cycle) $fatal(1, "snapshot cycle changed");
        read_register(8'h14, 0, value);
        if (value != expected_velocity) $fatal(1, "snapshot velocity changed");
        read_register(8'h18, 0, value);
        if (value != expected_reference) $fatal(1, "snapshot reference changed");
        read_register(8'h1c, 0, value);
        if (value != expected_ticks[31:0]) $fatal(1, "snapshot low time changed");
        read_register(8'h20, 0, value);
        if (value != expected_ticks[63:32]) $fatal(1, "snapshot high time changed");
        read_register(8'h24, 0, value);
        if (value != expected_misses) $fatal(1, "snapshot misses changed");
    endtask
    task automatic reset_run;
        @(negedge bus_clock);
        run_reset_n = 0;
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (arready && awready && wready);
    endtask
    task automatic expect_register(input logic [7:0] address, input logic [31:0] expected);
        read_register(address, 0, value);
        if (value != expected) $fatal(1, "configuration readback differs at %h", address);
    endtask
    task automatic verify_configuration;
        reset_run();
        expect_register(8'h38, 0);
        expect_register(8'h40, PERIOD_TICKS);
        expect_register(8'h6c, 32'(THERMAL));
        expect_register(8'h70, MISS_LIMIT);
        expect_register(8'h74, 0);
        expect_register(8'h78, 24);
        expect_register(8'h7c, 1);
        write_register(8'h38, 0, 15, 2);
        write_register(8'h40, 1, 15, 2);
        write_register(8'h44, 3, 15, 2);
        write_register(8'h54, 16, 15, 2);
        write_register(8'h58, 4, 15, 2);
        write_register(8'h3d, 1, 15, 2);
        read_register(8'h80, 2, value);
        write_register(8'h3c, 2, 0, 2);
        write_register(8'h64, 1, 15, 2);
        write_register(8'h3c, 2, 15, 0);
        write_register(8'h44, 32'(REFERENCE_MODE), 15, 0);
        write_register(8'h48, 33554432, 15, 0);
        write_register(8'h4c, 8388608, 15, 0);
        write_register(8'h50, 4194304, 15, 0);
        write_register(8'h54, 4, 15, 0);
        write_register(8'h58, 32'(FAULT_KIND), 15, 0);
        write_register(8'h5c, 3, 15, 0);
        write_register(8'h60, 1, 15, 0);
        write_register(8'h64, 1, 15, 2);
        write_register(8'h5c, 0, 15, 0);
        expect_register(8'h3c, 2);
        expect_register(8'h44, 32'(REFERENCE_MODE));
        expect_register(8'h48, 33554432);
        expect_register(8'h4c, 8388608);
        expect_register(8'h50, 4194304);
        expect_register(8'h54, 4);
        expect_register(8'h58, 32'(FAULT_KIND));
        expect_register(8'h5c, 0);
        expect_register(8'h60, 1);
        expect_register(8'h64, 0);
        expect_register(8'h68, 1);
        write_register(8'h64, 0, 15, 2);
        write_register(8'h64, 1, 0, 2);
        write_register(8'h64, 1, 15, 0);
        expect_register(8'h64, 1);
        write_register(8'h64, 1, 15, 2);
        write_register(8'h3c, 1, 15, 2);
        write_register(8'h48, 1, 15, 2);
        write_register(8'h38, 1, 15, 0);
        write_register(8'h38, 1, 15, 2);
        write_register(8'h38, 0, 15, 2);
        write_register(8'h44, 0, 15, 2);
        wait (run_finished && capture_quiescent && drain_empty);
        repeat (10) @(negedge bus_clock);
        expect_register(8'h34, 3);
        expect_register(8'h30, 0);
        if (samples != 3 || total_misses != 3 || !safe_interrupt || overflow_count)
            $fatal(1, "configured run did not close with actual monitor state");
        if (interrupts != (FAULT_KIND < 2 ? 2 : 3) || delayed != (FAULT_KIND == 1 ? 1 : 0))
            $fatal(1, "configured IRQ fault did not reach actual injector");
        if (freeze_seen != (FAULT_KIND == 2) || overload_seen != (FAULT_KIND == 3))
            $fatal(1, "configured fault action differs");
        expect_register(8'h38, 1);
        expect_register(8'h48, 33554432);
        reset_run();
        expect_register(8'h38, 0);
        expect_register(8'h64, 0);
        expect_register(8'h48, 16777216);
    endtask
    initial begin
        if (CONFIGURATION_ONLY) begin
            verify_configuration();
            $display("RUN_CONFIGURATION_PASS immutable=1 waveform=actual faults=actual");
            $finish;
        end
        reset_run();
        read_register(8'h00, 2, value);
        read_register(8'h10, 2, value);
        read_register(8'h0c, 2, value);
        read_register(8'h04, 0, value);
        if (value != 0) $fatal(1, "reset status retained state");
        write_register(8'h30, 1, 15, 2);
        write_register(8'h28, 0, 15, 0);
        write_register(8'h2c, 16777216, 15, 0);
        write_register(8'h30, 1, 15, 2);
        if (actuator_value != 0) $fatal(1, "inactive commit changed actuator");
        reset_run();
        write_register(8'h3c, 1, 15, 0);
        write_register(8'h38, 1, 15, 0);
        wait (enable);
        read_register(8'h00, 0, value);
        if (value != expected_sample) $fatal(1, "sample response not from capture edge");
        check_snapshot();
        read_register(8'h08, 0, value);
        if (value != observed_ticks[31:0]) $fatal(1, "clock observation low word differs");
        read_register(8'h0c, 0, value);
        if (value != observed_ticks[63:32]) $fatal(1, "clock observation upper word differs");
        write_register(8'h2c, 16777216, 15, 0);
        write_register(8'h30, 1, 15, 2);
        write_register(8'h28, 0, 15, 0);
        write_register(8'h30, 0, 15, 2);
        write_register(8'h30, 1, 0, 2);
        write_register(8'h30, 1, 15, 0);
        if (actuator_value != 16777216) $fatal(1, "commit did not reach actual actuator");
        write_register(8'h30, 1, 15, 2);
        write_register(8'h2c, 1, 1, 2);
        read_register(8'h2c, 0, value);
        if (value != 16777216) $fatal(1, "partial write corrupted command stage");
        read_register(8'h28, 0, value);
        if (value != 0) $fatal(1, "command cycle changed");
        write_register(8'h28, 1, 1, 2);
        write_register(8'h29, 1, 15, 2);
        write_register(8'h34, 1, 15, 2);
        write_register(8'h28, 0, 15, 0);
        write_register(8'h30, 1, 15, 2);
        write_register(8'h2c, 16777216, 15, 0);
        write_register(8'h30, 1, 15, 0);
        write_register(8'h00, 1, 15, 2);
        read_register(8'h11, 2, value);
        expect_register(8'h34, 0);
        expect_register(8'h30, 0);
        wait (sample_valid && cycle_number == 1);
        check_snapshot();
        write_register(8'h28, 1, 15, 0);
        write_register(8'h2c, 32'hff800000, 15, 0);
        write_register(8'h30, 1, 15, 0);
        if (actuator_value != -8388608) $fatal(1, "cycle/value commit mixed stages");
        read_register(8'h00, 0, value);
        if (value != expected_sample || expected_cycle != 1) $fatal(1, "snapshot did not advance");
        check_snapshot();
        wait (run_finished && capture_quiescent && drain_empty);
        repeat (10) @(negedge bus_clock);
        if (reads != 2 || writes != 2 || deadlines != 2 || total_misses || safe_interrupt || overflow_count)
            $fatal(1, "register control chain did not finish healthy");
        read_register(8'h00, 2, value);
        check_snapshot();
        read_register(8'h04, 0, value);
        if (value != 23) $fatal(1, "finished status not truthful");
        write_register(8'h28, 1, 15, 0);
        write_register(8'h2c, 16777216, 15, 0);
        write_register(8'h30, 1, 15, 2);
        if (actuator_value != -8388608) $fatal(1, "finished commit changed actuator");
        reset_run();
        write_register(8'h3c, 1, 15, 0);
        write_register(8'h38, 1, 15, 0);
        wait (safe_interrupt);
        write_register(8'h28, cycle_number, 15, 0);
        write_register(8'h2c, 16777216, 15, 0);
        write_register(8'h30, 1, 15, 2);
        if (actuator_value != 0) $fatal(1, "safe actuator escaped through commit");
        read_register(8'h04, 0, value);
        if (!value[3]) $fatal(1, "safe status missing");
        reset_run();
        read_register(8'h10, 2, value);
        read_register(8'h0c, 2, value);
        $display("CONTROL_REGISTERS_PASS snapshot=coherent commands=atomic safe=latched");
        $finish;
    end
    initial begin
        #3000000;
        $fatal(1, "control register simulation timeout");
    end
endmodule
