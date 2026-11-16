# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — local gate entry points

PYTHON_BOOTSTRAP ?= python3.15
VENV := .venv/bin
PREFLIGHT := $(VENV)/python tools/preflight.py
# Verilator build parallelism follows the executing host: the processors make may run on.
VERILATOR_JOBS ?= $(shell nproc)
# Hang guards in seconds on the reference profile; a host that declares a timeout scale passes
# its scaled values, as the tests do.
SAT_TIMEOUT ?= 30

FUZZ_DIRECTORY ?= build/fuzz
FUZZ_CC ?= clang-18
FUZZ_CXX ?= clang++-18
FUZZ_GCC_INSTALL ?= /usr/lib/gcc/x86_64-linux-gnu/13
FUZZ_SECONDS ?= 120
FUZZ_INPUT_TIMEOUT ?= 10
FUZZ_SOURCE ?= controllers/c/witness_controller.c

.PHONY: controller-fuzz-build controller-fuzz

controller-fuzz-build:
	test "$$( $(FUZZ_CC) -dumpversion )" = "18.1.3"
	test "$$( $(FUZZ_CXX) -dumpversion )" = "18.1.3"
	mkdir -p "$(FUZZ_DIRECTORY)"
	$(FUZZ_CC) -std=gnu11 -O1 -g -fno-omit-frame-pointer $(CONTROLLER_WARNINGS) -fsanitize=fuzzer-no-link,address,undefined -fno-sanitize-recover=all -Icontrollers/c -c "$(FUZZ_SOURCE)" -o "$(FUZZ_DIRECTORY)/controller.o"
	$(FUZZ_CXX) --gcc-install-dir="$(FUZZ_GCC_INSTALL)" -std=c++20 -O1 -g -UNDEBUG -Wall -Wextra -Werror -Wconversion -Wshadow -fno-omit-frame-pointer -fsanitize=fuzzer,address,undefined -fno-sanitize-recover=all -Icontrollers/c fuzz/controller_fuzz.cpp "$(FUZZ_DIRECTORY)/controller.o" -o "$(FUZZ_DIRECTORY)/controller_fuzz"

controller-fuzz: controller-fuzz-build
	mkdir -p "$(FUZZ_DIRECTORY)/corpus" "$(FUZZ_DIRECTORY)/crashes"
	cp fuzz/corpus/*.bin "$(FUZZ_DIRECTORY)/corpus/"
	ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 "$(FUZZ_DIRECTORY)/controller_fuzz" -max_total_time=$(FUZZ_SECONDS) -max_len=589 -timeout=$(FUZZ_INPUT_TIMEOUT) -rss_limit_mb=512 -artifact_prefix="$(FUZZ_DIRECTORY)/crashes/" "$(FUZZ_DIRECTORY)/corpus" > "$(FUZZ_DIRECTORY)/run.log" 2>&1 || { result=$$?; cat "$(FUZZ_DIRECTORY)/run.log"; exit "$$result"; }
	cat "$(FUZZ_DIRECTORY)/run.log"

.PHONY: venv hooks lint typecheck test validate docs security preflight inventory python-wheelhouse python-package-tests

venv:
	$(PYTHON_BOOTSTRAP) -m venv .venv
	$(VENV)/python -m pip install --require-hashes --no-deps -r requirements-build.txt
	PYYAML_FORCE_LIBYAML=0 $(VENV)/python -m pip install --require-hashes --no-deps --no-build-isolation -r requirements-dev.txt
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
	RUSTDOCFLAGS='-D warnings -D rustdoc::broken_intra_doc_links' cargo doc --offline --locked --no-deps --manifest-path analysis/rust/Cargo.toml --target-dir build/native-api/rust
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
	$(VENV)/pip-audit --require-hashes --disable-pip -r requirements-runtime.txt
	test "$$(cargo-audit --version)" = "cargo-audit 0.23.0"
	cargo audit --file analysis/rust/Cargo.lock
	cargo audit --file controllers/rust/Cargo.lock
	cargo audit --file runtime/bare_metal/rust_kernel/Cargo.lock

inventory:
	$(VENV)/python tools/generate_capability_inventory.py --write

preflight:
	$(PREFLIGHT)

# The native controller kernels have no third-party dependencies.
CONTROLLER_WARNINGS := -Wall -Wextra -Werror -Wconversion -Wshadow -Wstrict-prototypes -Wmissing-prototypes
CONTROLLER_CRATE := controllers/rust/Cargo.toml

ANALYSIS_CRATE := analysis/rust/Cargo.toml
ANALYSIS_WORKERS := analysis/rust/checker_worker

.PHONY: analysis-build analysis-tests

analysis-build:
	$(VENV)/python tools/check_analysis_package.py
	$(VENV)/mypy --strict $(ANALYSIS_WORKERS)
	cargo fmt --check --manifest-path $(ANALYSIS_CRATE)
	cargo clippy --offline --locked --all-targets --manifest-path $(ANALYSIS_CRATE) -- -D warnings
	cargo build --offline --locked --manifest-path $(ANALYSIS_CRATE)
	RUSTDOCFLAGS='-D warnings -D rustdoc::broken_intra_doc_links' cargo doc --no-deps --offline --locked --manifest-path $(ANALYSIS_CRATE)

analysis-tests:
	cargo test --offline --locked --manifest-path $(ANALYSIS_CRATE)

NATIVE_SBOM_DIRECTORY ?= build/native-analysis-sbom

.PHONY: native-sbom

native-sbom:
	test "$$(cargo cyclonedx --version)" = "cargo-cyclonedx-cyclonedx 0.5.10"
	$(VENV)/python tools/check_analysis_package.py
	$(VENV)/python -c 'from pathlib import Path; import sys; Path(sys.argv[1]).mkdir(parents=True)' "$(NATIVE_SBOM_DIRECTORY)"
	$(VENV)/python -c 'import shutil, sys; shutil.copytree(sys.argv[1], sys.argv[2], ignore=shutil.ignore_patterns("target", "__pycache__"))' analysis/rust "$(NATIVE_SBOM_DIRECTORY)/crate"
	cargo metadata --offline --locked --format-version 1 --manifest-path "$(NATIVE_SBOM_DIRECTORY)/crate/Cargo.toml" > "$(NATIVE_SBOM_DIRECTORY)/cargo-metadata.json"
	CARGO_NET_OFFLINE=true cargo cyclonedx --manifest-path "$(NATIVE_SBOM_DIRECTORY)/crate/Cargo.toml" --all --target all --spec-version 1.5 --format json --override-filename native-analysis-sbom
	$(VENV)/python tools/check_native_analysis_sbom.py "$(NATIVE_SBOM_DIRECTORY)/crate/native-analysis-sbom.json"
	mv "$(NATIVE_SBOM_DIRECTORY)/crate/native-analysis-sbom.json" "$(NATIVE_SBOM_DIRECTORY)/native-analysis-sbom.cdx.json"

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
	$(MAKE) controller-coverage
	$(MAKE) controller-rust-coverage

# Every line and branch of the C controller and its CLI must run. GCC counters
# use -O0 without the UB sanitizer: its boolean-load check adds a branch that
# only undefined behaviour can take. The sanitized builds above keep it.
CONTROLLER_COVERAGE_DIRECTORY ?= build/c-controller-coverage

.PHONY: controller-coverage
controller-coverage:
	rm -rf "$(CONTROLLER_COVERAGE_DIRECTORY)"
	mkdir -p "$(CONTROLLER_COVERAGE_DIRECTORY)/reports"
	gcc -std=gnu11 -O0 $(CONTROLLER_WARNINGS) --coverage -fprofile-abs-path -Icontrollers/c \
		controllers/c/witness_controller.c tests/native/controller_api_test.c \
		-o "$(CONTROLLER_COVERAGE_DIRECTORY)/controller_api_test"
	"$(CONTROLLER_COVERAGE_DIRECTORY)/controller_api_test"
	WITNESS_C_COVERAGE_DIRECTORY="$(abspath $(CONTROLLER_COVERAGE_DIRECTORY))" $(VENV)/pytest \
		-q -p no:cacheprovider --no-cov tests/test_controller_inputs.py tests/test_controller_parity.py
	for note in "$(CONTROLLER_COVERAGE_DIRECTORY)"/*.gcno; do \
		gcov --json-format --stdout --branch-probabilities "$$note" \
			> "$(CONTROLLER_COVERAGE_DIRECTORY)/reports/$$(basename "$$note" .gcno).json" || exit $$?; \
	done
	$(VENV)/python tools/c_coverage_gate.py --sources controllers/c \
		"$(CONTROLLER_COVERAGE_DIRECTORY)"/reports/*.json

# Every line and branch of the Rust controller crate must run too: its own tests, the
# streaming program under the shared parity and refusal tests, and one benchmark pass, all
# with the LLVM branch instrumentation of the native analysis gate.
CONTROLLER_RUST_COVERAGE_DIRECTORY ?= build/rust-controller-coverage
LLVM_TOOLS = $(shell rustc --print sysroot)/lib/rustlib/$(shell rustc -vV | sed -n 's/^host: //p')/bin

.PHONY: controller-rust-coverage
controller-rust-coverage:
	rm -rf "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)"
	mkdir -p "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/profiles"
	RUSTC_BOOTSTRAP=1 RUSTFLAGS="-C instrument-coverage -Z coverage-options=branch" \
		LLVM_PROFILE_FILE="$(abspath $(CONTROLLER_RUST_COVERAGE_DIRECTORY))/profiles/cargo-%p-%m.profraw" \
		cargo test --offline --locked --manifest-path $(CONTROLLER_CRATE) --message-format=json \
		--target-dir "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/target" > "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/cargo-test.json"
	jq -R -r 'fromjson? | select(.reason == "compiler-artifact" and .executable != null) | .executable' \
		"$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/cargo-test.json" | sort -u > "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/executables.txt"
	jq -R -r 'fromjson? | select(.reason == "compiler-artifact" and .executable != null and .target.name == "controller_benchmark" and (.profile.test | not)) | .executable' \
		"$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/cargo-test.json" > "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/benchmark.txt"
	test "$$(wc -l < "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/benchmark.txt")" = 1
	LLVM_PROFILE_FILE="$(abspath $(CONTROLLER_RUST_COVERAGE_DIRECTORY))/profiles/benchmark-%p-%m.profraw" \
		"$$(cat "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/benchmark.txt")" > /dev/null
	WITNESS_RUST_COVERAGE_DIRECTORY="$(abspath $(CONTROLLER_RUST_COVERAGE_DIRECTORY))" \
		LLVM_PROFILE_FILE="$(abspath $(CONTROLLER_RUST_COVERAGE_DIRECTORY))/profiles/python-%p-%m.profraw" \
		$(VENV)/pytest -q -p no:cacheprovider --no-cov tests/test_controller_inputs.py tests/test_controller_parity.py
	"$(LLVM_TOOLS)/llvm-profdata" merge -sparse "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)"/profiles/*.profraw \
		-o "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/merged.profdata"
	executables=$$(sed -e '1!s/^/-object=/' "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/executables.txt"); \
		"$(LLVM_TOOLS)/llvm-cov" export -summary-only $$executables \
		-instr-profile="$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/merged.profdata" "$(abspath controllers/rust/src)" \
		> "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/summary.json"
	$(VENV)/python tools/rust_coverage_gate.py --crate controllers/rust \
		--summary "$(CONTROLLER_RUST_COVERAGE_DIRECTORY)/summary.json"

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
	verilator --cc --exe --build --Wall --top-module axi_control_witness -j $(VERILATOR_JOBS) \
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
	verilator --cc --exe --build --Wall --top-module axi_control_witness -j $(VERILATOR_JOBS) \
		-GPERIOD_TICKS=32768 -GADDRESS_BITS=$(SIMULATION_FIFO_ADDRESS_BITS) -GGROUP_ADDRESS_BITS=4 \
		"-GTHERMAL=1'b$(SIMULATION_THERMAL)" --Mdir $(RUN_SIMULATION_DIRECTORY) \
		-CFLAGS "$(RUN_SIMULATION_CFLAGS)" \
		-LDFLAGS "$(abspath build/run_controller_kernel.o) -lcrypto $(RUN_SIMULATION_LDFLAGS)" \
		$(RTL_SOURCES) $(abspath runtime/rtl/run_simulation.cpp) \
		$(abspath runtime/run_configuration.cpp) $(abspath runtime/linux/file_digest.cpp) -o run_simulation

# Closed-loop benchmark data: the production plant witness at the minimum declared period, with
# production FIFO depth, driven by a declared service stimulus that computes with the C kernel.
CLOSED_LOOP_DIRECTORY ?= build/closed_loop
CLOSED_LOOP_CFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Werror
.PHONY: closed-loop-harness
closed-loop-harness:
	mkdir -p "$(CLOSED_LOOP_DIRECTORY)"
	gcc -std=gnu11 -O2 $(CONTROLLER_WARNINGS) -c controllers/c/witness_controller.c \
		-o "$(CLOSED_LOOP_DIRECTORY)/witness_controller.o"
	verilator --cc --exe --build --Wall --top-module control_plant_witness -j $(VERILATOR_JOBS) \
		-GPERIOD_TICKS=5000 -O3 --x-assign 0 --x-initial 0 --Mdir "$(CLOSED_LOOP_DIRECTORY)" \
		-MAKEFLAGS "OPT_FAST=-O2 OPT_SLOW=-O2 OPT_GLOBAL=-O2" -CFLAGS "$(CLOSED_LOOP_CFLAGS)" \
		-LDFLAGS "$(abspath $(CLOSED_LOOP_DIRECTORY)/witness_controller.o)" \
		$(RTL_SOURCES) $(abspath benchmarks/closed_loop_harness.cpp) -o closed_loop_harness

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
	verilator --cc --exe --build --Wall --assert --coverage-line \
		--top-module rtl_counter_saturation -GOVERFLOW_COUNTER_BITS=32 -j $(VERILATOR_JOBS) --Mdir "$(RTL_SATURATION_DIRECTORY)" \
		-CFLAGS "-std=c++17 -O3 -Wall -Wextra -Werror" -MAKEFLAGS "OPT_FAST=-O3" \
		rtl/control_cycle.sv rtl/deadline_monitor.sv rtl/event_witness.sv \
		rtl/clock_reset_release.sv rtl/event_record_capture.sv rtl/event_record_fifo.sv \
		$(abspath tests/rtl/rtl_counter_saturation.sv) \
		$(abspath tests/native/rtl_counter_saturation.cpp) -o saturation_test
	"$(RTL_SATURATION_DIRECTORY)/saturation_test" "$(RTL_SATURATION_STEPS)" \
		"$(RTL_SATURATION_DIRECTORY)/coverage.dat"

RTL_INVARIANT_DIRECTORY ?= build/rtl-invariants
RTL_INVARIANT_SOURCES := rtl/run_configuration_registers.sv rtl/control_io_registers.sv \
	rtl/axi_lite_clock_bridge.sv rtl/clock_request_bridge.sv rtl/clock_reset_release.sv rtl/split_multiplier.sv \
	rtl/fixed_point_math.sv

NATIVE_INVARIANT_DIRECTORY ?= build/native-invariants
NATIVE_INVARIANT_SOURCES := rtl/run_configuration_registers.sv rtl/control_io_registers.sv \
	rtl/control_cycle.sv rtl/deadline_monitor.sv rtl/clock_reset_release.sv tests/formal/runtime_commit_proof.sv

.PHONY: native-runtime-invariants
native-runtime-invariants:
	mkdir -p "$(NATIVE_INVARIANT_DIRECTORY)"
	for module in runtime_commit runtime_enabled runtime_finished runtime_safe runtime_release; do \
		yosys -Q -T -p "read_verilog -formal -sv $(NATIVE_INVARIANT_SOURCES); \
		prep -top $${module}_proof; write_json $(NATIVE_INVARIANT_DIRECTORY)/$${module}.json; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -verify -timeout $(SAT_TIMEOUT) -show-ports" \
		> "$(NATIVE_INVARIANT_DIRECTORY)/$${module}.log" 2>&1 || exit $$?; \
		yosys -Q -T -p "read_verilog -formal -sv $(NATIVE_INVARIANT_SOURCES); \
		chparam -set NEGATIVE_CONTROL 1 $${module}_proof; prep -top $${module}_proof; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -timeout $(SAT_TIMEOUT) -show-ports \
		-dump_json $(NATIVE_INVARIANT_DIRECTORY)/$${module}-counterexample.json" \
		> "$(NATIVE_INVARIANT_DIRECTORY)/$${module}-negative.log" 2>&1 || exit $$?; \
		grep -Fq 'SAT proof finished - model found: FAIL!' "$(NATIVE_INVARIANT_DIRECTORY)/$${module}-negative.log" || exit 1; \
	done

PLANT_TIMING_DIRECTORY ?= build/plant-timing-invariants
PLANT_TIMING_SOURCES := rtl/control_cycle.sv rtl/deadline_monitor.sv rtl/run_configuration_registers.sv \
	rtl/split_multiplier.sv tests/formal/plant_timing_proof.sv tests/formal/split_multiplier_proof.sv

# The invariants behind the one-edge plant and reference products; each negative
# control must yield a counterexample.
.PHONY: plant-timing-invariants
plant-timing-invariants:
	mkdir -p "$(PLANT_TIMING_DIRECTORY)"
	for module in plant_spacing plant_actuator plant_configuration split_multiplier; do \
		yosys -Q -T -p "read_verilog -formal -sv $(PLANT_TIMING_SOURCES); \
		prep -top $${module}_proof; write_json $(PLANT_TIMING_DIRECTORY)/$${module}.json; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -verify -timeout $(SAT_TIMEOUT) -show-ports" \
		> "$(PLANT_TIMING_DIRECTORY)/$${module}.log" 2>&1 || exit $$?; \
		yosys -Q -T -p "read_verilog -formal -sv $(PLANT_TIMING_SOURCES); \
		chparam -set NEGATIVE_CONTROL 1 $${module}_proof; prep -top $${module}_proof; \
		flatten; async2sync; opt; check -assert; sat -seq 4 -prove-asserts -timeout $(SAT_TIMEOUT) -show-ports \
		-dump_json $(PLANT_TIMING_DIRECTORY)/$${module}-counterexample.json" \
		> "$(PLANT_TIMING_DIRECTORY)/$${module}-negative.log" 2>&1 || exit $$?; \
		grep -Fq 'SAT proof finished - model found: FAIL!' "$(PLANT_TIMING_DIRECTORY)/$${module}-negative.log" || exit 1; \
	done

.PHONY: rtl-invariants
rtl-invariants:
	mkdir -p "$(RTL_INVARIANT_DIRECTORY)"
	for module in run_configuration_registers control_io_registers axi_lite_clock_bridge fixed_point_math; do \
		yosys -Q -T -p "read_verilog -formal -sv $(RTL_INVARIANT_SOURCES) tests/formal/$${module}_proof.sv; \
		prep -top $${module}_proof; write_json $(RTL_INVARIANT_DIRECTORY)/$${module}.json; \
		flatten; async2sync; opt; check -assert; sat -seq 1 -prove-asserts -verify -timeout $(SAT_TIMEOUT) -show-ports" \
		> "$(RTL_INVARIANT_DIRECTORY)/$${module}.log" 2>&1 || exit $$?; \
	done
	for period in 64 256 512 16384 32768 100000; do \
		for thermal in 0 1; do \
			yosys -Q -T -p "read_verilog -formal -sv rtl/run_configuration_registers.sv tests/formal/run_configuration_registers_proof.sv; \
			chparam -set PERIOD_TICKS $$period -set THERMAL $$thermal run_configuration_registers_proof; \
			prep -top run_configuration_registers_proof; write_json $(RTL_INVARIANT_DIRECTORY)/configuration-$${period}-$${thermal}.json; \
			flatten; async2sync; opt; check -assert; sat -seq 1 -prove-asserts -verify -timeout $(SAT_TIMEOUT) -show-ports" \
			> "$(RTL_INVARIANT_DIRECTORY)/configuration-$${period}-$${thermal}.log" 2>&1 || exit $$?; \
		done; \
	done
