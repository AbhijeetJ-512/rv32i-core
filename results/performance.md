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
