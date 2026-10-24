// rvfi_wrapper.sv - connects rv32i_core to the riscv-formal checks. The two memories are free inputs: the checks only look at the
// retirement trace, so every possible instruction word and load value is explored. BP_MODE and FWD_PRECOMP come from -D defines.
`ifndef RV32I_BP_MODE
`define RV32I_BP_MODE 0
`endif
`ifndef RV32I_FWD_PRECOMP
`define RV32I_FWD_PRECOMP 1
`endif

module rvfi_wrapper (
    input clock,
    input reset,
    `RVFI_OUTPUTS
);
    (* keep *) `rvformal_rand_reg [31:0] imem_rdata;
    (* keep *) `rvformal_rand_reg [31:0] dmem_rdata;

    (* keep *) wire [31:0] imem_addr;
    (* keep *) wire [31:0] dmem_addr;
    (* keep *) wire        dmem_re;
    (* keep *) wire [3:0]  dmem_we;
    (* keep *) wire [31:0] dmem_wdata;
    (* keep *) wire        halted;

    assign rvfi_intr = 1'b0;
    assign rvfi_mode = 2'd3;
    assign rvfi_ixl  = 2'd1;

    rv32i_core #(.RESET_PC(32'h0), .BP_MODE(`RV32I_BP_MODE), .FWD_PRECOMP(`RV32I_FWD_PRECOMP), .RVFI_EN(1)) uut (
        .clk(clock), .rst_n(!reset),
        .imem_addr(imem_addr), .imem_rdata(imem_rdata),
        .dmem_addr(dmem_addr), .dmem_re(dmem_re), .dmem_we(dmem_we), .dmem_wdata(dmem_wdata), .dmem_rdata(dmem_rdata),
        .halted(halted),
        .rvfi_valid(rvfi_valid), .rvfi_order(rvfi_order), .rvfi_insn(rvfi_insn), .rvfi_trap(rvfi_trap), .rvfi_halt(rvfi_halt),
        .rvfi_pc_rdata(rvfi_pc_rdata), .rvfi_pc_wdata(rvfi_pc_wdata),
        .rvfi_rs1_addr(rvfi_rs1_addr), .rvfi_rs2_addr(rvfi_rs2_addr), .rvfi_rs1_rdata(rvfi_rs1_rdata), .rvfi_rs2_rdata(rvfi_rs2_rdata),
        .rvfi_rd_addr(rvfi_rd_addr), .rvfi_rd_wdata(rvfi_rd_wdata),
        .rvfi_mem_addr(rvfi_mem_addr), .rvfi_mem_rmask(rvfi_mem_rmask), .rvfi_mem_wmask(rvfi_mem_wmask),
        .rvfi_mem_rdata(rvfi_mem_rdata), .rvfi_mem_wdata(rvfi_mem_wdata)
    );
endmodule
