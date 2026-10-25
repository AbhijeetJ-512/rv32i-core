#!/usr/bin/env bash
# run_as_found.sh - the same riscv-formal checks on the core as it was BEFORE the misaligned-target fix (formal/as_found/rv32i_core.sv),
# to show the checks can fail. Writes results/formal_as_found.txt. Variant: BP_MODE=0, FWD_PRECOMP=1.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; ROOT="$(dirname "$HERE")"
TC="${TC:-$(cd "$ROOT/../.." && pwd)/_toolchain}"
W="$ROOT/build/as_found"; rm -rf "$W"; mkdir -p "$W"
cp -r "$ROOT/rtl" "$W/rtl"; cp "$HERE/as_found/rv32i_core.sv" "$W/rtl/rv32i_core.sv"
mkdir -p "$W/formal"; cp "$HERE/wrapper.sv" "$HERE/checks.cfg.in" "$HERE/run_formal.sh" "$W/formal/"
out=$(TC="$TC" JOBS="${JOBS:-8}" bash "$W/formal/run_formal.sh" 0 1)
d="$W/build/formal/bp0_fwd1/checks"
{
  echo "riscv-formal on the core before the misaligned-target fix (formal/as_found/rv32i_core.sv), BP_MODE=0 FWD_PRECOMP=1"
  echo "$out"
  echo "failing checks:"
  for c in "$d"/*/; do c=$(basename "$c"); s=$(head -1 "$d/$c/status" 2>/dev/null); case "$s" in PASS*) ;; *) echo "  $c  ($s)";; esac; done
  echo "failing assertion: rvfi_insn_check.sv line 196, assert(spec_trap == trap): the specification says the transfer traps, the core did not"
} > "$ROOT/results/formal_as_found.txt"
cat "$ROOT/results/formal_as_found.txt"
