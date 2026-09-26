// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — sample period actuator acceptance and control strobes

// Synchronous control-cycle register contract; safe application overrides commands.
module control_cycle #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0
) (
    input logic capture_clock, reset_n, enable,
    input logic [31:0] stop_after_cycle,
    input logic sample_read, actuator_write,
    input logic [31:0] command_cycle,
    input logic signed [31:0] command_value,
    input logic freeze_actuator, safe_interrupt, trip_now, injected,
    output logic finished, sample_tick, deadline, timely_write, sample_valid,
    output logic [31:0] cycle_number, sample_cycle, late_commands,
    output logic signed [31:0] actuator_value, plant_actuator,
    output logic [7:0] event_mask,
    output logic [255:0] event_cycles
);
    logic started, read_seen, write_seen, late_seen, injection_open, accepted_write;
    logic [31:0] elapsed;
    if (PERIOD_TICKS < 2) begin : invalid_period
        initial $fatal(1, "PERIOD_TICKS must be at least two");
    end
    assign deadline = enable && started && !finished && elapsed == PERIOD_TICKS - 1'b1;
    assign sample_tick = enable && !finished && (!started ||
        (deadline && cycle_number < stop_after_cycle));
    assign sample_cycle = started ? cycle_number + 1'b1 : 32'd0;
    assign accepted_write = started && !finished && actuator_write && !freeze_actuator
        && !safe_interrupt && !trip_now;
    assign timely_write = accepted_write && !deadline && command_cycle == cycle_number
        && !write_seen;
    assign plant_actuator = (trip_now || safe_interrupt) ? SAFE_VALUE : actuator_value;
    always_comb begin
        event_mask = '0;
        event_cycles = '0;
        for (integer index = 0; index < 8; index = index + 1)
            event_cycles[32*index +: 32] = cycle_number;
        event_mask[0] = sample_tick;
        event_cycles[0 +: 32] = sample_cycle;
        event_mask[1] = sample_read && started && !finished && !read_seen;
        event_mask[2] = timely_write;
        event_mask[3] = deadline;
        event_mask[4] = trip_now;
        event_mask[5] = injected;
        event_cycles[160 +: 32] = sample_cycle;
        event_mask[6] = trip_now && injection_open;
        event_mask[7] = accepted_write && (deadline || command_cycle != cycle_number)
            && (!late_seen || sample_tick);
        // Boundary late writes are observed in the new cycle, never fulfil it.
        event_cycles[224 +: 32] = sample_tick ? sample_cycle : cycle_number;
    end
    always_ff @(posedge capture_clock or negedge reset_n) begin
        if (!reset_n) begin
            elapsed <= '0;
            started <= 1'b0;
            finished <= 1'b0;
            cycle_number <= '0;
            sample_valid <= 1'b0;
            actuator_value <= '0;
            read_seen <= 1'b0;
            write_seen <= 1'b0;
            late_seen <= 1'b0;
            late_commands <= '0;
            injection_open <= 1'b0;
        end else begin
            sample_valid <= sample_tick;
            if (enable && started && !finished) elapsed <= elapsed + 1'b1;
            if (deadline || sample_tick) elapsed <= '0;
            if (deadline && cycle_number >= stop_after_cycle) finished <= 1'b1;
            if (sample_read && started && !finished) read_seen <= 1'b1;
            if (timely_write) write_seen <= 1'b1;
            if (event_mask[7]) late_seen <= 1'b1;
            if (accepted_write) begin
                actuator_value <= command_value;
                if (deadline || command_cycle != cycle_number) begin
                    if (!(&late_commands)) late_commands <= late_commands + 1'b1;
                end
            end
            if (sample_tick) begin
                started <= 1'b1;
                cycle_number <= sample_cycle;
                read_seen <= 1'b0;
                write_seen <= 1'b0;
                late_seen <= event_mask[7];
            end
            if (injected) injection_open <= 1'b1;
            if (trip_now) begin
                actuator_value <= SAFE_VALUE;
                injection_open <= 1'b0;
            end
        end
    end
endmodule
