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

.PHONY: venv hooks lint typecheck test validate docs security preflight inventory

venv:
	$(PYTHON_BOOTSTRAP) -m venv .venv
	$(VENV)/python -m pip install --require-hashes --no-deps -r requirements-dev.txt

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
RTL_SOURCES := rtl/event_codes_pkg.sv $(filter-out rtl/event_codes_pkg.sv,$(wildcard rtl/*.sv))
.PHONY: axi-simulator
axi-simulator:
	verilator --cc --exe --build --Wall --top-module axi_control_witness -j 2 \
		-GPERIOD_TICKS=32768 -GADDRESS_BITS=8 -GGROUP_ADDRESS_BITS=4 \
		"-GTHERMAL=1'b$(SIMULATION_THERMAL)" --Mdir $(SIMULATION_DIRECTORY) \
		-CFLAGS "-std=c++17 -Wall -Wextra -Werror" \
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
