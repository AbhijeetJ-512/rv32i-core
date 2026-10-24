# pnr/config.tcl - design names and floorplan size for rv32i_core (RVFI_EN=0, the synthesised configuration).
set design        "rv32i"
set top_module    "rv32i_core"
# The frozen post-synthesis netlist (pnr/run_pnr.sh copies it here from build/ppa/<configuration>/synth.v).
if {[info exists ::env(PNR_NETLIST)]} { set synth_verilog $::env(PNR_NETLIST) } else { set synth_verilog "build/pnr/synth.v" }

# Percent of the core area filled with standard cells (CORE_UTILIZATION in the environment overrides).
if {[info exists ::env(CORE_UTILIZATION)]} { set core_utilization $::env(CORE_UTILIZATION) } else { set core_utilization 40 }
set core_aspect_ratio 1
set core_space        5  ;# microns between core and die edge
