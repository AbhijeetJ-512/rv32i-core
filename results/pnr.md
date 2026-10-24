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
