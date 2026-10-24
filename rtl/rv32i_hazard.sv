// rv32i_hazard - operand forwarding selects and the load-use stall.
`include "rv32i_defs.vh"
//   Forwarding (to the EX stage): the youngest older producer wins - MEM stage first, then WB.
//     Two implementations of the same rule: compared in EX from the pipeline registers (FWD_PRECOMP=0, shortest hardware),
//     or compared one stage earlier, in ID, and registered with the instruction (FWD_PRECOMP=1: the select arrives from a
//     flop, which takes the 5-bit compares and the priority logic off the EX critical path).
//     A load in the MEM stage is never forwarded from: its data is not ready until the end of that cycle, and
//     the load-use stall guarantees no consumer is in EX at that moment (an assertion in verif/ checks it).
//   Load-use: the instruction in ID needs a register that the load in EX is about to produce -> hold PC and
//     IF/ID for one cycle and insert a bubble into ID/EX. The load then reaches WB as the consumer reaches EX
//     and the WB->EX forward supplies the data.
module rv32i_hazard (
    // ID stage (the instruction that may have to wait)
    input  logic        valid_d,
    input  logic [4:0]  rs1_d,
    input  logic [4:0]  rs2_d,
    input  logic        uses_rs1_d,
    input  logic        uses_rs2_d,
    // EX stage
    input  logic [4:0]  rs1_e,
    input  logic [4:0]  rs2_e,
    input  logic [4:0]  rd_e,
    input  logic        mem_read_e,   // 0 for a bubble
    // MEM and WB stages (reg write flags are already qualified by the stage's valid bit)
    input  logic [4:0]  rd_m,
    input  logic        rw_m,
    input  logic [4:0]  rd_w,
    input  logic        rw_w,
    // ID-stage view of the same rule, for the precomputed-select variant: the producer now in EX will be in MEM, and the
    // producer now in MEM will be in WB, when the instruction now in ID reaches EX
    input  logic [4:0]  rd_e_pre,
    input  logic        rw_e_pre,
    output logic [1:0]  fwd_a_d,
    output logic [1:0]  fwd_b_d,
    output logic [1:0]  fwd_a,
    output logic [1:0]  fwd_b,
    output logic        stall_d
);
    always_comb begin
        if (rw_m && rd_m != 5'd0 && rd_m == rs1_e)       fwd_a = `FWD_MEM;
        else if (rw_w && rd_w != 5'd0 && rd_w == rs1_e)  fwd_a = `FWD_WB;
        else                                             fwd_a = `FWD_NONE;

        if (rw_m && rd_m != 5'd0 && rd_m == rs2_e)       fwd_b = `FWD_MEM;
        else if (rw_w && rd_w != 5'd0 && rd_w == rs2_e)  fwd_b = `FWD_WB;
        else                                             fwd_b = `FWD_NONE;

        // precomputed selects (registered in ID/EX by the core)
        if (rw_e_pre && rd_e_pre != 5'd0 && rd_e_pre == rs1_d)   fwd_a_d = `FWD_MEM;
        else if (rw_m && rd_m != 5'd0 && rd_m == rs1_d)          fwd_a_d = `FWD_WB;
        else                                                      fwd_a_d = `FWD_NONE;
        if (rw_e_pre && rd_e_pre != 5'd0 && rd_e_pre == rs2_d)   fwd_b_d = `FWD_MEM;
        else if (rw_m && rd_m != 5'd0 && rd_m == rs2_d)          fwd_b_d = `FWD_WB;
        else                                                      fwd_b_d = `FWD_NONE;

        stall_d = valid_d && mem_read_e && rd_e != 5'd0 &&
                  ((uses_rs1_d && rs1_d == rd_e) || (uses_rs2_d && rs2_d == rd_e));
    end
endmodule
