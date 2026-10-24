#!/usr/bin/env bash
# run_formal.sh [BP FWD ...]  - riscv-formal bounded model checks of rv32i_core with SymbiYosys + z3 (Yosys 0.33).
# Needs: _toolchain/riscv-formal, _toolchain/sbyroot, _toolchain/sbyvenv (see formal/README.md). One build directory per variant under build/formal.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"; TC="${TC:-$(cd "$ROOT/../.." && pwd)/_toolchain}"
export PATH="$TC/sbyvenv/bin:$TC/sbyroot/bin:$PATH"
RF="$TC/riscv-formal"
variants=("$@"); [ ${#variants[@]} -eq 0 ] && variants=(0 1 0 0 1 1 1 0)   # pairs "BP FWD": (0,1) (0,0) (1,1) (1,0)
[ ${#variants[@]} -eq 8 ] && variants=(0 1 0 0 1 1 1 0)
mkdir -p "$ROOT/build/formal"; for x in insns checks; do ln -sfn "$RF/$x" "$ROOT/build/$x"; done   # genchecks resolves @basedir@ as ../.. from its working directory
rc=0
for ((i=0; i<${#variants[@]}; i+=2)); do
  bp=${variants[i]}; fwd=${variants[i+1]}
  d="$ROOT/build/formal/bp${bp}_fwd${fwd}"; rm -rf "$d"; mkdir -p "$d"; mkdir -p "$d/cores/rv32i5"
  sed -e "s/@BP@/$bp/" -e "s/@FWD@/$fwd/" -e "s#@ROOT@#$ROOT#g" "$HERE/checks.cfg.in" > "$d/checks.cfg"
  ( cd "$d" && python3 "$RF/checks/genchecks.py" > genchecks.log 2>&1 && make -C checks -k -j"${JOBS:-4}" > make.log 2>&1 )
  pass=$(grep -l "PASS" "$d"/checks/*/status 2>/dev/null | wc -l); fail=$(grep -l "FAIL" "$d"/checks/*/status 2>/dev/null | wc -l)
  total=$(ls -d "$d"/checks/*/ 2>/dev/null | wc -l)
  echo "BP_MODE=$bp FWD_PRECOMP=$fwd : $total checks, $pass PASS, $fail FAIL"
  [ "$fail" -ne 0 ] || [ "$pass" -ne "$total" ] && rc=1
done
python3 "$HERE/summarize.py" > /dev/null || rc=1
exit $rc
