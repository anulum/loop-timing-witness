# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — Icicle SmartDesign connection

if {![info exists local_dir]} {
    error "TIME WITNESS requires the reference project's local_dir"
}
foreach witness_variant {
    MSS_BAREMETAL VECTORBLOX I2C_LOOPBACK SPI_LOOPBACK DRI_CCC_DEMO
    MICRON_QSPI SMARTHLS AXI4_STREAM_DEMO BFM_SIMULATION
} {
    if {[info exists $witness_variant]} {
        error "TIME WITNESS requires the baseline reference Linux configuration: $witness_variant"
    }
}
if {![info exists project_dir]} {
    error "TIME WITNESS requires the reference project's project_dir"
}
set witness_pins [file normalize [file join $local_dir script_support constraints LOOP_TIMING_WITNESS.pdc]]
if {![file isfile $witness_pins]} {
    error "derived source lacks the witness pin constraints"
}
set witness_rtl_dir [file normalize [file join $local_dir witness_rtl]]
set witness_top [file join $witness_rtl_dir icicle_witness.sv]
set witness_package [file join $witness_rtl_dir event_codes_pkg.sv]
if {![file isfile $witness_top] || ![file isfile $witness_package]} {
    error "derived witness_rtl snapshot lacks the witness top or event package"
}

import_files -library work -hdl_source $witness_package
foreach witness_source [lsort [glob -directory $witness_rtl_dir *.sv]] {
    if {$witness_source ne $witness_package} {
        import_files -library work -hdl_source $witness_source
    }
}
build_design_hierarchy
create_hdl_core -file {hdl/icicle_witness.sv} -module {icicle_witness} -library {work} -package {}
hdl_core_add_bif -hdl_core_name {icicle_witness} -bif_definition {AXI4:AMBA:AMBA4:slave} -bif_name {AXI4_LITE_TARGET} -signal_map {\
"AWADDR:awaddr" \
"AWVALID:awvalid" \
"AWREADY:awready" \
"WDATA:wdata" \
"WSTRB:wstrb" \
"WVALID:wvalid" \
"WREADY:wready" \
"BRESP:bresp" \
"BVALID:bvalid" \
"BREADY:bready" \
"ARADDR:araddr" \
"ARVALID:arvalid" \
"ARREADY:arready" \
"RDATA:rdata" \
"RRESP:rresp" \
"RVALID:rvalid" \
"RREADY:rready" }

open_smartdesign -sd_name {FIC_0_PERIPHERALS}
sd_instantiate_hdl_core -sd_name {FIC_0_PERIPHERALS} -hdl_core_name {icicle_witness} -instance_name {icicle_witness_0}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"FIC0_INITIATOR:AXI4mslave2" "icicle_witness_0:AXI4_LITE_TARGET"}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"ACLK" "icicle_witness_0:bus_clock"}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"ARESETN" "icicle_witness_0:run_reset_n"}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:capture_clock} -port_name {WITNESS_CAPTURE_CLK}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:capture_clock_locked} -port_name {WITNESS_CAPTURE_LOCK}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:interrupt_line} -port_name {WITNESS_IRQ}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:sample_ready_mirror} -port_name {WITNESS_SAMPLE_READY}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:actuator_write_mirror} -port_name {WITNESS_ACT_WRITE}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:safe_state_mirror} -port_name {WITNESS_SAFE_STATE}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:pps_in} -port_name {WITNESS_PPS}
generate_component -component_name {FIC_0_PERIPHERALS} -recursive 0
sd_update_instance -sd_name ${top_level_name} -instance_name {FIC_0_PERIPHERALS_1}
# The base design ties MSS fabric-to-processor interrupts 11 to 58 low; bit 11 becomes the witness interrupt
# input only now, after the base design has generated with every MSS input connected.
open_smartdesign -sd_name {MSS_WRAPPER}
sd_clear_pin_attributes -sd_name {MSS_WRAPPER} -pin_names {ICICLE_MSS:MSS_INT_F2M[58:11]}
sd_delete_pin_slices -sd_name {MSS_WRAPPER} -pin_name {ICICLE_MSS:MSS_INT_F2M} -pin_slices {[58:11]}
sd_create_pin_slices -sd_name {MSS_WRAPPER} -pin_name {ICICLE_MSS:MSS_INT_F2M} -pin_slices {[11:11]}
sd_create_pin_slices -sd_name {MSS_WRAPPER} -pin_name {ICICLE_MSS:MSS_INT_F2M} -pin_slices {[58:12]}
sd_connect_pins_to_constant -sd_name {MSS_WRAPPER} -pin_names {ICICLE_MSS:MSS_INT_F2M[58:12]} -value {GND}
sd_create_scalar_port -sd_name {MSS_WRAPPER} -port_name {MSS_INT_F2M_11} -port_direction {IN}
sd_connect_pins -sd_name {MSS_WRAPPER} -pin_names {"ICICLE_MSS:MSS_INT_F2M[11:11]" "MSS_INT_F2M_11"}
save_smartdesign -sd_name {MSS_WRAPPER}
generate_component -component_name {MSS_WRAPPER} -recursive 0
sd_update_instance -sd_name ${top_level_name} -instance_name {MSS_WRAPPER_1}

# The reference CCC uses all four PLL0 outputs (125, 125, 125 and 50 MHz) and has no PLL1, so the
# witness capture clock comes from its own CCC: 100 MHz from the same 50 MHz reference clock.
create_and_configure_core -download_core -core_vlnv {Actel:SgCore:PF_CCC:*} -component_name {WITNESS_CCC} -params {\
"GL0_0_IS_USED:true" \
"GL0_0_OUT_FREQ:100" \
"GL0_0_FABCLK_USED:true" \
"GL1_0_IS_USED:false" \
"GL2_0_IS_USED:false" \
"GL3_0_IS_USED:false" \
"PLL_IN_FREQ_0:50" \
"PLL_REF_CLK_SEL_0:false" \
"PLL_EXPORT_PWRDWN:false" }
open_smartdesign -sd_name {CLOCKS_AND_RESETS}
sd_instantiate_component -sd_name {CLOCKS_AND_RESETS} -component_name {WITNESS_CCC} -instance_name {WITNESS_CCC_0}
sd_create_scalar_port -sd_name {CLOCKS_AND_RESETS} -port_name {WITNESS_CAPTURE_CLK} -port_direction {OUT}
sd_connect_pins -sd_name {CLOCKS_AND_RESETS} -pin_names {"CLKINT_REF_CLK_50MHz:Y" "WITNESS_CCC_0:REF_CLK_0"}
sd_connect_pins -sd_name {CLOCKS_AND_RESETS} -pin_names {"WITNESS_CCC_0:OUT0_FABCLK_0" "WITNESS_CAPTURE_CLK"}
# The witness holds both of its domains in reset until this PLL locks.
sd_create_scalar_port -sd_name {CLOCKS_AND_RESETS} -port_name {WITNESS_CAPTURE_LOCK} -port_direction {OUT}
sd_connect_pins -sd_name {CLOCKS_AND_RESETS} -pin_names {"WITNESS_CCC_0:PLL_LOCK_0" "WITNESS_CAPTURE_LOCK"}
save_smartdesign -sd_name {CLOCKS_AND_RESETS}
generate_component -component_name {CLOCKS_AND_RESETS} -recursive 0
sd_update_instance -sd_name ${top_level_name} -instance_name {CLOCKS_AND_RESETS}

sd_connect_pins -sd_name ${top_level_name} -pin_names {"CLOCKS_AND_RESETS:WITNESS_CAPTURE_CLK"     "FIC_0_PERIPHERALS_1:WITNESS_CAPTURE_CLK"}
sd_connect_pins -sd_name ${top_level_name} -pin_names {"CLOCKS_AND_RESETS:WITNESS_CAPTURE_LOCK"    "FIC_0_PERIPHERALS_1:WITNESS_CAPTURE_LOCK"}
sd_connect_pins -sd_name ${top_level_name} -pin_names {"FIC_0_PERIPHERALS_1:WITNESS_IRQ" "MSS_WRAPPER_1:MSS_INT_F2M_11"}
# The event mirrors leave the device, and the pulse-per-second reference enters it, on the four
# pins that LOOP_TIMING_WITNESS.pdc fixes.
foreach witness_pin {WITNESS_SAMPLE_READY WITNESS_ACT_WRITE WITNESS_SAFE_STATE WITNESS_PPS} {
    sd_connect_pin_to_port -sd_name ${top_level_name} -pin_name "FIC_0_PERIPHERALS_1:$witness_pin" -port_name $witness_pin
}
generate_component -component_name ${top_level_name} -recursive 0

# Balls C15 and C14, the safe-state mirror and the pulse-per-second input, are the device's live
# probe pins LPRB_B and LPRB_A on the single-pin connectors J12 and J13. The reference reserves
# them for SmartDebug live probes (RESTRICTPROBEPINS:1); the witness releases them for user I/O,
# so this design offers no live probe.
set_device -adv_options {RESTRICTPROBEPINS:0}
# The reference has already associated its own I/O constraints with place-and-route; the
# association is replaced by the same list, of the baseline configuration the witness
# requires, with the witness pins added.
import_files -convert_EDN_to_HDL 0 -io_pdc $witness_pins
organize_tool_files \
    -tool {PLACEROUTE} \
    -file "${project_dir}/constraint/io/ICICLE_CAN0.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MIKROBUS.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_SDIO.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_USB.pdc" \
    -file "${project_dir}/constraint/io/ICICLE.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MAC.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_PCIE.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MMUART0.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MMUART1.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MMUART3.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_MMUART2.pdc" \
    -file "${project_dir}/constraint/io/ICICLE_RPi.pdc" \
    -file "${project_dir}/constraint/io/LOOP_TIMING_WITNESS.pdc" \
    -file "${project_dir}/constraint/fp/NW_PLL.pdc" \
    -file "${project_dir}/constraint/fic_clocks.sdc" \
    -module ${top_level_name}::work \
    -input_type {constraint}
