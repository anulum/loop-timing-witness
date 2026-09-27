// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — bus word window for one immutable FIFO record

// All ports belong to bus_clock. FIFO read_valid follows an accepted request
// by one cycle. Prefetch consumes a FIFO record into a held register; software
// sees words 0x80/84/88/8c until POP(0x94, data=1, strobes=15). Status0x90:
// bit0 held, bit1 fetch pending, bit2 upstream FIFO empty, bit3 run drained.
// Capture quiescence is stable after the producer's final FIFO write. Four
// synchroniser stages wait past the FIFO's two pointer stages and empty register.
// Invalid/unaligned/empty/read-only accesses return SLVERR and have no effect.
module event_record_window (
    input logic bus_clock, reset_n,
    input logic local_valid, local_write,
    input logic [7:0] local_address,
    input logic [31:0] local_write_data,
    input logic [3:0] local_write_strobes,
    output logic [31:0] local_read_data,
    output logic [1:0] local_response,
    output logic drain_request,
    input logic drain_valid, drain_empty,
    input logic [127:0] drain_record,
    input logic capture_quiescent,
    output logic run_drained
);
    logic held, pending, pop;
    logic [127:0] record;
    (* ASYNC_REG = "TRUE" *) logic [3:0] quiescent_sync;
    assign run_drained = reset_n && quiescent_sync[3] && drain_empty && !held && !pending;
    assign drain_request = reset_n && !held && !pending && !drain_empty;
    assign pop = local_valid && local_write && local_address == 8'h94 && held
        && local_write_strobes == 4'hf && local_write_data == 1;
    always_comb begin
        local_read_data = 0;
        local_response = 2'b10;
        if (reset_n && local_address[1:0] == 0) begin
            if (local_write) begin
                if (local_address == 8'h94 && held && local_write_strobes == 4'hf && local_write_data == 1)
                    local_response = 2'b00;
            end else begin
                case (local_address)
                    8'h80, 8'h84, 8'h88, 8'h8c: begin
                        if (held) begin
                            local_read_data = record[32*local_address[3:2] +: 32];
                            local_response = 2'b00;
                        end
                    end
                    8'h90: begin
                        local_read_data = {28'd0, run_drained, drain_empty, pending, held};
                        local_response = 2'b00;
                    end
                    default: begin end
                endcase
            end
        end
    end
    always_ff @(posedge bus_clock or negedge reset_n) begin
        if (!reset_n) begin
            held <= 0;
            pending <= 0;
            record <= 0;
            quiescent_sync <= 0;
        end else begin
            quiescent_sync <= {quiescent_sync[2:0], capture_quiescent};
            if (drain_request) pending <= 1;
            if (drain_valid && pending) begin
                record <= drain_record;
                held <= 1;
                pending <= 0;
            end
            if (pop) held <= 0;
        end
    end
endmodule
