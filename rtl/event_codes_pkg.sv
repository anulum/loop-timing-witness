// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — event code package

package event_codes_pkg;
    localparam logic [7:0] SAMPLE_READY = 8'd1;
    localparam logic [7:0] SAMPLE_READ = 8'd2;
    localparam logic [7:0] ACT_WRITE = 8'd3;
    localparam logic [7:0] DEADLINE = 8'd4;
    localparam logic [7:0] SAFE_STATE = 8'd5;
    localparam logic [7:0] FAULT_INJECTED = 8'd6;
    localparam logic [7:0] FAULT_DETECTED = 8'd7;
    localparam logic [7:0] INPUT_WRITE = 8'd8;
    localparam logic [7:0] COMPUTE_START = 8'd9;
    localparam logic [7:0] COMPUTE_DONE = 8'd10;
    localparam logic [7:0] OUTPUT_READ = 8'd11;
    localparam logic [7:0] INTERRUPT_ENTRY = 8'd12;
endpackage
