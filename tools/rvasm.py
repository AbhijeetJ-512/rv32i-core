#!/usr/bin/env python3
"""rvasm.py - a small RV32I assembler (no external toolchain needed).

    rvasm.py prog.S -o prog.hex [-l prog.lst] [--text-base 0x1000] [--data-base 0x8000] [--mem-words 16384]

Output: one 32-bit word per line in hex ($readmemh format) for a unified memory that starts at address 0.
`.text` is placed at --text-base (default 0x1000), `.data` at --data-base (default 0x8000); addresses below 0x1000
are left for the register dump written by the test epilogue. Every RV32I base instruction is supported, plus the usual pseudo
instructions (nop li la mv not neg seqz snez sltz sgtz j jal jr jalr ret call beqz bnez blez bgez bltz bgtz bgt ble
bgtu bleu) and the directives .text .data .org .word .half .byte .space .align .equ .globl.
Expressions: integers, labels, + - * << >> & | ~ ( ) and %hi(x) / %lo(x).

The encodings come straight from the RISC-V unprivileged specification (RV32I base instruction formats).
"""
import argparse
import re
import sys

IDENT = r"(?<![\w.])[A-Za-z_.][\w.]*"   # an identifier, not the tail of a hex literal like 0x12ab
REGS = {}
for i in range(32):
    REGS["x%d" % i] = i
for name, n in {"zero": 0, "ra": 1, "sp": 2, "gp": 3, "tp": 4, "t0": 5, "t1": 6, "t2": 7, "s0": 8, "fp": 8, "s1": 9}.items():
    REGS[name] = n
for i in range(8):
    REGS["a%d" % i] = 10 + i
for i in range(2, 12):
    REGS["s%d" % i] = 16 + i
for i in range(3, 7):
    REGS["t%d" % i] = 25 + i

R_OPS = {  # funct7, funct3
    "add": (0x00, 0), "sub": (0x20, 0), "sll": (0x00, 1), "slt": (0x00, 2), "sltu": (0x00, 3),
    "xor": (0x00, 4), "srl": (0x00, 5), "sra": (0x20, 5), "or": (0x00, 6), "and": (0x00, 7),
}
I_OPS = {"addi": 0, "slti": 2, "sltiu": 3, "xori": 4, "ori": 6, "andi": 7}
SH_OPS = {"slli": (0x00, 1), "srli": (0x00, 5), "srai": (0x20, 5)}
LOADS = {"lb": 0, "lh": 1, "lw": 2, "lbu": 4, "lhu": 5}
STORES = {"sb": 0, "sh": 1, "sw": 2}
BRANCHES = {"beq": 0, "bne": 1, "blt": 4, "bge": 5, "bltu": 6, "bgeu": 7}


class AsmError(Exception):
    pass


def to_s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


class Asm:
    def __init__(self, data_base=0x8000, mem_words=16384, text_base=0x1000):
        self.data_base = data_base
        self.mem_words = mem_words
        self.syms = {}
        self.items = []   # (addr, kind, payload, srcline, lineno)
        self.sec = "text"
        self.cur = {"text": text_base, "data": data_base}

    # ---------------------------------------------------------------- expressions
    def ev(self, expr, lineno, pass2=True, pc=0):
        e = expr.strip()
        e = re.sub(r"%hi\(([^)]*)\)", lambda m: "((((%s)+0x800)>>12)&0xFFFFF)" % m.group(1), e)
        e = re.sub(r"%lo\(([^)]*)\)", lambda m: "_lo12(%s)" % m.group(1), e)
        if not re.fullmatch(r"[\w\s+\-*()<>&|~.,]+", e):
            raise AsmError("line %d: bad expression %r" % (lineno, expr))
        names = dict(self.syms)

        def _lo12(v):
            v &= 0xFFF
            return v - 0x1000 if v & 0x800 else v

        names["_lo12"] = _lo12
        names["__builtins__"] = {}
        # unknown identifiers: error in pass 2, 0 in pass 1 (sizes never depend on them)
        for tok in re.findall(IDENT, e):
            if tok not in names:
                if pass2:
                    raise AsmError("line %d: undefined symbol %r" % (lineno, tok))
                names[tok] = 0
        try:
            return int(eval(e, names))  # noqa: S307 - whitelisted characters, empty builtins
        except Exception as ex:
            raise AsmError("line %d: cannot evaluate %r (%s)" % (lineno, expr, ex))

    def reg(self, tok, lineno):
        t = tok.strip().lower()
        if t not in REGS:
            raise AsmError("line %d: bad register %r" % (lineno, tok))
        return REGS[t]

    @staticmethod
    def split_ops(s):
        out, depth, cur = [], 0, ""
        for ch in s:
            if ch == "(":
                depth += 1
            if ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                out.append(cur.strip())
                cur = ""
            else:
                cur += ch
        if cur.strip():
            out.append(cur.strip())
        return out

    def mem_operand(self, s, lineno, pass2, pc):
        m = re.fullmatch(r"(.*)\(\s*([\w]+)\s*\)", s.strip())
        if not m:
            raise AsmError("line %d: bad memory operand %r" % (lineno, s))
        off = m.group(1).strip() or "0"
        return self.ev(off, lineno, pass2, pc), self.reg(m.group(2), lineno)

    # ---------------------------------------------------------------- pass 1: layout
    def pseudo_size(self, op, ops, lineno):
        if op == "li":
            try:
                v = to_s32(self.ev(ops[1], lineno, pass2=False))
                known = all(t in self.syms for t in re.findall(IDENT, ops[1]))
            except AsmError:
                return 2
            return 1 if (known and -2048 <= v <= 2047) else 2
        if op in ("la", "call"):
            return 2 if op == "la" else 1
        return 1

    def pass1(self, lines):
        for lineno, raw in enumerate(lines, 1):
            line = re.sub(r"(#|//).*$", "", raw).strip()
            while True:
                m = re.match(r"^([A-Za-z_.][\w.]*)\s*:(.*)$", line)
                if not m:
                    break
                lab = m.group(1)
                if lab in self.syms:
                    raise AsmError("line %d: duplicate label %r" % (lineno, lab))
                self.syms[lab] = self.cur[self.sec]
                line = m.group(2).strip()
            if not line:
                continue
            parts = line.split(None, 1)
            op = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""
            ops = self.split_ops(rest)
            if op.startswith("."):
                self.directive(op, ops, rest, lineno)
                continue
            n = self.pseudo_size(op, ops, lineno)
            self.items.append((self.cur[self.sec], "insn", (op, ops), raw.strip(), lineno))
            self.cur[self.sec] += 4 * n

    def directive(self, op, ops, rest, lineno):
        a = self.cur[self.sec]
        if op in (".text", ".data"):
            self.sec = op[1:]
        elif op == ".globl" or op == ".global" or op == ".section":
            pass
        elif op == ".org":
            self.cur[self.sec] = self.ev(ops[0], lineno, pass2=False)
        elif op == ".equ" or op == ".set":
            self.syms[ops[0]] = self.ev(ops[1], lineno, pass2=False)
        elif op == ".align":
            k = 1 << self.ev(ops[0], lineno, pass2=False)
            self.cur[self.sec] = (a + k - 1) // k * k
        elif op == ".space" or op == ".zero":
            n = self.ev(ops[0], lineno, pass2=False)
            self.items.append((a, "bytes", [0] * n, rest, lineno))
            self.cur[self.sec] += n
        elif op in (".word", ".half", ".byte"):
            size = {".word": 4, ".half": 2, ".byte": 1}[op]
            self.items.append((a, "data", (size, ops), rest, lineno))
            self.cur[self.sec] += size * len(ops)
        else:
            raise AsmError("line %d: unknown directive %s" % (lineno, op))

    # ---------------------------------------------------------------- encoders
    @staticmethod
    def enc_r(f7, rs2, rs1, f3, rd, op):
        return (f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    def enc_i(self, imm, rs1, f3, rd, op, lineno):
        if not -2048 <= imm <= 2047:
            raise AsmError("line %d: I-immediate %d out of range" % (lineno, imm))
        return ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) | (rd << 7) | op

    def enc_s(self, imm, rs2, rs1, f3, lineno):
        if not -2048 <= imm <= 2047:
            raise AsmError("line %d: S-immediate %d out of range" % (lineno, imm))
        return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | ((imm & 0x1F) << 7) | 0x23

    def enc_b(self, off, rs2, rs1, f3, lineno):
        if off & 1 or not -4096 <= off <= 4094:
            raise AsmError("line %d: branch offset %d out of range/odd" % (lineno, off))
        o = off & 0x1FFF
        return (((o >> 12) & 1) << 31) | (((o >> 5) & 0x3F) << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) | \
               (((o >> 1) & 0xF) << 8) | (((o >> 11) & 1) << 7) | 0x63

    @staticmethod
    def enc_u(imm20, rd, op):
        return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | op

    def enc_j(self, off, rd, lineno):
        if off & 1 or not -(1 << 20) <= off < (1 << 20):
            raise AsmError("line %d: jump offset %d out of range/odd" % (lineno, off))
        o = off & 0x1FFFFF
        return (((o >> 20) & 1) << 31) | (((o >> 1) & 0x3FF) << 21) | (((o >> 11) & 1) << 20) | \
               (((o >> 12) & 0xFF) << 12) | (rd << 7) | 0x6F

    # ---------------------------------------------------------------- pass 2: encode
    def encode(self, addr, op, ops, lineno):
        R = lambda i: self.reg(ops[i], lineno)  # noqa: E731
        E = lambda i: self.ev(ops[i], lineno, True, addr)  # noqa: E731
        want = lambda n: None if len(ops) == n else (_ for _ in ()).throw(  # noqa: E731
            AsmError("line %d: %s expects %d operands" % (lineno, op, n)))
        if op in R_OPS:
            want(3)
            f7, f3 = R_OPS[op]
            return [self.enc_r(f7, R(2), R(1), f3, R(0), 0x33)]
        if op in I_OPS:
            want(3)
            return [self.enc_i(to_s32(E(2)), R(1), I_OPS[op], R(0), 0x13, lineno)]
        if op in SH_OPS:
            want(3)
            f7, f3 = SH_OPS[op]
            sh = E(2)
            if not 0 <= sh <= 31:
                raise AsmError("line %d: shift amount %d" % (lineno, sh))
            return [self.enc_r(f7, sh, R(1), f3, R(0), 0x13)]
        if op in LOADS:
            want(2)
            off, rs1 = self.mem_operand(ops[1], lineno, True, addr)
            return [self.enc_i(off, rs1, LOADS[op], R(0), 0x03, lineno)]
        if op in STORES:
            want(2)
            off, rs1 = self.mem_operand(ops[1], lineno, True, addr)
            return [self.enc_s(off, R(0), rs1, STORES[op], lineno)]
        if op in BRANCHES:
            want(3)
            return [self.enc_b(E(2) - addr, R(1), R(0), BRANCHES[op], lineno)]
        if op == "lui":
            want(2)
            return [self.enc_u(E(1) & 0xFFFFF, R(0), 0x37)]
        if op == "auipc":
            want(2)
            return [self.enc_u(E(1) & 0xFFFFF, R(0), 0x17)]
        if op == "jal":
            if len(ops) == 1:
                return [self.enc_j(E(0) - addr, 1, lineno)]
            want(2)
            return [self.enc_j(E(1) - addr, R(0), lineno)]
        if op == "jalr":
            if len(ops) == 1:
                return [self.enc_i(0, R(0), 0, 1, 0x67, lineno)]
            if len(ops) == 2 and "(" in ops[1]:
                off, rs1 = self.mem_operand(ops[1], lineno, True, addr)
                return [self.enc_i(off, rs1, 0, R(0), 0x67, lineno)]
            want(3)
            return [self.enc_i(E(2), R(1), 0, R(0), 0x67, lineno)]
        if op == "ecall":
            return [0x00000073]
        if op == "ebreak":
            return [0x00100073]
        if op == "fence":
            return [0x0FF0000F]
        # ---- pseudo instructions
        if op == "nop":
            return [self.enc_i(0, 0, 0, 0, 0x13, lineno)]
        if op == "mv":
            want(2)
            return [self.enc_i(0, R(1), 0, R(0), 0x13, lineno)]
        if op == "not":
            want(2)
            return [self.enc_i(-1, R(1), 4, R(0), 0x13, lineno)]
        if op == "neg":
            want(2)
            return [self.enc_r(0x20, R(1), 0, 0, R(0), 0x33)]
        if op == "seqz":
            want(2)
            return [self.enc_i(1, R(1), 3, R(0), 0x13, lineno)]
        if op == "snez":
            want(2)
            return [self.enc_r(0, R(1), 0, 3, R(0), 0x33)]
        if op == "sltz":
            want(2)
            return [self.enc_r(0, 0, R(1), 2, R(0), 0x33)]
        if op == "sgtz":
            want(2)
            return [self.enc_r(0, R(1), 0, 2, R(0), 0x33)]
        if op == "j":
            want(1)
            return [self.enc_j(E(0) - addr, 0, lineno)]
        if op == "call":
            want(1)
            return [self.enc_j(E(0) - addr, 1, lineno)]
        if op == "jr":
            want(1)
            return [self.enc_i(0, R(0), 0, 0, 0x67, lineno)]
        if op == "ret":
            return [self.enc_i(0, 1, 0, 0, 0x67, lineno)]
        zero_br = {"beqz": ("beq", 0), "bnez": ("bne", 0), "blez": ("bge", 1), "bgez": ("bge", 0),
                   "bltz": ("blt", 0), "bgtz": ("blt", 1)}
        if op in zero_br:
            want(2)
            base, swap = zero_br[op]
            rs = R(0)
            a, b = (0, rs) if swap else (rs, 0)
            return [self.enc_b(E(1) - addr, b, a, BRANCHES[base], lineno)]
        swap_br = {"bgt": "blt", "ble": "bge", "bgtu": "bltu", "bleu": "bgeu"}
        if op in swap_br:
            want(3)
            return [self.enc_b(E(2) - addr, R(0), R(1), BRANCHES[swap_br[op]], lineno)]
        if op == "li":
            want(2)
            v = to_s32(E(1))
            rd = R(0)
            if -2048 <= v <= 2047 and self.pseudo_size("li", ops, lineno) == 1:
                return [self.enc_i(v, 0, 0, rd, 0x13, lineno)]
            lo = v & 0xFFF
            lo = lo - 0x1000 if lo & 0x800 else lo
            hi = ((v - lo) >> 12) & 0xFFFFF
            return [self.enc_u(hi, rd, 0x37), self.enc_i(lo, rd, 0, rd, 0x13, lineno)]
        if op == "la":
            want(2)
            v = E(1)
            rd = R(0)
            lo = v & 0xFFF
            lo = lo - 0x1000 if lo & 0x800 else lo
            hi = ((v - lo) >> 12) & 0xFFFFF
            return [self.enc_u(hi, rd, 0x37), self.enc_i(lo, rd, 0, rd, 0x13, lineno)]
        raise AsmError("line %d: unknown instruction %r" % (lineno, op))

    def assemble(self, text):
        lines = text.splitlines()
        self.pass1(lines)
        mem = {}   # byte address -> value
        listing = []
        for addr, kind, payload, src, lineno in self.items:
            if kind == "insn":
                op, ops = payload
                words = self.encode(addr, op, ops, lineno)
                for i, w in enumerate(words):
                    for b in range(4):
                        mem[addr + 4 * i + b] = (w >> (8 * b)) & 0xFF
                    listing.append("%08x: %08x  %s" % (addr + 4 * i, w, src if i == 0 else ""))
            elif kind == "data":
                size, exprs = payload
                for i, ex in enumerate(exprs):
                    v = self.ev(ex, lineno, True, addr) & ((1 << (8 * size)) - 1)
                    for b in range(size):
                        mem[addr + size * i + b] = (v >> (8 * b)) & 0xFF
                listing.append("%08x: .data %s" % (addr, src))
            else:
                for i, v in enumerate(payload):
                    mem[addr + i] = v
        top = max(mem) + 1 if mem else 0
        if top > self.mem_words * 4:
            raise AsmError("program (%d bytes) does not fit in %d words" % (top, self.mem_words))
        return mem, listing


def to_words(mem, mem_words):
    words = [0] * mem_words
    for a, v in mem.items():
        words[a // 4] |= v << (8 * (a % 4))
    return words


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("-l", "--listing")
    ap.add_argument("--data-base", type=lambda s: int(s, 0), default=0x8000)
    ap.add_argument("--text-base", type=lambda s: int(s, 0), default=0x1000)
    ap.add_argument("--mem-words", type=int, default=16384)
    a = ap.parse_args(argv)
    asm = Asm(a.data_base, a.mem_words, a.text_base)
    try:
        mem, listing = asm.assemble(open(a.src).read())
    except AsmError as e:
        print("rvasm: %s: %s" % (a.src, e), file=sys.stderr)
        return 2
    words = to_words(mem, a.mem_words)
    with open(a.out, "w") as f:
        for w in words:
            f.write("%08x\n" % w)
    if a.listing:
        with open(a.listing, "w") as f:
            f.write("\n".join(listing) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
