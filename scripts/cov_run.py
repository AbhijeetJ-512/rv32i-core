#!/usr/bin/env python3
"""cov_run.py - coverage run: build with Verilator --coverage, run every test in both BP modes, merge, gate.

    cov_run.py [--rand 60]

Merged coverage of the directed tests, the benchmarks and N random programs, BP_MODE 0 and 1 together (some cover points
only exist in one mode). scripts/cov_check.py (shared with the ALU-FIFO project) then fails on any named cover bin that
was never hit, any uncovered rtl/ line not excused in verif/cov_exclusions.txt with a reason, and any stale exclusion.
Verilator 5.020 has no covergroups: functional coverage here is the named `cover property` bins in verif/rv32i_checker.sv.
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import run_tests  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rand", type=int, default=60)
    a = ap.parse_args()
    cov = os.path.join(ROOT, "build", "cov")
    shutil.rmtree(cov, ignore_errors=True)
    os.makedirs(cov)
    exes = {}
    for bp in (0, 1):
        out = os.path.join(ROOT, "build", "cov_bp%d" % bp)
        shutil.rmtree(out, ignore_errors=True)
        subprocess.check_call([os.path.join(ROOT, "scripts", "build_sim.sh"), out, str(bp), "--coverage"], cwd=ROOT,
                              env=dict(os.environ, RTL_DIR="rtl"))   # relative paths: coverage.dat then names files rtl/<name>.sv
        exes[bp] = os.path.join(out, "Vtb_core")
    gen = os.path.join(ROOT, "build", "cov_rand")
    shutil.rmtree(gen, ignore_errors=True)
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "rvgen.py"), "--count", str(a.rand), "--first-seed", "5000",
                           "--out-dir", gen, "--length", "500"])
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "asm", "t*.S"))) + sorted(glob.glob(os.path.join(ROOT, "tests", "bench", "*.S"))) + \
        sorted(glob.glob(os.path.join(gen, "*.S")))
    out = os.path.join(ROOT, "build", "cov_out")
    os.makedirs(out, exist_ok=True)
    bad = [f for f in files if not run_tests.run_one(f, [0, 1], exes, out, cov_dir=cov)["ok"]]
    if bad:
        print("tests failed during the coverage run:", bad[:5])
        return 1
    dats = sorted(glob.glob(os.path.join(cov, "*.dat")))
    merged = os.path.join(cov, "merged.dat")
    subprocess.check_call(["verilator_coverage", "--write", merged] + dats, stdout=subprocess.DEVNULL)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, "cov_check.py"), merged, "--rtl-dir", "rtl", "--exclusions", "verif/cov_exclusions.txt",
                        "--bins-out", "results/coverage_bins.txt", "--summary-out", "results/coverage_summary.txt",
                        "--toggle-out", "results/coverage_toggle_unhit.txt"], cwd=ROOT, capture_output=True, text=True)
    print(r.stdout + r.stderr)
    print(open(os.path.join(ROOT, "results", "coverage_summary.txt")).read())
    print("runs merged: %d programs x 2 BP modes" % len(files))
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
