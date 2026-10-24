// rv32i_decode - combinational instruction decoder and immediate generator (RV32I base ISA, no CSRs).
// Legal encodings only: anything else sets is_illegal, and ECALL/EBREAK set is_halt. FENCE is a no-op.
// The decoder is shared by the pipelined core and the single-cycle baseline.
`include "rv32i_defs.vh"

module rv32i_decode (
    input  logic [31:0] instr,
    output logic [4:0]  rs1,
    output logic [4:0]  rs2,
    output logic [4:0]  rd,
    output logic [31:0] imm,
    output logic [3:0]  alu_op,
    output logic [1:0]  a_sel,       // ALU operand A: rs1, pc or zero
    output logic        b_imm,       // ALU operand B: 1 = immediate, 0 = rs2
    output logic        reg_write,
    output logic        mem_read,
    output logic        mem_write,
    output logic [2:0]  funct3,
    output logic        is_branch,
    output logic        is_jal,
    output logic        is_jalr,
    output logic        uses_rs1,
    output logic        uses_rs2,
    output logic        is_halt,     // ECALL or EBREAK
    output logic        is_illegal
);
    logic [6:0] opcode, funct7;
    assign opcode = instr[6:0];
    assign funct7 = instr[31:25];
    assign funct3 = instr[14:12];
    assign rs1    = instr[19:15];
    assign rs2    = instr[24:20];
    assign rd     = instr[11:7];

    logic [31:0] imm_i, imm_s, imm_b, imm_u, imm_j;
    assign imm_i = {{20{instr[31]}}, instr[31:20]};
    assign imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
    assign imm_b = {{19{instr[31]}}, instr[31], instr[7], instr[30:25], instr[11:8], 1'b0};
    assign imm_u = {instr[31:12], 12'b0};
    assign imm_j = {{11{instr[31]}}, instr[31], instr[19:12], instr[20], instr[30:21], 1'b0};

    always_comb begin
        imm        = imm_i;
        alu_op     = `ALU_ADD;
        a_sel      = `A_RS1;
        b_imm      = 1'b1;
        reg_write  = 1'b0;
        mem_read   = 1'b0;
        mem_write  = 1'b0;
        is_branch  = 1'b0;
        is_jal     = 1'b0;
        is_jalr    = 1'b0;
        uses_rs1   = 1'b0;
        uses_rs2   = 1'b0;
        is_halt    = 1'b0;
        is_illegal = 1'b0;

        case (opcode)
            `OP_LUI: begin
                imm = imm_u; a_sel = `A_ZERO; reg_write = 1'b1;
            end
            `OP_AUIPC: begin
                imm = imm_u; a_sel = `A_PC; reg_write = 1'b1;
            end
            `OP_JAL: begin
                imm = imm_j; is_jal = 1'b1; reg_write = 1'b1;
            end
            `OP_JALR: begin
                imm = imm_i; is_jalr = 1'b1; reg_write = 1'b1; uses_rs1 = 1'b1;
                if (funct3 != 3'b000) is_illegal = 1'b1;
            end
            `OP_BRANCH: begin
                imm = imm_b; is_branch = 1'b1; uses_rs1 = 1'b1; uses_rs2 = 1'b1;
                if (funct3 == 3'b010 || funct3 == 3'b011) is_illegal = 1'b1;
            end
            `OP_LOAD: begin
                imm = imm_i; mem_read = 1'b1; reg_write = 1'b1; uses_rs1 = 1'b1;
                if (funct3 != 3'b000 && funct3 != 3'b001 && funct3 != 3'b010 &&
                    funct3 != 3'b100 && funct3 != 3'b101) is_illegal = 1'b1;
            end
            `OP_STORE: begin
                imm = imm_s; mem_write = 1'b1; uses_rs1 = 1'b1; uses_rs2 = 1'b1;
                if (funct3 != 3'b000 && funct3 != 3'b001 && funct3 != 3'b010) is_illegal = 1'b1;
            end
            `OP_IMM: begin
                imm = imm_i; reg_write = 1'b1; uses_rs1 = 1'b1;
                case (funct3)
                    3'b000: alu_op = `ALU_ADD;
                    3'b010: alu_op = `ALU_SLT;
                    3'b011: alu_op = `ALU_SLTU;
                    3'b100: alu_op = `ALU_XOR;
                    3'b110: alu_op = `ALU_OR;
                    3'b111: alu_op = `ALU_AND;
                    3'b001: begin
                        alu_op = `ALU_SLL;
                        if (funct7 != 7'b0000000) is_illegal = 1'b1;
                    end
                    default: begin   // 3'b101: SRLI / SRAI
                        alu_op = (funct7 == 7'b0100000) ? `ALU_SRA : `ALU_SRL;
                        if (funct7 != 7'b0000000 && funct7 != 7'b0100000) is_illegal = 1'b1;
                    end
                endcase
            end
            `OP_REG: begin
                b_imm = 1'b0; reg_write = 1'b1; uses_rs1 = 1'b1; uses_rs2 = 1'b1;
                case (funct3)
                    3'b000: begin
                        alu_op = (funct7 == 7'b0100000) ? `ALU_SUB : `ALU_ADD;
                        if (funct7 != 7'b0000000 && funct7 != 7'b0100000) is_illegal = 1'b1;
                    end
                    3'b001: begin alu_op = `ALU_SLL;  if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                    3'b010: begin alu_op = `ALU_SLT;  if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                    3'b011: begin alu_op = `ALU_SLTU; if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                    3'b100: begin alu_op = `ALU_XOR;  if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                    3'b101: begin
                        alu_op = (funct7 == 7'b0100000) ? `ALU_SRA : `ALU_SRL;
                        if (funct7 != 7'b0000000 && funct7 != 7'b0100000) is_illegal = 1'b1;
                    end
                    3'b110: begin alu_op = `ALU_OR;   if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                    default: begin alu_op = `ALU_AND; if (funct7 != 7'b0000000) is_illegal = 1'b1; end
                endcase
            end
            `OP_FENCE: begin
                if (funct3 != 3'b000) is_illegal = 1'b1;   // FENCE.I is Zifencei, not in RV32I
            end
            `OP_SYSTEM: begin
                if (instr == 32'h00000073 || instr == 32'h00100073) is_halt = 1'b1;
                else is_illegal = 1'b1;                      // CSR instructions are not implemented
            end
            default: is_illegal = 1'b1;
        endcase

        // An illegal encoding has no architectural effect.
        if (is_illegal) begin
            reg_write = 1'b0; mem_read = 1'b0; mem_write = 1'b0;
            is_branch = 1'b0; is_jal = 1'b0; is_jalr = 1'b0;
            uses_rs1  = 1'b0; uses_rs2  = 1'b0;
        end
    end
endmodule
