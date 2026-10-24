# Performance: measured cycles x measured minimum period

T_min (ns, pre-layout, timing-driven mapping): single-cycle = 8.437, 5-stage BP0, EX-compare fwd = 6.024, 5-stage BP0, ID-precomputed fwd = 4.370, 5-stage BP1, ID-precomputed fwd = 4.669

Execution time in microseconds (cycles x T_min). Lower is better. Speed-up is relative to the single-cycle core.

| benchmark | instructions | single-cycle (us) | 5-stage BP0, EX-compare fwd (us) | 5-stage BP0, ID-precomputed fwd (us) | 5-stage BP1, ID-precomputed fwd (us) | best 5-stage speed-up |
|---|---:|---:|---:|---:|---:|---:|
| b_bubblesort | 13209 | 111.4 | 121.2 | 87.9 | 83.6 | 1.33x |
| b_crc32 | 9684 | 81.7 | 87.2 | 63.3 | 62.2 | 1.31x |
| b_fib | 522 | 4.4 | 4.3 | 3.1 | 2.9 | 1.52x |
| b_listwalk | 712 | 6.0 | 8.2 | 5.9 | 5.6 | 1.07x |
| b_matmul | 21644 | 182.6 | 191.6 | 139.0 | 130.6 | 1.40x |
| b_memcpy | 2894 | 24.4 | 26.7 | 19.4 | 18.3 | 1.33x |
| b_sieve | 33604 | 283.5 | 311.9 | 226.2 | 204.8 | 1.38x |
| **all** | 82269 | 694.1 | 751.0 | 544.8 | 508.1 | **1.37x** |

Speed-up of each 5-stage configuration over the single-cycle core, all benchmarks together: 5-stage BP0, EX-compare fwd 0.92x, 5-stage BP0, ID-precomputed fwd 1.27x, 5-stage BP1, ID-precomputed fwd 1.37x

Read with: pre-layout, ideal memories (2.0 ns read / 1.0 ns write budget assumed), 7 small kernels (82269 instructions), not a standard benchmark suite. The single-cycle figure is optimistic (see the script header), so these speed-ups are lower bounds under this model.
