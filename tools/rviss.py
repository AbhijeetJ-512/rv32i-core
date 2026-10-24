#!/usr/bin/env python3
"""rviss.py - instruction-set simulator for RV32I, the golden model for lock-step checking.

    rviss.py prog.hex -o prog.iss.trace [--max-insns N] [--mem-words 16384]

It is written from the unprivileged-spec instruction tables, independently of the RTL decoder. Each retired instruction
is one trace line in the same format the testbench writes for the RTL (see TRACE_FIELDS), so the two traces can be
compared line by line by compare_trace.py.

Behaviour chosen where the core has no hardware support (matching the RTL, documented in the README):
  ECALL / EBREAK                      -> retire with halt=1
  illegal or unsupported encoding     -> retire with halt=1 trap=1, no architectural effect
  misaligned load / store             -> retire with halt=1 trap=1, no architectural effect
  branch / jump to a non-4-byte-aligned target, access outside memory, read of a register never written
                                      -> ISSError: the PROGRAM is invalid for this core (exit code 3)
"""
import argparse
import sys

MASK32 = 0xFFFFFFFF
TRACE_FIELDS = ("order pc insn next_pc rs1_addr rs1_rdata rs2_addr rs2_rdata rd_addr rd_wdata "
                "mem_addr mem_rmask mem_wmask mem_rdata mem_wdata halt trap").split()


class ISSError(Exception):
    pass


def s32(v):
    v &= MASK32
    return v - (1 << 32) if v & 0x80000000 else v


def sext(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def fmt(rec):
    """One trace line. Addresses of registers in decimal, everything else in hex."""
    return ("%d %08x %08x %08x %d %08x %d %08x %d %08x %08x %x %x %08x %08x %d %d" % (
        rec["order"], rec["pc"], rec["insn"], rec["next_pc"], rec["rs1_addr"], rec["rs1_rdata"],
        rec["rs2_addr"], rec["rs2_rdata"], rec["rd_addr"], rec["rd_wdata"], rec["mem_addr"],
        rec["mem_rmask"], rec["mem_wmask"], rec["mem_rdata"], rec["mem_wdata"], rec["halt"], rec["trap"]))


class ISS:
    def __init__(self, words, mem_words=16384, strict_uninit=True, reset_pc=0x1000):
        self.mem = bytearray(mem_words * 4)
        for i, w in enumerate(words[:mem_words]):
            self.mem[4 * i:4 * i + 4] = (w & MASK32).to_bytes(4, "little")
        self.size = mem_words * 4
        self.x = [0] * 32
        self.defined = [False] * 32
        self.defined[0] = True
        self.pc = reset_pc
        self.order = 0
        self.strict = strict_uninit
        self.halted = False
        self.mix = {}

    # --- helpers
    def rd_reg(self, n):
        if self.strict and not self.defined[n]:
            raise ISSError("pc=%08x: read of register x%d that the program never wrote" % (self.pc, n))
        return self.x[n]

    def wr_reg(self, n, v):
        if n:
            self.x[n] = v & MASK32
            self.defined[n] = True

    def word_at(self, a):
        if a < 0 or a + 4 > self.size:
            raise ISSError("access outside memory at %08x (pc=%08x)" % (a, self.pc))
        return int.from_bytes(self.mem[a:a + 4], "little")

    # --- one instruction
    def step(self):
        pc = self.pc
        if pc & 3:
            raise ISSError("misaligned fetch at %08x" % pc)
        insn = self.word_at(pc)
        op = insn & 0x7F
        rd = (insn >> 7) & 31
        f3 = (insn >> 12) & 7
        rs1 = (insn >> 15) & 31
        rs2 = (insn >> 20) & 31
        f7 = insn >> 25
        rec = dict(order=self.order, pc=pc, insn=insn, next_pc=(pc + 4) & MASK32, rs1_addr=0, rs1_rdata=0,
                   rs2_addr=0, rs2_rdata=0, rd_addr=0, rd_wdata=0, mem_addr=0, mem_rmask=0, mem_wmask=0,
                   mem_rdata=0, mem_wdata=0, halt=0, trap=0)
        imm_i = sext(insn >> 20, 12)
        imm_s = sext(((insn >> 25) << 5) | ((insn >> 7) & 31), 12)
        imm_b = sext((((insn >> 31) & 1) << 12) | (((insn >> 7) & 1) << 11) | (((insn >> 25) & 63) << 5) |
                     (((insn >> 8) & 15) << 1), 13)
        imm_u = insn & 0xFFFFF000
        imm_j = sext((((insn >> 31) & 1) << 20) | (((insn >> 12) & 255) << 12) | (((insn >> 20) & 1) << 11) |
                     (((insn >> 21) & 1023) << 1), 21)

        def illegal():
            rec.update(halt=1, trap=1, rs1_addr=0, rs2_addr=0, rs1_rdata=0, rs2_rdata=0)
            self.halted = True
            self.mix["illegal"] = self.mix.get("illegal", 0) + 1

        def misaligned_target():   # instruction-address-misaligned (no C extension): the transfer traps, rd is not written, pc does not move
            rec.update(halt=1, trap=1)
            self.halted = True
            self.mix["misaligned_target"] = self.mix.get("misaligned_target", 0) + 1

        def use1():
            rec["rs1_addr"] = rs1
            rec["rs1_rdata"] = self.rd_reg(rs1) if rs1 else 0
            return rec["rs1_rdata"]

        def use2():
            rec["rs2_addr"] = rs2
            rec["rs2_rdata"] = self.rd_reg(rs2) if rs2 else 0
            return rec["rs2_rdata"]

        def write(v):
            self.wr_reg(rd, v)
            if rd:
                rec["rd_addr"] = rd
                rec["rd_wdata"] = v & MASK32

        name = None
        if op == 0x37:       # LUI
            name = "lui"
            write(imm_u)
        elif op == 0x17:     # AUIPC
            name = "auipc"
            write(pc + imm_u)
        elif op == 0x6F:     # JAL
            name = "jal"
            tgt = (pc + imm_j) & MASK32
            if tgt & 3:
                misaligned_target()
            else:
                write(pc + 4)
                rec["next_pc"] = tgt
        elif op == 0x67:     # JALR
            if f3 != 0:
                illegal()
            else:
                name = "jalr"
                a = use1()
                tgt = (a + imm_i) & MASK32 & ~1
                if tgt & 3:
                    misaligned_target()
                else:
                    write(pc + 4)
                    rec["next_pc"] = tgt
        elif op == 0x63:     # BRANCH
            if f3 in (2, 3):
                illegal()
            else:
                name = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}[f3]
                a, b = use1(), use2()
                taken = {0: a == b, 1: a != b, 4: s32(a) < s32(b), 5: s32(a) >= s32(b), 6: a < b, 7: a >= b}[f3]
                if taken:
                    if (pc + imm_b) & 3:
                        misaligned_target()
                    else:
                        rec["next_pc"] = (pc + imm_b) & MASK32
        elif op == 0x03:     # LOAD
            if f3 not in (0, 1, 2, 4, 5):
                illegal()
            else:
                name = {0: "lb", 1: "lh", 2: "lw", 4: "lbu", 5: "lhu"}[f3]
                a = use1()
                ea = (a + imm_i) & MASK32
                size = {0: 1, 1: 2, 2: 4, 4: 1, 5: 2}[f3]
                if ea % size:
                    rec.update(halt=1, trap=1)
                    self.halted = True
                else:
                    w = self.word_at(ea & ~3)
                    lane = ea & 3
                    v = (w >> (8 * lane)) & ((1 << (8 * size)) - 1)
                    if f3 in (0, 1):
                        v = sext(v, 8 * size) & MASK32
                    write(v)
                    rec.update(mem_addr=ea & ~3, mem_rmask=((1 << size) - 1) << lane, mem_rdata=w)
        elif op == 0x23:     # STORE
            if f3 not in (0, 1, 2):
                illegal()
            else:
                name = {0: "sb", 1: "sh", 2: "sw"}[f3]
                a, b = use1(), use2()
                ea = (a + imm_s) & MASK32
                size = {0: 1, 1: 2, 2: 4}[f3]
                if ea % size:
                    rec.update(halt=1, trap=1)
                    self.halted = True
                else:
                    if ea & ~3 < 0 or (ea & ~3) + 4 > self.size:
                        raise ISSError("store outside memory at %08x (pc=%08x)" % (ea, pc))
                    lane = ea & 3
                    for i in range(size):
                        self.mem[ea + i] = (b >> (8 * i)) & 0xFF
                    rec.update(mem_addr=ea & ~3, mem_wmask=((1 << size) - 1) << lane,
                               mem_wdata=((b & ((1 << (8 * size)) - 1)) << (8 * lane)) & MASK32)
        elif op == 0x13:     # OP-IMM
            sh = rs2
            if f3 == 1 and f7 != 0 or f3 == 5 and f7 not in (0, 0x20):
                illegal()
            else:
                name = {0: "addi", 2: "slti", 3: "sltiu", 4: "xori", 6: "ori", 7: "andi", 1: "slli"}.get(f3)
                a = use1()
                if f3 == 0:
                    r = a + imm_i
                elif f3 == 2:
                    r = int(s32(a) < imm_i)
                elif f3 == 3:
                    r = int(a < (imm_i & MASK32))
                elif f3 == 4:
                    r = a ^ (imm_i & MASK32)
                elif f3 == 6:
                    r = a | (imm_i & MASK32)
                elif f3 == 7:
                    r = a & (imm_i & MASK32)
                elif f3 == 1:
                    r = a << sh
                else:
                    name = "srai" if f7 == 0x20 else "srli"
                    r = (s32(a) >> sh) if f7 == 0x20 else (a >> sh)
                write(r)
        elif op == 0x33:     # OP
            ok = {(0, 0), (0x20, 0), (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0x20, 5), (0, 6), (0, 7)}
            if (f7, f3) not in ok:
                illegal()
            else:
                name = {(0, 0): "add", (0x20, 0): "sub", (0, 1): "sll", (0, 2): "slt", (0, 3): "sltu", (0, 4): "xor",
                        (0, 5): "srl", (0x20, 5): "sra", (0, 6): "or", (0, 7): "and"}[(f7, f3)]
                a, b = use1(), use2()
                sh = b & 31
                r = {"add": a + b, "sub": a - b, "sll": a << sh, "slt": int(s32(a) < s32(b)), "sltu": int(a < b),
                     "xor": a ^ b, "srl": a >> sh, "sra": s32(a) >> sh, "or": a | b, "and": a & b}[name]
                write(r)
        elif op == 0x0F:     # FENCE
            if f3 != 0:
                illegal()
            else:
                name = "fence"
        elif op == 0x73:     # SYSTEM
            if insn in (0x00000073, 0x00100073):
                name = "ecall" if insn == 0x73 else "ebreak"
                rec["halt"] = 1
                self.halted = True
            else:
                illegal()
        else:
            illegal()
        if rec["next_pc"] & 3 and not self.halted:   # unreachable now that a misaligned target traps; kept as a guard on the model itself
            raise ISSError("pc=%08x: jump/branch target %08x is not 4-byte aligned" % (pc, rec["next_pc"]))
        if name:
            self.mix[name] = self.mix.get(name, 0) + 1
        if rec["halt"]:
            self.halted = True
        self.pc = rec["next_pc"]
        self.order += 1
        return rec


def load_hex(path):
    with open(path) as f:
        return [int(l.strip(), 16) for l in f if l.strip()]


def run(words, max_insns=2_000_000, mem_words=16384, strict=True, reset_pc=0x1000):
    iss = ISS(words, mem_words, strict, reset_pc)
    recs = []
    while not iss.halted:
        if iss.order >= max_insns:
            raise ISSError("no ECALL/EBREAK after %d instructions" % max_insns)
        recs.append(iss.step())
    return recs, iss


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hex")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--max-insns", type=int, default=2_000_000)
    ap.add_argument("--mem-words", type=int, default=16384)
    ap.add_argument("--reset-pc", type=lambda v: int(v, 0), default=0x1000)
    ap.add_argument("--dump", help="write the final memory image (one word per line)")
    ap.add_argument("--allow-uninit", action="store_true", help="do not reject reads of never-written registers")
    a = ap.parse_args(argv)
    try:
        recs, iss = run(load_hex(a.hex), a.max_insns, a.mem_words, not a.allow_uninit, a.reset_pc)
    except ISSError as e:
        print("rviss: invalid program: %s" % e, file=sys.stderr)
        return 3
    with open(a.out, "w") as f:
        for r in recs:
            f.write(fmt(r) + "\n")
    if a.dump:
        with open(a.dump, "w") as f:
            for i in range(0, len(iss.mem), 4):
                f.write("%08x\n" % int.from_bytes(iss.mem[i:i + 4], "little"))
    print("rviss: %d instructions, exit a0=%d" % (len(recs), s32(iss.x[10])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
