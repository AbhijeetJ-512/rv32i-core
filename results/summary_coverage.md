Merged coverage of the directed tests, the benchmarks and random programs, both BP modes (`results/coverage_summary.txt`):

```text
source               : build/cov/merged.dat
named cover bins     : 143 total, 143 hit, 0 zero
rtl/ line blocks    : 117 total, 115 covered, 2 excluded, 0 uncovered
rtl/ files with no line records : rv32i_core_1cyc.sv (procedural blocks only are recorded; these are covered by toggle coverage, the cover bins and the assertions, not by the line gate)
rtl/ branches       : 72 total, 59 hit (reported, not gated)
rtl/ toggle bits    : 3853 total, 3773 toggled, 80 unhit (reported, not gated)
```
