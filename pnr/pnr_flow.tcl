# pnr_flow.tcl - OpenROAD physical design flow for rv32i_core (Sky130 HD), run from the project root:  pnr/run_pnr.sh <period_ns>
# Adapted from alu_fifo/scripts/pnr_flow.tcl (same stages: floorplan, global placement, repair_design, CTS, repair_timing, global and
# detailed route, antenna repair, parasitic extraction, final reports). Differences: design names, the netlist and constraints come
# from the environment (set by pnr/run_pnr.sh), results go to PNR_RESULTS.
#
# PNR_STOP_AFTER=floorplan|place|cts|repair stops after that stage.

source pnr/config.tcl
source sky130hd/sky130hd.vars
source pnr/helpers.tcl
source pnr/flow_helpers.tcl
set ::constraints_sdc "constraints/rv32i.sdc"

# Setup margin (ns) asked of repair_timing (PNR_SETUP_MARGIN, default 0.3, the value alu_fifo used; not tuned for this design).
if {[info exists ::env(PNR_SETUP_MARGIN)]} { set repair_setup_margin $::env(PNR_SETUP_MARGIN) } else { set repair_setup_margin 0.3 }

# PNR_GRT_ANTENNA=0 skips the antenna repair between global and detailed routing (default 1, as in alu_fifo). Reason this switch exists: at 6.0 ns and 7.0 ns
# that step crashed OpenROAD with GRT-0183 (heap underflow in 3D maze routing of the clock net, results/pnr_grt_antenna/); the antenna repair after detailed
# routing is unaffected and its result is the one reported.
if {[info exists ::env(PNR_GRT_ANTENNA)]} { set grt_antenna $::env(PNR_GRT_ANTENNA) } else { set grt_antenna 1 }

# Slew and capacitance margins (percent) for repair_design (20 / 20 as in alu_fifo; not tuned for this design).
set slew_margin 20
set cap_margin 20

# PNR_SET (environment, experiments only): "var value var value ..." overrides platform variables; every override is logged.
if {[info exists ::env(PNR_SET)]} {
  foreach {k v} $::env(PNR_SET) {
    puts "PNR_SET override: $k = $v (was [expr {[info exists $k] ? [set $k] : {unset}}])"
    set $k $v
  }
}

# Target placement density: the platform's 0.9 suits Full-Adder's tiny fixed die, not a 40%-utilisation core.
# PLACE_DENSITY (environment) overrides; the default follows the common rule of utilisation + 0.2.
if {[info exists ::env(PLACE_DENSITY)]} {
  set global_place_density $::env(PLACE_DENSITY)
} else {
  set global_place_density [expr {$core_utilization / 100.0 + 0.2}]
}
puts "global_place_density = $global_place_density (core utilisation $core_utilization%)"

# Override the helpers' default result directory
if {[info exists ::env(PNR_RESULTS)]} { set ::result_dir $::env(PNR_RESULTS) } else { set ::result_dir "results/pnr" }
if {![file exists $::result_dir]} { file mkdir $::result_dir }

set stop_after ""
if {[info exists ::env(PNR_STOP_AFTER)]} { set stop_after $::env(PNR_STOP_AFTER) }
proc stage_done {name} {
  global stop_after
  puts "=== stage complete: $name"
  if {$stop_after eq $name} {
    puts "PNR_STOP_AFTER=$name: stopping here"
    exit 0
  }
}

# ---------------------------------------------------------------- stage: floorplan
read_libraries
read_verilog $synth_verilog
link_design $top_module
read_sdc $::constraints_sdc

# What this run was made with, from the loaded design and the variables actually in force (make summary and
# scripts/pnr_check.sh read it back; a stale or mismatched results directory shows up as a mismatch here).
set fh [open $::result_dir/run_conditions.txt w]
puts $fh "clock_period_ns=[get_property [get_clocks clk] period]"
puts $fh "core_utilization=$core_utilization"
puts $fh "global_place_density=$global_place_density"
puts $fh "repair_setup_margin=$repair_setup_margin"
puts $fh "grt_antenna_repair=$grt_antenna"
puts $fh "pnr_stop_after=$stop_after"
puts $fh "pnr_set=[expr {[info exists ::env(PNR_SET)] ? $::env(PNR_SET) : {}}]"
close $fh

# One thread per core by default; PNR_THREADS limits it (several flows on one machine thrash otherwise).
if {[info exists ::env(PNR_THREADS)]} { set_thread_count $::env(PNR_THREADS) } else { set_thread_count [cpu_count] }
sta::set_thread_count 1

initialize_floorplan -utilization $core_utilization -aspect_ratio $core_aspect_ratio \
  -core_space $core_space -site $site
source $tracks_file

# remove buffers inserted by synthesis
remove_buffers

eval tapcell $tapcell_args
source $pdn_cfg
pdngen
stage_done floorplan

# ---------------------------------------------------------------- stage: place
foreach layer_adjustment $global_routing_layer_adjustments {
  lassign $layer_adjustment layer adjustment
  set_global_routing_layer_adjustment $layer $adjustment
}
set_routing_layers -signal $global_routing_layers -clock $global_routing_clock_layers
set_macro_extension 2

global_placement -density $global_place_density -pad_left $global_place_pad -pad_right $global_place_pad -skip_io
place_pins -hor_layers $io_placer_hor_layer -ver_layers $io_placer_ver_layer
global_placement -routability_driven -density $global_place_density \
  -pad_left $global_place_pad -pad_right $global_place_pad
write_db [make_result_file ${design}_${platform}_global_place.db]

# Repair max slew/cap/fanout violations and normalise slews (ideal clocks)
source $layer_rc_file
set_wire_rc -signal -layer $wire_rc_layer
set_wire_rc -clock -layer $wire_rc_layer_clk
set_dont_use $dont_use
estimate_parasitics -placement
repair_design -slew_margin $slew_margin -cap_margin $cap_margin
repair_tie_fanout -separation $tie_separation $tielo_port
repair_tie_fanout -separation $tie_separation $tiehi_port
set_placement_padding -global -left $detail_place_pad -right $detail_place_pad
detailed_placement

puts "--- after repair_design (ideal clocks)"
report_worst_slack -min -digits 3
report_worst_slack -max -digits 3
report_tns -digits 3
report_check_types -max_slew -max_capacitance -max_fanout -violators
stage_done place

# ---------------------------------------------------------------- stage: cts
# Clone clock tree inverters next to register loads so cts does not try to buffer inverted clocks.
repair_clock_inverters
clock_tree_synthesis -root_buf $cts_buffer -buf_list $cts_buffer \
  -sink_clustering_enable -sink_clustering_max_diameter $cts_cluster_diameter
repair_clock_nets
detailed_placement
write_db [make_result_file ${design}_${platform}_cts.db]
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 3 > $::result_dir/check_types_postcts.rpt
stage_done cts

# ---------------------------------------------------------------- stage: repair
set_propagated_clock [all_clocks]
estimate_parasitics -placement
repair_timing -skip_gate_cloning -setup_margin $repair_setup_margin

puts "--- after repair_timing (propagated clock, placement parasitics)"
report_worst_slack -min -digits 3
report_worst_slack -max -digits 3
report_tns -digits 3
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 3 > $::result_dir/check_types_postrepair.rpt

detailed_placement
write_db [make_result_file ${design}_${platform}_repair.db]
write_verilog [make_result_file ${design}_${platform}.v]
stage_done repair

# ---------------------------------------------------------------- stage: route
pin_access
set route_guide [make_result_file ${design}_${platform}.route_guide]
global_route -guide_file $route_guide -congestion_iterations 100 -verbose
write_verilog -remove_cells $filler_cells [make_result_file ${design}_${platform}.v]

# Repair antennas after global routing, then route in detail
if {$grt_antenna} {
  repair_antennas -iterations 5
  check_antennas
} else {
  puts "PNR_GRT_ANTENNA=0: antenna repair between global and detailed routing skipped"
}

pin_access
detailed_route -output_drc [make_result_file "${design}_${platform}_route_drc.rpt"] \
  -output_maze [make_result_file "${design}_${platform}_maze.log"] \
  -no_pin_access -verbose 0
write_db  [make_result_file ${design}_${platform}_route.db]
write_def [make_result_file ${design}_${platform}_route.def]

# Repair antennas after detailed routing (each pass re-routes), as in the reference flow
set repair_antennas_iters 0
while { [check_antennas] && $repair_antennas_iters < 5 } {
  repair_antennas
  detailed_route -output_drc [make_result_file "${design}_${platform}_ant_fix_drc.rpt"] \
    -output_maze [make_result_file "${design}_${platform}_ant_fix_maze.log"] -verbose 0
  incr repair_antennas_iters
}
check_antennas -verbose -report_file $::result_dir/antenna_detail.rpt
set drv_count [detailed_route_num_drvs]
set ant_count [ant::antenna_violation_count]

if { ![design_is_routed] } { error "Design has unrouted nets." }
stage_done route

# ---------------------------------------------------------------- stage: extract
# Design area before fillers make the utilisation 100%. report_design_area logs instead of
# redirecting, so the line is written from the same API values.
set fh [open $::result_dir/area_final.rpt w]
puts $fh "Design area [sta::format_area [rsz::design_area] 0] u^2 [format %.1f [expr [rsz::utilization] * 100]]% utilization (standard cells and tapcells, before filler cells)"
close $fh

filler_placement $filler_cells
check_placement -verbose
write_db [make_result_file ${design}_${platform}_fill.db]

define_process_corner -ext_model_index 0 X
extract_parasitics -ext_model_file $rcx_rules_file
set spef_file [make_result_file ${design}_${platform}.spef]
write_spef $spef_file
read_spef $spef_file
write_def [make_result_file ${design}_${platform}_final.def]
stage_done extract

# ---------------------------------------------------------------- final reports (routed, extracted, propagated clock)
report_checks -path_delay min_max -format full_clock_expanded -fields {input_pin slew capacitance} -digits 3 \
  > $::result_dir/timing_final.rpt
report_worst_slack -max -digits 3 >> $::result_dir/timing_final.rpt
report_worst_slack -min -digits 3 >> $::result_dir/timing_final.rpt
report_tns -digits 3 >> $::result_dir/timing_final.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 3 > $::result_dir/check_types_final.rpt
report_clock_skew -digits 3 > $::result_dir/clock_skew.rpt
report_power -corner $power_corner > $::result_dir/power_final.rpt
report_floating_nets -verbose > $::result_dir/floating_nets.rpt

set fh [open $::result_dir/drc_count.txt w]
puts $fh "drc_violations=$drv_count"
close $fh
set fh [open $::result_dir/antenna.rpt w]
puts $fh "antenna_violations=$ant_count"
puts $fh "(detail: antenna_detail.rpt)"
close $fh

puts "Final: drc_violations=$drv_count antenna_violations=$ant_count"
puts "PnR flow complete. Results (DEF/DB/SPEF/reports) in $::result_dir/"
