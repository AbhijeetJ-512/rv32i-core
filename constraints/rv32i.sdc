# rv32i.sdc - timing constraints for rv32i_core / rv32i_core_1cyc (same constraints for both, so the comparison is fair).
# The clock period comes from the environment (CLK_PERIOD_NS), the one source shared with Yosys `abc -D`.
#
# Memory interface budget (an ASSUMPTION about the surrounding system, not a result): the instruction and data memories
# are outside the core. A synchronous SRAM is modelled by its two timing numbers:
#   read data arrives MEM_IN  ns after the clock edge     (clock-to-output of the memory)
#   address / write data / strobes must be stable MEM_OUT ns before the next edge (memory setup)
# Absolute nanoseconds, not a fraction of the period, so the figures stay comparable across clock periods.
set period  $::env(CLK_PERIOD_NS)
set mem_in  2.0
set mem_out 1.0

create_clock -name clk -period $period [get_ports clk]

set_input_delay  $mem_in -clock clk [get_ports {imem_rdata[*] dmem_rdata[*]}]
set_input_delay  0.5     -clock clk [get_ports rst_n]
set_output_delay $mem_out -clock clk [get_ports {imem_addr[*] dmem_addr[*] dmem_re dmem_we[*] dmem_wdata[*]}]
set_output_delay 0.5      -clock clk [get_ports halted]

set_driving_cell -lib_cell sky130_fd_sc_hd__buf_2 -pin X [get_ports {imem_rdata[*] dmem_rdata[*] rst_n}]
set_load 0.02 [all_outputs]
