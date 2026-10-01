# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — local gate entry points

PYTHON_BOOTSTRAP ?= python3.13
VENV := .venv/bin
PREFLIGHT := $(VENV)/python tools/preflight.py

.PHONY: venv hooks lint typecheck test validate docs security preflight inventory python-wheelhouse python-package-tests

venv:
	$(PYTHON_BOOTSTRAP) -m venv .venv
	$(VENV)/python -m pip install --require-hashes --no-deps -r requirements-dev.txt
	$(VENV)/python -m pip install --no-index --no-build-isolation --no-deps -e .

python-wheelhouse:
	$(VENV)/python -m pip download --only-binary=:all: --require-hashes --no-deps -r requirements-runtime.txt --dest build/python-wheelhouse

python-package-tests: python-wheelhouse
	$(VENV)/python -m pytest -q tests/test_python_distribution.py

hooks:
	$(VENV)/pre-commit install

lint:
	$(PREFLIGHT) --only ruff-check
	$(PREFLIGHT) --only ruff-format

typecheck:
	$(PREFLIGHT) --only mypy

test:
	$(VENV)/pytest --cov --cov-branch --cov-report=term-missing --cov-fail-under=100

validate:
	$(PREFLIGHT) --only measurement-domain
	$(PREFLIGHT) --only capability-inventory
	$(PREFLIGHT) --only dependency-licences
	$(PREFLIGHT) --only workflows

docs:
	$(PREFLIGHT) --only documentation
	$(PREFLIGHT) --only provenance-headers

DOXYGEN_BINARY := .venv/native/doxygen/doxygen-1.18.0/bin/doxygen
.PHONY: documentation-toolchain native-api docs-site

documentation-toolchain:
	mkdir -p build/documentation-toolchain .venv/native/doxygen
	curl --fail --location --max-time 180 --retry 2 --retry-max-time 240 \
		--output build/documentation-toolchain/doxygen.tar.gz \
		https://github.com/doxygen/doxygen/releases/download/Release_1_18_0/doxygen-1.18.0.linux.bin.tar.gz
	printf '%s\n' '14fa81bdc34171edb5f1f02b1d60e74802f0439b77fa44e592565d517d72df90  build/documentation-toolchain/doxygen.tar.gz' | sha256sum --check --strict
	$(VENV)/python -c 'import tarfile; archive = tarfile.open("build/documentation-toolchain/doxygen.tar.gz"); archive.extractall(".venv/native/doxygen", filter="data"); archive.close()'
	$(DOXYGEN_BINARY) --version

native-api:
	test "$$( $(DOXYGEN_BINARY) --version | cut -d' ' -f1 )" = "1.18.0"
	mkdir -p build/native-api/c
	$(DOXYGEN_BINARY) Doxyfile
	RUSTDOCFLAGS='-D warnings -D rustdoc::broken_intra_doc_links' cargo doc --offline --locked --no-deps --manifest-path controllers/rust/Cargo.toml --target-dir build/native-api/rust
	RUSTDOCFLAGS='-D warnings -D rustdoc::broken_intra_doc_links' cargo doc --offline --locked --no-deps --manifest-path runtime/bare_metal/rust_kernel/Cargo.toml --target-dir build/native-api/rust

docs-site: native-api
	rm -rf build/docs-site
	$(VENV)/python tools/build_docs_site.py --output build/docs-site

security:
	$(PREFLIGHT) --only reuse
	$(PREFLIGHT) --only zizmor
	$(PREFLIGHT) --only actionlint
	$(PREFLIGHT) --only secrets
	$(VENV)/pip-audit --require-hashes --disable-pip -r requirements-dev.txt

inventory:
	$(VENV)/python tools/generate_capability_inventory.py --write

preflight:
	$(PREFLIGHT)

# Native kernels have no third-party dependencies. All build files stay here.
CONTROLLER_WARNINGS := -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes
CONTROLLER_CRATE := controllers/rust/Cargo.toml

.PHONY: controller-build controller-tests controller-benchmarks

controller-build:
	mkdir -p build
	gcc -std=gnu11 -O3 -flto $(CONTROLLER_WARNINGS) controllers/c/witness_controller.c controllers/c/controller_cli.c -o build/controller_cli
	gcc -std=gnu11 -O2 $(CONTROLLER_WARNINGS) -fsanitize=undefined -fno-sanitize-recover=all -Icontrollers/c controllers/c/witness_controller.c tests/native/controller_api_test.c -o build/controller_api_test
	gcc -std=gnu11 -O3 -flto $(CONTROLLER_WARNINGS) -Icontrollers/c controllers/c/witness_controller.c benchmarks/controller_benchmark.c -o build/controller_benchmark
	cargo fmt --check --manifest-path $(CONTROLLER_CRATE)
	cargo clippy --offline --locked --all-targets --manifest-path $(CONTROLLER_CRATE) -- -D warnings
	cargo build --release --offline --locked --manifest-path $(CONTROLLER_CRATE)
	cargo doc --no-deps --offline --locked --manifest-path $(CONTROLLER_CRATE)

controller-tests: controller-build
	build/controller_api_test
	cargo test --offline --locked --manifest-path $(CONTROLLER_CRATE)

CONTROLLER_BENCHMARK_OUTPUT ?= build/controller_comparison.local.json
CONTROLLER_BENCHMARK_CPU ?= 0

controller-benchmarks: controller-build
	$(VENV)/python tools/benchmark_controllers.py --output $(CONTROLLER_BENCHMARK_OUTPUT) --cpu $(CONTROLLER_BENCHMARK_CPU)

# The simulator compiles the production top, including plant, clocks and FIFO.
SIMULATION_THERMAL ?= 0
SIMULATION_FIFO_ADDRESS_BITS ?= 8
RUN_SIMULATION_DIRECTORY ?= build/run_simulation_$(SIMULATION_THERMAL)
RUN_SIMULATION_CFLAGS ?= -std=c++17 -Wall -Wextra -Werror
RUN_SIMULATION_LDFLAGS ?=
SIMULATION_DIRECTORY := build/axi_simulator_$(SIMULATION_THERMAL)
AXI_SIMULATOR_CFLAGS ?= -std=c++17 -Wall -Wextra -Werror
AXI_SIMULATOR_VERILATOR_FLAGS ?=
RTL_SOURCES := rtl/event_codes_pkg.sv $(filter-out rtl/event_codes_pkg.sv,$(wildcard rtl/*.sv))
.PHONY: axi-simulator
axi-simulator:
	mkdir -p "$(SIMULATION_DIRECTORY)"
	verilator --cc --exe --build --Wall --top-module axi_control_witness -j 2 \
		$(AXI_SIMULATOR_VERILATOR_FLAGS) \
		-GPERIOD_TICKS=32768 -GADDRESS_BITS=8 -GGROUP_ADDRESS_BITS=4 \
		"-GTHERMAL=1'b$(SIMULATION_THERMAL)" --Mdir $(SIMULATION_DIRECTORY) \
		-CFLAGS "$(AXI_SIMULATOR_CFLAGS)" \
		$(RTL_SOURCES) $(abspath runtime/rtl/axi_simulator.cpp) -o axi_simulator

LINUX_CC ?= gcc
LINUX_CXX ?= g++
LINUX_CPPFLAGS ?=
LINUX_LDFLAGS ?=
LINUX_BUILD_DIRECTORY ?= build

.PHONY: uio-transport
uio-transport:
	mkdir -p "$(LINUX_BUILD_DIRECTORY)"
	$(LINUX_CXX) $(LINUX_CPPFLAGS) -std=c++17 -O2 -Wall -Wextra -Werror -Wconversion -Wshadow \
		runtime/linux/uio_device.cpp runtime/linux/uio_transport.cpp $(LINUX_LDFLAGS) \
		-o "$(LINUX_BUILD_DIRECTORY)/uio_transport"

.PHONY: run-simulation
run-simulation:
	mkdir -p build "$(RUN_SIMULATION_DIRECTORY)"
	gcc -std=gnu11 -O2 $(CONTROLLER_WARNINGS) -c controllers/c/witness_controller.c -o build/run_controller_kernel.o
	verilator --cc --exe --build --Wall --top-module axi_control_witness -j 2 \
		-GPERIOD_TICKS=32768 -GADDRESS_BITS=$(SIMULATION_FIFO_ADDRESS_BITS) -GGROUP_ADDRESS_BITS=4 \
		"-GTHERMAL=1'b$(SIMULATION_THERMAL)" --Mdir $(RUN_SIMULATION_DIRECTORY) \
		-CFLAGS "$(RUN_SIMULATION_CFLAGS)" \
		-LDFLAGS "$(abspath build/run_controller_kernel.o) -lcrypto $(RUN_SIMULATION_LDFLAGS)" \
		$(RTL_SOURCES) $(abspath runtime/rtl/run_simulation.cpp) \
		$(abspath runtime/run_configuration.cpp) $(abspath runtime/linux/file_digest.cpp) -o run_simulation

.PHONY: run-uio
run-uio:
	mkdir -p "$(LINUX_BUILD_DIRECTORY)"
	$(LINUX_CC) $(LINUX_CPPFLAGS) -std=gnu11 -O2 $(CONTROLLER_WARNINGS) \
		-c controllers/c/witness_controller.c -o "$(LINUX_BUILD_DIRECTORY)/run_controller_kernel.o"
	$(LINUX_CXX) $(LINUX_CPPFLAGS) -std=c++17 -O2 -Wall -Wextra -Werror -Wconversion -Wshadow \
		runtime/linux/uio_device.cpp runtime/linux/run_uio.cpp runtime/run_configuration.cpp \
		runtime/linux/power_configuration.cpp runtime/linux/pac1934_device.cpp runtime/linux/power_journal.cpp runtime/linux/file_digest.cpp \
		"$(LINUX_BUILD_DIRECTORY)/run_controller_kernel.o" $(LINUX_LDFLAGS) \
		-pthread -lcrypto -o "$(LINUX_BUILD_DIRECTORY)/run_uio"

# The AMP logger owns configuration and drain; the dedicated hart retains its IRQ.
.PHONY: run-amp-uio
run-amp-uio:
	mkdir -p "$(LINUX_BUILD_DIRECTORY)"
	$(LINUX_CC) $(LINUX_CPPFLAGS) -std=gnu11 -O2 $(CONTROLLER_WARNINGS) \
		-c controllers/c/witness_controller.c -o "$(LINUX_BUILD_DIRECTORY)/amp_controller_kernel.o"
	$(LINUX_CXX) $(LINUX_CPPFLAGS) -std=c++17 -O2 -Wall -Wextra -Werror -Wconversion -Wshadow \
		runtime/linux/amp_uio_device.cpp runtime/linux/amp_uio_configuration.cpp runtime/linux/run_amp_uio.cpp \
		runtime/run_configuration.cpp runtime/linux/power_configuration.cpp runtime/linux/pac1934_device.cpp \
		runtime/linux/power_journal.cpp runtime/linux/file_digest.cpp \
		"$(LINUX_BUILD_DIRECTORY)/amp_controller_kernel.o" $(LINUX_LDFLAGS) \
		-pthread -lcrypto -o "$(LINUX_BUILD_DIRECTORY)/run_amp_uio"

# Build the actual production plugin for the explicitly supplied matching Spike SDK.
include runtime/isa/spike_plugin.mk

RTL_SATURATION_DIRECTORY ?= build/rtl-counter-saturation
RTL_SATURATION_STEPS ?= 4294967304

.PHONY: rtl-counter-saturation
rtl-counter-saturation:
	mkdir -p "$(RTL_SATURATION_DIRECTORY)"
	verilator --cc --exe --build --Wall -Wno-fatal --assert --coverage-line \
		--top-module rtl_counter_saturation -GOVERFLOW_COUNTER_BITS=32 -j 2 --Mdir "$(RTL_SATURATION_DIRECTORY)" \
		-CFLAGS "-std=c++17 -O3 -Wall -Wextra -Werror" -MAKEFLAGS "OPT_FAST=-O3" \
		rtl/control_cycle.sv rtl/deadline_monitor.sv rtl/event_witness.sv \
		rtl/clock_reset_release.sv rtl/event_record_capture.sv rtl/event_record_fifo.sv \
		$(abspath tests/rtl/rtl_counter_saturation.sv) \
		$(abspath tests/native/rtl_counter_saturation.cpp) -o saturation_test
	"$(RTL_SATURATION_DIRECTORY)/saturation_test" "$(RTL_SATURATION_STEPS)" \
		"$(RTL_SATURATION_DIRECTORY)/coverage.dat"

RTL_INVARIANT_DIRECTORY ?= build/rtl-invariants
RTL_INVARIANT_SOURCES := rtl/run_configuration_registers.sv rtl/control_io_registers.sv \
	rtl/axi_lite_clock_bridge.sv rtl/clock_request_bridge.sv rtl/clock_reset_release.sv rtl/fixed_point_math.sv

NATIVE_INVARIANT_DIRECTORY ?= build/native-invariants
NATIVE_INVARIANT_SOURCES := rtl/run_configuration_registers.sv rtl/control_io_registers.sv \
	rtl/control_cycle.sv rtl/deadline_monitor.sv rtl/clock_reset_release.sv tests/formal/runtime_commit_proof.sv

.PHONY: native-runtime-invariants
native-runtime-invariants:
	mkdir -p "$(NATIVE_INVARIANT_DIRECTORY)"
	for module in runtime_commit runtime_enabled runtime_finished runtime_safe runtime_release; do \
		yosys -Q -T -p "read_verilog -formal -sv $(NATIVE_INVARIANT_SOURCES); \
		prep -top $${module}_proof; write_json $(NATIVE_INVARIANT_DIRECTORY)/$${module}.json; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -verify -timeout 30 -show-ports" \
		> "$(NATIVE_INVARIANT_DIRECTORY)/$${module}.log" 2>&1 || exit $$?; \
		yosys -Q -T -p "read_verilog -formal -sv $(NATIVE_INVARIANT_SOURCES); \
		chparam -set NEGATIVE_CONTROL 1 $${module}_proof; prep -top $${module}_proof; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -timeout 30 -show-ports \
		-dump_json $(NATIVE_INVARIANT_DIRECTORY)/$${module}-counterexample.json" \
		> "$(NATIVE_INVARIANT_DIRECTORY)/$${module}-negative.log" 2>&1 || exit $$?; \
		grep -Fq 'SAT proof finished - model found: FAIL!' "$(NATIVE_INVARIANT_DIRECTORY)/$${module}-negative.log" || exit 1; \
	done

.PHONY: rtl-invariants
rtl-invariants:
	mkdir -p "$(RTL_INVARIANT_DIRECTORY)"
	for module in run_configuration_registers control_io_registers axi_lite_clock_bridge fixed_point_math; do \
		yosys -Q -T -p "read_verilog -formal -sv $(RTL_INVARIANT_SOURCES) tests/formal/$${module}_proof.sv; \
		prep -top $${module}_proof; write_json $(RTL_INVARIANT_DIRECTORY)/$${module}.json; \
		flatten; async2sync; opt; check -assert; sat -seq 1 -prove-asserts -verify -timeout 30 -show-ports" \
		> "$(RTL_INVARIANT_DIRECTORY)/$${module}.log" 2>&1 || exit $$?; \
	done
	for period in 64 256 512 16384 32768 100000; do \
		for thermal in 0 1; do \
			yosys -Q -T -p "read_verilog -formal -sv rtl/run_configuration_registers.sv tests/formal/run_configuration_registers_proof.sv; \
			chparam -set PERIOD_TICKS $$period -set THERMAL $$thermal run_configuration_registers_proof; \
			prep -top run_configuration_registers_proof; write_json $(RTL_INVARIANT_DIRECTORY)/configuration-$${period}-$${thermal}.json; \
			flatten; async2sync; opt; check -assert; sat -seq 1 -prove-asserts -verify -timeout 30 -show-ports" \
			> "$(RTL_INVARIANT_DIRECTORY)/configuration-$${period}-$${thermal}.log" 2>&1 || exit $$?; \
		done; \
	done
