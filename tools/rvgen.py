#!/usr/bin/env python3
"""rvgen.py - constrained-random RV32I program generator.

    rvgen.py --seed 17 --length 600 -o prog.S          one program
    rvgen.py --count 200 --first-seed 1 --out-dir DIR  many programs (seed s -> DIR/rand_s.S)

Programs are valid by construction for this core and its ISS (no misaligned targets, no out-of-range accesses, only
registers that have been written), and are meant to be run lock-step against the ISS (tools/run_tests.py). The
constraints that shape the stimulus:

  * instruction mix: weighted classes (ALU reg/imm, load, store, forward branch, JAL, JALR, LUI/AUIPC, counted loop)
  * dependency bias: a source register is, with probability --dep, one of the last few destination registers, so
    RAW distances 1..3 and load-use pairs occur often; otherwise uniform over the register file
  * load-use bias: after a load, the next instruction consumes the loaded register with probability --lu
  * operand values: edge values (0, 1, -1, INT_MIN, INT_MAX, 0xFFFF...) are over-represented
  * memory: all accesses are within a 512-byte window at x31 (= 0x9000), naturally aligned
  * control flow: forward branches skip 1..4 filler instructions (wrong-path fodder); counted loops run 2..6 times;
    memory-resident loop counters put a load directly in front of a backward branch
  * with probability --trap the program ends in a trapping instruction (illegal / misaligned) instead of ECALL
Reserved registers: x30 (loop counter), x31 (data window base).
"""
import argparse
import os
import random

EDGE = [0, 1, 2, 0x7FFFFFFF, 0x80000000, 0xFFFFFFFF, 0xFFFF, 0xFFFF0000, 0x55555555, 0xAAAAAAAA, 0x0000FF00, 31, 32]
ALU_R = ["add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and"]
ALU_I = ["addi", "slti", "sltiu", "xori", "ori", "andi"]
SH_I = ["slli", "srli", "srai"]
LOADS = [("lw", 4), ("lh", 2), ("lhu", 2), ("lb", 1), ("lbu", 1)]
STORES = [("sw", 4), ("sh", 2), ("sb", 1)]
BR = ["beq", "bne", "blt", "bge", "bltu", "bgeu"]
WINDOW = 512


class Gen:
    def __init__(self, seed, length, dep=0.6, lu=0.5, trap=0.05, weights=None):
        self.r = random.Random(seed)
        self.n = length
        self.dep, self.lu, self.trap = dep, lu, trap
        self.out = []
        self.recent = [5, 6, 7]
        self.label = 0
        self.w = weights or {"alu_r": 30, "alu_i": 18, "sh_i": 5, "load": 13, "store": 10, "branch": 8, "jal": 2,
                             "jalr": 2, "upper": 4, "loop": 3, "memloop": 2, "nop": 1}
        self.last_load_rd = None

    def emit(self, s):
        self.out.append("    " + s)

    def newlabel(self):
        self.label += 1
        return "L%d" % self.label

    def dest(self):
        if self.r.random() < 0.03:
            return 0
        return self.r.randint(1, 29)

    def src(self):
        if self.last_load_rd and self.r.random() < self.lu:
            rd, self.last_load_rd = self.last_load_rd, None
            return rd
        if self.r.random() < self.dep:
            return self.r.choice(self.recent)
        return self.r.randint(0, 29)

    def wrote(self, rd):
        if rd:
            self.recent = (self.recent + [rd])[-3:]

    def imm12(self):
        return self.r.choice([0, 1, -1, 2047, -2048, self.r.randint(-2048, 2047), self.r.randint(-64, 64)])

    def one(self, in_loop=False):
        kinds = [k for k in self.w if not (in_loop and k in ("branch", "jal", "jalr", "loop", "memloop"))]
        k = self.r.choices(kinds, [self.w[k] for k in kinds])[0]
        r = self.r
        if k == "alu_r":
            rd = self.dest(); self.emit("%-4s x%d, x%d, x%d" % (r.choice(ALU_R), rd, self.src(), self.src())); self.wrote(rd)
        elif k == "alu_i":
            rd = self.dest(); self.emit("%-5s x%d, x%d, %d" % (r.choice(ALU_I), rd, self.src(), self.imm12())); self.wrote(rd)
        elif k == "sh_i":
            rd = self.dest(); self.emit("%-4s x%d, x%d, %d" % (r.choice(SH_I), rd, self.src(), r.choice([0, 1, 31, r.randint(0, 31)]))); self.wrote(rd)
        elif k == "load":
            op, sz = r.choice(LOADS)
            rd = self.dest()
            self.emit("%-3s x%d, %d(x31)" % (op, rd, r.randrange(0, WINDOW, sz)))
            self.wrote(rd)
            self.last_load_rd = rd if rd else None
        elif k == "store":
            op, sz = r.choice(STORES)
            self.emit("%-2s x%d, %d(x31)" % (op, self.src(), r.randrange(0, WINDOW, sz)))
        elif k == "upper":
            rd = self.dest()
            if r.random() < 0.5:
                self.emit("lui  x%d, %d" % (rd, r.randint(0, 0xFFFFF)))
            else:
                self.emit("auipc x%d, %d" % (rd, r.randint(0, 0xFFFFF)))
            self.wrote(rd)
        elif k == "nop":
            self.emit("nop")
        elif k == "branch":
            lab = self.newlabel()
            self.emit("%-4s x%d, x%d, %s" % (r.choice(BR), self.src(), self.src(), lab))
            for _ in range(r.randint(1, 4)):
                self.one(in_loop=True)
            self.out.append(lab + ":")
        elif k == "jal":
            lab = self.newlabel()
            rd = self.dest()
            self.emit("jal  x%d, %s" % (rd, lab))
            for _ in range(r.randint(1, 3)):
                self.one(in_loop=True)
            self.out.append(lab + ":")
            self.wrote(rd)
        elif k == "jalr":
            lab = self.newlabel()
            tmp = r.randint(1, 29)
            rd = self.dest()
            here = self.newlabel()
            self.out.append(here + ":")
            self.emit("auipc x%d, 0" % tmp)                       # tmp = address of this instruction
            self.emit("addi x%d, x%d, 12" % (tmp, tmp))            # + 12: past auipc, addi, jalr
            self.emit("jalr x%d, %d(x%d)" % (rd, r.choice([0, 1]), tmp))   # target bit 0 is cleared by the core
            self.wrote(tmp); self.wrote(rd)
            self.out.append(lab + ":")
        elif k == "memloop":
            # a loop counter kept in memory just above the random window: load, decrement, store, load, then a backward
            # branch on the value just loaded (load-use stall on a branch that BP_MODE=1 predicts taken)
            lab = self.newlabel()
            self.emit("li   x30, %d" % r.randint(1, 4))
            self.emit("sw   x30, %d(x31)" % WINDOW)
            self.out.append(lab + ":")
            for _ in range(r.randint(1, 4)):
                self.one(in_loop=True)
            self.emit("lw   x30, %d(x31)" % WINDOW)
            self.emit("addi x30, x30, -1")
            self.emit("sw   x30, %d(x31)" % WINDOW)
            self.emit("lw   x30, %d(x31)" % WINDOW)
            self.emit("bnez x30, %s" % lab)
        elif k == "loop":
            lab = self.newlabel()
            self.emit("li   x30, %d" % r.randint(2, 6))
            self.out.append(lab + ":")
            for _ in range(r.randint(2, 7)):
                self.one(in_loop=True)
            self.emit("addi x30, x30, -1")
            self.emit("bnez x30, %s" % lab)

    def program(self, seed):
        r = self.r
        self.emit_header = ["# GENERATED by tools/rvgen.py seed=%d - random program" % seed, "# EXPECT: ecall"]
        self.out = []
        self.emit("lui  x31, 0x9")                                  # x31 = 0x9000, the data window
        for i in range(1, 30):
            v = r.choice(EDGE) if r.random() < 0.4 else r.getrandbits(32)
            self.emit("li   x%d, 0x%08x" % (i, v))
        while len(self.out) < self.n:
            self.one()
        if r.random() < self.trap:
            self.emit(r.choice([".word 0x00000000", "lw   x5, 1(x31)", "sw   x6, 2(x31)", "lh   x7, 3(x31)",
                                ".word 0x02208133"]))
        self.emit("j    _pass")
        data = [".data"]
        # data window: random words
        data.append(".org 0x9000")
        data.append("win:")
        for i in range(0, WINDOW, 16):
            data.append("    .word 0x%08x, 0x%08x, 0x%08x, 0x%08x" % tuple(r.getrandbits(32) for _ in range(4)))
        return "\n".join(self.emit_header + self.out + data) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--length", type=int, default=600)
    ap.add_argument("--dep", type=float, default=0.6)
    ap.add_argument("--lu", type=float, default=0.5)
    ap.add_argument("--trap", type=float, default=0.05)
    ap.add_argument("-o", "--out")
    ap.add_argument("--count", type=int)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--out-dir")
    a = ap.parse_args()
    if a.count:
        os.makedirs(a.out_dir, exist_ok=True)
        for s in range(a.first_seed, a.first_seed + a.count):
            g = Gen(s, a.length, a.dep, a.lu, a.trap)
            open(os.path.join(a.out_dir, "rand_%d.S" % s), "w").write(g.program(s))
    else:
        g = Gen(a.seed, a.length, a.dep, a.lu, a.trap)
        open(a.out, "w").write(g.program(a.seed))


if __name__ == "__main__":
    main()
