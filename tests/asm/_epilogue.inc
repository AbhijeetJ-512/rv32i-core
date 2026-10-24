
# ---- common epilogue (appended by tools/run_tests.py): test end points and the register dump
_pass:
    li   a0, 0
    j    _finish
_fail:                         # gp holds the number of the failed check
    li   a0, 1
_finish:
    sw   x1,  0x104(x0)
    sw   x2,  0x108(x0)
    sw   x3,  0x10c(x0)
    sw   x4,  0x110(x0)
    sw   x5,  0x114(x0)
    sw   x6,  0x118(x0)
    sw   x7,  0x11c(x0)
    sw   x8,  0x120(x0)
    sw   x9,  0x124(x0)
    sw   x10, 0x128(x0)
    sw   x11, 0x12c(x0)
    sw   x12, 0x130(x0)
    sw   x13, 0x134(x0)
    sw   x14, 0x138(x0)
    sw   x15, 0x13c(x0)
    sw   x16, 0x140(x0)
    sw   x17, 0x144(x0)
    sw   x18, 0x148(x0)
    sw   x19, 0x14c(x0)
    sw   x20, 0x150(x0)
    sw   x21, 0x154(x0)
    sw   x22, 0x158(x0)
    sw   x23, 0x15c(x0)
    sw   x24, 0x160(x0)
    sw   x25, 0x164(x0)
    sw   x26, 0x168(x0)
    sw   x27, 0x16c(x0)
    sw   x28, 0x170(x0)
    sw   x29, 0x174(x0)
    sw   x30, 0x178(x0)
    sw   x31, 0x17c(x0)
    ecall
