// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — capture-edge sample snapshot and command commit registers

// All ports belong to capture_clock. An accepted read at0x00 returns sample_value
// and latches cycle/velocity/reference/time/misses at that same edge. Metadata
// at0x10..24 stays immutable until another sample read, even across plant steps.
// Read0x08 latches a separate64-bit clock observation;0x0c reads its upper word.
// Full-word writes stage cycle0x28 and command0x2c. Commit0x30(data1) consumes
// both staging credits and emits one actuator_write; missing stage, inactive,
// finished or safe run refuses the commit. Independent monitor still owns timely
// acceptance and safe override: a bus acknowledgement is not proof of actuation.
module control_io_registers (
    input logic capture_clock, reset_n,
    input logic capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    output logic [31:0] capture_read_data,
    output logic [1:0] capture_response,
    input logic run_enabled, run_finished, capture_quiescent, safe_interrupt,
    input logic [31:0] cycle_number, total_misses, overflow_count,
    input logic signed [31:0] sample_value, velocity, reference_value,
    input logic [63:0] counter_ticks,
    output logic sample_read, actuator_write,
    output logic [31:0] command_cycle,
    output logic signed [31:0] command_value
);
    logic snapshot_valid, time_valid, cycle_staged, value_staged;
    logic [31:0] snapshot_cycle, snapshot_misses;
    logic signed [31:0] snapshot_velocity, snapshot_reference;
    logic [63:0] snapshot_ticks;
    logic [31:0] observed_upper;
    logic accepted;
    assign accepted = reset_n && capture_valid && capture_response == 0;
    assign sample_read = accepted && !capture_write && capture_address == 0;
    assign actuator_write = accepted && capture_write && capture_address == 8'h30;
    always_comb begin
        capture_read_data = 0;
        capture_response = 2'b10;
        if (reset_n && capture_address[1:0] == 0) begin
            if (capture_write) begin
                if (capture_write_strobes == 4'hf) begin
                    case (capture_address)
                        8'h28, 8'h2c: capture_response = 0;
                        8'h30: if (capture_write_data == 1 && cycle_staged && value_staged
                            && run_enabled && !run_finished && !safe_interrupt) capture_response = 0;
                        default: begin end
                    endcase
                end
            end else begin
                case (capture_address)
                    8'h00: if (run_enabled && !run_finished) begin
                        capture_read_data = sample_value;
                        capture_response = 0;
                    end
                    8'h04: begin
                        capture_read_data = {27'd0, capture_quiescent, safe_interrupt,
                            run_finished, run_enabled, snapshot_valid};
                        capture_response = 0;
                    end
                    8'h08: begin
                        capture_read_data = counter_ticks[31:0];
                        capture_response = 0;
                    end
                    8'h0c: if (time_valid) begin
                        capture_read_data = observed_upper;
                        capture_response = 0;
                    end
                    8'h10, 8'h14, 8'h18, 8'h1c, 8'h20, 8'h24: if (snapshot_valid) begin
                        capture_response = 0;
                        case (capture_address)
                            8'h10: capture_read_data = snapshot_cycle;
                            8'h14: capture_read_data = snapshot_velocity;
                            8'h18: capture_read_data = snapshot_reference;
                            8'h1c: capture_read_data = snapshot_ticks[31:0];
                            8'h20: capture_read_data = snapshot_ticks[63:32];
                            8'h24: capture_read_data = snapshot_misses;
                            default: begin end
                        endcase
                    end
                    8'h30: begin capture_read_data = overflow_count; capture_response = 0; end
                    8'h34: begin capture_read_data = total_misses; capture_response = 0; end
                    8'h28: begin capture_read_data = command_cycle; capture_response = 0; end
                    8'h2c: begin capture_read_data = command_value; capture_response = 0; end
                    default: begin end
                endcase
            end
        end
    end
    always_ff @(posedge capture_clock or negedge reset_n) begin
        if (!reset_n) begin
            snapshot_valid <= 0;
            time_valid <= 0;
            cycle_staged <= 0;
            value_staged <= 0;
            snapshot_cycle <= 0;
            snapshot_misses <= 0;
            snapshot_velocity <= 0;
            snapshot_reference <= 0;
            snapshot_ticks <= 0;
            observed_upper <= 0;
            command_cycle <= 0;
            command_value <= 0;
        end else begin
            if (sample_read) begin
                snapshot_valid <= 1;
                snapshot_cycle <= cycle_number;
                snapshot_velocity <= velocity;
                snapshot_reference <= reference_value;
                snapshot_ticks <= counter_ticks;
                snapshot_misses <= total_misses;
            end
            if (accepted && !capture_write && capture_address == 8'h08) begin
                time_valid <= 1;
                observed_upper <= counter_ticks[63:32];
            end
            if (accepted && capture_write) begin
                case (capture_address)
                    8'h28: begin command_cycle <= capture_write_data; cycle_staged <= 1; end
                    8'h2c: begin command_value <= capture_write_data; value_staged <= 1; end
                    8'h30: begin cycle_staged <= 0; value_staged <= 0; end
                    default: begin end
                endcase
            end
        end
    end
endmodule
