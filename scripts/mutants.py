#!/usr/bin/env python3
"""mutants.py - does the verification environment catch real bugs?

    mutants.py [--only M01 M07 ...] [--jobs 4] [--rand 30] [--report build/reports/mutants.txt]
    mutants.py --selftest

For every entry of verif/mutants.py: copy rtl/, apply the one-line bug, build the simulation twice (A: with the bound
assertions, B: without them) and run the directed tests plus --rand random programs lock-step against the ISS.
Layers that can catch a bug: assertion (A only), lock-step trace, final-memory diff, the program's own self-check.
The harness FAILS (exit 1) if
  * a mutant is caught by no layer                                 (a hole in the tests)
  * an `intended` assertion did not fire for its mutant            (the assertion is not doing its job)
  * an assertion of rv32i_checker.sv has no mutant bound to it     (an assertion nobody has shown can fail)
  * a mutant's `old` text is not found exactly once in its file    (the mutant list is stale)
"""
import argparse
import concurrent.futures as cf
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "verif"))
import run_tests  # noqa: E402
import mutants as M  # noqa: E402

BUILD = os.path.join(ROOT, "build", "mut")


def assertion_labels():
    txt = open(os.path.join(ROOT, "verif", "rv32i_checker.sv")).read()
    return re.findall(r"^\s*(a_\w+)\s*:\s*assert\s+property", txt, re.M)


def apply(m, dst):
    shutil.copytree(os.path.join(ROOT, "rtl"), dst, dirs_exist_ok=True)
    f = os.path.join(dst, m["file"])
    t = open(f).read()
    if t.count(m["old"]) != 1:
        raise RuntimeError("%s: old text occurs %d times in %s" % (m["id"], t.count(m["old"]), m["file"]))
    open(f, "w").write(t.replace(m["old"], m["new"]))


def build(m, wd, with_checkers):
    out = os.path.join(wd, "simA" if with_checkers else "simB")
    env = dict(os.environ, RTL_DIR=os.path.join(wd, "rtl"), FWD_PRECOMP=str(m.get("fwd", 1)))
    if not with_checkers:
        env["NO_VERIF"] = "1"
    r = subprocess.run([os.path.join(ROOT, "scripts", "build_sim.sh"), out, str(m["bp"])], env=env, capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stdout[-600:]
    return os.path.join(out, "Vtb_core"), ""


def run_set(m, exe, files, wd, tag):
    out = os.path.join(wd, "tests_" + tag)
    os.makedirs(out, exist_ok=True)
    kinds, fired, failing = set(), set(), []
    for f in files:
        r = run_tests.run_one(f, [m["bp"]], {m["bp"]: exe}, out, max_cycles=200000)
        if not r["ok"]:
            kinds |= r.get("kinds", {"invalid"})
            fired |= r.get("fired", set())
            failing.append(r["name"])
    return kinds, fired, failing


def one(m, files):
    wd = os.path.join(BUILD, m["id"])
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd)
    apply(m, os.path.join(wd, "rtl"))
    exeA, errA = build(m, wd, True)
    exeB, errB = build(m, wd, False)
    if exeA is None or exeB is None:
        return dict(m=m, error="build failed: " + (errA or errB))
    kA, fA, failA = run_set(m, exeA, files, wd, "A")
    kB, fB, failB = run_set(m, exeB, files, wd, "B")
    return dict(m=m, kindsA=kA, fired=fA, failA=failA, kindsB=kB, failB=failB)


def selftest():
    labels = assertion_labels()
    assert len(labels) == len(set(labels)), "duplicate assertion labels"
    bad = 0
    for m in M.MUTANTS:
        t = open(os.path.join(ROOT, "rtl", m["file"])).read()
        if t.count(m["old"]) != 1:
            print("selftest: %s old text occurs %d times" % (m["id"], t.count(m["old"])))
            bad += 1
        if m["old"] == m["new"]:
            print("selftest: %s does not change anything" % m["id"])
            bad += 1
        for a in m["intended"]:
            if a not in labels:
                print("selftest: %s names unknown assertion %s" % (m["id"], a))
                bad += 1
    print("mutants selftest:", "ok (%d mutants, %d assertions)" % (len(M.MUTANTS), len(labels)) if not bad else "FAILED")
    return bad == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=[])
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--rand", type=int, default=30)
    ap.add_argument("--report", default=os.path.join(ROOT, "results", "mutants.txt"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if not selftest():
        return 1
    if a.selftest:
        return 0
    # test set: all directed tests + N random programs
    gen = os.path.join(ROOT, "build", "mut_rand")
    shutil.rmtree(gen, ignore_errors=True)
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "rvgen.py"), "--count", str(a.rand), "--first-seed", "1000",
                           "--out-dir", gen, "--length", "400"])
    directed = os.path.join(ROOT, "tests", "asm")
    files = sorted(os.path.join(directed, f) for f in os.listdir(directed) if f.endswith(".S") and not f.startswith("_"))
    files += sorted(os.path.join(gen, f) for f in os.listdir(gen))
    muts = [m for m in M.MUTANTS if not a.only or m["id"] in a.only]
    os.makedirs(os.path.dirname(a.report), exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        results = list(ex.map(lambda m: one(m, files), muts))
    labels = assertion_labels()
    lines, problems = [], []
    killed = 0
    all_fired = set()
    bound = set()
    for r in results:
        m = r["m"]
        if "error" in r:
            lines.append("%s  ERROR   %s" % (m["id"], r["error"]))
            problems.append("%s: %s" % (m["id"], r["error"]))
            continue
        caught = bool(r["kindsA"] or r["kindsB"])
        killed += caught
        all_fired |= r["fired"]
        bound |= set(m["intended"])
        layers = sorted(r["kindsB"]) if r["kindsB"] else []
        miss = [x for x in m["intended"] if x not in r["fired"]]
        lines.append("%s  %-6s bp%d  %-62s assert-fired: %-48s without-assertions: %s" % (
            m["id"], "KILLED" if caught else "ALIVE", m["bp"], m["why"][:62], ",".join(sorted(r["fired"])) or "-",
            "/".join(layers) if layers else "NOT CAUGHT"))
        if not caught:
            problems.append("%s survived every layer" % m["id"])
        if miss:
            problems.append("%s: intended assertion(s) did not fire: %s" % (m["id"], ",".join(miss)))
    if not a.only:
        for l in labels:
            if l not in bound and l not in M.UNBOUND_OK:
                problems.append("assertion %s has no mutant bound to it" % l)
        for l in labels:
            if l not in all_fired and l not in M.UNBOUND_OK:
                problems.append("assertion %s fired in no mutant run" % l)
    only_assert = [r["m"]["id"] for r in results if "error" not in r and r["kindsA"] and not r["kindsB"]]
    summary = ["mutants: %d, caught %d" % (len(results), killed),
               "test set per mutant: %d directed + %d random programs, lock-step vs ISS%s" % (len(files) - a.rand, a.rand, "" ),
               "caught ONLY by an assertion (the other layers missed them): %s" % (", ".join(only_assert) or "none"),
               "assertions defined: %d; fired in at least one mutant run: %d" % (len(labels), len(set(labels) & all_fired)),
               "assertions with no mutant bound: %s" % (", ".join(l for l in labels if l not in bound) or "none"),
               "assertions that fired in no run: %s" % (", ".join(l for l in labels if l not in all_fired) or "none"),
               "PROBLEMS: %s" % ("; ".join(problems) if problems else "none")]
    with open(a.report, "w") as f:
        f.write("\n".join(summary + [""] + lines) + "\n")
    print("\n".join(summary))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
