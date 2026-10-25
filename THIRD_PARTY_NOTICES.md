# Third-party files

The MIT license in `LICENSE` covers my own work in this repository. It does not cover the files below, which keep their own licenses.

## `sky130hd/`

These are the Sky130 HD platform files that the synthesis, timing and place-and-route flows read. I copied them from the `test/sky130hd/`
directory of the OpenROAD project (https://github.com/The-OpenROAD-Project/OpenROAD), which is distributed under the BSD 3-Clause
License, Copyright (c) 2018-2025, The OpenROAD Authors. I changed two of them for this flow: `sky130hd.vars` and `sky130hd.tracks`.

The standard-cell library data in that folder (`sky130hd_tt.lib`, `sky130hd_std_cell.lef`, `sky130_fd_sc_hd_merged.lef` and
`sky130hd.tlef`) comes from the SkyWater SKY130 PDK, Copyright 2020 The SkyWater PDK Authors, licensed under the Apache License,
Version 2.0 (https://www.apache.org/licenses/LICENSE-2.0). The LEF files carry that notice in their headers.

## Tools that are used but not included

Verilator, Yosys, OpenSTA, OpenROAD, SymbiYosys, z3 and riscv-formal are run by the scripts here but none of their code is in this
repository. `formal/checks.cfg.in` and `formal/wrapper.sv` are my own files written for riscv-formal.
