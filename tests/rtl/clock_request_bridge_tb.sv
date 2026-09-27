// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — request bridge against the actual plant and event FIFO

`timescale 1ns/1ps
module clock_request_bridge_tb #(
    parameter int BUS_HALF_PERIOD = 7,
    parameter bit THERMAL = 0,
    parameter int REQUEST_BITS = 65,
    parameter int RESPONSE_BITS = 256
);
    logic bus_clock = 0, capture_clock = 0, run_reset_n = 0, enable = 0;
    logic request_valid = 0, request_ready, response_valid, response_ready = 0;
    logic capture_clock_enabled = 1;
    logic bus_clock_enabled = 1;
    logic [64:0] request_data = 0, capture_data;
    logic [255:0] response_data, capture_response, expected_response, stalled_response;
    logic capture_valid, capture_active, sample_valid, safe_interrupt;
    logic [31:0] cycle_number, total_misses, overflow_count;
    logic signed [31:0] sample_value, velocity, reference_value, actuator_value;
    logic [63:0] counter_ticks;
    logic drain_valid;
    logic [127:0] drain_record;
    logic [63:0] read_ticks [0:4];
    integer captures = 0, reads = 0, writes = 0, deadlines = 0, cycle_index;
    integer expected_captures;
    always #5 if (capture_clock_enabled) capture_clock = ~capture_clock;
    always #(BUS_HALF_PERIOD) if (bus_clock_enabled) bus_clock = ~bus_clock;
    assign capture_response = {counter_ticks, cycle_number, sample_value, velocity,
        reference_value, total_misses, 31'd0, safe_interrupt};
    clock_request_bridge #(.REQUEST_BITS(REQUEST_BITS), .RESPONSE_BITS(RESPONSE_BITS)) bridge (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .request_valid(request_valid), .request_ready(request_ready), .request_data(request_data),
        .response_valid(response_valid), .response_ready(response_ready), .response_data(response_data),
        .capture_valid(capture_valid), .capture_data(capture_data), .capture_response(capture_response)
    );
    control_plant_witness #(.PERIOD_TICKS(32'd512), .THERMAL(THERMAL), .ADDRESS_BITS(6)) plant (
        .capture_clock(capture_clock), .drain_clock(bus_clock), .run_reset_n(run_reset_n),
        .enable(enable), .stop_after_cycle(32'd4), .sample_read(capture_valid && !capture_data[64]),
        .actuator_write(capture_valid && capture_data[64]), .command_cycle(capture_data[63:32]),
        .command_value(capture_data[31:0]), .fault_arm(1'b0), .fault_kind(2'd0),
        .fault_cycle(32'd0), .fault_periods(32'd0), .reference_mode(2'd0),
        .reference_amplitude(32'sd16777216), .reference_offset(32'sd0), .ramp_increment(32'sd0),
        .phase_increment(4'd1), .capture_active(capture_active), .sample_valid(sample_valid),
        .cycle_number(cycle_number), .sample_value(sample_value), .velocity(velocity),
        .reference_value(reference_value), .actuator_value(actuator_value),
        .safe_interrupt(safe_interrupt), .total_misses(total_misses), .overflow_count(overflow_count),
        .counter_ticks(counter_ticks), .drain_request(1'b1), .drain_valid(drain_valid),
        .drain_record(drain_record), .buffer_full(), .sample_interrupt(), .delayed_interrupt(),
        .delayed_cycle(), .plant_clipped(), .reference_clipped(), .fault_ready(),
        .freeze_actuator(), .overload_request(), .consecutive_misses(), .late_commands(), .drain_empty()
    );
    always @(posedge capture_clock) begin
        if (capture_valid) begin
            captures = captures + 1;
            expected_response = capture_response;
            if (!capture_data[64] && enable) read_ticks[cycle_number] = counter_ticks;
        end
    end
    always @(posedge bus_clock) begin
        #1;
        if (drain_valid) begin
            case (drain_record[7:0])
                2: begin
                    reads = reads + 1;
                    if (drain_record[127:64] != read_ticks[drain_record[63:32]])
                        $fatal(1, "sample response and read event differ");
                end
                3: writes = writes + 1;
                4: deadlines = deadlines + 1;
                default: begin end
            endcase
        end
    end
    task automatic exchange(input logic [64:0] payload, input integer stall);
        begin
            @(negedge bus_clock);
            wait (request_ready);
            request_data = payload;
            request_valid = 1;
            @(posedge bus_clock);
            @(negedge bus_clock);
            request_valid = 0;
            // Changing unaccepted source data must not corrupt the held transaction.
            request_data = ~payload;
            wait (response_valid);
            @(negedge bus_clock);
            if (response_data !== expected_response) $fatal(1, "torn response snapshot");
            stalled_response = response_data;
            expected_captures = captures;
            request_valid = 1;
            repeat (stall) begin
                @(negedge bus_clock);
                if (request_ready || !response_valid || response_data !== stalled_response)
                    $fatal(1, "response backpressure lost snapshot");
                if (captures != expected_captures) $fatal(1, "busy request duplicated");
            end
            request_valid = 0;
            response_ready = 1;
            @(negedge bus_clock);
            response_ready = 0;
        end
    endtask
    initial begin
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (capture_active && request_ready);
        // A paused destination clock must delay, rather than duplicate, the request.
        @(negedge capture_clock);
        capture_clock_enabled = 0;
        @(negedge bus_clock);
        request_valid = 1;
        request_data = 0;
        @(negedge bus_clock);
        request_valid = 0;
        repeat (20) begin
            @(negedge bus_clock);
            if (response_valid || request_ready || captures) $fatal(1, "stopped capture acknowledged");
        end
        capture_clock_enabled = 1;
        wait (response_valid);
        @(negedge bus_clock);
        if (response_data !== expected_response) $fatal(1, "resumed capture snapshot differs");
        response_ready = 1;
        @(negedge bus_clock);
        response_ready = 0;
        // The destination holds its response while the source clock is stopped.
        expected_captures = captures + 1;
        @(negedge bus_clock);
        request_data = 0;
        request_valid = 1;
        @(negedge bus_clock);
        request_valid = 0;
        bus_clock_enabled = 0;
        repeat (20) @(negedge capture_clock);
        if (captures != expected_captures || capture_valid || response_valid)
            $fatal(1, "paused source lost or duplicated capture");
        bus_clock_enabled = 1;
        wait (response_valid);
        @(negedge bus_clock);
        if (response_data !== expected_response) $fatal(1, "paused source lost held response");
        response_ready = 1;
        @(negedge bus_clock);
        response_ready = 0;
        captures = 0;
        @(negedge capture_clock);
        enable = 1;
        for (cycle_index = 0; cycle_index < 5; cycle_index = cycle_index + 1) begin
            wait (sample_valid && cycle_number == 32'(cycle_index));
            exchange(65'd0, 7);
            if (response_data[191:160] != 32'(cycle_index) || response_data[63:32] != 0)
                $fatal(1, "snapshot does not identify healthy current sample");
            exchange({1'b1, 32'(cycle_index), 32'sd16777216}, 3);
            if (actuator_value != 32'sd16777216) $fatal(1, "command did not cross clock domain");
        end
        wait (counter_ticks > 2600);
        repeat (50) @(negedge bus_clock);
        if (reads != 5 || writes != 5 || deadlines != 5 || captures != 10)
            $fatal(1, "bridge event chain incomplete: %0d %0d %0d %0d", reads,writes,deadlines,captures);
        if (total_misses || safe_interrupt || overflow_count) $fatal(1, "healthy bridge lost service");
        enable = 0;
        // Abandon a pending request with common reset, then accept a fresh request.
        @(negedge bus_clock);
        request_valid = 1;
        request_data = 0;
        @(posedge bus_clock);
        #1;
        run_reset_n = 0;
        request_valid = 0;
        #1;
        if (response_valid || request_ready || capture_valid) $fatal(1, "reset left transaction active");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        exchange(65'd0, 2);
        if (response_data[191:160] || response_data[63:0]) $fatal(1, "stale state after common reset");
        // Reset also abandons an acknowledged response held by a stalled consumer.
        @(negedge bus_clock);
        request_valid = 1;
        @(negedge bus_clock);
        request_valid = 0;
        wait (response_valid);
        @(negedge bus_clock);
        run_reset_n = 0;
        #1;
        if (response_valid || response_data || capture_valid) $fatal(1, "reset retained response");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        exchange(65'd0, 1);
        if (response_data[191:160] || response_data[63:0]) $fatal(1, "response reset retained plant");
        $display("BRIDGE_PASS reads=%0d writes=%0d deadlines=%0d",reads,writes,deadlines);
        $finish;
    end
    initial begin
        #100000;
        $fatal(1, "request bridge simulation timeout");
    end
endmodule
