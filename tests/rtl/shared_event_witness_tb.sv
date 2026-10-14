// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — shared timestamp, independent loss and reset testbench

`timescale 1ns/1ps

module shared_event_witness_tb #(
    parameter int ADDRESS_BITS = 3,
    parameter int OVERFLOW_COUNTER_BITS = 32,
    parameter int OVERFLOW_RUN = 0,
    parameter int NORMAL_COUNT = 4,
    parameter int NEURAL_FORMAT = 0,
    parameter int NEURAL_PHASE = 0,
    parameter int EMPTY_SERVICE = 0,
    parameter int DRAIN_HALF_PERIOD = 7
);
    localparam int DEPTH = 1 << ADDRESS_BITS;
    logic capture_clock = 0, drain_clock = 0, run_reset_n = 0;
    logic [2:0] event_valid = 0, buffer_full, event_dropped, overflowed;
    logic [2:0][7:0] event_code = 0;
    logic [2:0][31:0] event_identity = 0;
    logic capture_active;
    logic [63:0] counter_ticks;
    logic [2:0][OVERFLOW_COUNTER_BITS-1:0] overflow_count;
    logic [2:0][63:0] attempt_count, accepted_count;
    logic [2:0] drain_request = 0, drain_valid, drain_empty;
    logic [2:0][127:0] drain_record;
    integer delivered [0:2];
    integer output_handle [0:2];
    integer counter_handle;
    integer channel, index, expected_drops;
    logic save_records = 1;
    string output_directory;
    string channel_role;

    always #5 capture_clock = ~capture_clock;
    always #(DRAIN_HALF_PERIOD) drain_clock = ~drain_clock;

    shared_event_witness #(
        .ADDRESS_BITS(ADDRESS_BITS), .OVERFLOW_COUNTER_BITS(OVERFLOW_COUNTER_BITS)
    ) witness (.*);

    for (genvar stream = 0; stream < 3; stream++) begin : writers
        always @(posedge drain_clock) begin
            #1;
            if (drain_valid[stream]) begin
                delivered[stream] = delivered[stream] + 1;
                if (drain_record[stream][31:8] !== 24'd0) $fatal(1, "reserved bits changed");
                if (!save_records && drain_record[stream] !== {64'd10, 32'd0, 24'd0, 8'd17})
                    $fatal(1, "reset recovery returned an old record or wrong tick");
                if (save_records) begin
                    for (integer byte_number = 0; byte_number < 16; byte_number++) begin
                        $fwrite(output_handle[stream], "%c", drain_record[stream][byte_number*8 +: 8]);
                    end
                end
            end
        end
    end

    task automatic simultaneous(input logic [7:0] code, input int identity, input int tick);
        do @(negedge capture_clock); while (counter_ticks < 64'(tick));
        if (counter_ticks != 64'(tick)) $fatal(1, "known capture edge missed");
        event_valid = (code == 14 && EMPTY_SERVICE) ? 3'b011 : 3'b111;
        for (integer stream = 0; stream < 3; stream++) begin
            event_code[stream] = (code == 14 && NEURAL_FORMAT) ? 8'(14 + stream) : code;
            event_identity[stream] = 32'(identity);
        end
        @(negedge capture_clock);
        event_valid = 0;
    endtask

    task automatic wait_empty;
        wait (&drain_empty);
        repeat (4) @(negedge drain_clock);
        if (drain_valid) $fatal(1, "record appeared after empty drain");
    endtask

    initial begin
        if (!$value$plusargs("EVENT_DIRECTORY=%s", output_directory)) $fatal(1, "directory missing");
        for (channel = 0; channel < 3; channel++) begin
            delivered[channel] = 0;
            output_handle[channel] = $fopen($sformatf("%s/channel-%0d.bin", output_directory, channel), "wb");
            if (!output_handle[channel]) $fatal(1, "cannot open stream");
        end
        repeat (4) @(negedge capture_clock);
        run_reset_n = 1;
        wait (capture_active);
        if (OVERFLOW_RUN == 0) begin
            drain_request = (NORMAL_COUNT == 1000 || NEURAL_PHASE) ? 3'b000 : 3'b111;
            simultaneous(17, 0, 10);
            if (NEURAL_PHASE) begin
                do @(negedge capture_clock); while (counter_ticks < 20);
                for (index = 0; index < NORMAL_COUNT+2; index++) begin
                    if (counter_ticks != 64'(20 + index)) $fatal(1, "phased input edge missed");
                    event_valid[0] = (index < NORMAL_COUNT);
                    event_valid[1] = (index >= 1 && index <= NORMAL_COUNT);
                    event_valid[2] = (index >= 2 && !EMPTY_SERVICE);
                    event_code[0] = 14;
                    event_code[1] = 15;
                    event_code[2] = 16;
                    event_identity[0] = 32'(index);
                    event_identity[1] = 32'(index - 1);
                    event_identity[2] = 32'(index - 2);
                    @(negedge capture_clock);
                end
                event_valid = 0;
                simultaneous(17, 1, 20 + NORMAL_COUNT + 10);
                repeat (3) @(negedge capture_clock);
                drain_request = 3'b111;
            end else if (NORMAL_COUNT == 1000) begin
                do @(negedge capture_clock); while (counter_ticks < 20);
                for (index = 0; index < NORMAL_COUNT; index++) begin
                    if (counter_ticks != 64'(20 + index)) $fatal(1, "continuous input edge missed");
                    event_valid = EMPTY_SERVICE ? 3'b011 : 3'b111;
                    for (channel = 0; channel < 3; channel++) begin
                        event_code[channel] = NEURAL_FORMAT ? 8'(14 + channel) : 8'd14;
                        event_identity[channel] = 32'(index);
                    end
                    @(negedge capture_clock);
                end
                event_valid = 0;
                simultaneous(17, 1, 1030);
                repeat (3) @(negedge capture_clock);
                drain_request = 3'b111;
            end else begin
                for (index = 0; index < NORMAL_COUNT; index++) simultaneous(14, index, 20 + 3*index);
                simultaneous(17, 1, 40);
            end
            wait (delivered[0] == NORMAL_COUNT+2 && delivered[1] == NORMAL_COUNT+2 &&
                delivered[2] == (EMPTY_SERVICE ? 2 : NORMAL_COUNT+2));
            wait_empty();
            for (channel = 0; channel < 3; channel++) begin
                if (attempt_count[channel] != ((EMPTY_SERVICE && channel == 2) ? 2 : NORMAL_COUNT+2) ||
                    accepted_count[channel] != ((EMPTY_SERVICE && channel == 2) ? 2 : NORMAL_COUNT+2) ||
                    overflowed[channel] || overflow_count[channel]) $fatal(1, "normal counts differ");
            end
        end else begin
            drain_request = 3'b110;
            for (index = 0; index < DEPTH + 17; index++) begin
                @(negedge capture_clock);
                event_valid = 3'b011;
                event_code[0] = 14;
                event_code[1] = 15;
                event_identity[0] = 32'(index);
                event_identity[1] = 32'(index);
            end
            @(negedge capture_clock);
            event_valid = 0;
            repeat (4) @(negedge capture_clock);
            if (attempt_count[0] != DEPTH+17 || accepted_count[0] != DEPTH ||
                !overflowed[0] || !buffer_full[0]) $fatal(1, "full channel counts differ");
            expected_drops = (17 < ((64'd1 << OVERFLOW_COUNTER_BITS)-1)) ?
                17 : int'((64'd1 << OVERFLOW_COUNTER_BITS)-1);
            if (overflow_count[0] != OVERFLOW_COUNTER_BITS'(expected_drops)) $fatal(1, "drop saturation differs");
            if (attempt_count[1] != DEPTH+17 || accepted_count[1] != DEPTH+17 ||
                overflowed[1] || overflow_count[1]) $fatal(1, "one full channel blocked another");
            if (attempt_count[2] || accepted_count[2] || delivered[2] || overflowed[2])
                $fatal(1, "empty channel invented records");
            drain_request = 3'b111;
            wait (delivered[0] == DEPTH && delivered[1] == DEPTH+17);
            wait_empty();
        end
        for (channel = 0; channel < 3; channel++) $fclose(output_handle[channel]);
        counter_handle = $fopen($sformatf("%s/capture-counts.json", output_directory), "w");
        if (!counter_handle) $fatal(1, "cannot open counter receipt");
        $fwrite(counter_handle, "{\"schema_id\":\"loop-timing-witness.neural-capture-counts.v1\",\"drop_counter_bits\":%0d,\"channels\":[", OVERFLOW_COUNTER_BITS);
        for (channel = 0; channel < 3; channel++) begin
            case (channel)
                0: channel_role = "input";
                1: channel_role = "state";
                default: channel_role = "service";
            endcase
            $fwrite(counter_handle, "{\"role\":\"%s\",\"attempts\":%0d,\"accepted\":%0d,\"dropped\":%0d,\"drained\":%0d,\"overflowed\":%s}%s",
                channel_role,
                attempt_count[channel], accepted_count[channel], overflow_count[channel], delivered[channel],
                overflowed[channel] ? "true" : "false", (channel == 2) ? "" : ",");
        end
        $fwrite(counter_handle, "]}\n");
        $fclose(counter_handle);
        save_records = 0;
        @(negedge capture_clock);
        drain_request = 0;
        event_valid = 3'b111;
        repeat (3) @(negedge capture_clock);
        run_reset_n = 0;
        event_valid = 0;
        #1;
        if (capture_active || counter_ticks || overflowed || overflow_count ||
            attempt_count || accepted_count || drain_valid || drain_empty != 3'b111)
            $fatal(1, "common reset retained a run");
        for (channel = 0; channel < 3; channel++) delivered[channel] = 0;
        repeat (4) @(negedge drain_clock);
        run_reset_n = 1;
        wait (capture_active);
        drain_request = 3'b111;
        simultaneous(17, 0, 10);
        wait (delivered[0] == 1 && delivered[1] == 1 && delivered[2] == 1);
        wait_empty();
        if (overflowed || overflow_count) $fatal(1, "new run kept prior overflow");
        $display("SHARED_CAPTURE_PASS reset_pass=1 overflow_run=%0d", OVERFLOW_RUN);
        $finish;
    end

    initial begin
        #200000;
        $fatal(1, "shared witness simulation timeout");
    end
endmodule
