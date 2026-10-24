#!/usr/bin/env bash
# run_pnr.sh <period_ns> [config] - OpenROAD place and route of rv32i_core (Sky130 HD) at one clock period.
#   config: bp1_fwd1 (default; BP_MODE=1 FWD_PRECOMP=1), bp0_fwd1, bp1_fwd0, bp0_fwd0 - which post-synthesis netlist to use
# The netlist is the timing-driven (`speed`) Yosys mapping that `make ppa` writes to build/ppa/pipe_<config>_speed_p10/synth.v.
# Results: results/pnr/<config>_p<period>/ (log, reports, databases). Environment: CORE_UTILIZATION (40), PNR_SETUP_MARGIN (0.3),
# PNR_THREADS (2), PNR_STOP_AFTER (floorplan|place|cts|repair; unset = full flow).
set -eu
cd "$(dirname "$0")/.."
period=${1:?usage: pnr/run_pnr.sh <period_ns> [config]}
cfg=${2:-bp1_fwd1}
src=build/ppa/pipe_${cfg}_speed_p10/synth.v
[ -s "$src" ] || { echo "missing $src: run 'make ppa' first" >&2; exit 1; }
tag=${cfg}_p${period}
out=results/pnr/$tag
work=build/pnr/$tag
rm -rf "$out" "$work"; mkdir -p "$out" "$work"
cp "$src" "$work/synth.v"; cp "$(dirname "$src")/stat.txt" "$work/stat.txt"
sha256sum "$work/synth.v" > "$out/netlist.sha256"
{ echo "config=$cfg"; echo "netlist_source=$src"; echo "openroad=$(openroad -version 2>&1 | head -n 1)"; echo "yosys=$(yosys -V 2>&1 | head -n 1)"; } > "$out/tool_versions.txt"
export CLK_PERIOD_NS=$period PNR_NETLIST=$work/synth.v PNR_RESULTS=$out PNR_THREADS=${PNR_THREADS:-2}
openroad -exit pnr/pnr_flow.tcl > "$out/pnr.log" 2>&1 || { echo "OpenROAD failed for $tag; tail of $out/pnr.log:" >&2; tail -n 25 "$out/pnr.log" >&2; exit 1; }
cp "$work/stat.txt" "$out/stat.txt"
echo "[PNR ] $tag done: $out"
