#!/usr/bin/env bash
# build_sim.sh <build-dir> <BP_MODE> [extra verilator flags...]  -> <build-dir>/Vtb_core
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
RTLDIR="${RTL_DIR:-$HERE/rtl}"        # override to build a mutated copy of rtl/
TOPPARAMS="${EXTRA_G:-}"
OUT="$1"; BP="$2"; shift 2
mkdir -p "$OUT"
RTL="$RTLDIR/rv32i_alu.sv $RTLDIR/rv32i_branch.sv $RTLDIR/rv32i_regfile.sv $RTLDIR/rv32i_decode.sv \
     $RTLDIR/rv32i_lsu.sv $RTLDIR/rv32i_hazard.sv $RTLDIR/rv32i_core.sv $RTLDIR/rv32i_core_1cyc.sv"
VERIF="$HERE/verif/rv32i_checker.sv $HERE/verif/checker_binds.sv"
[ -n "${NO_VERIF:-}" ] && VERIF=""
verilator --cc --exe --build --timing --assert --x-initial unique -j 4 \
    -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-fatal \
    -I"$RTLDIR" --top-module tb_core -GBP_MODE="$BP" -GFWD_PRECOMP="${FWD_PRECOMP:-1}" --Mdir "$OUT" "$@" \
    $RTL $VERIF "$HERE/tb/tb_core.sv" "$HERE/verif/sim_main.cpp" > "$OUT/verilator.log" 2>&1 || { tail -40 "$OUT/verilator.log"; exit 1; }
