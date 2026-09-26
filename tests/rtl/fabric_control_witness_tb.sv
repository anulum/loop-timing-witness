// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — integrated plant fault and host stream testbench

`timescale 1ns/1ps
module fabric_control_witness_tb #(
    parameter int FAULT = -1,
    parameter bit EXTERNAL = 1'b0,
    parameter bit INVALID = 1'b0,
    parameter bit LQR = 1'b0,
    parameter bit THERMAL = 1'b0
);
    localparam logic [31:0] PERIOD = 32'd100000;
    logic capture_clock = 0, drain_clock = 0, run_reset_n = 0, enable = 0;
    logic fault_arm = 0;
    logic [1:0] fault_kind = 2'(FAULT);
    logic capture_active, sample_valid, sample_interrupt, delayed_interrupt;
    logic [31:0] cycle_number, delayed_cycle;
    logic signed [31:0] sample_value, velocity, reference_value, actuator_value;
    logic plant_clipped, reference_clipped, safe_interrupt, fault_ready;
    logic freeze_actuator, overload_request, drain_valid, drain_empty, buffer_full;
    logic [31:0] total_misses, consecutive_misses, late_commands, overflow_count;
    logic [63:0] counter_ticks;
    logic [127:0] drain_record;
    logic signed [31:0] edge_actuator;
    logic [63:0] edge_tick, first_sample_tick;
    integer handle, track_handle, byte_index, records = 0;
    string event_file, track_file;
    always #5 capture_clock = ~capture_clock;
    always #7 drain_clock = ~drain_clock;
    logic sample_read = 1'b0, actuator_write = 1'b0, write_next = 1'b0;
    logic [31:0] command_cycle;
    logic signed [31:0] command_value;
    integer command_file, parsed, unused_integral, unused_derivative, unused_clip, unused_held;
    string command_path;
    if (EXTERNAL) begin : native_replay
    control_plant_witness #(.PERIOD_TICKS(PERIOD), .THERMAL(THERMAL),
        .MISS_LIMIT(FAULT == 0 ? 32'd1 : 32'd2), .ADDRESS_BITS(4)) instrument (
        .capture_clock(capture_clock), .drain_clock(drain_clock), .run_reset_n(run_reset_n),
        .enable(enable), .stop_after_cycle(32'd4), .sample_read(sample_read),
        .actuator_write(actuator_write), .command_cycle(command_cycle), .command_value(command_value),
        .fault_arm(fault_arm), .fault_kind(fault_kind), .fault_cycle(32'd1), .fault_periods(32'd2),
        .reference_mode(2'd0), .reference_amplitude(32'sd16777216), .reference_offset(32'sd0),
        .ramp_increment(32'sd0), .phase_increment(4'd1), .capture_active(capture_active),
        .sample_valid(sample_valid), .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt), .cycle_number(cycle_number), .delayed_cycle(delayed_cycle),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value),
        .actuator_value(actuator_value), .plant_clipped(plant_clipped), .reference_clipped(reference_clipped),
        .safe_interrupt(safe_interrupt), .fault_ready(fault_ready), .freeze_actuator(freeze_actuator),
        .overload_request(overload_request), .total_misses(total_misses),
        .consecutive_misses(consecutive_misses), .late_commands(late_commands),
        .overflow_count(overflow_count), .counter_ticks(counter_ticks), .drain_request(1'b1),
        .drain_valid(drain_valid), .drain_empty(drain_empty), .drain_record(drain_record),
        .buffer_full(buffer_full)
    );
    end else begin : fabric_feedback
    fabric_control_witness #(.LQR(LQR), .KP(INVALID ? -32'sd1 : 32'sd33554432),
        .PERIOD_TICKS(PERIOD), .THERMAL(THERMAL),
        .MISS_LIMIT(FAULT == 0 ? 32'd1 : 32'd2), .ADDRESS_BITS(4)) instrument (
        .capture_clock(capture_clock), .drain_clock(drain_clock), .run_reset_n(run_reset_n),
        .enable(enable), .stop_after_cycle(32'd4),
        .fault_arm(fault_arm), .fault_kind(fault_kind), .fault_cycle(32'd1), .fault_periods(32'd2),
        .reference_mode(2'd0), .reference_amplitude(32'sd16777216), .reference_offset(32'sd0),
        .ramp_increment(32'sd0), .phase_increment(4'd1), .capture_active(capture_active),
        .sample_valid(sample_valid), .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt), .cycle_number(cycle_number), .delayed_cycle(delayed_cycle),
        .sample_value(sample_value), .velocity(velocity), .reference_value(reference_value),
        .actuator_value(actuator_value), .plant_clipped(plant_clipped), .reference_clipped(reference_clipped),
        .safe_interrupt(safe_interrupt), .fault_ready(fault_ready), .freeze_actuator(freeze_actuator),
        .overload_request(overload_request), .total_misses(total_misses),
        .consecutive_misses(consecutive_misses), .late_commands(late_commands),
        .overflow_count(overflow_count), .counter_ticks(counter_ticks), .drain_request(1'b1),
        .drain_valid(drain_valid), .drain_empty(drain_empty), .drain_record(drain_record),
        .buffer_full(buffer_full)
    );
    end
    initial begin
        if (EXTERNAL) begin
            if (!$value$plusargs("COMMAND_FILE=%s", command_path)) $fatal(1, "command path missing");
            command_file = $fopen(command_path, "r");
            if (!command_file) $fatal(1, "cannot open native commands");
        end
    end
    always @(negedge capture_clock) begin
        sample_read = 1'b0;
        actuator_write = write_next;
        write_next = 1'b0;
        if (EXTERNAL && sample_valid && !safe_interrupt && !freeze_actuator) begin
            parsed = $fscanf(command_file, "%d,%d,%d,%d,%d,%d\n", command_cycle, command_value,
                unused_integral, unused_derivative, unused_clip, unused_held);
            if (parsed != 6 || command_cycle != cycle_number) $fatal(1, "native cycle tag mismatch");
            sample_read = 1'b1;
            write_next = 1'b1;
        end
    end
    always @(posedge capture_clock) begin
        edge_tick = counter_ticks;
        edge_actuator = actuator_value;
        #1;
        if (sample_valid) begin
            if (cycle_number == 0) first_sample_tick = edge_tick;
            $fwrite(track_handle, "%0d,%0d,%0d,%0d,%0d,%0d\n", cycle_number,
                reference_value, sample_value, velocity, safe_interrupt ? 32'sd0 : edge_actuator, edge_tick);
        end
        if (safe_interrupt && actuator_value != 0) $fatal(1, "safe value not held");
    end
    always @(posedge drain_clock) begin
        #1;
        if (drain_valid) begin
            records = records + 1;
            for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                $fwrite(handle, "%c", drain_record[8*byte_index +: 8]);
        end
    end
    initial begin
        first_sample_tick = 64'hffffffffffffffff;
        if (!$value$plusargs("EVENT_FILE=%s", event_file)) $fatal(1, "EVENT_FILE missing");
        if (!$value$plusargs("TRACK_FILE=%s", track_file)) $fatal(1, "TRACK_FILE missing");
        handle = $fopen(event_file, "wb");
        track_handle = $fopen(track_file, "w");
        if (!handle || !track_handle) $fatal(1, "output open failed");
        $fwrite(track_handle, "cycle,reference,output,velocity,actuator,ticks\n");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (capture_active);
        @(negedge capture_clock);
        fault_arm = FAULT >= 0;
        @(negedge capture_clock);
        fault_arm = 0;
        enable = 1;
        wait (counter_ticks > first_sample_tick + 5*PERIOD + 100);
        if (overflow_count || buffer_full) $fatal(1, "unexpected event loss");
        if (FAULT != 2 && !INVALID && (safe_interrupt || total_misses))
            $fatal(1, "fabric loop missed deadline");
        if ((FAULT == 2 || INVALID) && !safe_interrupt) $fatal(1, "freeze did not trip independent monitor");
        $display("CONTROL_PASS records=%0d misses=%0d late=%0d", records,
            total_misses, late_commands);
        enable = 0;
        @(negedge capture_clock);
        run_reset_n = 0;
        #1;
        if (safe_interrupt || total_misses || overflow_count || counter_ticks || late_commands)
            $fatal(1, "reset did not clear run state");
        $fclose(handle);
        $fclose(track_handle);
        $display("RESET_PASS");
        $finish;
    end
    initial begin
        #6000000;
        $fatal(1, "control simulation timeout");
    end
endmodule
