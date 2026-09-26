// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — buffered capture and host-stream testbench

`timescale 1ns/1ps

module event_witness_tb #(
    parameter int ADDRESS_BITS = 3,
    parameter int OVERFLOW_COUNTER_BITS = 32,
    parameter int OVERFLOW_RUN = 0
);
    import event_codes_pkg::*;
    localparam int DEPTH = 1 << ADDRESS_BITS;
    localparam logic [63:0] COUNTER_MAX = (64'd1 << OVERFLOW_COUNTER_BITS) - 1;
    logic capture_clock = 0, drain_clock = 0, run_reset_n = 0;
    logic event_valid = 0, capture_active, buffer_full, event_dropped, overflowed;
    logic [7:0] event_code = 0;
    logic [31:0] cycle_number = 0;
    logic [63:0] counter_ticks;
    logic [OVERFLOW_COUNTER_BITS-1:0] overflow_count;
    logic drain_request = 0, drain_valid, drain_empty;
    logic [127:0] drain_record, pending_record;
    logic pending_valid = 0, save_records = 1;
    logic [127:0] expected [0:DEPTH+100];
    integer accepted = 0, delivered = 0, dropped = 0, observed_drop_pulses = 0;
    integer output_handle, byte_index, index;
    string output_file;

    always #5 capture_clock = ~capture_clock;
    always #7 drain_clock = ~drain_clock;

    event_witness #(.ADDRESS_BITS(ADDRESS_BITS), .OVERFLOW_COUNTER_BITS(OVERFLOW_COUNTER_BITS)) witness (
        .capture_clock(capture_clock), .drain_clock(drain_clock), .run_reset_n(run_reset_n),
        .event_valid(event_valid), .event_code(event_code), .cycle_number(cycle_number),
        .capture_active(capture_active), .counter_ticks(counter_ticks), .buffer_full(buffer_full),
        .event_dropped(event_dropped), .overflowed(overflowed), .overflow_count(overflow_count),
        .drain_request(drain_request), .drain_valid(drain_valid), .drain_record(drain_record),
        .drain_empty(drain_empty)
    );

    always @(posedge capture_clock) begin
        if (capture_active) begin
            if (pending_valid) begin
                if (buffer_full) dropped = dropped + 1;
                else begin
                    expected[accepted] = pending_record;
                    accepted = accepted + 1;
                end
            end
            pending_valid = event_valid;
            pending_record = {counter_ticks, cycle_number, 16'd0, 8'd0, event_code};
        end else pending_valid = 0;
        #1;
        if (event_dropped) observed_drop_pulses = observed_drop_pulses + 1;
    end

    always @(posedge drain_clock) begin
        #1;
        if (drain_valid) begin
            if (delivered >= accepted) $fatal(1, "unexpected drained record");
            if (drain_record !== expected[delivered]) $fatal(1, "captured record corrupted at %0d", delivered);
            delivered = delivered + 1;
            if (save_records) begin
                for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1)
                    $fwrite(output_handle, "%c", drain_record[byte_index * 8 +: 8]);
            end
        end
    end

    task automatic emit(input logic [7:0] code, input logic [31:0] cycle, input logic [63:0] tick);
        begin
            do @(negedge capture_clock); while (counter_ticks < tick);
            if (counter_ticks != tick) $fatal(1, "missed known tick");
            event_valid = 1;
            event_code = code;
            cycle_number = cycle;
            @(negedge capture_clock);
            event_valid = 0;
        end
    endtask

    initial begin
        if (!$value$plusargs("EVENT_FILE=%s", output_file)) $fatal(1, "EVENT_FILE missing");
        output_handle = $fopen(output_file, "wb");
        if (output_handle == 0) $fatal(1, "cannot open binary event file");
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (capture_active);
        if (OVERFLOW_RUN == 0) begin
            drain_request = 1;
            for (index = 0; index < 3; index = index + 1) begin
                emit(SAMPLE_READY, 32'(index), 64'(5000 * index + 10));
                emit(SAMPLE_READ, 32'(index), 64'(5000 * index + 20));
                emit(ACT_WRITE, 32'(index), 64'(5000 * index + 30));
                emit(DEADLINE, 32'(index), 64'(5000 * (index + 1)));
            end
            wait (delivered == 12 && drain_empty);
            if (dropped || overflowed || overflow_count) $fatal(1, "known-period capture overflow");
        end else begin
            for (index = 0; index < DEPTH + 17; index = index + 1) begin
                @(negedge capture_clock);
                event_valid = 1;
                event_code = SAMPLE_READY;
                cycle_number = 32'(index);
            end
            @(negedge capture_clock);
            event_valid = 0;
            repeat (3) @(negedge capture_clock);
            if (accepted != DEPTH || dropped != 17 || !buffer_full || !overflowed)
                $fatal(1, "overflow accounting accepted=%0d dropped=%0d", accepted, dropped);
            if (overflow_count != OVERFLOW_COUNTER_BITS'((64'd17 < COUNTER_MAX) ? 64'd17 : COUNTER_MAX))
                $fatal(1, "overflow counter did not saturate correctly");
            if (observed_drop_pulses != dropped) $fatal(1, "drop pulse count differs");
            drain_request = 1;
            wait (delivered == DEPTH && drain_empty);
            repeat (5) @(negedge capture_clock);
            if (buffer_full) $fatal(1, "buffer failed to recover after drain");
            for (index = 0; index < 4; index = index + 1) begin
                @(negedge capture_clock);
                event_valid = 1;
                cycle_number = 32'(DEPTH + 17 + index);
            end
            @(negedge capture_clock);
            event_valid = 0;
            wait (delivered == DEPTH + 4 && drain_empty);
            if (dropped != 17 || !overflowed) $fatal(1, "recovery altered sticky overflow");
        end
        $display("WITNESS_PASS accepted=%0d dropped=%0d overflow_count=%0d", accepted, dropped, overflow_count);
        save_records = 0;
        $fclose(output_handle);
        @(negedge capture_clock);
        run_reset_n = 0;
        #1;
        if (capture_active || overflowed || overflow_count || counter_ticks || drain_valid || !drain_empty)
            $fatal(1, "run reset did not flush capture and overflow state");
        accepted = 0;
        delivered = 0;
        dropped = 0;
        observed_drop_pulses = 0;
        repeat (4) @(negedge drain_clock);
        run_reset_n = 1;
        wait (capture_active);
        emit(SAMPLE_READY, 0, 10);
        wait (delivered == 1 && drain_empty);
        $display("RESET_PASS");
        $finish;
    end

    initial begin
        #5000000;
        $fatal(1, "witness simulation timeout");
    end
endmodule
