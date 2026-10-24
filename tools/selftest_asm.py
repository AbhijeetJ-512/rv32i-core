#!/usr/bin/env python3
"""Assembler self-test against independently known encodings (hand-derived from the spec's instruction formats and the
words in the user's earlier RISC-V repository, which were produced by an external assembler)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rvasm import Asm  # noqa: E402

CASES = [
    ("addi x1, x0, 5", 0x00500093), ("addi x2, x0, 10", 0x00A00113), ("add x3, x1, x2", 0x002081B3),
    ("sub x4, x3, x1", 0x40118233), ("and x5, x3, x4", 0x0041F2B3), ("or x6, x3, x4", 0x0041E333),
    ("sub x7, x6, x5", 0x405303B3), ("add x8, x7, x3", 0x00338433), ("sub x9, x8, x2", 0x402404B3),
    ("and x10, x9, x1", 0x0014F533), ("or x11, x9, x1", 0x0014E5B3), ("add x12, x10, x11", 0x00B50633),
    ("sub x13, x12, x9", 0x409606B3), ("and x14, x13, x1", 0x0016F733), ("or x15, x14, x7", 0x007767B3),
    ("lw x5, 8(x6)", 0x00832283), ("sw x5, 8(x6)", 0x00532423), ("lui x5, 0x12345", 0x123452B7),
    ("slli x1, x2, 3", 0x00311093), ("srai x1, x2, 3", 0x40315093), ("xori x1, x2, -1", 0xFFF14093),
    ("sltu x3, x1, x2", 0x0020B1B3), ("jalr x0, 0(x1)", 0x00008067), ("ecall", 0x00000073), ("ebreak", 0x00100073),
    ("lbu x7, 3(x8)", 0x00344383), ("sh x9, -2(x10)", 0xFE951F23), ("srl x1, x2, x3", 0x003150B3),
    ("sra x1, x2, x3", 0x403150B3), ("slt x1, x2, x3", 0x003120B3), ("andi x4, x5, 255", 0x0FF2F213),
]
ok = True
for src, want in CASES:
    a = Asm(text_base=0)   # the default text base is 0x1000; the vectors are read from address 0
    mem, _ = a.assemble(src + "\n")
    got = sum(mem[i] << (8 * i) for i in range(4))
    if got != want:
        ok = False
        print("FAIL %-22s got %08x want %08x" % (src, got, want))
# branches / jumps need an address context
a = Asm(text_base=0)
mem, _ = a.assemble("start: beq x1, x2, tgt\n nop\ntgt: jal x1, tgt2\n nop\n nop\n nop\ntgt2: blt x3, x4, start\n")
w = [sum(mem[4 * i + b] << (8 * b) for b in range(4)) for i in range(7)]
for name, got, want in [("beq +8", w[0], 0x00208463), ("jal +16", w[2], 0x010000EF), ("blt -24", w[6], None)]:
    if want is not None and got != want:
        ok = False
        print("FAIL %s got %08x want %08x" % (name, got, want))
# blt x3,x4 back 24 bytes: imm=-24 -> hand-encoded
off = -24 & 0x1FFF
want_blt = (((off >> 12) & 1) << 31) | (((off >> 5) & 0x3F) << 25) | (4 << 20) | (3 << 15) | (4 << 12) | \
           (((off >> 1) & 0xF) << 8) | (((off >> 11) & 1) << 7) | 0x63
if w[6] != want_blt:
    ok = False
    print("FAIL blt -24 got %08x want %08x" % (w[6], want_blt))
# li / la sizes and values
a = Asm(text_base=0)
mem, _ = a.assemble("li t0, 0x12345678\nli t1, -1\nli t2, 0xFFFFF800\n.data\nd: .word 7\n")
# hand-derived: lui x5,0x12345 ; addi x5,x5,0x678 ; addi x6,x0,-1 ; addi x7,x0,-2048 ; the .word 7 at the data base
li_text = [sum(mem[4 * i + b] << (8 * b) for b in range(4)) for i in range(4)]
for name, got, want in zip(("li lui", "li addi", "li -1", "li 0xFFFFF800"), li_text, (0x123452B7, 0x67828293, 0xFFF00313, 0x80000393)):
    if got != want:
        ok = False
        print("FAIL %s got %08x want %08x" % (name, got, want))
if sum(mem[0x8000 + b] << (8 * b) for b in range(4)) != 7:
    ok = False
    print("FAIL .data word at the data base")
print("asm self-test:", "PASS (%d vectors + branch/jump cases)" % len(CASES) if ok else "FAIL")
sys.exit(0 if ok else 1)
