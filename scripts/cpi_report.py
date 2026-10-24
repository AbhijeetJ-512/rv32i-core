#!/usr/bin/env python3
"""cpi_report.py - run the benchmarks in both branch modes and tabulate CPI and where the bubbles come from.

    cpi_report.py [--out results/cpi.md]

Cycle accounting (checked for every run, the script fails if it does not hold):
    accounted = 4 (pipeline fill) + instret + load-use stalls + 2 x EX redirects + 1 x ID redirects
    BP_MODE 0: cycles == accounted exactly (the bubble sources cannot overlap).
    BP_MODE 1: cycles <= accounted, the difference being "overlap": a flush can squash a slot that an earlier ID
               redirect had already turned into a bubble, so the same lost slot is counted by two sources.
The testbench counts the three bubble sources from the RTL's own stall_d / redirect_ex / redirect_id signals, and
`cycles` and `instret` independently (cycles since reset release, retired instructions on the RVFI port), so the
identity is a cross-check of the counters, not a definition.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_tests  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "cpi.md"))
    a = ap.parse_args()
    outdir = os.path.join(ROOT, "build", "bench_out")
    bench = os.path.join(ROOT, "tests", "bench")
    rc = run_tests.main(["--tests", bench, "--out", outdir, "--bp", "0", "1"])
    if rc != 0:
        print("benchmarks failed")
        return 1
    names = sorted(f[:-2] for f in os.listdir(bench) if f.endswith(".S"))
    rows, bad = [], []
    tot = {0: [0, 0], 1: [0, 0]}
    for n in names:
        row = [n]
        for bp in (0, 1):
            st = dict(l.split("=") for l in open(os.path.join(outdir, "%s.bp%d.stats" % (n, bp))).read().split())
            st = {k: int(v) for k, v in st.items()}
            pred = 4 + st["instret"] + st["lu_stalls"] + 2 * st["ex_redirects"] + st["id_redirects"]
            st["overlap"] = pred - st["cycles"]
            if (bp == 0 and st["overlap"] != 0) or (bp == 1 and st["overlap"] < 0):
                bad.append("%s bp%d: cycles %d vs accounted %d" % (n, bp, st["cycles"], pred))
            tot[bp][0] += st["cycles"]
            tot[bp][1] += st["instret"]
            row.append(st)
        rows.append(row)
    lines = ["# CPI by benchmark and branch mode (measured, Verilator RTL simulation, ideal 1-cycle memories)", "",
             "| benchmark | instructions | BP_MODE 0 cycles | CPI | load-use stalls | EX redirects | BP_MODE 1 cycles | CPI | ID redirects | EX redirects | overlap | CPI change |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n, s0, s1 in rows:
        c0, c1 = s0["cycles"] / s0["instret"], s1["cycles"] / s1["instret"]
        lines.append("| %s | %d | %d | %.3f | %d | %d | %d | %.3f | %d | %d | %d | %+.1f %% |" % (
            n, s0["instret"], s0["cycles"], c0, s0["lu_stalls"], s0["ex_redirects"], s1["cycles"], c1,
            s1["id_redirects"], s1["ex_redirects"], s1["overlap"], 100 * (c1 / c0 - 1)))
    lines.append("| **all (sum)** | %d | %d | %.3f | | | %d | %.3f | | | | %+.1f %% |" % (
        tot[0][1], tot[0][0], tot[0][0] / tot[0][1], tot[1][0], tot[1][0] / tot[1][1],
        100 * ((tot[1][0] / tot[1][1]) / (tot[0][0] / tot[0][1]) - 1)))
    lines += ["", "Cycle accounting: accounted = 4 + instret + load-use stalls + 2 x EX redirects + ID redirects. BP_MODE 0: cycles == accounted "
              "(exact). BP_MODE 1: cycles <= accounted; `overlap` = accounted - cycles, slots squashed twice. Check: %s" %
              ("holds for all %d runs" % (2 * len(rows)) if not bad else "VIOLATED: " + "; ".join(bad))]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
