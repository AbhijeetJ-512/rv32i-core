#!/usr/bin/env python3
"""fmax.py - minimum clock period and area of every core configuration, with the method checked.

    fmax.py [--out results/ppa.md]

Method (pre-layout, so every number is an UPPER bound on period / LOWER bound on frequency quality is not claimed):
  1. Yosys maps the core with the timing-driven ABC script (buffer insertion + gate sizing for best delay, independent of
     any target period; scripts/abc_speed.script) and a default `abc -D` mapping for comparison.
  2. OpenSTA times the netlist with constraints/rv32i.sdc at a base period of 10 ns. All constraints except the clock
     period are absolute (memory read 2.0 ns in, address/write data 1.0 ns out), so the worst setup slack moves one for
     one with the period:   T_min = 10 ns - WNS(10 ns).
  3. The method is verified, not assumed: STA is re-run at 1.02 x T_min (must meet, WNS >= 0) and 0.98 x T_min (must fail).
Not included: clock tree, wires, placement, hold fixing, other corners, memory access beyond the 2.0/1.0 ns budget.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ppa  # noqa: E402

CONFIGS = [("pipe", 0, "speed", 0), ("pipe", 0, "speed", 1), ("pipe", 1, "speed", 0), ("pipe", 1, "speed", 1), ("1cyc", 0, "speed", 1),
           ("pipe", 0, "default", 1), ("pipe", 1, "default", 1), ("1cyc", 0, "default", 1)]


def one(core, bp, abc, fwd):
    r = ppa.run_cfg(core, bp, 10.0, abc=abc, fwd=fwd)
    if "error" in r:
        return dict(core=core, bp=bp, abc=abc, fwd=fwd, error=r["error"])
    out = os.path.join(ppa.ROOT, "build", "ppa", r["name"])
    top = "rv32i_core" if core == "pipe" else "rv32i_core_1cyc"
    tmin = 10.0 - r["wns_ns"]
    res = dict(core=core, bp=bp, abc=abc, fwd=fwd, cells=r["cells"], area=r["area_um2"], flops=r["flops"], wns10=r["wns_ns"],
               tmin=tmin, fmax=1000.0 / tmin, start=r["startpoint"], end=r["endpoint"], power_w=r["power_w"], hold=r["hold_wns_ns"])
    for tag, factor, must in (("hi", 1.02, True), ("lo", 0.98, False)):
        err = ppa.sta_only(out, top, tmin * factor, sub="verify_" + tag)
        if err:
            res["error"] = err
            return res
        w = ppa.read_wns(out, "verify_" + tag)
        res["wns_" + tag] = w
        res["verify_" + tag] = (w >= 0) == must
    res["verified"] = res["verify_hi"] and res["verify_lo"]
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ppa.ROOT, "results", "ppa.md"))
    ap.add_argument("--only-speed", action="store_true")
    a = ap.parse_args()
    cfgs = [c for c in CONFIGS if not a.only_speed or c[2] == "speed"]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    os.makedirs(os.path.join(ppa.ROOT, "build", "ppa"), exist_ok=True)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(4) as ex:
        res = list(ex.map(lambda c: one(*c), cfgs))
    json.dump(res, open(os.path.join(ppa.ROOT, "results", "ppa.json"), "w"), indent=1)
    L = ["# Synthesis and timing of the RV32I cores (measured: Yosys 0.33 + OpenSTA, Sky130 HD tt_025C_1v80, pre-layout)", "",
         "RVFI trace port removed (RVFI_EN=0). Ideal clock, no wires, no placement. Memory budget in the SDC: read data 2.0 ns after the edge, "
         "address/write data 1.0 ns before the next edge (assumption, identical for all rows). `speed` = timing-driven ABC script, "
         "`default` = `abc -D 10000`.", "",
         "| core | mapping | cells | area (um^2) | flip-flops | T_min (ns) | F_max (MHz) | method check (+2 % meets, -2 % fails) |",
         "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in res:
        name = {"pipe": "5-stage BP_MODE=%d FWD_PRECOMP=%d" % (r["bp"], r["fwd"]), "1cyc": "single-cycle"}[r["core"]]
        if "error" in r:
            L.append("| %s | %s | ERROR | | | | | %s |" % (name, r["abc"], r["error"][:80]))
            continue
        L.append("| %s | %s | %d | %.0f | %d | %.3f | %.1f | %s |" % (
            name, r["abc"], r["cells"], r["area"], r["flops"], r["tmin"], r["fmax"],
            "verified (WNS %+.3f / %+.3f ns)" % (r["wns_hi"], r["wns_lo"]) if r["verified"] else "NOT VERIFIED (%+.3f / %+.3f)" % (r["wns_hi"], r["wns_lo"])))
    open(a.out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
