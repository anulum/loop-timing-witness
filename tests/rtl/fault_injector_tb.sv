// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — fault schedule refusal and exact action duration

`timescale 1ns/1ps
module fault_injector_tb #(parameter int KIND = 0);
    logic clock = 0, reset_n = 0, sample_tick = 0, arm = 0;
    logic [31:0] sample_cycle = 0, target_cycle = 2, duration_periods = 3;
    logic [1:0] kind = 2'(KIND);
    logic arm_ready, injected, sample_interrupt, delayed_interrupt, freeze_actuator, overload_request;
    logic [31:0] delayed_cycle;
    integer tick, injections = 0, delayed = 0, freeze_ticks = 0, overload_ticks = 0;
    fault_injector #(.PERIOD_TICKS(32'd8)) injector (
        .clock(clock), .reset_n(reset_n), .sample_tick(sample_tick), .sample_cycle(sample_cycle),
        .arm(arm), .kind(kind), .target_cycle(target_cycle), .duration_periods(duration_periods),
        .arm_ready(arm_ready), .injected(injected), .sample_interrupt(sample_interrupt),
        .delayed_interrupt(delayed_interrupt), .delayed_cycle(delayed_cycle),
        .freeze_actuator(freeze_actuator), .overload_request(overload_request)
    );
    always #5 clock = ~clock;
    initial begin
        repeat (2) @(negedge clock); reset_n = 1;
        // Invalid arms leave the injector available and cannot inject.
        arm = 1; duration_periods = 0;
        @(negedge clock);
        if (!arm_ready || injected) $fatal(1, "zero-duration schedule accepted");
        duration_periods = 3; sample_cycle = 3; target_cycle = 1;
        @(negedge clock);
        if (!arm_ready || injected) $fatal(1, "past schedule accepted");
        arm = 0; sample_cycle = 0; target_cycle = 2;
        for (tick = 0; tick < 48; tick = tick + 1) begin
            @(negedge clock);
            sample_tick = tick % 8 == 0;
            sample_cycle = 32'(tick / 8);
            arm = tick == 1 || tick == 4 || tick == 25;
            if (tick > 2) begin target_cycle = 0; duration_periods = 1; kind = 2'(3-KIND); end
            #1;
            if (injected) begin
                if (tick != 16) $fatal(1, "schedule replaced or injection retimed");
                injections = injections + 1;
            end
            if (delayed_interrupt) begin
                if (tick != 40 || delayed_cycle != 2) $fatal(1, "delay/origin mismatch");
                delayed = delayed + 1;
            end
            if (freeze_actuator) begin
                if (tick < 16 || tick >= 40) $fatal(1, "freeze duration mismatch");
                freeze_ticks = freeze_ticks + 1;
            end
            if (overload_request) begin
                if (tick < 16 || tick >= 40) $fatal(1, "overload duration mismatch");
                overload_ticks = overload_ticks + 1;
            end
            if (sample_interrupt != ((tick % 8 == 0 && !(tick == 16 && KIND < 2)) ||
                (tick == 40 && KIND == 1))) $fatal(1, "IRQ drop/delay changed another sample");
            if (tick > 1 && arm_ready) $fatal(1, "pending/used schedule became replaceable");
        end
        if (injections != 1 || delayed != (KIND == 1 ? 1 : 0) ||
            freeze_ticks != (KIND == 2 ? 24 : 0) || overload_ticks != (KIND == 3 ? 24 : 0))
            $fatal(1, "action count mismatch");
        @(negedge clock); reset_n = 0;
        #1;
        if (!arm_ready || freeze_actuator || overload_request || delayed_interrupt)
            $fatal(1, "reset did not rearm injection");
        $display("INJECTOR_PASS kind=%0d", KIND);
        $finish;
    end
endmodule
