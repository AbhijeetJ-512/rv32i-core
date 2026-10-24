// rv32i_core - 5-stage in-order RV32I pipeline (IF, ID, EX, MEM, WB).
//
//   IF  : PC register; combinational instruction-memory read.
//   ID  : decode, register read (write-first bypass), load-use detection; optional early redirect (BP_MODE=1).
//   EX  : forwarding muxes, ALU, branch comparator, branch/jump target, redirect on mispredict or JALR.
//   MEM : data-memory access, byte strobes, load alignment, misalignment trap.
//   WB  : register-file write.
//
// Control hazards: BP_MODE=0 predicts every control transfer not-taken and resolves it in EX (2 bubbles when taken).
//                  BP_MODE=1 redirects JAL and backward-taken conditional branches from ID (1 bubble), so a correctly
//                  predicted loop branch costs 1 bubble instead of 2; a misprediction is repaired from EX (2 bubbles).
//                  JALR always resolves in EX (needs the forwarded rs1).
// Traps: ECALL, EBREAK, an illegal encoding or a misaligned load/store stops the core (no trap vector, no CSRs):
//        the instruction retires with rvfi_halt (and rvfi_trap unless ECALL/EBREAK), younger instructions are
//        squashed, `halted` stays high.
// Memories are outside the core: combinational read, synchronous write, no wait states.
// FWD_PRECOMP selects where the forwarding compare happens (see rv32i_hazard.sv); both variants are verified.
// RVFI_EN adds a retirement-trace port (a subset of the RISC-V Formal Interface) carried down the pipeline;
// RVFI_EN=0 removes it (that is the configuration synthesised for PPA).
`include "rv32i_defs.vh"

module rv32i_core #(
    parameter logic [31:0] RESET_PC = 32'h0000_0000,
    parameter int          BP_MODE  = 0,
    parameter int          FWD_PRECOMP = 1,   // 1: forwarding selects computed in ID and registered; 0: compared in EX
    parameter int          RVFI_EN  = 1
) (
    input  logic        clk,
    input  logic        rst_n,
    // instruction memory
    output logic [31:0] imem_addr,
    input  logic [31:0] imem_rdata,
    // data memory
    output logic [31:0] dmem_addr,     // word-aligned
    output logic        dmem_re,
    output logic [3:0]  dmem_we,       // byte strobes
    output logic [31:0] dmem_wdata,
    input  logic [31:0] dmem_rdata,
    output logic        halted,
    // retirement trace (RVFI subset), all zero when RVFI_EN = 0
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
    // ------------------------------------------------------------------ pipeline control (declared up front)
    logic        redirect_ex, redirect_id, trap_ex, trap_mem, stall_d;
    logic [31:0] target_ex, target_id;

    // ================================================================== IF
    logic [31:0] pc_f, pc_n;
    assign imem_addr = pc_f;

    always_comb begin
        if (halted)           pc_n = pc_f;
        else if (redirect_ex) pc_n = target_ex;
        else if (stall_d)     pc_n = pc_f;
        else if (redirect_id) pc_n = target_id;
        else                  pc_n = pc_f + 32'd4;
    end

    always_ff @(posedge clk) begin
        if (!rst_n) pc_f <= RESET_PC;
        else        pc_f <= pc_n;
    end

    // ---- IF/ID
    logic        valid_d;
    logic [31:0] pc_d, instr_d;
    logic        flush_if_id;
    assign flush_if_id = redirect_ex | redirect_id | trap_ex | trap_mem | halted;

    always_ff @(posedge clk) begin
        if (!rst_n || flush_if_id) valid_d <= 1'b0;
        else if (!stall_d)         valid_d <= 1'b1;
        if (!rst_n) begin
            pc_d    <= 32'b0;
            instr_d <= 32'b0;
        end else if (!flush_if_id && !stall_d) begin
            pc_d    <= pc_f;
            instr_d <= imem_rdata;
        end
    end

    // ================================================================== ID
    logic [4:0]  rs1_d, rs2_d, rd_d;
    logic [31:0] imm_d;
    logic [3:0]  alu_op_d;
    logic [1:0]  a_sel_d;
    logic        b_imm_d, reg_write_d, mem_read_d, mem_write_d;
    logic [2:0]  funct3_d;
    logic        is_branch_d, is_jal_d, is_jalr_d, uses_rs1_d, uses_rs2_d, is_halt_d, is_illegal_d;

    rv32i_decode u_decode (
        .instr(instr_d), .rs1(rs1_d), .rs2(rs2_d), .rd(rd_d), .imm(imm_d), .alu_op(alu_op_d),
        .a_sel(a_sel_d), .b_imm(b_imm_d), .reg_write(reg_write_d), .mem_read(mem_read_d),
        .mem_write(mem_write_d), .funct3(funct3_d), .is_branch(is_branch_d), .is_jal(is_jal_d),
        .is_jalr(is_jalr_d), .uses_rs1(uses_rs1_d), .uses_rs2(uses_rs2_d), .is_halt(is_halt_d),
        .is_illegal(is_illegal_d)
    );

    logic [31:0] rs1_data_d, rs2_data_d;
    logic        rw_w;
    logic [4:0]  rd_w;
    logic [31:0] wb_data_w;

    rv32i_regfile u_regfile (
        .clk(clk), .rst_n(rst_n), .ra1(rs1_d), .ra2(rs2_d), .rd1(rs1_data_d), .rd2(rs2_data_d),
        .we(rw_w), .wa(rd_w), .wd(wb_data_w)
    );

    // static prediction made in ID (BP_MODE = 1): JAL always, conditional branch when it jumps backwards
    logic pred_taken_d;
    assign pred_taken_d = (BP_MODE == 1) && is_branch_d && imm_d[31];
    assign target_id    = pc_d + imm_d;
    assign redirect_id  = (BP_MODE == 1) && valid_d && !stall_d && !redirect_ex && !trap_ex && !trap_mem &&
                          !halted && (is_jal_d || pred_taken_d);

    // ---- ID/EX
    logic        valid_e, reg_write_e, mem_read_e, mem_write_e, is_branch_e, is_jal_e, is_jalr_e, trap_e, pred_taken_e;
    logic [31:0] pc_e, imm_e, rs1_data_e, rs2_data_e;
    logic [4:0]  rs1_e, rs2_e, rd_e;
    logic [3:0]  alu_op_e;
    logic [1:0]  a_sel_e;
    logic        b_imm_e;
    logic [2:0]  funct3_e;
    logic        flush_id_ex;
    assign flush_id_ex = redirect_ex | trap_ex | trap_mem | halted;

    always_ff @(posedge clk) begin
        if (!rst_n || flush_id_ex || stall_d || !valid_d) begin
            valid_e     <= 1'b0;
            reg_write_e <= 1'b0;
            mem_read_e  <= 1'b0;
            mem_write_e <= 1'b0;
            is_branch_e <= 1'b0;
            is_jal_e    <= 1'b0;
            is_jalr_e   <= 1'b0;
            trap_e      <= 1'b0;
            pred_taken_e <= 1'b0;
        end else begin
            valid_e     <= 1'b1;
            reg_write_e <= reg_write_d;
            mem_read_e  <= mem_read_d;
            mem_write_e <= mem_write_d;
            is_branch_e <= is_branch_d;
            is_jal_e    <= is_jal_d;
            is_jalr_e   <= is_jalr_d;
            trap_e      <= is_halt_d | is_illegal_d;
            pred_taken_e <= pred_taken_d;
        end
        pc_e        <= pc_d;
        imm_e       <= imm_d;
        rs1_data_e  <= rs1_data_d;
        rs2_data_e  <= rs2_data_d;
        rs1_e       <= rs1_d;
        rs2_e       <= rs2_d;
        rd_e        <= rd_d;
        alu_op_e    <= alu_op_d;
        a_sel_e     <= a_sel_d;
        b_imm_e     <= b_imm_d;
        funct3_e    <= funct3_d;
    end

    // ================================================================== EX
    logic [1:0]  fwd_a, fwd_b, fwd_a_x, fwd_b_x, fwd_a_d, fwd_b_d, fwd_a_r, fwd_b_r;
    logic [4:0]  rd_m;
    logic        rw_m, mem_read_m;
    logic [31:0] alu_result_m;

    rv32i_hazard u_hazard (
        .valid_d(valid_d), .rs1_d(rs1_d), .rs2_d(rs2_d), .uses_rs1_d(uses_rs1_d), .uses_rs2_d(uses_rs2_d),
        .rs1_e(rs1_e), .rs2_e(rs2_e), .rd_e(rd_e), .mem_read_e(mem_read_e),
        .rd_m(rd_m), .rw_m(rw_m), .rd_w(rd_w), .rw_w(rw_w),
        .rd_e_pre(rd_e), .rw_e_pre(reg_write_e), .fwd_a_d(fwd_a_d), .fwd_b_d(fwd_b_d),
        .fwd_a(fwd_a_x), .fwd_b(fwd_b_x), .stall_d(stall_d)
    );

    always_ff @(posedge clk) begin
        fwd_a_r <= fwd_a_d;
        fwd_b_r <= fwd_b_d;
    end
    assign fwd_a = (FWD_PRECOMP != 0) ? fwd_a_r : fwd_a_x;
    assign fwd_b = (FWD_PRECOMP != 0) ? fwd_b_r : fwd_b_x;

    logic [31:0] rs1_fwd_e, rs2_fwd_e, alu_a_e, alu_b_e, alu_y_e;
    always_comb begin
        case (fwd_a)
            `FWD_MEM: rs1_fwd_e = alu_result_m;
            `FWD_WB:  rs1_fwd_e = wb_data_w;
            default:  rs1_fwd_e = rs1_data_e;
        endcase
        case (fwd_b)
            `FWD_MEM: rs2_fwd_e = alu_result_m;
            `FWD_WB:  rs2_fwd_e = wb_data_w;
            default:  rs2_fwd_e = rs2_data_e;
        endcase
        case (a_sel_e)
            `A_PC:   alu_a_e = pc_e;
            `A_ZERO: alu_a_e = 32'b0;
            default: alu_a_e = rs1_fwd_e;
        endcase
        alu_b_e = b_imm_e ? imm_e : rs2_fwd_e;
    end

    rv32i_alu u_alu (.a(alu_a_e), .b(alu_b_e), .op(alu_op_e), .y(alu_y_e));

    logic br_cmp_e, br_taken_e;
    rv32i_branch u_branch (.a(rs1_fwd_e), .b(rs2_fwd_e), .funct3(funct3_e), .taken(br_cmp_e));
    assign br_taken_e = is_branch_e & br_cmp_e;

    logic [31:0] pc4_e, target_add_e, jalr_target_e, result_e;
    assign pc4_e         = pc_e + 32'd4;
    assign target_add_e  = pc_e + imm_e;
    assign jalr_target_e = {alu_y_e[31:1], 1'b0};
    assign result_e      = (is_jal_e | is_jalr_e) ? pc4_e : alu_y_e;

    logic mispredict_e;
    assign mispredict_e = (BP_MODE == 1) ? (is_branch_e && (br_taken_e != pred_taken_e)) : br_taken_e;
    always_comb begin
        // BP_MODE = 1 handles JAL in ID; BP_MODE = 0 handles it here
        redirect_ex = valid_e && (mispredict_e || is_jalr_e || (BP_MODE == 0 && is_jal_e));
        if (is_jalr_e)                          target_ex = jalr_target_e;
        else if (BP_MODE == 1 && !br_taken_e)   target_ex = pc4_e;       // predicted taken, not taken
        else                                    target_ex = target_add_e;
    end
    assign trap_ex = valid_e && trap_e;

    // ---- EX/MEM
    logic        valid_m, mem_write_m;
    logic [31:0] store_data_m;
    logic [2:0]  funct3_m;

    always_ff @(posedge clk) begin
        if (!rst_n || trap_mem) begin
            valid_m     <= 1'b0;
            rw_m        <= 1'b0;
            mem_read_m  <= 1'b0;
            mem_write_m <= 1'b0;
        end else begin
            valid_m     <= valid_e;
            rw_m        <= reg_write_e;
            mem_read_m  <= mem_read_e;
            mem_write_m <= mem_write_e;
        end
        alu_result_m <= result_e;
        store_data_m <= rs2_fwd_e;
        rd_m         <= rd_e;
        funct3_m     <= funct3_e;
    end

    // ================================================================== MEM
    logic [3:0]  wstrb_m;
    logic [31:0] wdata_m, load_value_m;
    logic        misaligned_m;

    rv32i_lsu u_lsu (
        .funct3(funct3_m), .addr_lo(alu_result_m[1:0]), .store_data(store_data_m), .load_word(dmem_rdata),
        .wstrb(wstrb_m), .wdata(wdata_m), .load_value(load_value_m), .misaligned(misaligned_m)
    );

    logic mem_access_m;
    assign mem_access_m = valid_m && (mem_read_m || mem_write_m);
    assign trap_mem     = mem_access_m && misaligned_m;
    assign dmem_addr    = {alu_result_m[31:2], 2'b00};
    assign dmem_re      = valid_m && mem_read_m && !misaligned_m;
    assign dmem_we      = (valid_m && mem_write_m && !misaligned_m) ? wstrb_m : 4'b0000;
    assign dmem_wdata   = wdata_m;

    // ---- MEM/WB
    always_ff @(posedge clk) begin
        if (!rst_n) rw_w <= 1'b0;
        else        rw_w <= rw_m && !trap_mem;
        wb_data_w <= mem_read_m ? load_value_m : alu_result_m;
        rd_w      <= rd_m;
    end

    // ================================================================== halt state
    always_ff @(posedge clk) begin
        if (!rst_n)                       halted <= 1'b0;
        else if (trap_ex || trap_mem)     halted <= 1'b1;
    end

    // ================================================================== RVFI retirement trace
    if (RVFI_EN != 0) begin : g_rvfi
        logic [31:0] instr_e, instr_m, instr_w, next_pc_e, next_pc_m, next_pc_w;
        logic [31:0] rs1_rd_m, rs1_rd_w, rs2_rd_m, rs2_rd_w, rs1_rd_e, rs2_rd_e;
        logic [4:0]  rs1a_m, rs1a_w, rs2a_m, rs2a_w;
        logic        halt_e, halt_m, halt_w, ill_e, ill_m, ill_w, misal_w;
        logic [31:0] maddr_w, mrdata_w, mwdata_w;
        logic [3:0]  mrmask_w, mwmask_w;
        logic        uses1_e, uses2_e;
        logic [63:0] order;
        logic        valid_w;
        logic [31:0] pc_m, pc_w;

        // instruction word and decoder facts travel with the instruction
        always_ff @(posedge clk) begin
            instr_e <= instr_d;
            halt_e  <= is_halt_d;
            ill_e   <= is_illegal_d;
            uses1_e <= uses_rs1_d;
            uses2_e <= uses_rs2_d;
        end

        always_comb begin
            if (is_jalr_e)                      next_pc_e = jalr_target_e;
            else if (is_jal_e || br_taken_e)    next_pc_e = target_add_e;
            else                                next_pc_e = pc4_e;
            rs1_rd_e = uses1_e ? rs1_fwd_e : 32'b0;
            rs2_rd_e = uses2_e ? rs2_fwd_e : 32'b0;
        end

        always_ff @(posedge clk) begin
            pc_m      <= pc_e;
            instr_m   <= instr_e;   next_pc_m <= next_pc_e;
            rs1_rd_m  <= rs1_rd_e;  rs2_rd_m  <= rs2_rd_e;
            rs1a_m    <= uses1_e ? rs1_e : 5'd0;  rs2a_m <= uses2_e ? rs2_e : 5'd0;
            halt_m    <= halt_e;    ill_m     <= ill_e;
        end

        always_ff @(posedge clk) begin
            if (!rst_n) valid_w <= 1'b0;
            else        valid_w <= valid_m;
            pc_w      <= pc_m;
            instr_w   <= instr_m;   next_pc_w <= next_pc_m;
            rs1_rd_w  <= rs1_rd_m;  rs2_rd_w  <= rs2_rd_m;
            rs1a_w    <= rs1a_m;    rs2a_w    <= rs2a_m;
            halt_w    <= halt_m;    ill_w     <= ill_m;
            misal_w   <= trap_mem;
            maddr_w   <= dmem_addr;
            mrdata_w  <= dmem_rdata;
            mwdata_w  <= wdata_m;
            mrmask_w  <= (valid_m && mem_read_m && !misaligned_m) ?
                         ((funct3_m[1:0] == 2'b00) ? (4'b0001 << alu_result_m[1:0]) :
                          (funct3_m[1:0] == 2'b01) ? (4'b0011 << {alu_result_m[1], 1'b0}) : 4'b1111) : 4'b0000;
            mwmask_w  <= dmem_we;
        end
        always_ff @(posedge clk) begin
            if (!rst_n) order <= 64'd0;
            else if (valid_w) order <= order + 64'd1;
        end

        assign rvfi_valid     = valid_w;
        assign rvfi_order     = order;
        assign rvfi_insn      = instr_w;
        assign rvfi_halt      = valid_w && (halt_w || ill_w || misal_w);
        assign rvfi_trap      = valid_w && (ill_w || misal_w);
        assign rvfi_pc_rdata  = pc_w;
        assign rvfi_pc_wdata  = next_pc_w;
        assign rvfi_rs1_addr  = rs1a_w;
        assign rvfi_rs2_addr  = rs2a_w;
        assign rvfi_rs1_rdata = rs1_rd_w;
        assign rvfi_rs2_rdata = rs2_rd_w;
        assign rvfi_rd_addr   = (rw_w) ? rd_w : 5'd0;
        assign rvfi_rd_wdata  = (rw_w && rd_w != 5'd0) ? wb_data_w : 32'd0;
        assign rvfi_mem_addr  = (mrmask_w != 4'd0 || mwmask_w != 4'd0) ? maddr_w : 32'd0;
        assign rvfi_mem_rmask = mrmask_w;
        assign rvfi_mem_wmask = mwmask_w;
        assign rvfi_mem_rdata = (mrmask_w != 4'd0) ? mrdata_w : 32'd0;
        assign rvfi_mem_wdata = (mwmask_w != 4'd0) ? mwdata_w : 32'd0;
    end else begin : g_no_rvfi
        assign rvfi_valid = 1'b0;      assign rvfi_order = 64'd0;     assign rvfi_insn = 32'd0;
        assign rvfi_trap = 1'b0;       assign rvfi_halt = 1'b0;       assign rvfi_pc_rdata = 32'd0;
        assign rvfi_pc_wdata = 32'd0;  assign rvfi_rs1_addr = 5'd0;   assign rvfi_rs2_addr = 5'd0;
        assign rvfi_rs1_rdata = 32'd0; assign rvfi_rs2_rdata = 32'd0; assign rvfi_rd_addr = 5'd0;
        assign rvfi_rd_wdata = 32'd0;  assign rvfi_mem_addr = 32'd0;  assign rvfi_mem_rmask = 4'd0;
        assign rvfi_mem_wmask = 4'd0;  assign rvfi_mem_rdata = 32'd0; assign rvfi_mem_wdata = 32'd0;
    end
endmodule
