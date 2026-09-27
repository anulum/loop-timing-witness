// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — production AXI peripheral to immutable binary records

`timescale 1ns/1ps
module axi_control_witness_tb #(
    parameter int BUS_HALF_PERIOD = 7,
    parameter bit THERMAL = 0
);
    logic bus_clock = 0, capture_clock = 0, run_reset_n = 0;
    logic [7:0] awaddr = 0, araddr = 0;
    logic awvalid = 0, awready, wvalid = 0, wready, arvalid = 0, arready;
    logic bvalid, bready = 0, rvalid, rready = 0;
    logic [31:0] wdata = 0, rdata;
    logic [1:0] bresp, rresp;
    logic [3:0] wstrb = 15;
    logic run_drained, run_enabled, run_finished, capture_quiescent, sample_read, safe_interrupt;
    logic [31:0] cycle_number, total_misses, overflow_count, value, sample, reference;
    logic signed [31:0] sample_value;
    logic [63:0] counter_ticks, read_ticks [0:1];
    logic [127:0] record;
    logic [31:0] words [0:3];
    logic [31:0] stalled_read;
    logic capture_clock_enabled = 1;
    logic interrupt_line;
    integer event_file, tracking_file, cycle_index, record_index, word_index;
    string event_path, tracking_path;
    always #(BUS_HALF_PERIOD) bus_clock = ~bus_clock;
    always #5 if (capture_clock_enabled) capture_clock = ~capture_clock;
    axi_control_witness #(.PERIOD_TICKS(32'd32768), .THERMAL(THERMAL), .ADDRESS_BITS(6)) witness (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wstrb(wstrb),
        .wvalid(wvalid), .wready(wready), .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp),
        .rvalid(rvalid), .rready(rready), .run_drained(run_drained), .run_enabled(run_enabled),
        .run_finished(run_finished), .capture_quiescent(capture_quiescent), .sample_read(sample_read), .interrupt_line(interrupt_line),
        .cycle_number(cycle_number), .sample_value(sample_value), .safe_interrupt(safe_interrupt),
        .total_misses(total_misses), .overflow_count(overflow_count), .counter_ticks(counter_ticks),
        .actuator_write(), .buffer_full(), .capture_active(), .sample_valid(), .sample_interrupt(),
        .delayed_interrupt(), .delayed_cycle(), .velocity(), .reference_value(), .actuator_value(),
        .plant_clipped(), .reference_clipped(), .fault_ready(), .freeze_actuator(), .overload_request(),
        .consecutive_misses(), .late_commands(), .drain_valid(), .drain_empty(), .drain_record()
    );
    always @(posedge capture_clock) begin
        if (sample_read) read_ticks[cycle_number] = counter_ticks;
    end
    task automatic read_register(input logic [7:0] address, output logic [31:0] result,
        input logic [1:0] response = 0);
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
            if (!rvalid || rresp != response || rdata !== result) $fatal(1, "top read response unstable");
        end
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
    endtask
    task automatic write_register(input logic [7:0] address, input logic [31:0] data,
        input logic [1:0] response = 0);
        @(negedge bus_clock);
        wait (awready && wready);
        awaddr = address;
        awvalid = 1;
        wdata = data;
        wvalid = 1;
        @(negedge bus_clock);
        awvalid = 0;
        wvalid = 0;
        wait (bvalid);
        @(negedge bus_clock);
        repeat (6) begin
            @(negedge bus_clock);
            if (!bvalid || bresp != response) $fatal(1, "top write response lost during bank reset or stall");
        end
        bready = 1;
        @(negedge bus_clock);
        bready = 0;
    endtask
    task automatic software_reset(input bit pause_release = 0);
        read_register(8'h98, value);
        while (!value[3]) read_register(8'h98, value);
        write_register(8'h98, 0);
        if (run_enabled || run_drained) $fatal(1, "software reset retained run state");
        read_register(8'h98, value);
        if (value != 8) $fatal(1, "held reset reports stale ready state");
        read_register(8'h00, value, 2);
        if (pause_release) begin
            @(negedge capture_clock);
            capture_clock_enabled = 0;
        end
        write_register(8'h98, 1);
        if (pause_release) begin
            repeat (3) begin
                read_register(8'h98, value);
                if (value[2:0] != 5) $fatal(1, "stopped capture clock falsely ready after release");
            end
            capture_clock_enabled = 1;
        end
        read_register(8'h98, value);
        while (value[2:0] != 7) read_register(8'h98, value);
        read_register(8'h90, value);
        if (value != 4) $fatal(1, "software reset retained FIFO receiver");
        read_register(8'h10, value, 2);
        read_register(8'ha8, value);
        if (value != 0 || interrupt_line) $fatal(1, "software reset retained IRQ generation or snapshot");
        read_register(8'ha0, value, 2);
    endtask
    task automatic common_reset;
        @(negedge bus_clock);
        if (awvalid || wvalid || arvalid || bvalid || rvalid) $fatal(1, "master not quiescent for reset");
        run_reset_n = 0;
        #1;
        if (run_drained || run_enabled) $fatal(1, "reset retained completion or start");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (awready && wready && arready);
        read_register(8'h90, value);
        if (value != 4) $fatal(1, "reset FIFO window retained a record");
    endtask
    task automatic fetch_record;
        read_register(8'h90, value);
        while (!value[0]) begin
            if (value[3]) $fatal(1, "drained flag asserted before expected record");
            read_register(8'h90, value);
        end
        if (value[3] || run_drained) $fatal(1, "held receiver record counted as drained");
        for (word_index = 3; word_index >= 0; word_index = word_index - 1)
            read_register(8'h80 + 8'(4*word_index), words[word_index]);
        record = {words[3], words[2], words[1], words[0]};
        read_register(8'h80, value);
        if (value != words[0]) $fatal(1, "record changed across four bus reads");
        if (record[7:0] == 2 && record[127:64] != read_ticks[record[63:32]])
            $fatal(1, "top sample snapshot and drained timestamp differ");
        write_register(8'h94, 1);
    endtask
    initial begin
        if (!$value$plusargs("EVENT_FILE=%s", event_path) || !$value$plusargs("TRACK_FILE=%s", tracking_path))
            $fatal(1, "missing real simulation output paths");
        event_file = $fopen(event_path, "wb");
        tracking_file = $fopen(tracking_path, "w");
        if (!event_file || !tracking_file) $fatal(1, "cannot open simulation records");
        $fwrite(tracking_file, "cycle,reference_raw,output_raw\n");
        common_reset();
        read_register(8'ha0, value, 2);
        write_register(8'ha4, 1, 2);
        read_register(8'h9c, value);
        if (value || interrupt_line) $fatal(1, "initial IRQ generation is not zero");
        write_register(8'ha4, 1);
        write_register(8'ha4, 1, 2);
        write_register(8'h98, 2, 2);
        wstrb = 1;
        write_register(8'h98, 0, 2);
        wstrb = 15;
        write_register(8'h98, 1, 2);
        write_register(8'h3c, 1);
        write_register(8'h38, 1);
        write_register(8'h98, 0, 2);
        if (!run_enabled) $fatal(1, "active reset erased deadlines");
        wait (interrupt_line);
        read_register(8'h9c, value);
        if (value != 1) $fatal(1, "first sample IRQ was not retained");
        read_register(8'ha0, value);
        if (value != 0) $fatal(1, "IRQ snapshot high word differs");
        wstrb = 1;
        write_register(8'ha4, 1, 2);
        wstrb = 15;
        write_register(8'ha4, 2, 2);
        for (cycle_index = 0; cycle_index < 2; cycle_index = cycle_index + 1) begin
            wait (run_enabled && cycle_number == 32'(cycle_index));
            if (cycle_index == 1) begin
                repeat (4) @(negedge bus_clock);
                write_register(8'ha4, 1);
                if (!interrupt_line) $fatal(1, "ACK of old generation lost newer sample IRQ");
                read_register(8'h9c, value);
                if (value != 2) $fatal(1, "newer sample IRQ generation differs");
                write_register(8'ha4, 1);
                if (interrupt_line) $fatal(1, "ACK of current generation left IRQ pending");
            end
            read_register(8'h00, sample);
            read_register(8'h10, value);
            if (value != 32'(cycle_index)) $fatal(1, "sample snapshot cycle differs");
            read_register(8'h18, reference);
            $fwrite(tracking_file, "%0d,%0d,%0d\n", cycle_index, $signed(reference), $signed(sample));
            write_register(8'h28, 32'(cycle_index));
            write_register(8'h2c, 32'd16777216);
            write_register(8'h30, 1);
        end
        wait (run_finished && capture_quiescent);
        if (run_drained) $fatal(1, "capture completion ignored receiver backlog");
        for (record_index = 0; record_index < 8; record_index = record_index + 1) begin
            fetch_record();
            for (integer byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                $fwrite(event_file, "%c", record[8*byte_index +: 8]);
        end
        wait (run_drained);
        read_register(8'h90, value);
        if (value != 12 || total_misses || safe_interrupt || overflow_count)
            $fatal(1, "healthy top run did not drain completely");
        if (!interrupt_line) $fatal(1, "finish notification lost while draining");
        read_register(8'h9c, value);
        if (value != 3) $fatal(1, "finished IRQ generation differs");
        write_register(8'ha4, 1);
        if (interrupt_line) $fatal(1, "finish ACK did not clear level IRQ");
        $fclose(event_file);
        $fclose(tracking_file);
        // An accepted remote R response survives a local run-bank reset.
        @(negedge bus_clock);
        wait (arready);
        araddr = 8'h04;
        arvalid = 1;
        @(negedge bus_clock);
        arvalid = 0;
        wait (rvalid);
        @(negedge bus_clock);
        stalled_read = rdata;
        write_register(8'h98, 0);
        if (!rvalid || rresp != 0 || rdata != stalled_read || run_enabled)
            $fatal(1, "run reset orphaned accepted R response");
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
        // Reset also abandons an unconsumed receiver record after master quiescence.
        software_reset(1);
        write_register(8'h38, 1);
        wait (run_finished && capture_quiescent);
        read_register(8'h90, value);
        if (!value[0] || value[3]) $fatal(1, "abandoned run lost held record");
        software_reset();
        write_register(8'h38, 1);
        read_register(8'h00, sample);
        write_register(8'h28, 0);
        write_register(8'h2c, 16777216);
        write_register(8'h30, 1);
        wait (run_finished && capture_quiescent);
        repeat (4) fetch_record();
        wait (run_drained);
        if (total_misses || safe_interrupt || overflow_count) $fatal(1, "fresh run retained abandoned state");
        read_register(8'h9c, value);
        if (value != 2) $fatal(1, "fresh run retained old IRQ generation");
        software_reset();
        // Actual dropped first IRQ and coincident final safe/finish coalesce.
        write_register(8'h3c, 2);
        write_register(8'h60, 1);
        write_register(8'h64, 1);
        write_register(8'h38, 1);
        wait (run_finished && capture_quiescent);
        repeat (4) @(negedge bus_clock);
        if (!safe_interrupt || total_misses != 3 || !interrupt_line)
            $fatal(1, "actual drop/miss/safe run did not notify processor");
        repeat (3) begin
            read_register(8'h9c, value);
            if (value != 3) $fatal(1, "coincident safe/finish or held levels overcounted IRQ");
        end
        write_register(8'ha4, 1);
        if (interrupt_line || !safe_interrupt) $fatal(1, "IRQ ACK changed independent safe latch");
        $display("RETAINED_IRQ_PASS old_ack=preserved coalesced=1 reset=cleared");
        $display("AXI_TOP_PASS records=8 drained=1 reset_reuse=1");
        $finish;
    end
    initial begin
        #3000000;
        $fatal(1, "production AXI witness simulation timeout");
    end
endmodule
