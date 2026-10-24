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
