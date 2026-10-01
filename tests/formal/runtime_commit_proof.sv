// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — native commit and monotonic-state proof wrappers

// Serial full-word staging followed by commit; initial DUT state is unconstrained.
// NEGATIVE_CONTROL deliberately omits cycle staging to test the assertion itself.
module runtime_commit_proof #(parameter bit NEGATIVE_CONTROL = 0) (
    input logic capture_clock,
    input logic run_finished, safe_interrupt
);
    (* anyconst *) logic [31:0] staged_cycle, staged_value;
    logic [2:0] step = 0;
    wire capture_write = step < 3;
    wire [7:0] capture_address = step == 0 ? (NEGATIVE_CONTROL ? 8'h2c : 8'h28) :
        step == 1 ? 8'h2c : step == 2 ? 8'h30 : 8'h04;
    wire [31:0] capture_write_data = step == 0 ? staged_cycle : step == 1 ? staged_value : 1;
    wire [31:0] capture_read_data;
    wire [1:0] capture_response;
    wire sample_read, actuator_write;
    wire [31:0] command_cycle;
    wire signed [31:0] command_value;
    control_io_registers dut (
        .capture_clock(capture_clock), .reset_n(1'b1), .capture_valid(1'b1),
        .capture_write(capture_write), .capture_address(capture_address),
        .capture_write_data(capture_write_data), .capture_write_strobes(4'hf),
        .capture_read_data(capture_read_data), .capture_response(capture_response),
        .run_enabled(1'b1), .run_finished(run_finished), .capture_quiescent(1'b0),
        .safe_interrupt(safe_interrupt), .cycle_number(32'd0), .total_misses(32'd0),
        .overflow_count(32'd0), .sample_value(32'd0), .velocity(32'd0),
        .reference_value(32'd0), .counter_ticks(64'd0), .sample_read(sample_read),
        .actuator_write(actuator_write), .command_cycle(command_cycle), .command_value(command_value)
    );
    always @(posedge capture_clock) begin
        if (step < 4) step <= step + 1'b1;
    end
    always @* if (step == 2) begin
        assert ((capture_response != 0) == (run_finished || safe_interrupt));
        if (!run_finished && !safe_interrupt) begin
            assert (actuator_write);
            assert (command_cycle == staged_cycle && command_value == staged_value);
        end
    end
endmodule

// The native call never requests a reset between its sample read and commit.
// Prove persistence from arbitrary DUT state, rather than assume reset reachability.
module runtime_enabled_proof #(parameter bit NEGATIVE_CONTROL = 0) (
    input logic capture_clock, reset_n, capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    input logic fault_ready, freeze_actuator, overload_request
);
    wire [31:0] capture_read_data, stop_after_cycle, fault_cycle, fault_periods;
    wire [1:0] capture_response, reference_mode, fault_kind;
    wire run_enabled, fault_arm;
    wire signed [31:0] reference_amplitude, reference_offset, ramp_increment;
    wire [3:0] phase_increment;
    logic observed = 0;
    run_configuration_registers dut (.*);
    always @* if (reset_n && !capture_write) begin
        if (capture_address == 8'h7c) assert (capture_response == 0 && capture_read_data == 1);
        if (capture_address == 8'h78) assert (capture_response == 0 && capture_read_data == 24);
    end
    always @(posedge capture_clock) begin
        observed <= 1;
        if (observed && reset_n && $past(reset_n) && $past(run_enabled))
            assert (NEGATIVE_CONTROL ? !run_enabled : run_enabled);
    end
endmodule

// A running domain releases reset after two real local rising edges from any state.
module runtime_release_proof #(parameter bit NEGATIVE_CONTROL = 0) (
    input logic clock
);
    logic [1:0] step = 0;
    wire local_reset_n;
    clock_reset_release dut (.clock(clock), .run_reset_n(1'b1), .local_reset_n(local_reset_n));
    always @(posedge clock) if (step < 3) step <= step + 1'b1;
    always @* if (step >= 2) assert (NEGATIVE_CONTROL ? !local_reset_n : local_reset_n);
endmodule

module runtime_finished_proof #(parameter bit NEGATIVE_CONTROL = 0) (
    input logic capture_clock, reset_n, enable,
    input logic [31:0] stop_after_cycle, command_cycle,
    input logic sample_read, actuator_write,
    input logic signed [31:0] command_value,
    input logic freeze_actuator, safe_interrupt, trip_now, injected
);
    wire finished, sample_tick, deadline, timely_write, sample_valid;
    wire [31:0] cycle_number, sample_cycle, late_commands;
    wire signed [31:0] actuator_value, plant_actuator;
    wire [7:0] event_mask;
    wire [255:0] event_cycles;
    logic observed = 0;
    control_cycle dut (.*);
    always @(posedge capture_clock) begin
        observed <= 1;
        if (observed && reset_n && $past(reset_n) && $past(finished))
            assert (NEGATIVE_CONTROL ? !finished : finished);
    end
endmodule

module runtime_safe_proof #(parameter bit NEGATIVE_CONTROL = 0) (
    input logic clock, reset_n, cycle_start, deadline, timely_write
);
    wire trip_now, safe_latched;
    wire [31:0] total_misses, consecutive_misses;
    logic observed = 0;
    deadline_monitor dut (.*);
    always @(posedge clock) begin
        observed <= 1;
        if (observed && reset_n && $past(reset_n) && $past(safe_latched))
            assert (NEGATIVE_CONTROL ? !safe_latched : safe_latched);
    end
endmodule
