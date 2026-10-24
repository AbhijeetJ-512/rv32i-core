// rv32i_branch - branch condition comparator (funct3 selects BEQ/BNE/BLT/BGE/BLTU/BGEU).
module rv32i_branch (
    input  logic [31:0] a,
    input  logic [31:0] b,
    input  logic [2:0]  funct3,
    output logic        taken
);
    logic eq, lt, ltu;
    assign eq  = (a == b);
    assign lt  = ($signed(a) < $signed(b));
    assign ltu = (a < b);

    always_comb begin
        case (funct3)
            3'b000:  taken = eq;     // BEQ
            3'b001:  taken = ~eq;    // BNE
            3'b100:  taken = lt;     // BLT
            3'b101:  taken = ~lt;    // BGE
            3'b110:  taken = ltu;    // BLTU
            3'b111:  taken = ~ltu;   // BGEU
            default: taken = 1'b0;
        endcase
    end
endmodule
