#!/usr/bin/env python3
"""pnr_report.py - read every OpenROAD run in results/pnr/ back, check that it is what it claims to be, and write results/pnr.md + results/pnr.json.

    pnr_report.py [--runs results/pnr] [--out results/pnr.md]

Per run (a directory results/pnr/<config>_p<period>/ written by pnr/run_pnr.sh) the checks are:
  - no `[ERROR` in pnr.log; the log reaches `stage complete: repair` and prints `PnR flow complete`
  - the clock period in run_conditions.txt equals the directory name's period
  - the clock-tree sink count equals the flip-flop count in the post-synthesis stat.txt
  - the netlist the flow read has the checksum recorded by run_pnr.sh
  - every routed / extracted report exists; the route DRC report is consistent with drc_count.txt
  - the timing report has setup, hold and TNS lines
A run that fails a check is listed with the failure and its figures are shown as NOT USED. Every figure is parsed from a report file;
nothing is computed except the ratio of the routed period to the pre-layout period (labelled).
Exit status 1 if any run fails a check or no run exists.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    return open(path, errors="replace").read() if os.path.exists(path) else None


def first(pat, text, group=1, flags=re.M):
    m = re.search(pat, text or "", flags)
    return m.group(group) if m else None


def check_run(d):
    tag = os.path.basename(d)
    m = re.match(r"(bp\d_fwd\d)_p([\d.]+)$", tag)
    r = dict(tag=tag, config=m.group(1) if m else None, target_ns=float(m.group(2)) if m else None, problems=[])
    bad = r["problems"].append
    log = read(os.path.join(d, "pnr.log"))
    if not log:
        bad("pnr.log missing or empty")
        return r
    if "[ERROR" in log:
        bad("pnr.log has [ERROR lines")
    if "=== stage complete: repair" not in log:
        bad("the flow never completed the repair stage")
    if "PnR flow complete" not in log:
        bad("no 'PnR flow complete' line (stopped early or failed)")
    if "Design has unrouted nets" in log:
        bad("design has unrouted nets")
    rc = read(os.path.join(d, "run_conditions.txt")) or ""
    per = first(r"^clock_period_ns=([\d.]+)", rc)
    r["clock_period_ns"] = float(per) if per else None
    if per is None or abs(float(per) - (r["target_ns"] or -1)) > 1e-6:
        bad("run_conditions.txt period %s does not match the directory name" % per)
    r["core_utilization"] = first(r"^core_utilization=(\S+)", rc)
    r["setup_margin_ns"] = first(r"^repair_setup_margin=(\S+)", rc)
    pd = first(r"^global_place_density=(\S+)", rc)
    r["place_density"] = ("%.2f" % float(pd)) if pd else None
    r["grt_antenna_repair"] = first(r"^grt_antenna_repair=(\S+)", rc) or "1"
    stat = read(os.path.join(d, "stat.txt")) or ""
    flops = sum(int(x) for x in re.findall(r"sky130_fd_sc_hd__df\w*\s+(\d+)", stat))
    sinks = first(r"Clock net \"clk\" has (\d+) sinks", log)
    r["flops"], r["clock_sinks"] = flops, int(sinks) if sinks else None
    if not sinks or int(sinks) != flops:
        bad("clock sinks %s != flip-flops %d in stat.txt" % (sinks, flops))
    r["cells_synth"] = first(r"Number of cells:\s+(\d+)", stat)
    r["area_synth_um2"] = first(r"Chip area for module '[^']+': ([\d.]+)", stat)
    sha = read(os.path.join(d, "netlist.sha256"))
    nl = os.path.join(ROOT, "build", "pnr", r["tag"], "synth.v")
    if not sha or not os.path.exists(nl) or hashlib.sha256(open(nl, "rb").read()).hexdigest() != sha.split()[0]:
        bad("netlist checksum missing or differs from the one recorded when the run started")
    for f in ("rv32i_sky130hd_route-tcl.def", "rv32i_sky130hd_route-tcl.db", "rv32i_sky130hd_fill-tcl.db", "rv32i_sky130hd_final-tcl.def",
              "rv32i_sky130hd-tcl.spef", "timing_final.rpt", "clock_skew.rpt", "power_final.rpt", "area_final.rpt", "antenna.rpt", "drc_count.txt"):
        p = os.path.join(d, f)
        if not (os.path.exists(p) and os.path.getsize(p) > 0):
            bad("%s missing or empty" % f)
    drc = first(r"^drc_violations=(\d+)", read(os.path.join(d, "drc_count.txt")))
    rpt = os.path.join(d, "rv32i_sky130hd_route_drc-tcl.rpt")
    if drc is None:
        bad("drc_count.txt has no drc_violations=<n>")
    elif not os.path.exists(rpt):
        bad("route DRC report missing")
    elif (int(drc) == 0) != (os.path.getsize(rpt) == 0):
        bad("route DRC report (%d bytes) disagrees with drc_violations=%s" % (os.path.getsize(rpt), drc))
    r["drc_violations"] = int(drc) if drc is not None else None
    ant = first(r"^antenna_violations=(\d+)", read(os.path.join(d, "antenna.rpt")))
    r["antenna_violations"] = int(ant) if ant is not None else None
    if ant is None:
        bad("antenna.rpt has no antenna_violations=<n>")
    tim = read(os.path.join(d, "timing_final.rpt")) or ""
    for key, pat in (("wns_setup_ns", r"^worst slack max (-?[\d.]+)"), ("wns_hold_ns", r"^worst slack min (-?[\d.]+)"), ("tns_ns", r"^tns max (-?[\d.]+)")):
        v = first(pat, tim)
        if v is None:
            bad("timing_final.rpt has no '%s'" % pat[1:])
        r[key] = float(v) if v is not None else None
    # worst setup path of the routed design: start and end point
    sp = re.search(r"Startpoint: (\S+)[^\n]*\nEndpoint: (\S+)[^\n]*\n(?:[^\n]*\n){0,3}?Path Type: max", tim)
    r["start"], r["end"] = (sp.group(1), sp.group(2)) if sp else (None, None)
    nl_text = read(os.path.join(d, "rv32i_sky130hd-tcl.v")) or ""

    def net(inst, pin):  # the net a flop pin is connected to, from the post-repair netlist (Yosys / OpenROAD names)
        m = re.search(r"\n\s*\S+ %s \((.*?)\);" % re.escape(inst), nl_text, re.S) if inst else None
        n = re.search(r"\.%s\(([^)]*)\)" % pin, m.group(1)) if m else None
        return n.group(1).strip() if n else None
    r["start_net"], r["end_net"] = net(r["start"], "Q"), net(r["end"], "D")
    chk = read(os.path.join(d, "check_types_final.rpt"))
    if chk is None:
        bad("check_types_final.rpt missing")
    else:
        sec, n = None, {"max slew": 0, "max capacitance": 0, "max fanout": 0}
        for line in chk.splitlines():
            for k in n:
                if line.startswith(k):
                    sec = k
            if "VIOLATED" in line and sec:
                n[sec] += 1
        r["violations_routed"] = n
        r["violations_antenna_pins"] = sum(1 for l in chk.splitlines() if "VIOLATED" in l and "ANTENNA" in l)
    area = read(os.path.join(d, "area_final.rpt")) or ""
    r["design_area_um2"] = first(r"Design area ([\d.]+) u\^2", area)
    r["utilization_pct"] = first(r"u\^2 ([\d.]+)% utilization", area)
    pw = read(os.path.join(d, "power_final.rpt")) or ""
    r["power_total_w"] = first(r"^Total\s+\S+\s+\S+\s+\S+\s+(\S+)", pw)
    skew = read(os.path.join(d, "clock_skew.rpt")) or ""
    r["skew_text"] = " ".join(l.strip() for l in skew.splitlines() if re.search(r"skew|latency|Clock clk|source latency", l, re.I))[:240]
    die = first(r"^DIEAREA \( \d+ \d+ \) \( (\d+) (\d+) \)", read(os.path.join(d, "rv32i_sky130hd_final-tcl.def")), group=0)
    if die:
        mm = re.match(r"DIEAREA \( \d+ \d+ \) \( (\d+) (\d+) \)", die)
        r["die_um"] = (int(mm.group(1)) / 1000.0, int(mm.group(2)) / 1000.0)
    r["ok"] = not r["problems"]
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", default=os.path.join(ROOT, "results", "pnr"))
    ap.add_argument("--out", default=os.path.join(ROOT, "results", "pnr.md"))
    a = ap.parse_args()
    dirs = sorted(d for d in glob.glob(os.path.join(a.runs, "*_p*")) if os.path.isdir(d))
    runs = [check_run(d) for d in dirs]
    pre = {}
    try:
        for x in json.load(open(os.path.join(ROOT, "results", "ppa.json"))):
            if x["core"] == "pipe" and x["abc"] == "speed":
                pre["bp%d_fwd%d" % (x["bp"], x["fwd"])] = x
    except (OSError, ValueError):
        pass
    L = ["# Place and route of rv32i_core (measured: OpenROAD, Sky130 HD tt_025C_1v80, RVFI_EN=0)", "",
         "Flow: floorplan at the stated utilisation, global placement, repair_design, clock-tree synthesis, repair_timing, global and detailed routing, "
         "antenna repair, RC extraction (SPEF), final STA with the propagated clock on the extracted parasitics (`pnr/pnr_flow.tcl`, adapted from alu_fifo). "
         "Netlist: the timing-driven Yosys mapping of `make ppa`. Constraints: `constraints/rv32i.sdc` (memory read 2.0 ns after the edge, "
         "address/write data 1.0 ns before the next edge: an assumption). Typical corner only; no hold fixing beyond what repair_timing did; no signoff DRC/LVS "
         "(Magic/KLayout/Netgen are not installed), so \"DRC\" below is the router's own count. Power is OpenSTA's default-activity figure, not a workload figure.", "",
         "| run | target period (ns) | setup WNS (ns) | hold WNS (ns) | TNS (ns) | route DRC | antenna viol. | slew / cap / fanout viol. | design area (um^2) | die (um) | checks |",
         "|---|---:|---:|---:|---:|---:|---:|---|---:|---|---|"]
    for r in runs:
        if not r["ok"]:
            L.append("| %s | %s | NOT USED | | | | | | | | FAILED: %s |" % (r["tag"], r["target_ns"], "; ".join(r["problems"])))
            continue
        v = r["violations_routed"]
        die = "%.0f x %.0f" % r["die_um"] if r.get("die_um") else "?"
        L.append("| %s | %.1f | %+.3f | %+.3f | %.3f | %s | %s | %d / %d / %d | %s | %s | all passed |" % (
            r["tag"], r["target_ns"], r["wns_setup_ns"], r["wns_hold_ns"], r["tns_ns"], r["drc_violations"], r["antenna_violations"],
            v["max slew"], v["max capacitance"], v["max fanout"], r["design_area_um2"], die))
    good = [r for r in runs if r["ok"]]
    L += ["", "Worst routed setup path per run (start flop output net -> end flop input net, names from the post-repair netlist):", ""]
    for r in good:
        L.append("- `%s`: `%s` -> `%s` (setup slack %+.3f ns)" % (r["tag"], r.get("start_net") or r["start"], r.get("end_net") or r["end"], r["wns_setup_ns"]))
    met = sorted((r for r in good if r["wns_setup_ns"] >= 0 and r["wns_hold_ns"] >= 0 and r["drc_violations"] == 0), key=lambda r: r["target_ns"])
    L += ["", "Clock-tree sinks equal the flip-flop count in every accepted run; the netlist checksum matches the one recorded at the start of the run.", ""]
    if met:
        b = met[0]
        p = pre.get(b["config"])
        L.append("**Smallest tried target that closed setup and hold in the routed, extracted design with zero route DRC violations: %.1f ns (%.1f MHz)**, run `%s`. "
                 "This is the best of the targets that were run (a tested value, not an optimum): finer steps below it were not tried." % (b["target_ns"], 1000.0 / b["target_ns"], b["tag"]))
        if p:
            L.append("The pre-layout minimum period of the same configuration is %.3f ns (`results/ppa.md`); the smallest closing routed target is %.2fx that "
                     "(derived: %.1f / %.3f)." % (p["tmin"], b["target_ns"] / p["tmin"], b["target_ns"], p["tmin"]))
        L.append("Selected run: %s | target %.1f ns | %.1f MHz | setup WNS %+.3f ns | hold WNS %+.3f ns | route DRC %d | antenna violations %d | area %s um^2" % (
            b["tag"], b["target_ns"], 1000.0 / b["target_ns"], b["wns_setup_ns"], b["wns_hold_ns"], b["drc_violations"], b["antenna_violations"], b["design_area_um2"]))
        vb = b["violations_routed"]
        L.append("In that run the routed design still has %d max-slew, %d max-capacitance and %d max-fanout violating pins/nets (`check_types_final.rpt`; %d of "
                 "the violating pins are antenna diodes)." % (vb["max slew"], vb["max capacitance"], vb["max fanout"], b["violations_antenna_pins"]))
        L.append("Power, default activity (W): %s. Design area before fillers: %s um^2 at %s %% utilisation. Clock skew report: %s" % (
            b["power_total_w"], b["design_area_um2"], b["utilization_pct"], b["skew_text"] or "see clock_skew.rpt"))
    else:
        L.append("**No tried target closed setup and hold with zero route DRC violations in the routed design.** Nothing about a routed frequency is claimed.")
    same = {}
    for r in good:
        same.setdefault((r["design_area_um2"], r["violations_routed"]["max slew"], r["violations_routed"]["max capacitance"]), []).append(r)
    for k, g in same.items():
        if len(g) > 2:
            d = [round(r["target_ns"] - r["wns_setup_ns"], 3) for r in g]
            if max(d) - min(d) < 0.002:
                L.append("")
                L.append("Runs %s have identical area and violation counts (repair_timing changed nothing at those targets) and their setup slack moves one for one with the period: "
                         "the routed critical path of that layout is %.3f ns (target minus slack, derived)." % (", ".join(r["tag"] for r in sorted(g, key=lambda r: r["target_ns"])), d[0]))
    L.append("")
    L.append("Run settings: core utilisation %s %%, repair_setup_margin %s ns, global placement density %s (alu_fifo's values, not tuned for this design); "
             "antenna repair between global and detailed routing: %s." % (
        good[0]["core_utilization"], good[0]["setup_margin_ns"], good[0]["place_density"],
        ", ".join("%s %s" % (r["tag"], "on" if r["grt_antenna_repair"] == "1" else "off") for r in good)) if good else "No accepted run.")
    open(a.out, "w").write("\n".join(L) + "\n")
    json.dump(runs, open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print("\n".join(L))
    return 0 if runs and all(r["ok"] for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
