// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — invariants of the retained interrupt

// The capture and bus clocks are free inputs, so after clk2fflogic every interleaving of their
// edges is explored; both local resets come from one bank reset through clock_reset_release, as
// in axi_control_witness. From any state reached through that reset: the bus domain's view of the
// generation count never runs ahead of the capture domain's count; a snapshot read at 0x9c never
// runs ahead of the bus view, and an acknowledge never runs ahead of the snapshot it consumes; the
// interrupt line is high exactly while the bus domain has seen a generation that is not
// acknowledged, so an acknowledge cannot clear a generation newer than its snapshot; an
// acknowledge and an upper-word read at 0xa0 succeed only with a held snapshot, and 0xa0 returns
// that snapshot's upper word; an acknowledge consumes the snapshot, so a second acknowledge
// needs a new 0x9c read. The Gray crossing is modelled without wire skew; the timing
// constraints bound the skew on silicon (hardware/icicle/README.md). The proof assumes fewer than
// 2^64 - 1 generations, more than 5,800 years of capture edges at 100 MHz. The observed wires are
// connected to the module's registers after flatten (connect -set, see make
// fault-interrupt-invariants). NEGATIVE_CONTROL asserts that the line never rises, which must
// yield a counterexample.
module retained_interrupt_proof #(
    parameter bit NEGATIVE_CONTROL = 0
) (
    input logic capture_clock, bus_clock, bank_reset_n,
    input logic sample_interrupt, safe_interrupt, run_finished,
    input logic local_valid, local_write,
    input logic [7:0] local_address,
    input logic [31:0] local_write_data,
    input logic [3:0] local_write_strobes
);
    wire capture_reset_n, bus_reset_n, interrupt_line;
    wire [31:0] local_read_data;
    wire [1:0] local_response;
    clock_reset_release capture_reset (
        .clock(capture_clock), .run_reset_n(bank_reset_n), .local_reset_n(capture_reset_n)
    );
    clock_reset_release bus_reset (
        .clock(bus_clock), .run_reset_n(bank_reset_n), .local_reset_n(bus_reset_n)
    );
    retained_interrupt dut (.*);

    // Registers and the decoded bus count of the module, connected after flatten.
    wire [63:0] generation, generation_gray, gray_first, gray_second, bus_generation;
    wire [63:0] observed_generation, acknowledged_generation;
    wire observed_valid;
    // Release stages of both reset synchronisers, connected after flatten.
    wire [1:0] capture_stage, bus_stage;

    function automatic [63:0] gray(input [63:0] value);
        gray = (value >> 1) ^ value;
    endfunction
    // Binary shadows of the two synchroniser stages: each samples, on the same bus edge, the count
    // whose Gray code the stage samples.
    logic [63:0] first_count, bus_count;
    always_ff @(posedge bus_clock or negedge bus_reset_n) begin
        if (!bus_reset_n) begin
            first_count <= '0;
            bus_count <= '0;
        end else begin
            first_count <= generation;
            bus_count <= first_count;
        end
    end

    // Whether the last accepted access consumed the snapshot (an acknowledge) rather than taking
    // one (a 0x9c read); a reset leaves no snapshot.
    logic consumed;
    always_ff @(posedge bus_clock or negedge bus_reset_n) begin
        if (!bus_reset_n) consumed <= 1'b1;
        else if (local_valid && local_response == 2'b00) begin
            if (local_write) consumed <= 1'b1;
            else if (local_address == 8'h9c) consumed <= 1'b0;
        end
    end

    logic reset_seen = 1'b0;
    always_ff @(posedge capture_clock or negedge bank_reset_n)
        if (!bank_reset_n) reset_seen <= 1'b1;

    always @* begin
        assume (generation != '1);
        if (reset_seen) begin
            // A local reset releases only after a bank reset, through stages 00, 01 and 11.
            assert (capture_stage != 2'b10 && bus_stage != 2'b10);
            // The bus view lags the capture count; snapshot and acknowledge lag the bus view.
            assert (generation_gray == gray(generation));
            assert (gray_first == gray(first_count) && gray_second == gray(bus_count));
            assert (bus_generation == bus_count);
            assert (bus_count <= first_count && first_count <= generation);
            assert (acknowledged_generation <= observed_generation && observed_generation <= bus_count);
            if (!observed_valid) assert (acknowledged_generation == observed_generation);
            // An acknowledge consumes the snapshot; only a new 0x9c read takes another.
            assert (observed_valid == !consumed);
            if (!capture_reset_n) assert (first_count == 64'd0 && bus_count == 64'd0
                && observed_generation == 64'd0);
            // The line is high exactly while a seen generation is unacknowledged.
            assert (interrupt_line == (bus_reset_n && acknowledged_generation < bus_count));
            if (bus_reset_n && local_response == 2'b00) begin
                if (local_write) assert (observed_valid && local_address == 8'ha4);
                if (!local_write && local_address == 8'ha0)
                    assert (observed_valid && local_read_data == observed_generation[63:32]);
            end
            if (NEGATIVE_CONTROL) assert (!interrupt_line);
        end
    end
endmodule
