# sta_template.tcl - OpenSTA on a synthesised rv32i netlist (pre-layout: ideal clock, no wire parasitics, typical corner).
# Environment: NETLIST TOP SDC CLK_PERIOD_NS OUTDIR
read_liberty sky130hd/sky130hd_tt.lib
read_verilog $::env(NETLIST)
link_design $::env(TOP)
read_sdc $::env(SDC)
write_sdc -no_timestamp $::env(OUTDIR)/sdc_readback.sdc
set f [open $::env(OUTDIR)/timing.txt w]
puts $f "# pre-layout STA, ideal clock, no wire parasitics, sky130_fd_sc_hd tt_025C_1v80; period [get_property [get_clocks clk] period] ns"
close $f
report_checks -path_delay max -group_path_count 1 -digits 3 >> $::env(OUTDIR)/timing.txt
report_worst_slack -max -digits 3 >> $::env(OUTDIR)/timing.txt
report_tns -digits 3 >> $::env(OUTDIR)/timing.txt
report_checks -path_delay min -digits 3 >> $::env(OUTDIR)/timing.txt
report_worst_slack -min -digits 3 >> $::env(OUTDIR)/timing.txt
set f [open $::env(OUTDIR)/power.txt w]
puts $f "# switching activity: OpenSTA defaults (no VCD/SAIF), so this is not a measured workload"
close $f
report_power >> $::env(OUTDIR)/power.txt
exit
