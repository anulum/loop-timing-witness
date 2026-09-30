# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — production RTL Spike plugin build

# Source and build must be the actual matching Spike installation used for execution.
AMP_SPIKE_SOURCE ?=
AMP_SPIKE_BUILD ?=
AMP_PLUGIN_DIRECTORY ?= build/amp_spike_$(SIMULATION_THERMAL)
AMP_VERILATOR_ROOT ?= $(shell verilator --getenv VERILATOR_ROOT)
AMP_PLUGIN_PYTHON ?= $(VENV)/python
AMP_PLUGIN_CFLAGS := -std=gnu11 -O2 -fPIC $(CONTROLLER_WARNINGS)
AMP_PLUGIN_CXXFLAGS := -std=c++20 -O2 -fPIC -Wall -Wextra -Werror -Wconversion -Wshadow
AMP_PLUGIN_RUNTIME_FLAGS := -std=c++20 -O2 -fPIC
AMP_PLUGIN_INCLUDES := -I"$(AMP_PLUGIN_DIRECTORY)/rtl" \
    -isystem "$(AMP_VERILATOR_ROOT)/include" -isystem "$(AMP_VERILATOR_ROOT)/include/vltstd" \
    -isystem "$(AMP_SPIKE_SOURCE)" -isystem "$(AMP_SPIKE_SOURCE)/riscv" \
    -isystem "$(AMP_SPIKE_SOURCE)/fdt" -isystem "$(AMP_SPIKE_BUILD)"
AMP_PLUGIN_MODEL_FLAGS := -fPIC -std=c++20 -MD -I. \
    -I"$(AMP_VERILATOR_ROOT)/include" -I"$(AMP_VERILATOR_ROOT)/include/vltstd" \
    -DVM_COVERAGE=0 -DVM_SC=0 -DVM_TRACE=0 -DVM_TRACE_FST=0 -DVM_TRACE_VCD=0
AMP_PLUGIN_PREPARE := $(AMP_PLUGIN_PYTHON) tools/amp_plugin_preparation.py \
    --directory "$(AMP_PLUGIN_DIRECTORY)" --source "$(AMP_SPIKE_SOURCE)" --sdk "$(AMP_SPIKE_BUILD)" \
    --cc "$(LINUX_CC)" --cxx "$(LINUX_CXX)" --thermal "$(SIMULATION_THERMAL)" \
    --fifo-address-bits "$(SIMULATION_FIFO_ADDRESS_BITS)" --runtime-root "$(AMP_VERILATOR_ROOT)"

.PHONY: amp-spike-plugin amp-spike-plugin-prepare
amp-spike-plugin-prepare:
	test -n "$(AMP_SPIKE_SOURCE)" -a -n "$(AMP_SPIKE_BUILD)"
	test -f "$(AMP_SPIKE_SOURCE)/riscv/abstract_device.h" -a -f "$(AMP_SPIKE_BUILD)/config.h"
	test ! -e "$(AMP_PLUGIN_DIRECTORY)/plugin.json"
	test ! -e "$(AMP_PLUGIN_DIRECTORY)/generation.json"
	mkdir -p "$(AMP_PLUGIN_DIRECTORY)"
	$(AMP_PLUGIN_PREPARE) --stage generation
	verilator --cc --Wall --top-module axi_control_witness \
		-GPERIOD_TICKS=32768 -GADDRESS_BITS=$(SIMULATION_FIFO_ADDRESS_BITS) -GGROUP_ADDRESS_BITS=4 \
		"-GTHERMAL=1'b$(SIMULATION_THERMAL)" --Mdir "$(AMP_PLUGIN_DIRECTORY)/rtl" \
		-CFLAGS "-fPIC -std=c++20 -MD" $(RTL_SOURCES)
	$(MAKE) -C "$(AMP_PLUGIN_DIRECTORY)/rtl" -f Vaxi_control_witness.mk \
		PYTHON3="$(abspath $(AMP_PLUGIN_PYTHON))" Vaxi_control_witness__ALL.cpp
	mkdir "$(AMP_PLUGIN_DIRECTORY)/precompile"
	$(LINUX_CC) $(AMP_PLUGIN_CFLAGS) -M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/controller.d" controllers/c/witness_controller.c
	$(LINUX_CXX) $(AMP_PLUGIN_CXXFLAGS) -M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/configuration.d" runtime/run_configuration.cpp
	$(LINUX_CXX) $(AMP_PLUGIN_CXXFLAGS) $(AMP_PLUGIN_INCLUDES) \
		-M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/plugin.d" runtime/isa/spike_axi_device.cpp
	$(LINUX_CXX) $(AMP_PLUGIN_RUNTIME_FLAGS) -I"$(AMP_VERILATOR_ROOT)/include" -I"$(AMP_VERILATOR_ROOT)/include/vltstd" \
		-M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/verilated.d" "$(AMP_VERILATOR_ROOT)/include/verilated.cpp"
	$(LINUX_CXX) $(AMP_PLUGIN_RUNTIME_FLAGS) -I"$(AMP_VERILATOR_ROOT)/include" -I"$(AMP_VERILATOR_ROOT)/include/vltstd" \
		-M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/verilated_threads.d" "$(AMP_VERILATOR_ROOT)/include/verilated_threads.cpp"
	$(LINUX_CXX) $(AMP_PLUGIN_MODEL_FLAGS) -Os -I"$(AMP_PLUGIN_DIRECTORY)/rtl" \
		-M -MF "$(AMP_PLUGIN_DIRECTORY)/precompile/model.d" "$(AMP_PLUGIN_DIRECTORY)/rtl/Vaxi_control_witness__ALL.cpp"
	$(AMP_PLUGIN_PREPARE) --stage compilation

amp-spike-plugin: amp-spike-plugin-prepare
	$(MAKE) -C "$(AMP_PLUGIN_DIRECTORY)/rtl" -f Vaxi_control_witness.mk -j 2 \
		CXX="$(LINUX_CXX)" CXXFLAGS= CPPFLAGS='$(AMP_PLUGIN_MODEL_FLAGS)' \
		AR=ar PYTHON3="$(abspath $(AMP_PLUGIN_PYTHON))" Vaxi_control_witness__ALL.a
	$(LINUX_CC) $(AMP_PLUGIN_CFLAGS) \
		-MD -MF "$(AMP_PLUGIN_DIRECTORY)/controller.d" -c controllers/c/witness_controller.c -o "$(AMP_PLUGIN_DIRECTORY)/controller.o"
	$(LINUX_CXX) $(AMP_PLUGIN_CXXFLAGS) -MD -MF "$(AMP_PLUGIN_DIRECTORY)/configuration.d" -c runtime/run_configuration.cpp \
		-o "$(AMP_PLUGIN_DIRECTORY)/configuration.o"
	$(LINUX_CXX) $(AMP_PLUGIN_CXXFLAGS) $(AMP_PLUGIN_INCLUDES) \
		-MD -MF "$(AMP_PLUGIN_DIRECTORY)/plugin.d" -c runtime/isa/spike_axi_device.cpp -o "$(AMP_PLUGIN_DIRECTORY)/plugin.o"
	$(LINUX_CXX) $(AMP_PLUGIN_RUNTIME_FLAGS) -I"$(AMP_VERILATOR_ROOT)/include" \
		-I"$(AMP_VERILATOR_ROOT)/include/vltstd" -MD -MF "$(AMP_PLUGIN_DIRECTORY)/verilated.d" -c "$(AMP_VERILATOR_ROOT)/include/verilated.cpp" \
		-o "$(AMP_PLUGIN_DIRECTORY)/verilated.o"
	$(LINUX_CXX) $(AMP_PLUGIN_RUNTIME_FLAGS) -I"$(AMP_VERILATOR_ROOT)/include" \
		-I"$(AMP_VERILATOR_ROOT)/include/vltstd" -MD -MF "$(AMP_PLUGIN_DIRECTORY)/verilated_threads.d" -c "$(AMP_VERILATOR_ROOT)/include/verilated_threads.cpp" \
		-o "$(AMP_PLUGIN_DIRECTORY)/verilated_threads.o"
	$(LINUX_CXX) -shared -Wl,--fatal-warnings "$(AMP_PLUGIN_DIRECTORY)/configuration.o" \
		"$(AMP_PLUGIN_DIRECTORY)/controller.o" "$(AMP_PLUGIN_DIRECTORY)/plugin.o" \
		"$(AMP_PLUGIN_DIRECTORY)/rtl/Vaxi_control_witness__ALL.a" \
		"$(AMP_PLUGIN_DIRECTORY)/verilated.o" "$(AMP_PLUGIN_DIRECTORY)/verilated_threads.o" \
		-pthread -o "$(AMP_PLUGIN_DIRECTORY)/witness_spike_axi.so"
	$(AMP_PLUGIN_PYTHON) tools/write_amp_plugin_manifest.py --directory "$(AMP_PLUGIN_DIRECTORY)" \
		--source "$(AMP_SPIKE_SOURCE)" --sdk "$(AMP_SPIKE_BUILD)" \
		--cc "$(LINUX_CC)" --cxx "$(LINUX_CXX)" --thermal "$(SIMULATION_THERMAL)" \
		--fifo-address-bits "$(SIMULATION_FIFO_ADDRESS_BITS)" --runtime-root "$(AMP_VERILATOR_ROOT)"
