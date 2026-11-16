// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — split multiplier public-port testbench

`timescale 1ns/1ps
// Every WIDTH 8 operand pair, the 32-bit half-boundary corner pairs and seeded
// random pairs are compared with the direct signed product one edge later; reset
// clears the product.
module split_multiplier_tb;
    logic clock = 0, reset_n = 0;
    logic signed [7:0] narrow_a = 0, narrow_b = 0;
    logic signed [15:0] narrow_product;
    logic signed [31:0] wide_a = 0, wide_b = 0;
    logic signed [63:0] wide_product, expected;
    logic signed [31:0] corners [0:19];
    integer first, second, checked = 0, seed = 20261116;
    split_multiplier #(.WIDTH(8)) narrow (
        .clock(clock), .reset_n(reset_n), .multiplicand(narrow_a),
        .multiplier(narrow_b), .product(narrow_product)
    );
    split_multiplier wide (
        .clock(clock), .reset_n(reset_n), .multiplicand(wide_a),
        .multiplier(wide_b), .product(wide_product)
    );
    always #5 clock = ~clock;
    task automatic check_wide(input logic signed [31:0] a, input logic signed [31:0] b);
        begin
            @(negedge clock); wide_a = a; wide_b = b;
            expected = $signed({{32{a[31]}}, a}) * $signed({{32{b[31]}}, b});
            @(negedge clock);
            if (wide_product != expected) $fatal(1, "wide product %0d * %0d", a, b);
            checked = checked + 1;
        end
    endtask
    initial begin
        corners[0] = 0; corners[1] = 1; corners[2] = -1; corners[3] = 2;
        corners[4] = 32'sh00007fff; corners[5] = 32'sh00008000; corners[6] = 32'sh0000ffff;
        corners[7] = 32'sh00010000; corners[8] = 32'sh7fffffff; corners[9] = 32'sh80000000;
        corners[10] = 32'sh80000001; corners[11] = 32'shffff0000; corners[12] = 32'shffff8000;
        corners[13] = 32'shffff7fff; corners[14] = 32'sh7fff0000; corners[15] = 32'sh8000ffff;
        corners[16] = 32'sh00ffffff; corners[17] = 32'sh01000000; corners[18] = 32'sd16777208;
        corners[19] = -32'sd16769;
        @(negedge clock);
        if (narrow_product != 0 || wide_product != 0) $fatal(1, "reset product not zero");
        reset_n = 1;
        for (first = -128; first < 128; first = first + 1)
            for (second = -128; second < 128; second = second + 1) begin
                @(negedge clock); narrow_a = first[7:0]; narrow_b = second[7:0];
                @(negedge clock);
                if ($signed({{16{narrow_product[15]}}, narrow_product}) != first * second)
                    $fatal(1, "narrow %0d * %0d", first, second);
            end
        for (first = 0; first < 20; first = first + 1)
            for (second = 0; second < 20; second = second + 1)
                check_wide(corners[first], corners[second]);
        repeat (20000) check_wide($random(seed), $random(seed));
        reset_n = 0; #1;
        if (wide_product != 0 || narrow_product != 0) $fatal(1, "reset did not clear the product");
        $display("SPLIT_MULTIPLIER_PASS narrow=65536 wide=%0d", checked);
        $finish;
    end
endmodule
