#!/usr/bin/env python3
"""ppa.py - synthesise (Yosys) and time (OpenSTA) one rv32i core configuration at one or more target periods.

    ppa.py --core pipe --bp 0 --periods 4 5 6 --jobs 3
    ppa.py --core 1cyc --periods 8 10 12

Per period: `abc -D <period>` maps the netlist to Sky130 HD, OpenSTA times it with constraints/rv32i.sdc at that same
period. Pre-layout: ideal clock, no wire parasitics, typical corner, RVFI trace port removed (RVFI_EN=0).
A period "meets" when the worst setup slack is >= 0. Results go to build/ppa/<cfg>/ and one JSON line per run is
appended to build/ppa/results.jsonl.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RTL = ["rv32i_alu.sv", "rv32i_branch.sv", "rv32i_regfile.sv", "rv32i_decode.sv", "rv32i_lsu.sv"]
PIPE = RTL + ["rv32i_hazard.sv", "rv32i_core.sv"]
ONE = RTL + ["rv32i_core_1cyc.sv"]


def sta_only(out, top, period, sub=""):
    """OpenSTA on out/synth.v at `period`; reports to out/<sub>/. Returns an error string or None."""
    rep = os.path.join(out, sub) if sub else out
    os.makedirs(rep, exist_ok=True)
    env = dict(os.environ, NETLIST=os.path.join(out, "synth.v"), TOP=top, SDC=os.path.join(ROOT, "constraints", "rv32i.sdc"),
               CLK_PERIOD_NS=repr(float(period)), OUTDIR=rep)
    r = subprocess.run(["sta", "-no_splash", "-exit", os.path.join(ROOT, "scripts", "sta_template.tcl")], env=env, capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0 or not os.path.exists(os.path.join(rep, "timing.txt")):
        return "sta failed: " + (r.stdout + r.stderr)[-400:]
    return None


def read_wns(out, sub=""):
    tim = open(os.path.join(out, sub, "timing.txt")).read()
    return float(re.search(r"worst slack max (-?[\d.]+)", tim).group(1))


def run_cfg(core, bp, period, rtl_dir=None, tag="", abc="speed", fwd=1):
    rtl_dir = rtl_dir or os.path.join(ROOT, "rtl")
    top = "rv32i_core" if core == "pipe" else "rv32i_core_1cyc"
    name = "%s%s%s_%s_p%g%s" % (core, ("_bp%d" % bp) if core == "pipe" else "", ("_fwd%d" % fwd) if core == "pipe" else "", abc, period, tag)
    out = os.path.join(ROOT, "build", "ppa", name)
    os.makedirs(out, exist_ok=True)
    srcs = " ".join(os.path.join(rtl_dir, f) for f in (PIPE if core == "pipe" else ONE))
    lib = os.path.join(ROOT, "build", "sky130hd_synth.lib")
    params = ("-set BP_MODE %d -set FWD_PRECOMP %d" % (bp, fwd)) if core == "pipe" else ""
    ys = open(os.path.join(ROOT, "scripts", "synth_template.ys")).read()
    abc_cmd = ("abc -constr %s -script %s -liberty %s" % (os.path.join(ROOT, "scripts", "abc_speed.constr"),
               os.path.join(ROOT, "scripts", "abc_speed.script"), lib)) if abc == "speed" else \
              ("abc -D %d -liberty %s" % (int(period * 1000), lib))
    for k, v in {"@ABC@": abc_cmd, "@RTLDIR@": rtl_dir, "@SOURCES@": srcs, "@LIB@": lib, "@TOP@": top, "@PARAMS@": params,
                 "@PERIOD_PS@": str(int(period * 1000)), "@OUTDIR@": out}.items():
        ys = ys.replace(k, v)
    open(os.path.join(out, "synth.ys"), "w").write(ys)
    r = subprocess.run(["yosys", "-l", os.path.join(out, "yosys.log"), os.path.join(out, "synth.ys")], capture_output=True, text=True, cwd=ROOT)
    if r.returncode != 0:
        return dict(name=name, error="yosys failed: " + (r.stdout + r.stderr)[-400:])
    err = sta_only(out, top, period)
    if err:
        return dict(name=name, error=err)
    stat = open(os.path.join(out, "stat.txt")).read()
    tim = open(os.path.join(out, "timing.txt")).read()
    pw = open(os.path.join(out, "power.txt")).read()
    g = lambda pat, s: (re.search(pat, s, re.M).group(1) if re.search(pat, s, re.M) else None)  # noqa: E731
    res = dict(name=name, core=core, abc=abc, fwd=fwd if core == "pipe" else None, bp=bp if core == "pipe" else None, period_ns=period,
               cells=int(g(r"Number of cells:\s+(\d+)", stat)),
               area_um2=float(g(r"Chip area for module '[^']+': ([\d.]+)", stat)),
               flops=sum(int(m.group(1)) for m in re.finditer(r"sky130_fd_sc_hd__df\w*\s+(\d+)", stat)),
               wns_ns=float(g(r"worst slack max (-?[\d.]+)", tim)), tns_ns=float(g(r"tns max (-?[\d.]+)", tim)),
               hold_wns_ns=float(g(r"worst slack min (-?[\d.]+)", tim)),
               startpoint=g(r"Startpoint: (\S+)", tim), endpoint=g(r"Endpoint: (\S+)", tim),
               power_w=float(g(r"^Total\s+\S+\s+\S+\s+\S+\s+(\S+)", pw) or 0))
    res["meets"] = res["wns_ns"] >= 0
    with open(os.path.join(ROOT, "build", "ppa", "results.jsonl"), "a") as f:
        f.write(json.dumps(res) + "\n")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core", choices=["pipe", "1cyc"], required=True)
    ap.add_argument("--bp", type=int, default=0)
    ap.add_argument("--periods", nargs="+", type=float, required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--abc", choices=["speed", "default"], default="speed",
                    help="speed: timing-driven ABC script (buffering, sizing; scripts/abc_speed.*); default: `abc -D <period>`")
    a = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "build", "ppa"), exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(lambda p: run_cfg(a.core, a.bp, p, abc=a.abc), a.periods):
            if "error" in r:
                print(r["name"], "ERROR", r["error"])
            else:
                print("%-18s period %5.2f ns  cells %6d  area %9.1f um2  WNS %7.3f ns  %s  crit: %s -> %s" % (
                    r["name"], r["period_ns"], r["cells"], r["area_um2"], r["wns_ns"], "MEETS" if r["meets"] else "fails", r["startpoint"], r["endpoint"]))


if __name__ == "__main__":
    sys.exit(main())
