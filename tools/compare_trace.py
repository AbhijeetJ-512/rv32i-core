#!/usr/bin/env python3
"""compare_trace.py rtl.trace iss.trace - lock-step comparison of the RTL retirement trace with the ISS trace.

Every retired instruction must agree on every field: order, pc, instruction word, next pc, source register
addresses and values, destination register and value, memory address, byte masks, load data and store data.
Memory data are compared only in the byte lanes the mask marks (RVFI leaves the other lanes unspecified).
Exit 0 only if the traces have the same length and every line matches. Prints the first mismatch with context.
"""
import sys

FIELDS = ("order pc insn next_pc rs1_addr rs1_rdata rs2_addr rs2_rdata rd_addr rd_wdata "
          "mem_addr mem_rmask mem_wmask mem_rdata mem_wdata halt trap").split()
DEC = {"order", "rs1_addr", "rs2_addr", "rd_addr", "halt", "trap"}


def parse(line):
    t = line.split()
    if len(t) != len(FIELDS):
        raise ValueError("bad trace line: %r" % line)
    return {f: int(v, 10 if f in DEC else 16) for f, v in zip(FIELDS, t)}


def lane_mask(m):
    return sum(0xFF << (8 * i) for i in range(4) if m >> i & 1)


def canon(r):
    r = dict(r)
    r["mem_rdata"] &= lane_mask(r["mem_rmask"])
    r["mem_wdata"] &= lane_mask(r["mem_wmask"])
    return r


def compare(rtl_lines, iss_lines):
    n = min(len(rtl_lines), len(iss_lines))
    for i in range(n):
        a, b = canon(parse(rtl_lines[i])), canon(parse(iss_lines[i]))
        diff = [f for f in FIELDS if a[f] != b[f]]
        if diff:
            return i, diff, a, b
    if len(rtl_lines) != len(iss_lines):
        return n, ["length"], None, None
    return None


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    rtl = [l for l in open(argv[1]) if l.strip()]
    iss = [l for l in open(argv[2]) if l.strip()]
    res = compare(rtl, iss)
    if res is None:
        print("compare_trace: MATCH, %d instructions" % len(rtl))
        return 0
    i, diff, a, b = res
    print("compare_trace: MISMATCH at instruction #%d (fields: %s); rtl has %d lines, iss has %d" % (
        i, ", ".join(diff), len(rtl), len(iss)))
    if a:
        for f in diff:
            print("  %-10s rtl=%08x  iss=%08x" % (f, a[f], b[f]))
        print("  pc=%08x insn=%08x" % (b["pc"], b["insn"]))
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
