// rv32i_regfile - 31 x 32-bit registers (x0 reads as zero), two combinational read ports, one write port.
// A read of the register being written in the same cycle returns the new value (write-first bypass), which
// closes the three-instruction-apart RAW distance without a separate forwarding path.
// Registers are NOT reset by default (a reset would add a mux per flop); programs initialise what they read.
module rv32i_regfile #(
    parameter bit RESET_REGS = 1'b0,
    parameter bit BYPASS     = 1'b1    // write-first bypass; the single-cycle core must turn it off (it would feed its own result back)
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [4:0]  ra1,
    input  logic [4:0]  ra2,
    output logic [31:0] rd1,
    output logic [31:0] rd2,
    input  logic        we,
    input  logic [4:0]  wa,
    input  logic [31:0] wd
);
    logic [31:0] regs [1:31];

    always_ff @(posedge clk) begin
        if (RESET_REGS && !rst_n) begin
            for (int i = 1; i < 32; i++) regs[i] <= 32'b0;
        end else if (we && wa != 5'd0) begin
            regs[wa] <= wd;
        end
    end

    always_comb begin
        if (ra1 == 5'd0)                      rd1 = 32'b0;
        else if (BYPASS && we && wa == ra1)   rd1 = wd;
        else                                  rd1 = regs[ra1];
        if (ra2 == 5'd0)                      rd2 = 32'b0;
        else if (BYPASS && we && wa == ra2)   rd2 = wd;
        else                                  rd2 = regs[ra2];
    end
endmodule
