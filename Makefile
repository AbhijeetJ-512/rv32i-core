# Makefile - rv32i_5stage_core: lint, verification, coverage, mutation, synthesis/timing, performance.
# Everything here is open source: Verilator 5.020+, Yosys 0.33, OpenSTA, Python 3 (matplotlib/pillow only for the diagrams).
# Run `make help`. `make check` is the one-command gate.

PYTHON ?= python3
RTL := rtl/rv32i_alu.sv rtl/rv32i_branch.sv rtl/rv32i_regfile.sv rtl/rv32i_decode.sv rtl/rv32i_lsu.sv rtl/rv32i_hazard.sv rtl/rv32i_core.sv
NRAND ?= 100

.DEFAULT_GOAL := help
.PHONY: help
help:
	@echo "make lint        Verilator -Wall on every parameter combination (BP_MODE, FWD_PRECOMP, RVFI_EN) and the single-cycle core"
	@echo "make selftest    assembler against independent encodings; mutant list consistency"
	@echo "make gen         regenerate tests/asm/t*.S and tests/bench/*.S from tools/gen_*.py"
	@echo "make sims        build both BP_MODE simulators (with the bound assertions)"
	@echo "make test        directed tests, lock-step against the ISS, BP_MODE 0 and 1"
	@echo "make bench       benchmarks (self-checking) + CPI table -> results/cpi.md"
	@echo "make rand        NRAND constrained-random programs, lock-step (NRAND=100)"
	@echo "make cov         merged coverage run -> results/coverage_*.txt"
	@echo "make mutants     73 injected bugs, every one must be caught -> results/mutants.txt (about 15 min)"
	@echo "make formal      riscv-formal bounded checks, 4 variants -> results/formal.txt (needs ../../_toolchain; about 10 min)"
	@echo "make ppa         Yosys + OpenSTA for all configurations -> results/ppa.md"
	@echo "make perf        execution time = cycles x T_min -> results/performance.md"
	@echo "make pnr         OpenROAD place and route of the BP_MODE=1 FWD_PRECOMP=1 core at PNR_PERIODS (nine periods from 6.0 to 10.0 ns) -> results/pnr/, results/pnr.md (needs make ppa first)"
	@echo "make diagrams    redraw docs/diagrams (needs matplotlib, pillow)"
	@echo "make check       lint selftest test bench rand cov"
	@echo "make clean       remove build/"

.PHONY: lint
lint:
	@set -e; for bp in 0 1; do for f in 0 1; do for r in 0 1; do \
	  verilator --lint-only -Wall --top-module rv32i_core -GBP_MODE=$$bp -GFWD_PRECOMP=$$f -GRVFI_EN=$$r $(RTL) -Irtl; \
	done; done; done
	@verilator --lint-only -Wall --top-module rv32i_core_1cyc rtl/rv32i_alu.sv rtl/rv32i_branch.sv rtl/rv32i_regfile.sv rtl/rv32i_decode.sv rtl/rv32i_lsu.sv rtl/rv32i_core_1cyc.sv -Irtl
	@echo "[LINT] clean: 8 pipelined configurations + single-cycle core"

.PHONY: selftest
selftest:
	@$(PYTHON) tools/selftest_asm.py
	@$(PYTHON) scripts/mutants.py --selftest

.PHONY: gen
gen:
	@$(PYTHON) tools/gen_directed.py
	@$(PYTHON) tools/gen_bench.py

.PHONY: sims
sims:
	@./scripts/build_sim.sh build/sim_bp0 0
	@./scripts/build_sim.sh build/sim_bp1 1

.PHONY: test
test: sims
	@$(PYTHON) tools/run_tests.py --report results/directed.txt

.PHONY: bench
bench: sims
	@mkdir -p build/sc_out
	@./scripts/build_sim.sh build/sim_1cyc 0 +define+SINGLE_CYCLE
	@$(PYTHON) scripts/cpi_report.py
	@$(PYTHON) -c "import sys,glob; sys.path.insert(0,'tools'); import run_tests; exe={0:'build/sim_1cyc/Vtb_core'}; [run_tests.run_one(f,[0],exe,'build/sc_out') for f in sorted(glob.glob('tests/bench/*.S'))]"

.PHONY: rand
rand: sims
	@$(PYTHON) tools/rvgen.py --count $(NRAND) --first-seed 1 --out-dir build/rand
	@$(PYTHON) tools/run_tests.py --tests build/rand --out build/rand_out --report results/random.txt

.PHONY: cov
cov:
	@$(PYTHON) scripts/cov_run.py

.PHONY: mutants
mutants:
	@$(PYTHON) scripts/mutants.py --jobs 4 --rand 40 --report results/mutants.txt

.PHONY: ppa
ppa:
	@mkdir -p build
	@$(PYTHON) scripts/prune_lib.py sky130hd/sky130hd_tt.lib build/sky130hd_synth.lib --drop sky130_fd_sc_hd__lpflow_ --drop sky130_fd_sc_hd__probe
	@$(PYTHON) scripts/fmax.py

.PHONY: perf
perf:
	@$(PYTHON) scripts/perf_report.py

PNR_PERIODS ?= 6.0 7.0 8.0 8.4 8.6 8.8 9.0 9.5 10.0
.PHONY: pnr
pnr:   # place and route at each period (4 at a time, two threads each; about 40 minutes), then read every run back and write results/pnr.md
	@rm -rf results/pnr; mkdir -p results/pnr build
	@printf '%s\n' $(PNR_PERIODS) | xargs -P 4 -I{} sh -c 'PNR_GRT_ANTENNA=0 pnr/run_pnr.sh {} bp1_fwd1 > build/pnr_run_{}.log 2>&1' || true
	@$(PYTHON) pnr/pnr_report.py > /dev/null && echo "[PNR] all runs passed their checks: results/pnr.md" || { echo "[PNR] a run failed its checks, see results/pnr.md"; exit 1; }

.PHONY: diagrams
diagrams:
	@$(PYTHON) docs/diagrams/make_diagrams.py

.PHONY: formal
formal:   # riscv-formal bounded checks, 4 variants (needs ../../_toolchain/{riscv-formal,sbyroot,sbyvenv}); also: formal/run_as_found.sh
	@bash formal/run_formal.sh

.PHONY: check
check: lint selftest test bench rand cov
	@echo "[CHECK] all gates passed"

.PHONY: clean
clean:
	rm -rf build
