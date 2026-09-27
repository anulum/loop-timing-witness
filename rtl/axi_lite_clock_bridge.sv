// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — AXI4-Lite transactions across capture and bus clocks

// 32-bit data, 256-byte aperture, one read and one write outstanding.
// AW and W are independent: neither channel waits for the other to assert VALID.
// Fair arbitration forwards a complete write or read to the capture edge. The
// destination supplies combinational read data and response for that same edge.
// Destination logic owns address decode, alignment, strobes and access policy.
// Common reset abandons all bus and capture transactions. Bundled-data physical
// timing constraints are required by clock_request_bridge before board use.
// ENABLE_LOCAL keeps addresses 0x80..0xff in the bus clock domain. local_valid
// is an accepted-edge strobe; local response/data are sampled on that edge.
// Local and remote dispatch share the same arbitration and response credits.
module axi_lite_clock_bridge #(
    parameter bit ENABLE_LOCAL = 0
) (
    input logic bus_clock, capture_clock, run_reset_n,
    input logic [7:0] awaddr,
    input logic awvalid,
    output logic awready,
    input logic [31:0] wdata,
    input logic [3:0] wstrb,
    input logic wvalid,
    output logic wready,
    output logic [1:0] bresp,
    output logic bvalid,
    input logic bready,
    input logic [7:0] araddr,
    input logic arvalid,
    output logic arready,
    output logic [31:0] rdata,
    output logic [1:0] rresp,
    output logic rvalid,
    input logic rready,
    output logic capture_valid, capture_write,
    output logic [7:0] capture_address,
    output logic [31:0] capture_write_data,
    output logic [3:0] capture_write_strobes,
    input logic [31:0] capture_read_data,
    input logic [1:0] capture_response,
    output logic local_valid, local_write,
    output logic [7:0] local_address,
    output logic [31:0] local_write_data,
    output logic [3:0] local_write_strobes,
    input logic [31:0] local_read_data,
    input logic [1:0] local_response
);
    logic reset_n, address_held, data_held, read_held;
    logic write_outstanding, read_outstanding, prefer_write, selected_write, response_write;
    logic [7:0] write_address, read_address;
    logic [31:0] write_data;
    logic [3:0] write_strobes;
    logic request_valid, request_ready, response_valid, response_ready;
    logic [44:0] request_data, capture_data;
    logic [33:0] response_data;
    logic local_selected;
    clock_reset_release bus_reset (
        .clock(bus_clock), .run_reset_n(run_reset_n), .local_reset_n(reset_n)
    );
    assign awready = reset_n && !address_held && !write_outstanding;
    assign wready = reset_n && !data_held && !write_outstanding;
    assign arready = reset_n && !read_held && !read_outstanding;
    assign selected_write = address_held && data_held && (!read_held || prefer_write);
    assign request_valid = reset_n && ((address_held && data_held) || read_held);
    assign request_data = selected_write
        ? {1'b1, write_address, write_data, write_strobes}
        : {1'b0, read_address, 32'd0, 4'd0};
    assign {capture_write, capture_address, capture_write_data, capture_write_strobes} = capture_data;
    assign {local_write, local_address, local_write_data, local_write_strobes} = request_data;
    assign local_selected = ENABLE_LOCAL && request_data[43];
    assign local_valid = request_valid && request_ready && local_selected;
    assign response_ready = response_write ? !bvalid : !rvalid;
    clock_request_bridge #(.REQUEST_BITS(45), .RESPONSE_BITS(34)) transaction_bridge (
        .bus_clock(bus_clock), .capture_clock(capture_clock), .run_reset_n(run_reset_n),
        .request_valid(request_valid && !local_selected), .request_ready(request_ready), .request_data(request_data),
        .response_valid(response_valid), .response_ready(response_ready), .response_data(response_data),
        .capture_valid(capture_valid), .capture_data(capture_data),
        .capture_response({capture_read_data, capture_response})
    );
    always_ff @(posedge bus_clock or negedge reset_n) begin
        if (!reset_n) begin
            address_held <= 0;
            data_held <= 0;
            read_held <= 0;
            write_outstanding <= 0;
            read_outstanding <= 0;
            prefer_write <= 1;
            response_write <= 0;
            write_address <= 0;
            read_address <= 0;
            write_data <= 0;
            write_strobes <= 0;
            bresp <= 0;
            bvalid <= 0;
            rdata <= 0;
            rresp <= 0;
            rvalid <= 0;
        end else begin
            if (awvalid && awready) begin
                address_held <= 1;
                write_address <= awaddr;
            end
            if (wvalid && wready) begin
                data_held <= 1;
                write_data <= wdata;
                write_strobes <= wstrb;
            end
            if (arvalid && arready) begin
                read_held <= 1;
                read_address <= araddr;
            end
            if (request_valid && request_ready) begin
                response_write <= selected_write;
                prefer_write <= !selected_write;
                if (selected_write) begin
                    address_held <= 0;
                    data_held <= 0;
                    write_outstanding <= 1;
                end else begin
                    read_held <= 0;
                    read_outstanding <= 1;
                end
            end
            if (bvalid && bready) begin
                bvalid <= 0;
                write_outstanding <= 0;
            end
            if (rvalid && rready) begin
                rvalid <= 0;
                read_outstanding <= 0;
            end
            if (response_valid && response_ready) begin
                if (response_write) begin
                    bresp <= response_data[1:0];
                    bvalid <= 1;
                end else begin
                    rdata <= response_data[33:2];
                    rresp <= response_data[1:0];
                    rvalid <= 1;
                end
            end
            if (local_valid) begin
                if (selected_write) begin
                    bresp <= local_response;
                    bvalid <= 1;
                end else begin
                    rdata <= local_read_data;
                    rresp <= local_response;
                    rvalid <= 1;
                end
            end
        end
    end
endmodule
