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
