# Smoke test: the instruction sequence from the earlier RISC-V repository (back-to-back RAW dependences), then exit.
    addi x1, x0, 5
    addi x2, x0, 10
    add  x3, x1, x2
    sub  x4, x3, x1
    and  x5, x3, x4
    or   x6, x3, x4
    sub  x7, x6, x5
    add  x8, x7, x3
    sub  x9, x8, x2
    and  x10, x9, x1
    or   x11, x9, x1
    add  x12, x10, x11
    sub  x13, x12, x9
    and  x14, x13, x1
    or   x15, x14, x7
    j    _pass
