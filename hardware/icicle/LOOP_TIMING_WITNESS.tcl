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
create_hdl_core -file $witness_top -module {icicle_witness} -library {work} -package {}
hdl_core_add_bif -hdl_core_name {icicle_witness} -bif_definition {AXI4:AMBA:AMBA4:mirroredMaster} -bif_name {AXI4_LITE_TARGET} -signal_map {\
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

sd_instantiate_component -sd_name {FIC_0_PERIPHERALS} -component_name {icicle_witness} -instance_name {icicle_witness_0}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"FIC0_INITIATOR:AXI4mslave2" "icicle_witness_0:AXI4_LITE_TARGET"}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"ACLK" "icicle_witness_0:bus_clock"}
sd_connect_pins -sd_name {FIC_0_PERIPHERALS} -pin_names {"ARESETN" "icicle_witness_0:run_reset_n"}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:capture_clock} -port_name {WITNESS_CAPTURE_CLK}
sd_connect_pin_to_port -sd_name {FIC_0_PERIPHERALS} -pin_name {icicle_witness_0:interrupt_line} -port_name {WITNESS_IRQ}
generate_component -component_name {FIC_0_PERIPHERALS} -recursive 0
sd_update_instance -sd_name ${top_level_name} -instance_name {FIC_0_PERIPHERALS_1}
sd_connect_pins -sd_name ${top_level_name} -pin_names {"CLOCKS_AND_RESETS:WITNESS_CAPTURE_CLK"     "FIC_0_PERIPHERALS_1:WITNESS_CAPTURE_CLK"}
sd_connect_pins -sd_name ${top_level_name} -pin_names {"FIC_0_PERIPHERALS_1:WITNESS_IRQ" "MSS_WRAPPER_1:MSS_INT_F2M_11"}
generate_component -component_name ${top_level_name} -recursive 0
