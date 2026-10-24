// rv32i_checker - bound assertions and cover points for rv32i_core (attached by verif/checker_binds.sv).
//
// Conventions: every assertion is labelled `a_*`, every cover `c_*`; scripts/mutants.py binds each deliberate RTL
// bug to the assertion that must catch it. Ready/valid-style "whenever / only when" pairs are written in BOTH
// directions (an "only if" alone lets a unit that never acts pass). Verilator 5.020 has no `##` sequence delays and
// no covergroups, so properties use |-> |=> $past, and coverage is named cover points plus Verilator line/toggle.
`include "rv32i_defs.vh"

module rv32i_checker #(
    parameter int BP_MODE = 0
) (
    input logic        clk,
    input logic        rst_n,
    // pipeline valid bits and control
    input logic        valid_d, valid_e, valid_m,
    input logic        rw_m, rw_w, mem_read_e, mem_read_m, mem_write_m, reg_write_e,
    input logic [4:0]  rs1_d, rs2_d, rs1_e, rs2_e, rd_e, rd_m, rd_w,
    input logic        uses_rs1_d, uses_rs2_d,
    input logic        uses1_e, uses2_e,        // does the instruction in EX actually read rs1 / rs2
    input logic [1:0]  fwd_a, fwd_b,
    input logic        stall_d,
    input logic        redirect_ex, redirect_id, trap_ex, trap_mem, halted,
    input logic        is_branch_e, is_jal_e, is_jalr_e, br_taken_e, pred_taken_e, pred_taken_d, is_branch_d, is_jal_d,
    input logic        trap_e, misal_tgt_e,
    input logic [31:0] pc_f, pc_d, instr_d, target_ex, target_id, target_add_e, jalr_target_e,
    input logic [31:0] alu_result_m, wb_data_w,
    input logic [2:0]  funct3_m,
    input logic        misaligned_m,
    // memory port
    input logic        dmem_re,
    input logic [3:0]  dmem_we,
    // retirement trace
    input logic        rvfi_valid, rvfi_halt, rvfi_trap,
    input logic [63:0] rvfi_order,
    input logic [31:0] rvfi_insn,
    input logic [4:0]  rvfi_rd_addr,
    input logic [31:0] rvfi_rd_wdata
);
    // ------------------------------------------------------------------ forwarding: exactly the rule, both directions
    // (only for a valid instruction in EX: a bubble has no operands, and with precomputed selects its select is don't-care)
    logic hit_a_m, hit_a_w, hit_b_m, hit_b_w;
    assign hit_a_m = rw_m && rd_m != 5'd0 && rd_m == rs1_e;
    assign hit_a_w = rw_w && rd_w != 5'd0 && rd_w == rs1_e;
    assign hit_b_m = rw_m && rd_m != 5'd0 && rd_m == rs2_e;
    assign hit_b_w = rw_w && rd_w != 5'd0 && rd_w == rs2_e;

    a_fwd_a_mem_only:   assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_MEM |-> hit_a_m);
    a_fwd_a_mem_always: assert property (@(posedge clk) disable iff (!rst_n) valid_e && hit_a_m |-> fwd_a == `FWD_MEM);
    a_fwd_a_wb_only:    assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_WB |-> (hit_a_w && !hit_a_m));
    a_fwd_a_wb_always:  assert property (@(posedge clk) disable iff (!rst_n) valid_e && (hit_a_w && !hit_a_m) |-> fwd_a == `FWD_WB);
    a_fwd_a_none:       assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_NONE |-> (!hit_a_m && !hit_a_w));
    a_fwd_b_mem_only:   assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_b == `FWD_MEM |-> hit_b_m);
    a_fwd_b_mem_always: assert property (@(posedge clk) disable iff (!rst_n) valid_e && hit_b_m |-> fwd_b == `FWD_MEM);
    a_fwd_b_wb_only:    assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_b == `FWD_WB |-> (hit_b_w && !hit_b_m));
    a_fwd_b_wb_always:  assert property (@(posedge clk) disable iff (!rst_n) valid_e && (hit_b_w && !hit_b_m) |-> fwd_b == `FWD_WB);
    a_fwd_b_none:       assert property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_b == `FWD_NONE |-> (!hit_b_m && !hit_b_w));

    // ------------------------------------------------------------------ load-use stall: whenever and only when
    logic lu_hazard;
    assign lu_hazard = valid_d && mem_read_e && rd_e != 5'd0 &&
                       ((uses_rs1_d && rs1_d == rd_e) || (uses_rs2_d && rs2_d == rd_e));
    a_stall_always:     assert property (@(posedge clk) disable iff (!rst_n) lu_hazard |-> stall_d);
    a_stall_only:       assert property (@(posedge clk) disable iff (!rst_n) stall_d |-> lu_hazard);
    a_stall_bubble:     assert property (@(posedge clk) disable iff (!rst_n) (stall_d && !trap_mem) |=> !valid_e);              // a bubble enters EX
    a_stall_holds_pc:   assert property (@(posedge clk) disable iff (!rst_n) (stall_d && !halted && !trap_mem) |=> pc_f == $past(pc_f));
    a_stall_holds_id:   assert property (@(posedge clk) disable iff (!rst_n) (stall_d && !trap_mem) |=> (valid_d && pc_d == $past(pc_d) && instr_d == $past(instr_d)));
    // The invariant the stall exists to establish: a consumer is never in EX directly behind the load that feeds it
    // (a load's data is not available for forwarding from MEM). If the hazard check were wrong, this fires.
    a_no_load_use_slip: assert property (@(posedge clk) disable iff (!rst_n) !(valid_e && valid_m && mem_read_m && rw_m && rd_m != 5'd0 &&
                                           ((uses1_e && rs1_e == rd_m) || (uses2_e && rs2_e == rd_m))));

    // ------------------------------------------------------------------ control flow
    a_jalr_redirects:   assert property (@(posedge clk) disable iff (!rst_n) (valid_e && is_jalr_e && !misal_tgt_e) |-> redirect_ex);
    a_redirect_only:    assert property (@(posedge clk) disable iff (!rst_n) redirect_ex |-> (valid_e && (is_branch_e || is_jalr_e || is_jal_e)));
    generate
        if (BP_MODE == 0) begin : g_bp0
            a_taken_redirects: assert property (@(posedge clk) disable iff (!rst_n) (valid_e && (br_taken_e || is_jal_e) && !misal_tgt_e) |-> redirect_ex);
            a_nt_no_redirect:  assert property (@(posedge clk) disable iff (!rst_n) (valid_e && is_branch_e && !br_taken_e) |-> !redirect_ex);
            a_no_id_redirect:  assert property (@(posedge clk) disable iff (!rst_n) !redirect_id);
        end else begin : g_bp1
            a_mispredict:      assert property (@(posedge clk) disable iff (!rst_n) (valid_e && is_branch_e && (br_taken_e != pred_taken_e) && !misal_tgt_e) |-> redirect_ex);
            a_predict_ok:      assert property (@(posedge clk) disable iff (!rst_n) (valid_e && is_branch_e && (br_taken_e == pred_taken_e)) |-> !redirect_ex);
            a_jal_in_id:       assert property (@(posedge clk) disable iff (!rst_n) (valid_d && is_jal_d && !stall_d && !redirect_ex && !trap_ex && !trap_mem && !halted && target_id[1:0] == 2'b00) |-> redirect_id);
            a_id_redirect_only: assert property (@(posedge clk) disable iff (!rst_n) redirect_id |-> (valid_d && (is_jal_d || (is_branch_d && pred_taken_d))));
            a_btfn:            assert property (@(posedge clk) disable iff (!rst_n) (valid_d && is_branch_d) |-> (pred_taken_d == instr_d[31]));
        end
    endgenerate
    a_ex_flush_two:     assert property (@(posedge clk) disable iff (!rst_n) redirect_ex |=> (!valid_d && !valid_e));          // both younger instructions squashed
    a_id_flush_one:     assert property (@(posedge clk) disable iff (!rst_n) (redirect_id && !redirect_ex) |=> !valid_d);
    a_ex_target:        assert property (@(posedge clk) disable iff (!rst_n) (redirect_ex && !halted && !trap_mem) |=> pc_f == $past(target_ex));
    a_pc_aligned:       assert property (@(posedge clk) disable iff (!rst_n) pc_f[1:0] == 2'b00);   // no redirect ever loads a misaligned pc
    // A taken branch / JAL / JALR to a target that is not 4-byte aligned traps in EX (both directions, written from the raw target bits)
    a_misal_traps:      assert property (@(posedge clk) disable iff (!rst_n)
                            (valid_e && (((is_jal_e || br_taken_e) && target_add_e[1:0] != 2'b00) || (is_jalr_e && jalr_target_e[1]))) |-> (trap_ex && !redirect_ex));
    a_misal_only:       assert property (@(posedge clk) disable iff (!rst_n) misal_tgt_e |-> (is_jal_e || is_jalr_e || br_taken_e));
    a_trap_no_write:    assert property (@(posedge clk) disable iff (!rst_n) trap_ex |=> !rw_m);                  // a trapping instruction never writes a register

    // ------------------------------------------------------------------ traps and the halted state
    a_halted_sticky:    assert property (@(posedge clk) disable iff (!rst_n) halted |=> halted);
    a_halted_drains:    assert property (@(posedge clk) disable iff (!rst_n) halted |-> (!valid_d && !valid_e));
    a_trap_squashes:    assert property (@(posedge clk) disable iff (!rst_n) (trap_ex || trap_mem) |=> (!valid_d && !valid_e));
    a_trap_mem_squash_m: assert property (@(posedge clk) disable iff (!rst_n) trap_mem |=> !valid_m);
    a_no_retire_after_halt: assert property (@(posedge clk) disable iff (!rst_n) (rvfi_valid && rvfi_halt) |=> !rvfi_valid);

    // ------------------------------------------------------------------ side effects only from valid instructions
    a_rw_valid_m:       assert property (@(posedge clk) disable iff (!rst_n) rw_m |-> valid_m);
    a_mem_valid_m:      assert property (@(posedge clk) disable iff (!rst_n) (mem_read_m || mem_write_m) |-> valid_m);
    a_we_only:          assert property (@(posedge clk) disable iff (!rst_n) (dmem_we != 4'b0000) |-> (valid_m && mem_write_m && !misaligned_m));
    a_we_always:        assert property (@(posedge clk) disable iff (!rst_n) (valid_m && mem_write_m && !misaligned_m) |-> dmem_we != 4'b0000);
    a_re_only:          assert property (@(posedge clk) disable iff (!rst_n) dmem_re |-> (valid_m && mem_read_m && !misaligned_m));
    a_re_always:        assert property (@(posedge clk) disable iff (!rst_n) (valid_m && mem_read_m && !misaligned_m) |-> dmem_re);
    a_store_strobe_lane: assert property (@(posedge clk) disable iff (!rst_n) (dmem_we != 4'b0000) |-> (
        (funct3_m[1:0] == 2'b00 && dmem_we == (4'b0001 << alu_result_m[1:0])) ||
        (funct3_m[1:0] == 2'b01 && dmem_we == (alu_result_m[1] ? 4'b1100 : 4'b0011)) ||
        (funct3_m[1:0] == 2'b10 && dmem_we == 4'b1111)));

    // ------------------------------------------------------------------ retirement trace
    a_x0_no_write:      assert property (@(posedge clk) disable iff (!rst_n) (rvfi_rd_addr == 5'd0) |-> (rvfi_rd_wdata == 32'd0));
    a_order_counts:     assert property (@(posedge clk) disable iff (!rst_n) (rvfi_valid && $past(rvfi_valid)) |-> rvfi_order == $past(rvfi_order) + 64'd1);
    a_trap_implies_halt: assert property (@(posedge clk) disable iff (!rst_n) rvfi_trap |-> rvfi_halt);

    // ------------------------------------------------------------------ functional coverage (named cover points)
    // forwarding
    c_fwd_a_mem:        cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_MEM);
    c_fwd_a_wb:         cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_WB);
    c_fwd_b_mem:        cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_b == `FWD_MEM);
    c_fwd_b_wb:         cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_b == `FWD_WB);
    c_fwd_both_mem:     cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_MEM && fwd_b == `FWD_MEM);
    c_fwd_a_mem_b_wb:   cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_MEM && fwd_b == `FWD_WB);
    c_fwd_a_wb_b_mem:   cover property (@(posedge clk) disable iff (!rst_n) valid_e && fwd_a == `FWD_WB && fwd_b == `FWD_MEM);
    c_fwd_priority:     cover property (@(posedge clk) disable iff (!rst_n) valid_e && rw_m && rw_w && rd_m == rd_w && hit_a_m && hit_a_w);   // MEM must beat WB
    c_fwd_wb_after_stall: cover property (@(posedge clk) disable iff (!rst_n) $past(stall_d, 2) && valid_e && fwd_a == `FWD_WB);   // the consumer reaches EX two cycles after the stall
    c_fwd_wb_b_after_stall: cover property (@(posedge clk) disable iff (!rst_n) $past(stall_d, 2) && valid_e && fwd_b == `FWD_WB);
    // load-use
    c_stall:            cover property (@(posedge clk) disable iff (!rst_n) stall_d);
    c_stall_rs1:        cover property (@(posedge clk) disable iff (!rst_n) stall_d && uses_rs1_d && rs1_d == rd_e);
    c_stall_rs2:        cover property (@(posedge clk) disable iff (!rst_n) stall_d && uses_rs2_d && rs2_d == rd_e);
    c_stall_both:       cover property (@(posedge clk) disable iff (!rst_n) stall_d && uses_rs1_d && uses_rs2_d && rs1_d == rd_e && rs2_d == rd_e);
    c_stall_twice_apart: cover property (@(posedge clk) disable iff (!rst_n) stall_d && $past(stall_d, 2));
    c_stall_on_branch:  cover property (@(posedge clk) disable iff (!rst_n) stall_d && is_branch_d);
    c_load_dist2:       cover property (@(posedge clk) disable iff (!rst_n) valid_d && !stall_d && mem_read_m && ((uses_rs1_d && rs1_d == rd_m) || (uses_rs2_d && rs2_d == rd_m)));
    // control flow
    c_branch_taken:     cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_branch_e && br_taken_e);
    c_branch_not_taken: cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_branch_e && !br_taken_e);
    c_redirect_ex:      cover property (@(posedge clk) disable iff (!rst_n) redirect_ex);
    c_jal_ex:           cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_jal_e);
    c_jalr_ex:          cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_jalr_e);
    c_back_to_back_redirect: cover property (@(posedge clk) disable iff (!rst_n) redirect_ex && $past(redirect_ex, 3));
    c_branch_after_stall: cover property (@(posedge clk) disable iff (!rst_n) $past(stall_d, 2) && valid_e && is_branch_e);
    // BP_MODE = 1 only (these points do not exist in the BP_MODE = 0 variant, so they cannot be reported as unreachable there)
    generate
        if (BP_MODE == 1) begin : g_cov_bp1
            c_redirect_id:      cover property (@(posedge clk) disable iff (!rst_n) redirect_id);
            c_mispredict_taken: cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_branch_e && br_taken_e && !pred_taken_e);
            c_mispredict_nt:    cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_branch_e && !br_taken_e && pred_taken_e);
            c_predict_taken_ok: cover property (@(posedge clk) disable iff (!rst_n) valid_e && is_branch_e && br_taken_e && pred_taken_e);
            c_stall_pred_taken: cover property (@(posedge clk) disable iff (!rst_n) stall_d && pred_taken_d);   // a predicted-taken branch held by a load-use stall
        end
    endgenerate
    // traps
    c_trap_ex:          cover property (@(posedge clk) disable iff (!rst_n) trap_ex);
    c_trap_mem:         cover property (@(posedge clk) disable iff (!rst_n) trap_mem);
    c_halted:           cover property (@(posedge clk) disable iff (!rst_n) halted);
    // memory
    c_lb:  cover property (@(posedge clk) disable iff (!rst_n) valid_m && mem_read_m && funct3_m == 3'b000 && !misaligned_m);
    c_lh:  cover property (@(posedge clk) disable iff (!rst_n) valid_m && mem_read_m && funct3_m == 3'b001 && !misaligned_m);
    c_lw:  cover property (@(posedge clk) disable iff (!rst_n) valid_m && mem_read_m && funct3_m == 3'b010 && !misaligned_m);
    c_lbu: cover property (@(posedge clk) disable iff (!rst_n) valid_m && mem_read_m && funct3_m == 3'b100 && !misaligned_m);
    c_lhu: cover property (@(posedge clk) disable iff (!rst_n) valid_m && mem_read_m && funct3_m == 3'b101 && !misaligned_m);
    c_sb:  cover property (@(posedge clk) disable iff (!rst_n) dmem_we != 4'b0 && funct3_m[1:0] == 2'b00);
    c_sh:  cover property (@(posedge clk) disable iff (!rst_n) dmem_we != 4'b0 && funct3_m[1:0] == 2'b01);
    c_sw:  cover property (@(posedge clk) disable iff (!rst_n) dmem_we != 4'b0 && funct3_m[1:0] == 2'b10);
    c_sb_lane0: cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b0001);
    c_sb_lane1: cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b0010);
    c_sb_lane2: cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b0100);
    c_sb_lane3: cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b1000);
    c_sh_low:   cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b0011);
    c_sh_high:  cover property (@(posedge clk) disable iff (!rst_n) dmem_we == 4'b1100);
    // retired instruction classes (by opcode) and ALU operations (by opcode/funct3/funct7 of the retiring word)
    c_ret_lui:    cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_LUI);
    c_ret_auipc:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_AUIPC);
    c_ret_jal:    cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_JAL);
    c_ret_jalr:   cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_JALR);
    c_ret_branch: cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH);
    c_ret_load:   cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_LOAD);
    c_ret_store:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_STORE);
    c_ret_imm:    cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_IMM);
    c_ret_reg:    cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG);
    c_ret_fence:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_FENCE);
    c_ret_ecall:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn == 32'h00000073);
    c_ret_ebreak: cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn == 32'h00100073);
    c_ret_add:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b000 && rvfi_insn[31:25] == 7'h00);
    c_ret_sub:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b000 && rvfi_insn[31:25] == 7'h20);
    c_ret_sll:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b001);
    c_ret_slt:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b010);
    c_ret_sltu: cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b011);
    c_ret_xor:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b100);
    c_ret_srl:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b101 && rvfi_insn[31:25] == 7'h00);
    c_ret_sra:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b101 && rvfi_insn[31:25] == 7'h20);
    c_ret_or:   cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b110);
    c_ret_and:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_REG && rvfi_insn[14:12] == 3'b111);
    c_ret_beq:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b000);
    c_ret_bne:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b001);
    c_ret_blt:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b100);
    c_ret_bge:  cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b101);
    c_ret_bltu: cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b110);
    c_ret_bgeu: cover property (@(posedge clk) disable iff (!rst_n) rvfi_valid && rvfi_insn[6:0] == `OP_BRANCH && rvfi_insn[14:12] == 3'b111);
endmodule
