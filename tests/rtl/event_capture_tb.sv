// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — event capture simulation testbench

module event_capture_tb;
    import event_codes_pkg::*;

    logic clock = 1'b0;
    logic reset_n = 1'b0;
    logic event_valid = 1'b0;
    logic [7:0] event_code = 8'd0;
    logic [31:0] cycle_number = 32'd0;
    logic record_valid;
    logic [127:0] record;
    logic [63:0] counter_ticks;
    integer output_handle;
    string output_file;
    string profile;

    always #5 clock = ~clock;

    event_record_capture witness (
        .clock(clock),
        .reset_n(reset_n),
        .event_valid(event_valid),
        .event_code(event_code),
        .cycle_number(cycle_number),
        .record_valid(record_valid),
        .record(record),
        .counter_ticks(counter_ticks)
    );

    task automatic emit(input logic [7:0] code, input logic [31:0] cycle, input logic [63:0] tick);
        integer byte_index;
        begin
            do @(negedge clock); while (counter_ticks < tick);
            if (counter_ticks != tick) $fatal(1, "missed scheduled tick %0d", tick);
            event_valid = 1'b1;
            event_code = code;
            cycle_number = cycle;
            @(posedge clock);
            #1;
            if (!record_valid) $fatal(1, "capture did not assert record_valid");
            if (record[127:64] != tick) $fatal(1, "captured wrong timebase tick");
            for (byte_index = 0; byte_index < 16; byte_index = byte_index + 1) begin
                $fwrite(output_handle, "%c", record[byte_index * 8 +: 8]);
            end
            @(negedge clock);
            event_valid = 1'b0;
        end
    endtask

    initial begin
        if (!$value$plusargs("EVENT_FILE=%s", output_file)) $fatal(1, "EVENT_FILE missing");
        if (!$value$plusargs("PROFILE=%s", profile)) profile = "CONTROL";
        output_handle = $fopen(output_file, "wb");
        if (output_handle == 0) $fatal(1, "cannot open event file");
        repeat (2) @(negedge clock);
        reset_n = 1'b1;
        if (profile == "CONTROL") begin
            emit(SAMPLE_READY, 0, 10);
            emit(SAMPLE_READ, 0, 20);
            emit(ACT_WRITE, 0, 30);
            emit(DEADLINE, 0, 5000);
            emit(SAMPLE_READY, 1, 5010);
            emit(SAMPLE_READ, 1, 5020);
            emit(ACT_WRITE, 1, 5030);
            emit(DEADLINE, 1, 10000);
            emit(SAMPLE_READY, 2, 10010);
            emit(FAULT_INJECTED, 2, 10015);
            emit(SAMPLE_READ, 2, 10020);
            emit(FAULT_DETECTED, 2, 10030);
            emit(DEADLINE, 2, 15000);
            emit(SAFE_STATE, 2, 15010);
            emit(ACT_WRITE, 2, 15020);
        end else if (profile == "COMPUTE") begin
            emit(INPUT_WRITE, 0, 10);
            emit(COMPUTE_START, 0, 20);
            emit(COMPUTE_DONE, 0, 30);
            emit(OUTPUT_READ, 0, 40);
            emit(INTERRUPT_ENTRY, 0, 50);
            emit(INPUT_WRITE, 1, 1010);
            emit(COMPUTE_START, 1, 1020);
            emit(COMPUTE_DONE, 1, 1030);
            emit(OUTPUT_READ, 1, 1040);
            emit(INTERRUPT_ENTRY, 1, 1050);
        end else begin
            $fatal(1, "unknown profile %s", profile);
        end
        $fclose(output_handle);
        $finish;
    end
endmodule
