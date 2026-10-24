// rv32i_core_1cyc - single-cycle RV32I baseline: the same decoder, ALU, branch comparator, register file and
// load/store unit as the pipelined core, but fetch, decode, execute, memory access and write-back all happen in one
// clock cycle (CPI = 1, long critical path). It exists only so the pipelined core's frequency and throughput gain
// can be MEASURED against a same-RTL baseline instead of asserted. Same ports and trap behaviour as rv32i_core.
`include "rv32i_defs.vh"

module rv32i_core_1cyc #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter int          RVFI_EN  = 1
) (
    input  logic        clk,
    input  logic        rst_n,
    output logic [31:0] imem_addr,
    input  logic [31:0] imem_rdata,
    output logic [31:0] dmem_addr,
    output logic        dmem_re,
    output logic [3:0]  dmem_we,
    output logic [31:0] dmem_wdata,
    input  logic [31:0] dmem_rdata,
    output logic        halted,
    output logic        rvfi_valid,
    output logic [63:0] rvfi_order,
    output logic [31:0] rvfi_insn,
    output logic        rvfi_trap,
    output logic        rvfi_halt,
    output logic [31:0] rvfi_pc_rdata,
    output logic [31:0] rvfi_pc_wdata,
    output logic [4:0]  rvfi_rs1_addr,
    output logic [4:0]  rvfi_rs2_addr,
    output logic [31:0] rvfi_rs1_rdata,
    output logic [31:0] rvfi_rs2_rdata,
    output logic [4:0]  rvfi_rd_addr,
    output logic [31:0] rvfi_rd_wdata,
    output logic [31:0] rvfi_mem_addr,
    output logic [3:0]  rvfi_mem_rmask,
    output logic [3:0]  rvfi_mem_wmask,
    output logic [31:0] rvfi_mem_rdata,
    output logic [31:0] rvfi_mem_wdata
);
    // stall / redirect names exist only so the shared testbench's counters compile; a single-cycle core has none
    /* verilator lint_off UNUSEDSIGNAL */
    logic stall_d, redirect_ex, redirect_id;
    /* verilator lint_on UNUSEDSIGNAL */
    assign stall_d = 1'b0;
    assign redirect_ex = 1'b0;
    assign redirect_id = 1'b0;

    logic [31:0] pc;
    assign imem_addr = pc;

    logic [4:0]  rs1, rs2, rd;
    logic [31:0] imm, rs1_data, rs2_data, alu_a, alu_b, alu_y, load_value, wdata_lsu, pc4, target, next_pc, result;
    logic [3:0]  alu_op, wstrb;
    logic [1:0]  a_sel;
    logic        b_imm, reg_write, mem_read, mem_write, is_branch, is_jal, is_jalr, uses_rs1, uses_rs2, is_halt, is_illegal;
    logic [2:0]  funct3;
    logic        br_cmp, misaligned, we_rf, active, trap_now;

    assign active = !halted;

    rv32i_decode u_decode (
        .instr(imem_rdata), .rs1, .rs2, .rd, .imm, .alu_op, .a_sel, .b_imm, .reg_write, .mem_read, .mem_write,
        .funct3, .is_branch, .is_jal, .is_jalr, .uses_rs1, .uses_rs2, .is_halt, .is_illegal
    );

    rv32i_regfile #(.BYPASS(1'b0)) u_regfile (
        .clk, .rst_n, .ra1(rs1), .ra2(rs2), .rd1(rs1_data), .rd2(rs2_data), .we(we_rf), .wa(rd), .wd(result)
    );

    always_comb begin
        case (a_sel)
            `A_PC:   alu_a = pc;
            `A_ZERO: alu_a = 32'b0;
            default: alu_a = rs1_data;
        endcase
        alu_b = b_imm ? imm : rs2_data;
    end

    rv32i_alu    u_alu    (.a(alu_a), .b(alu_b), .op(alu_op), .y(alu_y));
    rv32i_branch u_branch (.a(rs1_data), .b(rs2_data), .funct3(funct3), .taken(br_cmp));
    rv32i_lsu    u_lsu    (.funct3(funct3), .addr_lo(alu_y[1:0]), .store_data(rs2_data), .load_word(dmem_rdata),
                           .wstrb(wstrb), .wdata(wdata_lsu), .load_value(load_value), .misaligned(misaligned));

    assign pc4     = pc + 32'd4;
    assign target  = pc + imm;
    logic misal_tgt;   // taken branch / JAL / JALR to a target that is not 4-byte aligned: traps, no link write, pc does not move
    assign misal_tgt = active && (((is_jal || (is_branch && br_cmp)) && (target[1:0] != 2'b00)) || (is_jalr && alu_y[1]));
    always_comb begin
        if (misal_tgt)                       next_pc = pc4;
        else if (is_jalr)                    next_pc = {alu_y[31:1], 1'b0};
        else if (is_jal || (is_branch && br_cmp)) next_pc = target;
        else                                 next_pc = pc4;
    end
    assign result = (is_jal || is_jalr) ? pc4 : (mem_read ? load_value : alu_y);

    assign trap_now  = active && (is_halt || is_illegal || misal_tgt || ((mem_read || mem_write) && misaligned));
    assign we_rf     = active && reg_write && !misal_tgt && !((mem_read || mem_write) && misaligned);
    assign dmem_addr = {alu_y[31:2], 2'b00};
    assign dmem_re   = active && mem_read && !misaligned;
    assign dmem_we   = (active && mem_write && !misaligned) ? wstrb : 4'b0000;
    assign dmem_wdata = wdata_lsu;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            pc     <= RESET_PC;
            halted <= 1'b0;
        end else if (active) begin
            pc <= next_pc;
            if (trap_now) halted <= 1'b1;
        end
    end

    if (RVFI_EN != 0) begin : g_rvfi
        logic [63:0] order;
        logic [3:0]  rmask;
        always_comb begin
            rmask = 4'b0000;
            if (active && mem_read && !misaligned)
                rmask = (funct3[1:0] == 2'b00) ? (4'b0001 << alu_y[1:0]) : (funct3[1:0] == 2'b01) ? (4'b0011 << {alu_y[1], 1'b0}) : 4'b1111;
        end
        always_ff @(posedge clk) begin
            if (!rst_n)      order <= 64'd0;
            else if (active) order <= order + 64'd1;
        end
        assign rvfi_valid     = active && rst_n;
        assign rvfi_order     = order;
        assign rvfi_insn      = imem_rdata;
        assign rvfi_halt      = trap_now;
        assign rvfi_trap      = active && (is_illegal || misal_tgt || ((mem_read || mem_write) && misaligned));
        assign rvfi_pc_rdata  = pc;
        assign rvfi_pc_wdata  = next_pc;
        assign rvfi_rs1_addr  = uses_rs1 ? rs1 : 5'd0;
        assign rvfi_rs2_addr  = uses_rs2 ? rs2 : 5'd0;
        assign rvfi_rs1_rdata = uses_rs1 ? rs1_data : 32'd0;
        assign rvfi_rs2_rdata = uses_rs2 ? rs2_data : 32'd0;
        assign rvfi_rd_addr   = (we_rf && rd != 5'd0) ? rd : 5'd0;
        assign rvfi_rd_wdata  = (we_rf && rd != 5'd0) ? result : 32'd0;
        assign rvfi_mem_rmask = rmask;
        assign rvfi_mem_wmask = dmem_we;
        assign rvfi_mem_addr  = (rmask != 4'd0 || dmem_we != 4'd0) ? dmem_addr : 32'd0;
        assign rvfi_mem_rdata = (rmask != 4'd0) ? dmem_rdata : 32'd0;
        assign rvfi_mem_wdata = (dmem_we != 4'd0) ? wdata_lsu : 32'd0;
    end else begin : g_no_rvfi
        assign rvfi_valid = 1'b0;      assign rvfi_order = 64'd0;     assign rvfi_insn = 32'd0;
        assign rvfi_trap = 1'b0;       assign rvfi_halt = 1'b0;       assign rvfi_pc_rdata = 32'd0;
        assign rvfi_pc_wdata = 32'd0;  assign rvfi_rs1_addr = 5'd0;   assign rvfi_rs2_addr = 5'd0;
        assign rvfi_rs1_rdata = 32'd0; assign rvfi_rs2_rdata = 32'd0; assign rvfi_rd_addr = 5'd0;
        assign rvfi_rd_wdata = 32'd0;  assign rvfi_mem_addr = 32'd0;  assign rvfi_mem_rmask = 4'd0;
        assign rvfi_mem_wmask = 4'd0;  assign rvfi_mem_rdata = 32'd0; assign rvfi_mem_wdata = 32'd0;
    end
endmodule
