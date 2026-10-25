#!/usr/bin/env python3
"""cov_check.py - gate on a Verilator coverage.dat (spec 5.3).

  cov_check.py COVDAT --rtl-dir rtl --exclusions FILE
               --bins-out F --summary-out F --toggle-out F

Fails (exit 1) on:
  ZERO-HIT BIN       a named cover property (page v_user) that was never hit
  UNCOVERED LINE     an rtl/ source line with no hits that is not listed in the exclusions file
  STALE EXCLUSION    an exclusion for a line that is in fact covered (it would hide a regression)
Exit 2 on anything that would make a pass meaningless: unreadable file, no cover bins in the
file, no rtl/ line records, a malformed exclusions file.

A line counts as covered when the hits summed over every instance and parameterisation of that
(file, line) are non-zero. Toggle and branch coverage are reported, never gated.
The coverage.dat record format is: C '<\\x01key\\x02value ...>' <count>
"""
import argparse
import collections
import glob
import os
import re
import sys

REC = re.compile(r"^C '(.*)' (\d+)$")


def fail_usage(msg):
    print(f"cov_check: {msg}")
    sys.exit(2)


def parse(path):
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("latin-1")
    except OSError as exc:
        fail_usage(f"cannot read {path}: {exc}")
    recs = []
    for raw in text.splitlines():
        m = REC.match(raw)
        if not m:
            continue
        fields = {}
        for part in m.group(1).split("\x01")[1:]:
            key, _, val = part.partition("\x02")
            fields[key] = val
        recs.append((fields, int(m.group(2))))
    return recs


def read_exclusions(path):
    excl = {}
    try:
        with open(path) as fh:
            for n, line in enumerate(fh, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                spec, _, reason = line.partition(" ")
                m = re.match(r"^(.+):(\d+)$", spec)
                if not m or not reason.strip():
                    fail_usage(f"{path}:{n}: expected '<file>:<line> <reason>' with a reason")
                excl[(m.group(1), int(m.group(2)))] = reason.strip()
    except OSError as exc:
        fail_usage(f"cannot read {path}: {exc}")
    return excl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("covdat")
    ap.add_argument("--rtl-dir", required=True)
    ap.add_argument("--exclusions", required=True)
    ap.add_argument("--bins-out", required=True)
    ap.add_argument("--summary-out", required=True)
    ap.add_argument("--toggle-out", required=True)
    args = ap.parse_args()

    recs = parse(args.covdat)
    excl = read_exclusions(args.exclusions)
    prefix = args.rtl_dir.rstrip("/") + "/"

    def page(f):
        return f.get("page", "").split("/")[0]

    bins = [(f["h"], c) for f, c in recs if page(f) == "v_user"]
    if not bins:
        fail_usage(f"no cover bins (page v_user) found in {args.covdat}; refusing to pass vacuously")
    lines = collections.defaultdict(int)
    for f, c in recs:
        if page(f) == "v_line" and f.get("f", "").startswith(prefix):
            lines[(f["f"], int(f["l"]))] += c
    if not lines:
        fail_usage(f"no line records under {prefix} in {args.covdat}")

    # Verilator records line coverage for procedural blocks only. A file made of continuous assignments (the top level,
    # where the transfer rule and the ready/valid logic live) has no line records, so this gate cannot see it at all.
    rtl_files = sorted(glob.glob(prefix + "*.sv"))
    with_lines = {f for f, _ in lines}
    blind = [os.path.basename(f) for f in rtl_files if f not in with_lines]

    problems = []
    for name, hits in bins:
        if hits == 0:
            problems.append(f"ZERO-HIT BIN {name}")
    uncovered, excluded = [], []
    for key, hits in sorted(lines.items()):
        if hits == 0:
            (excluded if key in excl else uncovered).append(key)
    for key in uncovered:
        problems.append(f"UNCOVERED LINE {key[0]}:{key[1]}")
    for key, reason in sorted(excl.items()):
        if lines.get(key, 0) != 0:
            problems.append(f"STALE EXCLUSION {key[0]}:{key[1]} ({reason}) is covered; remove the exclusion")
        elif key not in lines:
            problems.append(f"STALE EXCLUSION {key[0]}:{key[1]} ({reason}) matches no line record")

    branches = [c for f, c in recs if page(f) == "v_branch" and f.get("f", "").startswith(prefix)]
    toggles = [(f, c) for f, c in recs if page(f) == "v_toggle" and f.get("f", "").startswith(prefix)]
    unhit_toggles = sorted(f"{f['f']}  {f['h']}  {f['o']}" for f, c in toggles if c == 0)

    shown = os.path.relpath(os.path.abspath(args.covdat), os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(args.bins_out, "w") as out:
        out.write("# hits  hierarchical name of each named cover bin (from %s)\n" % shown)
        for name, hits in sorted(bins):
            out.write(f"{hits:10d}  {name}\n")
    with open(args.toggle_out, "w") as out:
        out.write("# rtl/ toggle bits never toggled: file  instance  signal (reported, not gated)\n")
        for row in unhit_toggles:
            out.write(row + "\n")
    with open(args.summary_out, "w") as out:
        out.write(f"source               : {shown}\n")
        out.write(f"named cover bins     : {len(bins)} total, {sum(1 for _, c in bins if c)} hit, "
                  f"{sum(1 for _, c in bins if not c)} zero\n")
        out.write(f"{prefix} line blocks    : {len(lines)} total, "
                  f"{sum(1 for v in lines.values() if v)} covered, {len(excluded)} excluded, "
                  f"{len(uncovered)} uncovered\n")
        out.write(f"{prefix} files with no line records : {', '.join(blind) or 'none'} "
                  "(procedural blocks only are recorded; these are covered by toggle coverage, the cover bins and the assertions, not by the line gate)\n")
        out.write(f"{prefix} branches       : {len(branches)} total, {sum(1 for c in branches if c)} hit "
                  "(reported, not gated)\n")
        out.write(f"{prefix} toggle bits    : {len(toggles)} total, {sum(1 for _, c in toggles if c)} toggled, "
                  f"{len(unhit_toggles)} unhit (reported, not gated)\n")

    if problems:
        for p in problems:
            print(p)
        print(f"cov_check: FAIL ({len(problems)} problem(s))")
        sys.exit(1)
    print(f"cov_check: ok ({len(bins)} bins hit, {len(lines)} line blocks, {len(excluded)} excluded)")
    if blind:
        print(f"cov_check: note - the line gate cannot see {', '.join(blind)} (no line records: no procedural blocks)")


if __name__ == "__main__":
    main()
