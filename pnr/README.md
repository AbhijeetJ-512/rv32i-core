# pnr/ - OpenROAD place and route of rv32i_core

```bash
make ppa          # writes the post-synthesis netlists (build/ppa/pipe_<config>_speed_p10/synth.v)
make pnr          # place and route at PNR_PERIODS (default "6.0 7.0 8.0 8.4 8.6 8.8 9.0 9.5 10.0" ns, four runs at a time, two threads each, about 40 minutes; `make pnr` sets `PNR_GRT_ANTENNA=0`, see the end of this file), then pnr/pnr_report.py -> results/pnr.md, results/pnr.json
pnr/run_pnr.sh 7.0 bp1_fwd1     # one run: results/pnr/bp1_fwd1_p7.0/
```

What runs: floorplan (40 % core utilisation, square die), tap cells, power grid, global placement, `repair_design`, clock-tree synthesis,
`repair_timing` (propagated clock), global routing, antenna repair, detailed routing, antenna repair again, RC extraction to SPEF, filler cells, then
the final STA on the extracted parasitics. `pnr_flow.tcl` is `alu_fifo/scripts/pnr_flow.tcl` with the design names, the netlist and the results
directory taken from the environment; the platform files in `../sky130hd/` are the same ones `alu_fifo` uses. Nothing was tuned for this design:
utilisation 40 %, `repair_setup_margin` 0.3 ns and the slew / capacitance margins of 20 % are alu_fifo's values.

`pnr_report.py` reads every run back and refuses to use one that does not pass its checks (no `[ERROR`, flow completed, clock period equals the
directory name, clock-tree sinks equal the flip-flop count, netlist checksum unchanged, every routed report present, route DRC report consistent with the
count). A run that fails is listed with the reason and its numbers are not used.

Not covered: signoff DRC and LVS (Magic, KLayout and Netgen are not installed; the DRC figure is the router's own count), other process corners,
hold fixing beyond what `repair_timing` did, IR drop, power with a real workload, and any memory macro (the instruction and data memories are outside the
core; the SDC gives them a fixed 2.0 ns / 1.0 ns budget).

`PNR_GRT_ANTENNA=0` skips the antenna repair between global and detailed routing. It exists because that step crashed OpenROAD (GRT-0183, heap underflow in
the 3D maze router on the clock net) in two of the first three runs; the logs of those crashes are in `results/pnr_grt_antenna/`.
