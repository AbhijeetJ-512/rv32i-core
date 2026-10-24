#!/usr/bin/env python3
"""summarize.py - write results/formal.txt from the status files that riscv-formal / SymbiYosys left in build/formal/*/checks/*/."""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows, total_pass, total = [], 0, 0
for d in sorted(glob.glob(os.path.join(ROOT, "build/formal/bp*_fwd*"))):
    name = os.path.basename(d)
    st = {}
    for s in glob.glob(os.path.join(d, "checks/*/status")):
        st[os.path.basename(os.path.dirname(s))] = open(s).read().split()[0]
    p = sum(1 for v in st.values() if v == "PASS")
    fam = {}
    for k, v in st.items():
        f = re.sub(r"_ch0$", "", k)
        f = "insn" if f.startswith("insn_") else f
        fam.setdefault(f, [0, 0])
        fam[f][0] += v == "PASS"
        fam[f][1] += 1
    rows.append((name, p, len(st), fam, [k for k, v in st.items() if v != "PASS"]))
    total_pass += p
    total += len(st)
depth = {}
cfg = os.path.join(ROOT, "formal/checks.cfg.in")
sec = None
for line in open(cfg):
    m = re.match(r"\[(.+)\]", line.strip())
    if m:
        sec = m.group(1)
    elif sec == "depth" and line.strip():
        depth[line.split()[0]] = line.split()[-1]
out = ["riscv-formal bounded model checks of rv32i_core (RVFI_EN=1), SymbiYosys + z3, Yosys 0.33, isa rv32i, one retirement channel",
       "instruction memory and load data are free inputs; reset is asserted in the first cycle; RISCV_FORMAL_ALIGNED_MEM",
       "BOUNDED checks (the depth is the number of cycles from reset explored), not unbounded proofs. depth per check family: " +
       ", ".join("%s %s" % (k, v) for k, v in depth.items()), ""]
for name, p, n, fam, bad in rows:
    out.append("%s : %d checks, %d PASS, %d not PASS%s" % (name.replace("bp", "BP_MODE=").replace("_fwd", " FWD_PRECOMP="), n, p, n - p,
               ("  (" + ", ".join(bad) + ")") if bad else ""))
    out.append("    " + ", ".join("%s %d/%d" % (k, v[0], v[1]) for k, v in sorted(fam.items())))
out.append("")
out.append("scope: 37 per-instruction checks (every RV32I instruction except FENCE / ECALL / EBREAK / CSR), plus reg (register x5 only), pc_fwd and pc_bwd (parameter 5),")
out.append("  unique, causal (parameter 5) and ill (an all-zero word must trap). NOT RUN: liveness / hang, the memory-bus checks, CSR checks (no CSRs),")
out.append("  and any unbounded (k-induction / PDR) proof; FENCE, ECALL and EBREAK are not covered by an instruction check.")
out.append("")
out.append("all variants: %d of %d checks PASS" % (total_pass, total))
open(os.path.join(ROOT, "results/formal.txt"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
sys.exit(0 if total_pass == total and total else 1)
