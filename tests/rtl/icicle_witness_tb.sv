// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — Icicle AXI4-Lite fabric boundary simulation

`timescale 1ns/1ps
module icicle_witness_tb #(parameter bit THERMAL = 0);
    localparam logic [37:0] BASE = 38'h0060020000;
    logic bus_clock = 0, capture_clock = 0, run_reset_n = 0;
    logic [37:0] awaddr = BASE, araddr = BASE;
    logic [31:0] wdata = 0, rdata, read_value;
    logic [3:0] wstrb = 4'hf;
    logic awvalid = 0, awready, wvalid = 0, wready, bvalid, bready = 0;
    logic arvalid = 0, arready, rvalid, rready = 0, interrupt_line;
    logic [1:0] bresp, rresp;
    integer cycles;

    always #7 bus_clock = ~bus_clock;
    always #5 capture_clock = ~capture_clock;

    icicle_witness #(.PERIOD_TICKS(32'd64), .THERMAL(THERMAL)) device (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready),
        .wdata(wdata), .wstrb(wstrb), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready),
        .rdata(rdata), .rresp(rresp), .rvalid(rvalid), .rready(rready),
        .interrupt_line(interrupt_line)
    );

    task automatic write_register(input logic [7:0] offset, input logic [31:0] data);
        @(negedge bus_clock);
        while (!(awready && wready)) @(negedge bus_clock);
        awaddr = BASE | {30'b0, offset};
        awvalid = 1;
        wdata = data;
        wvalid = 1;
        @(negedge bus_clock);
        awvalid = 0;
        wvalid = 0;
        wait (bvalid);
        if (bresp != 0) $fatal(1, "board-facing AXI write failed");
        @(negedge bus_clock);
        bready = 1;
        @(negedge bus_clock);
        bready = 0;
    endtask

    task automatic read_register(input logic [7:0] offset, output logic [31:0] result);
        @(negedge bus_clock);
        while (!arready) @(negedge bus_clock);
        araddr = BASE | {30'b0, offset};
        arvalid = 1;
        @(negedge bus_clock);
        arvalid = 0;
        wait (rvalid);
        if (rresp != 0) $fatal(1, "board-facing AXI read failed");
        result = rdata;
        @(negedge bus_clock);
        rready = 1;
        @(negedge bus_clock);
        rready = 0;
    endtask

    initial begin
        #200000;
        $fatal(1, "board-facing witness timed out");
    end

    initial begin
        repeat (6) @(negedge bus_clock);
        run_reset_n = 1;
        wait (awready && wready && arready);
        read_register(8'h7c, read_value);
        if (read_value != 1) $fatal(1, "incorrect register identity through physical base");
        write_register(8'h98, 0);
        write_register(8'h98, 1);
        read_register(8'h98, read_value);
        while (read_value[2:0] != 7) read_register(8'h98, read_value);
        write_register(8'h38, 1);
        cycles = 0;
        while (!interrupt_line && cycles < 1000) begin
            @(negedge bus_clock);
            cycles = cycles + 1;
        end
        if (!interrupt_line) $fatal(1, "sample interrupt did not reach board port");
        read_register(8'h9c, read_value);
        if (!read_value[0]) $fatal(1, "sample interrupt status missing");
        write_register(8'ha4, 1);
        repeat (5) @(negedge bus_clock);
        if (interrupt_line) $fatal(1, "interrupt did not clear through physical base");
        $display("ICICLE_WITNESS_PASS thermal=%0d", THERMAL);
        $finish;
    end
endmodule
