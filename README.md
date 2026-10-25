# rv32i_5stage_core

A 5-stage, in-order RV32I core in SystemVerilog. I built it so that anything I say about it can be checked. Every instruction it
retires is compared against an instruction-set simulator I wrote separately from the RTL, the pipeline-control rules are written
down as bound assertions, and I tested the test setup itself by putting bugs into the RTL on purpose and making sure something
catches each one. The clock periods and cycle counts behind the performance numbers come from tool reports in `results/`.

It replaces my earlier `RISC-V` repository. That design didn't implement all of RV32I and its testbench didn't check any results,
so I started again and nothing from it is reused here.

None of the numbers in the Results section are typed by hand. `scripts/readme_results.py` copies them in from `results/`, and
anything I haven't measured says NOT YET MEASURED, with the command that would measure it. Values in the text such as the
2.0 ns / 1.0 ns memory budget and the ideal memories are design choices and assumptions, not results.

## What it is

| | |
|---|---|
| ISA | The RV32I base set: LUI, AUIPC, JAL, JALR, 6 branches, 5 loads, 3 stores, 9 ALU-immediate and 10 register-register instructions, FENCE (as a no-op), ECALL and EBREAK |
| Pipeline | IF, ID, EX, MEM, WB; in order, one instruction per cycle |
| Hazards | Full forwarding from MEM and WB into EX, a register file that passes a same-cycle write straight through, and a one-cycle stall for load-use |
| Control flow | With `BP_MODE=0` every jump and branch resolves in EX (2 bubbles when taken). With `BP_MODE=1`, JAL and backward conditional branches redirect from ID (1 bubble, static backward-taken / forward-not-taken) and EX repairs a misprediction |
| Memory interface | Separate instruction and data ports, combinational read, byte-strobed write and no wait states. The memories sit outside the core |
| Traps | There are no CSRs and no trap vectors. ECALL, EBREAK, an illegal encoding, a misaligned load or store, or a taken branch or jump to a target that isn't 4-byte aligned stops the core (`halted`), squashes the younger instructions and retires with a halt/trap flag |
| Observability | `RVFI_EN=1` adds a retirement-trace port, a subset of the RISC-V Formal Interface. `RVFI_EN=0` removes it, and that is the version I synthesise |
| Baseline | `rv32i_core_1cyc.sv` puts the same decoder, ALU, register file and load/store unit into a single-cycle core, so the pipeline has something to be measured against |

`rv32i_core` takes four parameters: `RESET_PC`, `BP_MODE` (0 or 1), `FWD_PRECOMP` and `RVFI_EN`. With `FWD_PRECOMP=1` the
forwarding selects are compared in ID and registered, with 0 they are compared in EX. Both settings pass every test; they only
differ in clock period (see Results).

## Architecture

![architecture](docs/diagrams/rv32i_architecture.png)

- **IF**: `pc_f` drives `imem_addr`. The next PC is chosen in this order: `halted`, an EX redirect, a load-use stall (hold), an
  ID redirect, and otherwise `pc+4`.
- **ID**: `rv32i_decode` works out the opcode, immediates, control signals and the illegal and halt cases. `rv32i_regfile` is
  31 x 32 with two read ports and the write-first bypass. `rv32i_hazard` detects load-use and, with `FWD_PRECOMP=1`, also
  computes the forwarding selects for the next cycle.
- **EX**: the forwarding muxes, `rv32i_alu` (10 operations), `rv32i_branch` (6 conditions), the branch and jump targets, and the
  redirect and misprediction logic.
- **MEM**: `rv32i_lsu` makes the byte strobes and shifts store data into its lane, picks the lane for loads and sign- or
  zero-extends them, and flags misaligned accesses.
- **WB**: writes the register and the RVFI record.

`docs/diagrams/rv32i_flowchart.png` follows one instruction through the stall, redirect, trap and retire paths, and
`docs/diagrams/rv32i_pipeline_timing.png` goes cycle by cycle through forwarding, a load-use stall and a taken-branch flush. The
editable draw.io sources (`.drawio`) are next to the images. The full design document is `docs/rv32i_design_document.md`, also
as `.docx` and `.pdf`.

## How it's verified

There are several layers, and each one is there to catch what the others could miss.

1. **Lock-step against an ISS.** `tools/rviss.py` is written from the instruction tables and shares no code with the RTL decoder.
   For every retired instruction the RVFI record (pc, instruction, next pc, source and destination registers and their values,
   memory address, byte masks, load and store data, halt/trap) has to match the ISS record, and the final memory images have to be
   identical.
2. **A third, independent reference.** The directed tests (`tools/gen_directed.py`) carry expected values computed with plain
   Python arithmetic in the generator, and a failing test reports its check number in `gp`. The benchmarks (`tools/gen_bench.py`)
   end by comparing their result with Python, for example `zlib.crc32`, the sieve count or a checksum of the sorted array. The
   assembler (`tools/rvasm.py`) is checked against 31 encodings worked out independently, including the words an external
   assembler produced for my earlier repository.
3. **Constrained-random programs** (`tools/rvgen.py`). The instruction classes are weighted, and a dependency bias makes RAW
   distances of 1..3 and load-use pairs common. The generator also uses edge-value operands, forward branches over wrong-path
   filler, counted loops, loop counters kept in memory (so a load sits right in front of a backward branch), JALR through computed
   addresses, and now and then a program that ends in a trap.
4. **Bound assertions** (`verif/rv32i_checker.sv`): 48 labelled assertions and a set of named cover points. They check the
   forwarding selects against the rule in both directions (set whenever the rule says so, and only then), that the load-use stall
   is exact and a consumer never sits in EX behind the load that feeds it, the flush and redirect behaviour in both BP modes, trap
   squashing and the sticky halt, that an invalid instruction has no side effect, that store strobes match the address lane, that
   the RVFI output makes sense, and that a misaligned control-transfer target traps and writes nothing.
5. **Checking the checks** (`scripts/mutants.py`, `verif/mutants.py`). I wrote 73 deliberate one-line bugs into the RTL. Each one
   is built twice, with and without the assertions, and run against the directed tests plus 40 random programs. The harness fails
   if no layer catches a mutant, if an assertion that a mutant is meant to trip stays quiet, or if any assertion is never seen to
   fire.
6. **Coverage** (`scripts/cov_run.py`): the named cover points plus Verilator line coverage, merged over the runs of both BP
   modes. The gate fails on a cover bin with no hits, on an uncovered `rtl/` line that has no written reason, and on an exclusion
   that turns out to be covered.
7. **Bounded formal checks** (`formal/`, `make formal`). The RVFI port goes through riscv-formal with SymbiYosys and z3 for all
   four `BP_MODE` x `FWD_PRECOMP` variants: one check per RV32I instruction, plus the register, PC, uniqueness, causality and
   illegal-instruction checks. This found a real bug that every layer above had missed: a taken branch or jump to a misaligned
   target didn't trap. I fixed it and kept the evidence from before the fix (`results/formal_as_found.txt`). These are bounded
   checks, so they are not an unbounded proof.

## How to run

```bash
make help       # every target
make check      # lint, self-tests, directed tests, benchmarks + CPI, 200 random programs, coverage
make mutants    # the 73-mutant campaign (about 15 minutes)
make formal     # riscv-formal bounded checks, four variants (needs SymbiYosys, z3 and riscv-formal under ../../_toolchain)
make ppa perf   # Yosys + OpenSTA for every configuration, then execution time = cycles x T_min
```

You need Verilator 5.020 or newer, Yosys 0.33, OpenSTA (`sta`), Python 3 and GNU make; matplotlib and pillow are only for
`make diagrams`. The Sky130 HD liberty file is in `sky130hd/`. There's no need for a RISC-V toolchain, since the assembler and
the ISS are in `tools/`.

```
rtl/        rv32i_defs.vh alu branch regfile decode lsu hazard core core_1cyc
tb/         tb_core.sv  (memory, trace writer, cycle accounting)
verif/      rv32i_checker.sv checker_binds.sv mutants.py cov_exclusions.txt sim_main.cpp
tools/      rvasm.py rviss.py rvgen.py compare_trace.py run_tests.py gen_directed.py gen_bench.py selftest_asm.py
tests/      asm/ (28 directed, generated)  bench/ (7 benchmarks, generated)
formal/     wrapper.sv checks.cfg.in run_formal.sh summarize.py run_as_found.sh as_found/ README.md
scripts/    build_sim.sh mutants.py cov_run.py cov_check.py ppa.py fmax.py cpi_report.py perf_report.py abc_speed.* synth_template.ys ...
constraints/rv32i.sdc    results/    docs/ (design document, diagrams)
```

## Results

<!-- BEGIN RESULTS (generated by scripts/readme_results.py from results/; do not edit by hand) -->

### Directed tests (lock-step against the ISS, both BP modes)

From `results/directed.txt` (`make test`).

```text
28/28 tests passed (BP_MODE 0,1)
```

### Constrained-random programs

`results/random.txt` (`make rand NRAND=200`): `200/200 tests passed (BP_MODE 0,1)`; 161597 instructions retired and compared in total.

### Coverage (merged: directed + benchmarks + random, both BP modes)

From `results/coverage_summary.txt` (`make cov`).

```text
source               : build/cov/merged.dat
named cover bins     : 143 total, 143 hit, 0 zero
rtl/ line blocks    : 117 total, 115 covered, 2 excluded, 0 uncovered
rtl/ files with no line records : rv32i_core_1cyc.sv (procedural blocks only are recorded; these are covered by toggle coverage, the cover bins and the assertions, not by the line gate)
rtl/ branches       : 72 total, 59 hit (reported, not gated)
rtl/ toggle bits    : 3853 total, 3773 toggled, 80 unhit (reported, not gated)
```

### Mutation run (checks of the checks)

From `results/mutants.txt` (`make mutants`).

```text
mutants: 73, caught 73
test set per mutant: 28 directed + 40 random programs, lock-step vs ISS
caught ONLY by an assertion (the other layers missed them): M07, M29, M33, M49, M50, M53, M58, M59, M60, M61, M63, M72, M73
assertions defined: 48; fired in at least one mutant run: 48
assertions with no mutant bound: none
assertions that fired in no run: none
PROBLEMS: none
```

### Formal: riscv-formal bounded checks (current core)

From `results/formal.txt` (`make formal`).

```text
riscv-formal bounded model checks of rv32i_core (RVFI_EN=1), SymbiYosys + z3, Yosys 0.33, isa rv32i, one retirement channel
instruction memory and load data are free inputs; reset is asserted in the first cycle; RISCV_FORMAL_ALIGNED_MEM
BOUNDED checks (the depth is the number of cycles from reset explored), not unbounded proofs. depth per check family: insn 12, reg 14, pc_fwd 14, pc_bwd 14, unique 14, causal 14, ill 12

BP_MODE=0 FWD_PRECOMP=0 : 43 checks, 43 PASS, 0 not PASS
    causal 1/1, ill 1/1, insn 37/37, pc_bwd 1/1, pc_fwd 1/1, reg 1/1, unique 1/1
BP_MODE=0 FWD_PRECOMP=1 : 43 checks, 43 PASS, 0 not PASS
    causal 1/1, ill 1/1, insn 37/37, pc_bwd 1/1, pc_fwd 1/1, reg 1/1, unique 1/1
BP_MODE=1 FWD_PRECOMP=0 : 43 checks, 43 PASS, 0 not PASS
    causal 1/1, ill 1/1, insn 37/37, pc_bwd 1/1, pc_fwd 1/1, reg 1/1, unique 1/1
BP_MODE=1 FWD_PRECOMP=1 : 43 checks, 43 PASS, 0 not PASS
    causal 1/1, ill 1/1, insn 37/37, pc_bwd 1/1, pc_fwd 1/1, reg 1/1, unique 1/1

scope: 37 per-instruction checks (every RV32I instruction except FENCE / ECALL / EBREAK / CSR), plus reg (register x5 only), pc_fwd and pc_bwd (parameter 5),
  unique, causal (parameter 5) and ill (an all-zero word must trap). NOT RUN: liveness / hang, the memory-bus checks, CSR checks (no CSRs),
  and any unbounded (k-induction / PDR) proof; FENCE, ECALL and EBREAK are not covered by an instruction check.

all variants: 172 of 172 checks PASS
```

### Formal: the same checks on the core before the misaligned-target fix

From `results/formal_as_found.txt` (`formal/run_as_found.sh`).

```text
riscv-formal on the core before the misaligned-target fix (formal/as_found/rv32i_core.sv), BP_MODE=0 FWD_PRECOMP=1
BP_MODE=0 FWD_PRECOMP=1 : 43 checks, 35 PASS, 8 FAIL
failing checks:
  insn_beq_ch0  (FAIL 0 15)
  insn_bge_ch0  (FAIL 0 24)
  insn_bgeu_ch0  (FAIL 0 23)
  insn_blt_ch0  (FAIL 0 26)
  insn_bltu_ch0  (FAIL 0 24)
  insn_bne_ch0  (FAIL 0 21)
  insn_jal_ch0  (FAIL 0 21)
  insn_jalr_ch0  (FAIL 0 17)
failing assertion: rvfi_insn_check.sv line 196, assert(spec_trap == trap): the specification says the transfer traps, the core did not
```

### CPI and bubble sources

From `results/cpi.md` (`make bench`).

# CPI by benchmark and branch mode (measured, Verilator RTL simulation, ideal 1-cycle memories)

| benchmark | instructions | BP_MODE 0 cycles | CPI | load-use stalls | EX redirects | BP_MODE 1 cycles | CPI | ID redirects | EX redirects | overlap | CPI change |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| b_bubblesort | 13209 | 20123 | 1.523 | 1128 | 2891 | 17914 | 1.356 | 2353 | 634 | 48 | -11.0 % |
| b_crc32 | 9684 | 14476 | 1.495 | 192 | 2298 | 13325 | 1.376 | 1730 | 954 | 193 | -8.0 % |
| b_fib | 522 | 710 | 1.360 | 0 | 92 | 621 | 1.190 | 92 | 2 | 1 | -12.5 % |
| b_listwalk | 712 | 1360 | 1.910 | 320 | 162 | 1201 | 1.687 | 162 | 2 | 1 | -11.7 % |
| b_matmul | 21644 | 31802 | 1.469 | 36 | 5059 | 27966 | 1.292 | 3968 | 1179 | 44 | -12.1 % |
| b_memcpy | 2894 | 4436 | 1.533 | 512 | 513 | 3928 | 1.357 | 514 | 3 | 2 | -11.5 % |
| b_sieve | 33604 | 51768 | 1.541 | 2044 | 8058 | 43861 | 1.305 | 8087 | 91 | 60 | -15.3 % |
| **all (sum)** | 82269 | 124675 | 1.515 | | | 108816 | 1.323 | | | | -12.7 % |

Cycle accounting: accounted = 4 + instret + load-use stalls + 2 x EX redirects + ID redirects. BP_MODE 0: cycles == accounted (exact). BP_MODE 1: cycles <= accounted; `overlap` = accounted - cycles, slots squashed twice. Check: holds for all 14 runs

### Synthesis and timing

From `results/ppa.md` (`make ppa`).

# Synthesis and timing of the RV32I cores (measured: Yosys 0.33 + OpenSTA, Sky130 HD tt_025C_1v80, pre-layout)

RVFI trace port removed (RVFI_EN=0). Ideal clock, no wires, no placement. Memory budget in the SDC: read data 2.0 ns after the edge, address/write data 1.0 ns before the next edge (assumption, identical for all rows). `speed` = timing-driven ABC script, `default` = `abc -D 10000`.

| core | mapping | cells | area (um^2) | flip-flops | T_min (ns) | F_max (MHz) | method check (+2 % meets, -2 % fails) |
|---|---|---:|---:|---:|---:|---:|---|
| 5-stage BP_MODE=0 FWD_PRECOMP=0 | speed | 6951 | 75452 | 1371 | 5.549 | 180.2 | verified (WNS +0.111 / -0.111 ns) |
| 5-stage BP_MODE=0 FWD_PRECOMP=1 | speed | 6906 | 75275 | 1365 | 4.330 | 230.9 | verified (WNS +0.086 / -0.087 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=0 | speed | 7374 | 77986 | 1372 | 6.072 | 164.7 | verified (WNS +0.122 / -0.121 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=1 | speed | 7396 | 77594 | 1366 | 4.842 | 206.5 | verified (WNS +0.097 / -0.097 ns) |
| single-cycle | speed | 6326 | 66975 | 1025 | 8.746 | 114.3 | verified (WNS +0.175 / -0.175 ns) |
| 5-stage BP_MODE=0 FWD_PRECOMP=1 | default | 6750 | 69276 | 1365 | 20.191 | 49.5 | verified (WNS +0.404 / -0.404 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=1 | default | 7070 | 71540 | 1366 | 18.184 | 55.0 | verified (WNS +0.364 / -0.364 ns) |
| single-cycle | default | 7140 | 59023 | 1025 | 25.407 | 39.4 | verified (WNS +0.508 / -0.508 ns) |

### Execution time: cycles x T_min

From `results/performance.md` (`make perf`).

# Performance: measured cycles x measured minimum period

T_min (ns, pre-layout, timing-driven mapping): single-cycle = 8.746, 5-stage BP0, EX-compare fwd = 5.549, 5-stage BP0, ID-precomputed fwd = 4.330, 5-stage BP1, ID-precomputed fwd = 4.842

Execution time in microseconds (cycles x T_min). Lower is better. Speed-up is relative to the single-cycle core.

| benchmark | instructions | single-cycle (us) | 5-stage BP0, EX-compare fwd (us) | 5-stage BP0, ID-precomputed fwd (us) | 5-stage BP1, ID-precomputed fwd (us) | best 5-stage speed-up |
|---|---:|---:|---:|---:|---:|---:|
| b_bubblesort | 13209 | 115.5 | 111.7 | 87.1 | 86.7 | 1.33x |
| b_crc32 | 9684 | 84.7 | 80.3 | 62.7 | 64.5 | 1.35x |
| b_fib | 522 | 4.6 | 3.9 | 3.1 | 3.0 | 1.52x |
| b_listwalk | 712 | 6.2 | 7.5 | 5.9 | 5.8 | 1.07x |
| b_matmul | 21644 | 189.3 | 176.5 | 137.7 | 135.4 | 1.40x |
| b_memcpy | 2894 | 25.3 | 24.6 | 19.2 | 19.0 | 1.33x |
| b_sieve | 33604 | 293.9 | 287.3 | 224.2 | 212.4 | 1.38x |
| **all** | 82269 | 719.5 | 691.8 | 539.8 | 526.9 | **1.37x** |

Speed-up of each 5-stage configuration over the single-cycle core, all benchmarks together: 5-stage BP0, EX-compare fwd 1.04x, 5-stage BP0, ID-precomputed fwd 1.33x, 5-stage BP1, ID-precomputed fwd 1.37x

Read with: pre-layout, ideal memories (2.0 ns read / 1.0 ns write budget assumed), 7 small kernels (82269 instructions), not a standard benchmark suite. The single-cycle figure is optimistic (see the script header), so these speed-ups are lower bounds under this model.

### Place and route (OpenROAD)

From `results/pnr.md` (`make pnr`).

# Place and route of rv32i_core (measured: OpenROAD, Sky130 HD tt_025C_1v80, RVFI_EN=0)

Flow: floorplan at the stated utilisation, global placement, repair_design, clock-tree synthesis, repair_timing, global and detailed routing, antenna repair, RC extraction (SPEF), final STA with the propagated clock on the extracted parasitics (`pnr/pnr_flow.tcl`, adapted from alu_fifo). Netlist: the timing-driven Yosys mapping of `make ppa`. Constraints: `constraints/rv32i.sdc` (memory read 2.0 ns after the edge, address/write data 1.0 ns before the next edge: an assumption). Typical corner only; no hold fixing beyond what repair_timing did; no signoff DRC/LVS (Magic/KLayout/Netgen are not installed), so "DRC" below is the router's own count. Power is OpenSTA's default-activity figure, not a workload figure.

| run | target period (ns) | setup WNS (ns) | hold WNS (ns) | TNS (ns) | route DRC | antenna viol. | slew / cap / fanout viol. | design area (um^2) | die (um) | checks |
|---|---:|---:|---:|---:|---:|---:|---|---:|---|---|
| bp1_fwd1_p10.0 | 10.0 | +0.626 | +0.091 | 0.000 | 0 | 0 | 61 / 5 / 0 | 79330 | 450 x 450 | all passed |
| bp1_fwd1_p6.0 | 6.0 | -0.575 | -0.131 | -45.888 | 0 | 0 | 16 / 5 / 0 | 81775 | 450 x 450 | all passed |
| bp1_fwd1_p7.0 | 7.0 | -0.554 | +0.117 | -27.181 | 0 | 0 | 21 / 3 / 0 | 79922 | 450 x 450 | all passed |
| bp1_fwd1_p8.0 | 8.0 | -0.303 | +0.093 | -5.719 | 0 | 0 | 17 / 7 / 0 | 79534 | 450 x 450 | all passed |
| bp1_fwd1_p8.4 | 8.4 | -0.538 | +0.073 | -33.977 | 0 | 0 | 26 / 8 / 0 | 79420 | 450 x 450 | all passed |
| bp1_fwd1_p8.6 | 8.6 | -0.774 | +0.091 | -23.009 | 0 | 0 | 61 / 5 / 0 | 79330 | 450 x 450 | all passed |
| bp1_fwd1_p8.8 | 8.8 | -0.574 | +0.091 | -6.151 | 0 | 0 | 61 / 5 / 0 | 79330 | 450 x 450 | all passed |
| bp1_fwd1_p9.0 | 9.0 | -0.374 | +0.091 | -1.313 | 0 | 0 | 61 / 5 / 0 | 79330 | 450 x 450 | all passed |
| bp1_fwd1_p9.5 | 9.5 | +0.126 | +0.091 | 0.000 | 0 | 0 | 61 / 5 / 0 | 79330 | 450 x 450 | all passed |

Worst routed setup path per run (start flop output net -> end flop input net, names from the post-repair netlist):

- `bp1_fwd1_p10.0`: `b_imm_e` -> `result_e[27]` (setup slack +0.626 ns)
- `bp1_fwd1_p6.0`: `\u_regfile.wd [29]` -> `_00363_` (setup slack -0.575 ns)
- `bp1_fwd1_p7.0`: `\u_regfile.wd [4]` -> `_00785_` (setup slack -0.554 ns)
- `bp1_fwd1_p8.0`: `b_imm_e` -> `_00789_` (setup slack -0.303 ns)
- `bp1_fwd1_p8.4`: `fwd_a_r[0]` -> `_00332_` (setup slack -0.538 ns)
- `bp1_fwd1_p8.6`: `b_imm_e` -> `result_e[27]` (setup slack -0.774 ns)
- `bp1_fwd1_p8.8`: `b_imm_e` -> `result_e[27]` (setup slack -0.574 ns)
- `bp1_fwd1_p9.0`: `b_imm_e` -> `result_e[27]` (setup slack -0.374 ns)
- `bp1_fwd1_p9.5`: `b_imm_e` -> `result_e[27]` (setup slack +0.126 ns)

Clock-tree sinks equal the flip-flop count in every accepted run; the netlist checksum matches the one recorded at the start of the run.

**Smallest tried target that closed setup and hold in the routed, extracted design with zero route DRC violations: 9.5 ns (105.3 MHz)**, run `bp1_fwd1_p9.5`. This is the best of the targets that were run (a tested value, not an optimum): finer steps below it were not tried.
The pre-layout minimum period of the same configuration is 4.842 ns (`results/ppa.md`); the smallest closing routed target is 1.96x that (derived: 9.5 / 4.842).
Selected run: bp1_fwd1_p9.5 | target 9.5 ns | 105.3 MHz | setup WNS +0.126 ns | hold WNS +0.091 ns | route DRC 0 | antenna violations 0 | area 79330 um^2
In that run the routed design still has 61 max-slew, 5 max-capacitance and 0 max-fanout violating pins/nets (`check_types_final.rpt`; 9 of the violating pins are antenna diodes).
Power, default activity (W): 9.90e-03. Design area before fillers: 79330 um^2 at 41.2 % utilisation. Clock skew report: Clock clk 1.216 source latency _11552_/CLK ^ -1.345 target latency _11599_/CLK ^ -0.130 setup skew

Runs bp1_fwd1_p8.6, bp1_fwd1_p8.8, bp1_fwd1_p9.0, bp1_fwd1_p9.5, bp1_fwd1_p10.0 have identical area and violation counts (repair_timing changed nothing at those targets) and their setup slack moves one for one with the period: the routed critical path of that layout is 9.374 ns (target minus slack, derived).

Run settings: core utilisation 40 %, repair_setup_margin 0.3 ns, global placement density 0.60 (alu_fifo's values, not tuned for this design); antenna repair between global and detailed routing: bp1_fwd1_p10.0 off, bp1_fwd1_p6.0 off, bp1_fwd1_p7.0 off, bp1_fwd1_p8.0 off, bp1_fwd1_p8.4 off, bp1_fwd1_p8.6 off, bp1_fwd1_p8.8 off, bp1_fwd1_p9.0 off, bp1_fwd1_p9.5 off.

<!-- END RESULTS -->

## Reading the timing and performance numbers

- The synthesis table is pre-layout: ideal clock, no wires, no placement, typical corner. It's useful for comparing designs, not as
  a sign-off frequency. I also placed and routed one configuration (`BP_MODE=1`, `FWD_PRECOMP=1`, see Place and route above), and
  its routed minimum period is about twice the pre-layout figure.
- The memories are outside the core. The SDC gives them a budget (read data 2.0 ns after the edge, address and write data 1.0 ns
  before the next edge). That's an assumption, and it is the same for every configuration.
- The single-cycle core's period is the tool's worst case over its port-bounded paths, so it doesn't include the two memory
  accesses a real single-cycle machine would have to fit into one cycle. That makes its figure optimistic, so every pipelined
  speed-up I quote is a lower bound under this model.
- `T_min = 10 ns - WNS(10 ns)` isn't taken on trust: STA is re-run at +2 % of T_min (it must meet) and at -2 % (it must fail), and
  the table says whether it did.
- The pipeline with the forwarding compare in EX (`FWD_PRECOMP=0`, `BP_MODE=0`) didn't clearly beat the single-cycle core on these
  kernels: 0.92x when I first measured it (`results/performance_before_misaligned_fix.md`) and 1.04x after the misaligned-target
  fix and a re-run (`results/performance.md`). Its T_min went from 6.024 to 5.549 ns even though the fix added logic, so the
  timing-driven mapping moves by up to 8 % between RTL revisions, and differences that small between configurations are within
  that noise. Precomputing the forwarding selects in ID gave 1.27x and then 1.33x with `BP_MODE=0`, and 1.37x both times with
  `BP_MODE=1`. I kept both `FWD_PRECOMP` variants.
- CPI is measured on seven small kernels (82,269 instructions in total), not on a standard benchmark suite.

## Limitations

Things I left out on purpose or haven't done yet:

- No Zicsr, no interrupts, no exceptions beyond stopping the core, no M or C extension and no privilege levels. A real core would
  trap and carry on.
- Ideal memories with no wait states: no cache, no bus interface and no instruction-fetch stall.
- Static branch prediction only (backward-taken, from ID) and no branch target buffer.
- Timing is pre-layout except for the one routed configuration (nine target periods, OpenROAD, extracted parasitics, typical
  corner). The other three pipelined configurations and the single-cycle baseline aren't routed, so I don't claim a routed
  speed-up. There's no signoff DRC or LVS because Magic, KLayout and Netgen aren't installed, and the power number is OpenSTA's
  default-activity figure, not a measurement on a real workload.
- The formal checks are bounded (riscv-formal to a stated depth, 172 of 172 pass across the four variants). There's no unbounded
  proof and no liveness or bus check, and the `reg` check only covers register x5.
- I haven't run riscv-tests or riscv-arch-test because they need a RISC-V GCC toolchain, which isn't installed here. The directed
  tests and the ISS stand in for them, and they are labelled as such.
