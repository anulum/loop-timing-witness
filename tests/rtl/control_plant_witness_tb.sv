// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — integrated plant fault and host stream testbench

`timescale 1ns/1ps
module control_plant_witness_tb #(
    parameter int FAULT = -1,
    parameter bit THERMAL = 1'b0,
    parameter bit BOUNDARY_WRITE = 1'b0,
    parameter bit SIGNED_COMMAND = 1'b0
);
    localparam logic [31:0] PERIOD = 32'd100000;
    logic capture_clock = 0, drain_clock = 0, run_reset_n = 0, enable = 0;
    logic sample_read = 0, actuator_write = 0, fault_arm = 0;
    logic [31:0] command_cycle = 0;
    logic signed [31:0] command_value = 32'sd16777216;
    logic [1:0] fault_kind = 2'(FAULT);
    logic capture_active, sample_valid, sample_interrupt, delayed_interrupt;
    logic [31:0] cycle_number, delayed_cycle;
    logic signed [31:0] sample_value, velocity, reference_value, actuator_value;
    logic plant_clipped, reference_clipped, safe_interrupt, fault_ready;
    logic freeze_actuator, overload_request, drain_valid, drain_empty, buffer_full;
    logic [31:0] total_misses, consecutive_misses, late_commands, overflow_count;
    logic [63:0] counter_ticks;
    logic [127:0] drain_record;
    logic irq_seen [0:4];
    logic delay_wait = 0, saw_freeze = 0, saw_overload = 0;
    logic signed [31:0] edge_actuator;
    logic [63:0] injection_tick, delayed_tick, edge_tick, first_sample_tick;
    integer handle, track_handle, byte_index, records = 0, index;
    string event_file, track_file;
    always #5 capture_clock = ~capture_clock;
    always #7 drain_clock = ~drain_clock;
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
    // The simulated service waits for its delayed IRQ; overload means no service.
    // This is a declared stimulus, not a benchmark of processor execution.
    always @(posedge capture_clock) begin
        edge_tick = counter_ticks;
        edge_actuator = actuator_value;
        if (sample_interrupt && capture_active && enable) begin
            if (delayed_interrupt) begin
                delayed_tick = counter_ticks;
                if (delayed_cycle != 1) $fatal(1, "delayed IRQ lost origin");
                delay_wait = 0;
            end
            if (!delay_wait) begin
                if (first_sample_tick == 64'hffffffffffffffff) irq_seen[0] = 1;
                else irq_seen[32'((counter_ticks-first_sample_tick)/PERIOD)] = 1;
            end
        end
        if (FAULT == 1 && counter_ticks == first_sample_tick + PERIOD) delay_wait = 1;
        if (freeze_actuator) saw_freeze = 1;
        if (overload_request) saw_overload = 1;
        #1;
        if (sample_valid) begin
            if (cycle_number == 0) begin
                first_sample_tick = edge_tick;
                irq_seen[0] = 1;
            end
            $fwrite(track_handle, "%0d,%0d,%0d,%0d,%0d,%0d\n", cycle_number,
                reference_value, sample_value, velocity, safe_interrupt ? 32'sd0 : edge_actuator, edge_tick);
        end
        if (safe_interrupt && actuator_value != 0) $fatal(1, "safe value not held");
    end
    always @(negedge capture_clock) begin
        sample_read = 0;
        actuator_write = 0;
        command_cycle = cycle_number;
        if (SIGNED_COMMAND) begin
            case (cycle_number)
                0: command_value = 32'sd33554432;
                1: command_value = -32'sd16777216;
                2: command_value = 32'sd8388608;
                3: command_value = -32'sd33554432;
                default: command_value = 32'sd0;
            endcase
        end
        if (enable && capture_active && counter_ticks >= first_sample_tick) begin
            if (irq_seen[cycle_number] && !delay_wait && !overload_request &&
                counter_ticks == first_sample_tick + 64'(cycle_number)*PERIOD + 10)
                sample_read = 1;
            if (irq_seen[cycle_number] && !delay_wait && !overload_request &&
                (counter_ticks == first_sample_tick + 64'(cycle_number)*PERIOD + 20 ||
                 counter_ticks == first_sample_tick + 64'(cycle_number)*PERIOD + 21) && !BOUNDARY_WRITE)
                actuator_write = 1;
            if (BOUNDARY_WRITE && counter_ticks == first_sample_tick + PERIOD && cycle_number == 0)
                actuator_write = 1;
            if (BOUNDARY_WRITE && (counter_ticks == first_sample_tick + PERIOD + 30 ||
                counter_ticks == first_sample_tick + PERIOD + 40)) begin
                actuator_write = 1;
                command_cycle = 0;
            end
        end
    end
    always @(posedge drain_clock) begin
        #1;
        if (drain_valid) begin
            records = records + 1;
            if (drain_record[7:0] == 6) injection_tick = drain_record[127:64];
            for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                $fwrite(handle, "%c", drain_record[8*byte_index +: 8]);
        end
    end
    initial begin
        for (index = 0; index < 5; index = index + 1) irq_seen[index] = 0;
        first_sample_tick = 64'hffffffffffffffff;
        injection_tick = 0;
        delayed_tick = 0;
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
        if (FAULT < 0 && !BOUNDARY_WRITE && (safe_interrupt || total_misses))
            $fatal(1, "healthy loop missed deadline");
        if ((FAULT >= 0 || BOUNDARY_WRITE) && !safe_interrupt) $fatal(1, "monitor failed to trip");
        if (FAULT == 1 && delayed_tick - injection_tick != 2*PERIOD)
            $fatal(1, "injected delay not exactly two periods: %0d", delayed_tick-injection_tick);
        if (FAULT == 2 && !saw_freeze) $fatal(1, "freeze never asserted");
        if (FAULT == 3 && !saw_overload) $fatal(1, "overload never asserted");
        if (BOUNDARY_WRITE && late_commands != 3) $fatal(1, "boundary write not counted late");
        $display("CONTROL_PASS records=%0d misses=%0d late=%0d delay=%0d", records,
            total_misses, late_commands, delayed_tick-injection_tick);
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
