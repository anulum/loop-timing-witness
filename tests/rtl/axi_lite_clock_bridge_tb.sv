// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AXI transaction transport into the actual plant

`timescale 1ns/1ps
module axi_lite_clock_bridge_tb #(
    parameter int BUS_HALF_PERIOD = 7,
    parameter bit THERMAL = 0,
    parameter bit ENABLE_LOCAL = 1
);
    logic bus_clock = 0, capture_clock = 0, run_reset_n = 0, enable = 0;
    logic capture_clock_enabled = 1;
    logic [7:0] awaddr = 0, araddr = 0, capture_address;
    logic awvalid = 0, awready, wvalid = 0, wready, arvalid = 0, arready;
    logic bvalid, bready = 0, rvalid, rready = 0;
    logic [31:0] wdata = 0, rdata, capture_write_data, capture_read_data;
    logic [3:0] wstrb = 0, capture_write_strobes;
    logic [1:0] bresp, rresp, capture_response;
    logic capture_valid, capture_write, capture_active, sample_valid, safe_interrupt;
    logic [63:0] counter_ticks;
    logic [31:0] cycle_number, total_misses, overflow_count;
    logic signed [31:0] sample_value, actuator_value;
    logic [31:0] expected_read;
    logic [1:0] expected_read_response;
    integer captures = 0, capture_before;
    logic bus_reset_n, local_valid, local_write, drain_request, drain_valid, drain_empty;
    logic [7:0] local_address;
    logic [31:0] local_write_data, local_read_data, word_value;
    logic [3:0] local_write_strobes;
    logic [1:0] local_response;
    logic [127:0] drain_record;
    logic [63:0] first_sample_ticks;
    logic capture_quiescent, run_drained;
    always #(BUS_HALF_PERIOD) bus_clock = ~bus_clock;
    always #5 if (capture_clock_enabled) capture_clock = ~capture_clock;
    // The transport is exercised against the production plant, counter and
    // command ports. This small test wiring is not the production register map.
    assign capture_read_data = capture_address == 0 ? sample_value : counter_ticks[31:0];
    assign capture_response = capture_address == 0 || capture_address == 4 || capture_address == 8
        ? 2'b00 : 2'b10;
    axi_lite_clock_bridge #(.ENABLE_LOCAL(ENABLE_LOCAL)) transport (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wstrb(wstrb),
        .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .capture_valid(capture_valid), .capture_write(capture_write),
        .capture_address(capture_address), .capture_write_data(capture_write_data),
        .capture_write_strobes(capture_write_strobes), .capture_read_data(capture_read_data),
        .capture_response(capture_response), .local_valid(local_valid), .local_write(local_write),
        .local_address(local_address), .local_write_data(local_write_data),
        .local_write_strobes(local_write_strobes), .local_read_data(local_read_data),
        .local_response(local_response)
    );
    clock_reset_release bus_reset (
        .clock(bus_clock), .run_reset_n(run_reset_n), .local_reset_n(bus_reset_n)
    );
    event_record_window window (
        .bus_clock(bus_clock), .reset_n(bus_reset_n), .local_valid(local_valid), .local_write(local_write),
        .local_address(local_address), .local_write_data(local_write_data),
        .local_write_strobes(local_write_strobes), .local_read_data(local_read_data),
        .local_response(local_response), .drain_request(drain_request), .drain_valid(drain_valid),
        .drain_empty(drain_empty), .drain_record(drain_record),
        .capture_quiescent(capture_quiescent), .run_drained(run_drained)
    );
    control_plant_witness #(.PERIOD_TICKS(32'd16384), .THERMAL(THERMAL), .ADDRESS_BITS(6)) plant (
        .capture_clock(capture_clock), .drain_clock(bus_clock), .run_reset_n(run_reset_n),
        .enable(enable), .stop_after_cycle(32'd0),
        .sample_read(capture_valid && !capture_write && capture_address == 0),
        .actuator_write(capture_valid && capture_write && capture_address == 4 && capture_write_strobes == 15),
        .command_cycle(cycle_number), .command_value(capture_write_data), .fault_arm(1'b0),
        .fault_kind(2'd0), .fault_cycle(32'd0), .fault_periods(32'd0), .reference_mode(2'd0),
        .reference_amplitude(32'sd16777216), .reference_offset(32'sd0), .ramp_increment(32'sd0),
        .phase_increment(4'd1), .capture_active(capture_active), .sample_valid(sample_valid),
        .cycle_number(cycle_number), .sample_value(sample_value), .actuator_value(actuator_value),
        .safe_interrupt(safe_interrupt), .total_misses(total_misses), .overflow_count(overflow_count),
        .counter_ticks(counter_ticks), .drain_request(drain_request), .drain_valid(drain_valid), .drain_record(drain_record),
        .buffer_full(), .sample_interrupt(), .delayed_interrupt(), .delayed_cycle(), .plant_clipped(),
        .reference_clipped(), .fault_ready(), .freeze_actuator(), .overload_request(),
        .consecutive_misses(), .late_commands(), .drain_empty(drain_empty), .velocity(), .reference_value(),
        .run_finished(), .capture_quiescent(capture_quiescent)
    );
    always @(posedge capture_clock) begin
        if (capture_valid) begin
            captures = captures + 1;
            if (!capture_write) begin
                expected_read = capture_read_data;
                expected_read_response = capture_response;
            end
        end
    end
    task automatic send_address(input logic [7:0] address);
        @(negedge bus_clock);
        wait (awready);
        awaddr = address;
        awvalid = 1;
        @(posedge bus_clock);
        @(negedge bus_clock);
        awvalid = 0;
        awaddr = ~address;
    endtask
    task automatic read_local(input logic [7:0] address, input logic [1:0] response,
        output logic [31:0] value);
        send_read(address);
        wait (rvalid);
        @(negedge bus_clock);
        value = rdata;
        repeat (7) begin
            @(negedge bus_clock);
            if (!rvalid || rresp !== response || rdata !== value)
                $fatal(1, "local read changed under AXI backpressure");
        end
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
    endtask
    task automatic pop_local(input logic [31:0] value, input logic [3:0] strobes,
        input logic [1:0] response);
        fork send_address(8'h94); send_data(value, strobes); join
        accept_write(response);
    endtask
    task automatic send_data(input logic [31:0] value, input logic [3:0] strobes);
        @(negedge bus_clock);
        wait (wready);
        wdata = value;
        wstrb = strobes;
        wvalid = 1;
        @(posedge bus_clock);
        @(negedge bus_clock);
        wvalid = 0;
        wdata = ~value;
        wstrb = ~strobes;
    endtask
    task automatic accept_write(input logic [1:0] response);
        wait (bvalid);
        repeat (7) begin
            @(negedge bus_clock);
            if (!bvalid || bresp !== response || awready || wready)
                $fatal(1, "write response or credit changed under backpressure");
        end
        bready = 1;
        @(negedge bus_clock);
        bready = 0;
    endtask
    task automatic send_read(input logic [7:0] address);
        @(negedge bus_clock);
        wait (arready);
        araddr = address;
        arvalid = 1;
        @(posedge bus_clock);
        @(negedge bus_clock);
        arvalid = 0;
        araddr = ~address;
    endtask
    task automatic accept_read;
        wait (rvalid);
        repeat (9) begin
            @(negedge bus_clock);
            if (!rvalid || rdata !== expected_read || rresp !== expected_read_response || arready)
                $fatal(1, "read snapshot or credit changed under backpressure");
        end
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
    endtask
    task automatic write_command(input integer order, input logic [31:0] value, input logic [3:0] strobes);
        fork
            begin
                if (order < 0) repeat (4) @(negedge bus_clock);
                send_address(8'd4);
            end
            begin
                if (order > 0) repeat (4) @(negedge bus_clock);
                send_data(value, strobes);
            end
        join
        accept_write(2'b00);
    endtask
    task automatic common_reset;
        @(negedge bus_clock);
        run_reset_n = 0;
        enable = 0;
        awvalid = 0;
        wvalid = 0;
        arvalid = 0;
        bready = 0;
        rready = 0;
        #1;
        if (awready || wready || arready || bvalid || rvalid || capture_valid)
            $fatal(1, "reset retained AXI transaction");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (awready && wready && arready && capture_active);
    endtask
    initial begin
        common_reset();
        if (ENABLE_LOCAL) begin
            read_local(8'h80, 2'b10, word_value);
            read_local(8'h90, 2'b00, word_value);
            if (word_value != 4) $fatal(1, "reset FIFO window is not empty");
            pop_local(32'd1, 4'hf, 2'b10);
        end
        @(negedge capture_clock);
        enable = 1;
        wait (sample_valid);
        #1;
        first_sample_ticks = counter_ticks - 1;
        send_read(8'd0);
        accept_read();
        write_command(1, 32'd16777216, 4'hf);
        if (actuator_value != 16777216) $fatal(1, "AW before W lost command");
        write_command(-1, 32'd8388608, 4'hf);
        if (actuator_value != 8388608) $fatal(1, "W before AW lost command");
        write_command(0, 32'd4194304, 4'hf);
        if (actuator_value != 4194304) $fatal(1, "simultaneous AW/W lost command");
        write_command(0, 32'd1, 4'h0);
        if (actuator_value != 4194304) $fatal(1, "zero write strobes changed command");
        // A held write response must not prevent an independent read completing.
        fork
            send_address(8'd4);
            send_data(32'd2097152, 4'hf);
        join
        wait (bvalid);
        if (ENABLE_LOCAL) read_local(8'h90, 2'b00, word_value);
        send_read(8'd8);
        accept_read();
        accept_write(2'b00);
        // A held read response similarly leaves write progress available.
        send_read(8'd8);
        wait (rvalid);
        write_command(0, 32'd1048576, 4'hf);
        accept_read();
        // Concurrent complete requests exercise arbitration, both must finish.
        fork
            write_command(0, 32'd524288, 4'hf);
            begin send_read(8'd8); accept_read(); end
        join
        send_read(8'h7c);
        accept_read();
        fork send_address(8'h7c); send_data(32'd0, 4'hf); join
        accept_write(2'b10);
        if (total_misses || safe_interrupt || overflow_count) $fatal(1, "AXI service lost healthy plant");
        if (ENABLE_LOCAL) begin
            capture_before = captures;
            // The first genuine FIFO record stays pinned across arbitrary word reads.
            read_local(8'h80, 2'b00, word_value);
            if (word_value != 1) $fatal(1, "first window record is not SAMPLE_READY");
            read_local(8'h8c, 2'b00, word_value);
            if (word_value != first_sample_ticks[63:32]) $fatal(1, "record high timestamp differs");
            read_local(8'h88, 2'b00, word_value);
            if (word_value != first_sample_ticks[31:0]) $fatal(1, "record low timestamp differs");
            read_local(8'h84, 2'b00, word_value);
            if (word_value != 0) $fatal(1, "record cycle differs");
            read_local(8'h81, 2'b10, word_value);
            read_local(8'h98, 2'b10, word_value);
            pop_local(32'd1, 4'h0, 2'b10);
            pop_local(32'd0, 4'hf, 2'b10);
            fork send_address(8'h80); send_data(32'd0, 4'hf); join
            accept_write(2'b10);
            read_local(8'h80, 2'b00, word_value);
            if (word_value != 1) $fatal(1, "invalid access consumed held record");
            pop_local(32'd1, 4'hf, 2'b00);
            read_local(8'h80, 2'b00, word_value);
            if (word_value != 2) $fatal(1, "POP did not advance to SAMPLE_READ");
            pop_local(32'd1, 4'hf, 2'b00);
            read_local(8'h80, 2'b00, word_value);
            if (word_value != 3) $fatal(1, "POP did not advance to ACTUATOR_WRITE");
            pop_local(32'd1, 4'hf, 2'b00);
            read_local(8'h80, 2'b10, word_value);
            if (captures != capture_before) $fatal(1, "local record access leaked into capture domain");
            $display("FIFO_WINDOW_PASS immutable_words=4 records=3");
            // A held local R response must coexist with a remote write completion.
            send_read(8'h90);
            wait (rvalid);
            @(negedge bus_clock);
            word_value = rdata;
            write_command(0, 32'd262144, 4'hf);
            @(negedge bus_clock);
            if (!rvalid || rresp != 0 || rdata != word_value)
                $fatal(1, "remote completion disturbed held local response");
            rready = 1;
            @(negedge bus_clock);
            rready = 0;
        end else begin
            // With the local aperture disabled, upper addresses use capture CDC.
            send_read(8'hfc);
            accept_read();
            fork send_address(8'hfc); send_data(32'd0, 4'hf); join
            accept_write(2'b10);
            $display("REMOTE_APERTURE_PASS");
        end
        // Partial independent channels and pending/held transactions are discarded.
        send_address(8'd4);
        common_reset();
        send_data(32'd1, 4'hf);
        common_reset();
        @(negedge capture_clock);
        capture_clock_enabled = 0;
        capture_before = captures;
        send_read(8'd8);
        repeat (20) @(negedge bus_clock);
        if (rvalid || captures != capture_before) $fatal(1, "paused capture completed request");
        run_reset_n = 0;
        capture_clock_enabled = 1;
        common_reset();
        send_read(8'd8);
        wait (rvalid);
        common_reset();
        fork send_address(8'd4); send_data(32'd0, 4'hf); join
        wait (bvalid);
        common_reset();
        send_read(8'd8);
        accept_read();
        $display("AXI_BRIDGE_PASS captures=%0d", captures);
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1, "AXI transport simulation timeout");
    end
endmodule
