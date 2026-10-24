// rv32i_defs.vh - opcode and ALU-operation encodings shared by every rv32i_* module.
// Plain macros (not a package or enum) so Verilator 5.020 and Yosys 0.33 read the same text.
`ifndef RV32I_DEFS_VH
`define RV32I_DEFS_VH

// RV32I base opcodes, instruction bits [6:0]
`define OP_LUI    7'b0110111
`define OP_AUIPC  7'b0010111
`define OP_JAL    7'b1101111
`define OP_JALR   7'b1100111
`define OP_BRANCH 7'b1100011
`define OP_LOAD   7'b0000011
`define OP_STORE  7'b0100011
`define OP_IMM    7'b0010011
`define OP_REG    7'b0110011
`define OP_FENCE  7'b0001111
`define OP_SYSTEM 7'b1110011

// ALU operations (4 bits)
`define ALU_ADD   4'd0
`define ALU_SUB   4'd1
`define ALU_SLL   4'd2
`define ALU_SLT   4'd3
`define ALU_SLTU  4'd4
`define ALU_XOR   4'd5
`define ALU_SRL   4'd6
`define ALU_SRA   4'd7
`define ALU_OR    4'd8
`define ALU_AND   4'd9

// ALU operand-A source
`define A_RS1     2'd0
`define A_PC      2'd1
`define A_ZERO    2'd2

// Forwarding selects
`define FWD_NONE  2'd0
`define FWD_MEM   2'd1
`define FWD_WB    2'd2

`endif
