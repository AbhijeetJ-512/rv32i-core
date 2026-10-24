# Synthesis and timing of the RV32I cores (measured: Yosys 0.33 + OpenSTA, Sky130 HD tt_025C_1v80, pre-layout)

RVFI trace port removed (RVFI_EN=0). Ideal clock, no wires, no placement. Memory budget in the SDC: read data 2.0 ns after the edge, address/write data 1.0 ns before the next edge (assumption, identical for all rows). `speed` = timing-driven ABC script, `default` = `abc -D 10000`.

| core | mapping | cells | area (um^2) | flip-flops | T_min (ns) | F_max (MHz) | method check (+2 % meets, -2 % fails) |
|---|---|---:|---:|---:|---:|---:|---|
| 5-stage BP_MODE=0 FWD_PRECOMP=0 | speed | 7155 | 75375 | 1371 | 6.024 | 166.0 | verified (WNS +0.121 / -0.120 ns) |
| 5-stage BP_MODE=0 FWD_PRECOMP=1 | speed | 7172 | 75535 | 1365 | 4.370 | 228.8 | verified (WNS +0.087 / -0.088 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=0 | speed | 7381 | 77701 | 1372 | 6.066 | 164.9 | verified (WNS +0.121 / -0.122 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=1 | speed | 7521 | 77537 | 1366 | 4.669 | 214.2 | verified (WNS +0.093 / -0.093 ns) |
| single-cycle | speed | 6294 | 67923 | 1025 | 8.437 | 118.5 | verified (WNS +0.169 / -0.169 ns) |
| 5-stage BP_MODE=0 FWD_PRECOMP=1 | default | 6799 | 69985 | 1365 | 20.202 | 49.5 | verified (WNS +0.404 / -0.404 ns) |
| 5-stage BP_MODE=1 FWD_PRECOMP=1 | default | 7069 | 71476 | 1366 | 17.204 | 58.1 | verified (WNS +0.345 / -0.344 ns) |
| single-cycle | default | 6327 | 59087 | 1025 | 27.418 | 36.5 | verified (WNS +0.549 / -0.548 ns) |
