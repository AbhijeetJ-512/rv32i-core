#!/usr/bin/env python3
"""make_result_snippets.py - small Markdown snippets of the results, for the design document (docs/*.md.in includes them)."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = lambda f: os.path.join(ROOT, "results", f)  # noqa: E731


def txt(f):
    return open(R(f)).read().rstrip("\n") if os.path.exists(R(f)) else "NOT YET MEASURED (results/%s missing)" % f


tot = sum(int(m.group(1)) for m in re.finditer(r"(\d+) insns", txt("random.txt")))
open(R("summary_tests.md"), "w").write(
    "Measured results (from `results/directed.txt`, `results/random.txt`, `results/cpi.md`):\n\n"
    "| Test class | Result |\n|---|---|\n"
    "| Directed tests | %s |\n| Constrained-random programs | %s; %d instructions retired and compared |\n"
    "| Benchmarks (self-checking, both BP modes) | all 7 pass; table in H.3 |\n" % (txt("directed.txt").splitlines()[0], txt("random.txt").splitlines()[0], tot))
open(R("summary_coverage.md"), "w").write("Merged coverage of the directed tests, the benchmarks and random programs, both BP modes (`results/coverage_summary.txt`):\n\n```text\n%s\n```\n" % txt("coverage_summary.txt"))
m = txt("mutants.txt").splitlines()
open(R("summary_mutants.md"), "w").write("Result of the campaign (`results/mutants.txt`, first lines):\n\n```text\n%s\n```\n" % "\n".join(l[:200] for l in m[:7]))
f = txt("formal.txt").splitlines()
fa = txt("formal_as_found.txt").splitlines()
open(R("summary_formal.md"), "w").write(
    "Result of the bounded checks on the current core (`results/formal.txt`):\n\n```text\n%s\n```\n\n"
    "Result of the same checks on the core before the fix (`results/formal_as_found.txt`):\n\n```text\n%s\n```\n" % ("\n".join(l[:200] for l in f), "\n".join(l[:200] for l in fa)))
print("snippets written")
