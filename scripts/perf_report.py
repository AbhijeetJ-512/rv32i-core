#!/usr/bin/env python3
"""perf_report.py - execution time = measured cycles x measured minimum period, pipelined cores vs the single-cycle baseline.

    perf_report.py [--out results/performance.md]

Inputs (both produced by this repository's own flows, nothing typed in by hand):
  results/ppa.json          T_min per core configuration (scripts/fmax.py: Yosys + OpenSTA, pre-layout)
  build/bench_out/*.stats   cycles and instructions per benchmark and BP_MODE (scripts/cpi_report.py, Verilator RTL simulation)
  build/sc_out/*.stats      the same for the single-cycle core (CPI = 1 by construction; measured, not assumed)
Method limits, stated once here and repeated in the output: pre-layout timing; memories are ideal and outside the core (2.0 ns
read / 1.0 ns write budget, assumption); the single-cycle core's T_min is the tool's max over three port-bounded path
classes, so it does NOT add the two memory accesses it would serialise in one cycle - its figure is therefore optimistic and
the pipelined speed-up a LOWER bound.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def stats(path):
    return {k: int(v) for k, v in (l.split("=") for l in open(path).read().split())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "performance.md"))
    a = ap.parse_args()
    ppa = json.load(open(os.path.join(ROOT, "results", "ppa.json")))
    tmin = {}
    for r in ppa:
        if r.get("abc") != "speed" or "error" in r:
            continue
        key = "1cyc" if r["core"] == "1cyc" else "bp%d_fwd%d" % (r["bp"], r["fwd"])
        tmin[key] = r["tmin"]
    names = sorted(f[:-2] for f in os.listdir(os.path.join(ROOT, "tests", "bench")) if f.endswith(".S"))
    cols = [("1cyc", "single-cycle"), ("bp0_fwd0", "5-stage BP0, EX-compare fwd"), ("bp0_fwd1", "5-stage BP0, ID-precomputed fwd"),
            ("bp1_fwd1", "5-stage BP1, ID-precomputed fwd")]
    L = ["# Performance: measured cycles x measured minimum period", "",
         "T_min (ns, pre-layout, timing-driven mapping): " + ", ".join("%s = %.3f" % (lab, tmin[k]) for k, lab in cols), "",
         "Execution time in microseconds (cycles x T_min). Lower is better. Speed-up is relative to the single-cycle core.", "",
         "| benchmark | instructions | " + " | ".join("%s (us)" % lab for _, lab in cols) + " | best 5-stage speed-up |",
         "|---|---:|" + "---:|" * len(cols) + "---:|"]
    tot = {k: 0.0 for k, _ in cols}
    tot_i = 0
    for n in names:
        b0 = stats(os.path.join(ROOT, "build", "bench_out", "%s.bp0.stats" % n))
        b1 = stats(os.path.join(ROOT, "build", "bench_out", "%s.bp1.stats" % n))
        sc = stats(os.path.join(ROOT, "build", "sc_out", "%s.bp0.stats" % n))
        cyc = {"1cyc": sc["cycles"], "bp0_fwd0": b0["cycles"], "bp0_fwd1": b0["cycles"], "bp1_fwd1": b1["cycles"]}
        t = {k: cyc[k] * tmin[k] / 1000.0 for k, _ in cols}
        for k in t:
            tot[k] += t[k]
        tot_i += b0["instret"]
        L.append("| %s | %d | %s | %.2fx |" % (n, b0["instret"], " | ".join("%.1f" % t[k] for k, _ in cols), t["1cyc"] / min(t[k] for k in t if k != "1cyc")))
    L.append("| **all** | %d | %s | **%.2fx** |" % (tot_i, " | ".join("%.1f" % tot[k] for k, _ in cols), tot["1cyc"] / min(tot[k] for k in tot if k != "1cyc")))
    L += ["", "Speed-up of each 5-stage configuration over the single-cycle core, all benchmarks together: " +
          ", ".join("%s %.2fx" % (lab, tot["1cyc"] / tot[k]) for k, lab in cols if k != "1cyc"), "",
          "Read with: pre-layout, ideal memories (2.0 ns read / 1.0 ns write budget assumed), 7 small kernels (%d instructions), not a standard benchmark suite. "
          "The single-cycle figure is optimistic (see the script header), so these speed-ups are lower bounds under this model." % tot_i]
    open(a.out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
