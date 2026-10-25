# Formal checks (riscv-formal, bounded)

`run_formal.sh` runs the riscv-formal instruction, register, PC, uniqueness, causality and illegal-instruction checks on `rv32i_core` for all four
`BP_MODE` x `FWD_PRECOMP` variants with SymbiYosys 0.33 and z3, and writes `results/formal.txt`. `run_as_found.sh` runs the same checks on the core as it was
before the misaligned-target fix (`as_found/rv32i_core.sv`) and writes `results/formal_as_found.txt` (8 checks fail there: every branch, JAL and JALR).

Tools (not part of this folder), looked for under `$TC` (default `../../_toolchain`): `$TC/riscv-formal`, `$TC/sbyroot` (sby, installed with
`make install PREFIX=...`), `$TC/sbyvenv` (z3 and click in a Python venv). For example `make formal TC=/opt/formal`. `wrapper.sv` ties `rv32i_core` to the riscv-formal harness; instruction memory and load data
are free inputs. These are bounded model checks (depth 12 to 14 cycles from reset), not unbounded proofs.
