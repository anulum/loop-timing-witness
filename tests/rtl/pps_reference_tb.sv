// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — pulse-per-second reference records under a held drain

`timescale 1ns/1ps
// No run is enabled, so every record is a PPS record. A pulse high at the run reset's release is
// not an edge. With the drain held, four edges fill the four-record buffer, the fifth waits, the
// sixth arrives while the fifth still waits and is not recorded, and after the drain resumes the
// seventh is recorded again: the sequence numbers 0 to 4 and 6 remain, each record with the
// counter value two captures after its rise, and the capture overflow counter stays zero.
module pps_reference_tb;
    logic capture_clock = 0, drain_clock = 0, run_reset_n = 0, pps_in = 1, drain_request = 0;
    logic capture_active, drain_valid, drain_empty, buffer_full, saw_full = 0;
    logic [31:0] overflow_count;
    logic [63:0] counter_ticks;
    logic [127:0] drain_record;
    logic [63:0] rises [0:6];
    logic [31:0] sequences [0:5];
    logic [63:0] stamps [0:5];
    integer records = 0, edge_index;
    always #5 capture_clock = ~capture_clock;
    always #7 drain_clock = ~drain_clock;
    control_plant_witness #(.PERIOD_TICKS(32'd1000), .ADDRESS_BITS(2)) instrument (
        .capture_clock(capture_clock), .drain_clock(drain_clock), .run_reset_n(run_reset_n),
        .enable(1'b0), .stop_after_cycle(32'd4), .sample_read(1'b0), .actuator_write(1'b0),
        .command_cycle(32'd0), .command_value(32'sd0), .fault_arm(1'b0), .fault_kind(2'd0),
        .fault_cycle(32'd0), .fault_periods(32'd0), .reference_mode(2'd0),
        .reference_amplitude(32'sd0), .reference_offset(32'sd0), .ramp_increment(32'sd0),
        .phase_increment(4'd1), .pps_in(pps_in), .capture_active(capture_active),
        .overflow_count(overflow_count), .counter_ticks(counter_ticks),
        .drain_request(drain_request), .drain_valid(drain_valid), .drain_empty(drain_empty),
        .drain_record(drain_record), .buffer_full(buffer_full)
    );
    always @(posedge capture_clock) if (buffer_full) saw_full = 1;
    always @(posedge drain_clock) begin
        #1;
        if (drain_valid) begin
            if (records > 5) $fatal(1, "more PPS records than expected");
            if (drain_record[7:0] != 8'd18 || drain_record[31:8] != 0)
                $fatal(1, "record %0d is not a PPS record", records);
            sequences[records] = drain_record[63:32];
            stamps[records] = drain_record[127:64];
            records = records + 1;
        end
    end
    task automatic pulse(input integer index);
        @(negedge capture_clock);
        pps_in = 1;
        rises[index] = counter_ticks;
        repeat (10) @(negedge capture_clock);
        pps_in = 0;
        repeat (40) @(negedge capture_clock);
    endtask
    initial begin
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (capture_active);
        repeat (20) @(negedge capture_clock);
        pps_in = 0;
        repeat (20) @(negedge capture_clock);
        if (records != 0 || instrument.pps_valid) $fatal(1, "a pulse high at release was recorded");
        for (edge_index = 0; edge_index < 6; edge_index = edge_index + 1) pulse(edge_index);
        if (!saw_full || !instrument.pps_valid) $fatal(1, "the fifth edge does not wait");
        drain_request = 1;
        repeat (40) @(negedge capture_clock);
        pulse(6);
        repeat (40) @(negedge capture_clock);
        if (records != 6 || !drain_empty) $fatal(1, "expected six PPS records, drained %0d", records);
        for (edge_index = 0; edge_index < 6; edge_index = edge_index + 1) begin
            if (sequences[edge_index] != (edge_index < 5 ? edge_index : 6))
                $fatal(1, "record %0d has sequence %0d", edge_index, sequences[edge_index]);
            if (stamps[edge_index] != rises[edge_index < 5 ? edge_index : 6] + 2)
                $fatal(1, "record %0d has counter value %0d", edge_index, stamps[edge_index]);
        end
        if (overflow_count != 0) $fatal(1, "a PPS edge counted as capture overflow");
        $display("PPS_PASS records=%0d", records);
        $finish;
    end
    initial begin
        #200000;
        $fatal(1, "PPS simulation timeout");
    end
endmodule
