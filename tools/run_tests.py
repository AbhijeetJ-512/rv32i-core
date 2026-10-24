#!/usr/bin/env python3
"""run_tests.py - assemble, run on the ISS and on the RTL (both BP_MODEs), compare lock-step, summarise.

    run_tests.py [--tests DIR ...] [--only SUBSTR] [--bp 0 1] [--jobs N] [--out DIR] [--report FILE]

For every test program: prologue + test + epilogue is assembled; the ISS produces the golden trace and final memory;
the RTL testbench produces its retirement trace and final memory; the two must match exactly (compare_trace.py and a
memory-image diff). A test passes if (a) every comparison matches and (b) the program's own verdict is as expected:
a0 == 0 in the final register dump (self-checking tests), or - for a test containing '# EXPECT: trap' - the last
retired instruction carries trap=1. '# EXPECT: ecall' means a plain halt with whatever a0 holds.
"""
import argparse
import concurrent.futures as cf
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import compare_trace  # noqa: E402
import rvasm  # noqa: E402
import rviss  # noqa: E402

A0_DUMP_WORD = 0x128 // 4


def read(path):
    with open(path) as f:
        return f.read()


def build_exe(bp, build_dir):
    exe = os.path.join(build_dir, "sim_bp%d" % bp, "Vtb_core")
    if not os.path.exists(exe):
        subprocess.check_call([os.path.join(ROOT, "scripts", "build_sim.sh"), os.path.dirname(exe), str(bp)])
    return exe


def run_one(path, bps, exes, out_dir, max_cycles=3_000_000, cov_dir=None):
    name = os.path.splitext(os.path.basename(path))[0]
    src = read(path)
    expect = re.search(r"#\s*EXPECT:\s*(\w+)", src)
    expect = expect.group(1) if expect else "pass"
    full = read(os.path.join(ROOT, "tests", "asm", "_prologue.inc")) + src + read(os.path.join(ROOT, "tests", "asm", "_epilogue.inc"))
    asm_path = os.path.join(out_dir, name + ".S")
    open(asm_path, "w").write(full)
    hexf = os.path.join(out_dir, name + ".hex")
    asm = rvasm.Asm()
    try:
        mem, listing = asm.assemble(full)
    except rvasm.AsmError as e:
        return dict(name=name, ok=False, why="assembler: %s" % e)
    words = rvasm.to_words(mem, 16384)
    with open(hexf, "w") as f:
        f.write("".join("%08x\n" % w for w in words))
    open(os.path.join(out_dir, name + ".lst"), "w").write("\n".join(listing) + "\n")
    try:
        recs, iss = rviss.run(words, 5_000_000)
    except rviss.ISSError as e:
        return dict(name=name, ok=False, why="invalid program (ISS): %s" % e)
    iss_trace = [rviss.fmt(r) for r in recs]
    open(os.path.join(out_dir, name + ".iss.trace"), "w").write("\n".join(iss_trace) + "\n")
    iss_dump = [("%08x" % int.from_bytes(iss.mem[i:i + 4], "little")) for i in range(0, len(iss.mem), 4)]
    res = dict(name=name, ok=True, why="", insns=len(recs), mix=iss.mix)
    last = recs[-1]
    a0 = int(iss_dump[A0_DUMP_WORD], 16)
    if expect == "pass" and (last["trap"] or a0 != 0):
        return dict(res, ok=False, why="self-check failed: a0=%d gp=%d trap=%d" % (a0, iss.x[3], last["trap"]))
    if expect == "trap" and not last["trap"]:
        return dict(res, ok=False, why="expected a trap, program ended with a plain halt")
    res["fired"] = set()
    res["kinds"] = set()
    problems = []
    for bp in bps:
        trace = os.path.join(out_dir, "%s.bp%d.rtl.trace" % (name, bp))
        stats = os.path.join(out_dir, "%s.bp%d.stats" % (name, bp))
        dump = os.path.join(out_dir, "%s.bp%d.dump" % (name, bp))
        for f in (trace, stats, dump):
            if os.path.exists(f):
                os.remove(f)
        p = subprocess.run([exes[bp], "+hex=" + hexf, "+trace=" + trace, "+stats=" + stats, "+dump=" + dump,
                            "+maxcycles=%d" % max_cycles, "+verilator+rand+reset+2", "+verilator+seed+7",
                            "+verilator+error+limit+100000"] + (["+cov_file=%s/%s.bp%d.dat" % (cov_dir, name, bp)] if cov_dir else []),
                           capture_output=True, text=True)
        out = p.stdout + p.stderr
        fired = set(re.findall(r"Assertion failed in \S*?u_chk\.(?:\w+\.)*(a_\w+)", out))
        if fired:
            res["fired"] |= fired
            res["kinds"].add("assert")
            problems.append("bp%d: assertion(s) fired: %s" % (bp, ", ".join(sorted(fired))))
        if "TB DONE" not in out or not os.path.exists(trace):
            res["kinds"].add("hang")
            problems.append("bp%d: simulation did not finish (%s)" % (bp, out.strip()[-200:].replace("\n", " ")))
            continue
        rtl_lines = [l for l in read(trace).splitlines() if l.strip()]
        cmp = compare_trace.compare(rtl_lines, iss_trace)
        if cmp is not None:
            i, diff, a, b = cmp
            detail = ""
            if a:
                detail = " | " + ", ".join("%s rtl=%08x iss=%08x" % (f, a[f], b[f]) for f in diff) + \
                         " | pc=%08x insn=%08x" % (b["pc"], b["insn"])
            res["kinds"].add("trace")
            problems.append("bp%d: trace mismatch at #%d (%s)%s" % (bp, i, ",".join(diff), detail))
            continue
        rtl_dump = read(dump).split()
        if rtl_dump != iss_dump:
            bad = next(i for i, (x, y) in enumerate(zip(rtl_dump, iss_dump)) if x != y)
            res["kinds"].add("memory")
            problems.append("bp%d: final memory differs at word 0x%x (rtl %s iss %s)" % (bp, bad, rtl_dump[bad], iss_dump[bad]))
            continue
        if expect == "pass" and int(rtl_dump[A0_DUMP_WORD], 16) != 0:
            res["kinds"].add("selfcheck")
            problems.append("bp%d: RTL self-check failed" % bp)
        st = dict(l.split("=") for l in read(stats).split())
        res["bp%d" % bp] = {k: int(v) for k, v in st.items()}
    if problems:
        return dict(res, ok=False, why=" ; ".join(problems))
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tests", nargs="*", default=[os.path.join(ROOT, "tests", "asm")])
    ap.add_argument("--only", default="")
    ap.add_argument("--bp", nargs="*", type=int, default=[0, 1])
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--build", default=os.path.join(ROOT, "build"))
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "tests"))
    ap.add_argument("--report", default="")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    exes = {bp: build_exe(bp, a.build) for bp in a.bp}
    files = []
    for d in a.tests:
        if os.path.isfile(d):
            files.append(d)
        else:
            files += sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".S") and not f.startswith("_"))
    files = [f for f in files if a.only in os.path.basename(f)]
    results = []
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for r in ex.map(lambda f: run_one(f, a.bp, exes, a.out), files):
            results.append(r)
            print("%-4s %-28s %s" % ("PASS" if r["ok"] else "FAIL", r["name"], r.get("why", "") if not r["ok"] else
                                     "%d insns" % r["insns"]))
    npass = sum(r["ok"] for r in results)
    lines = ["%d/%d tests passed (BP_MODE %s)" % (npass, len(results), ",".join(map(str, a.bp)))]
    for r in results:
        if r["ok"]:
            cpi = "  ".join("bp%d: %d cyc CPI %.3f" % (bp, r["bp%d" % bp]["cycles"], r["bp%d" % bp]["cycles"] / r["bp%d" % bp]["instret"])
                            for bp in a.bp)
            lines.append("PASS %-26s %6d insns  %s" % (r["name"], r["insns"], cpi))
        else:
            lines.append("FAIL %-26s %s" % (r["name"], r["why"]))
    print(lines[0])
    if a.report:
        open(a.report, "w").write("\n".join(lines) + "\n")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
