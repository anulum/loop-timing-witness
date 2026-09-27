// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — immutable run reference and fault configuration registers

// Capture-domain decoder. Configure before START0x38(data1); only common reset
// permits another run. ARM0x64(data1) saves one validated fault before START.
// Arming also locks configuration so readback remains the injection's provenance.
// No software disable can erase a deadline. Period/model/monitor are read-only:
// plant coefficients are compiled for their declared sample interval.
module run_configuration_registers #(
    parameter logic [31:0] PERIOD_TICKS = 32'd100000,
    parameter logic [31:0] MISS_LIMIT = 32'd3,
    parameter logic signed [31:0] SAFE_VALUE = 32'sd0,
    parameter bit THERMAL = 0
) (
    input logic capture_clock, reset_n,
    input logic capture_valid, capture_write,
    input logic [7:0] capture_address,
    input logic [31:0] capture_write_data,
    input logic [3:0] capture_write_strobes,
    output logic [31:0] capture_read_data,
    output logic [1:0] capture_response,
    output logic run_enabled,
    output logic [31:0] stop_after_cycle,
    output logic [1:0] reference_mode,
    output logic signed [31:0] reference_amplitude, reference_offset, ramp_increment,
    output logic [3:0] phase_increment,
    output logic fault_arm,
    output logic [1:0] fault_kind,
    output logic [31:0] fault_cycle, fault_periods,
    input logic fault_ready, freeze_actuator, overload_request
);
    logic fault_programmed, accepted, configurable;
    assign configurable = !run_enabled && !fault_programmed;
    assign accepted = reset_n && capture_valid && capture_response == 0;
    assign fault_arm = accepted && capture_write && capture_address == 8'h64;
    always_comb begin
        capture_read_data = 0;
        capture_response = 2'b10;
        if (reset_n && capture_address[1:0] == 0) begin
            if (capture_write) begin
                if (capture_write_strobes == 4'hf) begin
                    case (capture_address)
                        8'h38: if (!run_enabled && capture_write_data == 1) capture_response = 0;
                        8'h3c, 8'h48, 8'h4c, 8'h50, 8'h5c, 8'h60:
                            if (configurable) capture_response = 0;
                        8'h44: if (configurable && capture_write_data <= 2) capture_response = 0;
                        8'h54: if (configurable && capture_write_data <= 15) capture_response = 0;
                        8'h58: if (configurable && capture_write_data <= 3) capture_response = 0;
                        8'h64: if (configurable && fault_ready && capture_write_data == 1
                            && fault_periods != 0 && fault_cycle <= stop_after_cycle) capture_response = 0;
                        default: begin end
                    endcase
                end
            end else begin
                capture_response = 0;
                case (capture_address)
                    8'h38: capture_read_data = {31'd0, run_enabled};
                    8'h3c: capture_read_data = stop_after_cycle;
                    8'h40: capture_read_data = PERIOD_TICKS;
                    8'h44: capture_read_data = {30'd0, reference_mode};
                    8'h48: capture_read_data = reference_amplitude;
                    8'h4c: capture_read_data = reference_offset;
                    8'h50: capture_read_data = ramp_increment;
                    8'h54: capture_read_data = {28'd0, phase_increment};
                    8'h58: capture_read_data = {30'd0, fault_kind};
                    8'h5c: capture_read_data = fault_cycle;
                    8'h60: capture_read_data = fault_periods;
                    8'h64: capture_read_data = {31'd0, fault_programmed};
                    8'h68: capture_read_data = {29'd0, overload_request, freeze_actuator, fault_ready};
                    8'h6c: capture_read_data = {31'd0, THERMAL};
                    8'h70: capture_read_data = MISS_LIMIT;
                    8'h74: capture_read_data = SAFE_VALUE;
                    8'h78: capture_read_data = 24;
                    8'h7c: capture_read_data = 1;
                    default: begin capture_read_data = 0; capture_response = 2'b10; end
                endcase
            end
        end
    end
    always_ff @(posedge capture_clock or negedge reset_n) begin
        if (!reset_n) begin
            run_enabled <= 0;
            stop_after_cycle <= 0;
            reference_mode <= 0;
            reference_amplitude <= 32'sd16777216;
            reference_offset <= 0;
            ramp_increment <= 0;
            phase_increment <= 1;
            fault_kind <= 0;
            fault_cycle <= 0;
            fault_periods <= 0;
            fault_programmed <= 0;
        end else if (accepted && capture_write) begin
            case (capture_address)
                8'h38: run_enabled <= 1;
                8'h3c: stop_after_cycle <= capture_write_data;
                8'h44: reference_mode <= capture_write_data[1:0];
                8'h48: reference_amplitude <= capture_write_data;
                8'h4c: reference_offset <= capture_write_data;
                8'h50: ramp_increment <= capture_write_data;
                8'h54: phase_increment <= capture_write_data[3:0];
                8'h58: fault_kind <= capture_write_data[1:0];
                8'h5c: fault_cycle <= capture_write_data;
                8'h60: fault_periods <= capture_write_data;
                8'h64: fault_programmed <= 1;
                default: begin end
            endcase
        end
    end
endmodule
