// tb_core - Verilator testbench for rv32i_core: unified 64 KiB memory, retirement-trace writer, cycle accounting.
//
//   +hex=<file>      program image, one 32-bit word per line (tools/rvasm.py output); required
//   +trace=<file>    write one line per retired instruction (same format as tools/rviss.py)
//   +stats=<file>    write the cycle accounting at the end
//   +maxcycles=<n>   give up after n cycles (default 2000000)
//   +dump=<file>     final memory image, one word per line
//   +vcd=<file>      waveform
//
// The memory is outside the core: instruction and data reads are combinational, writes happen on the clock edge
// with byte strobes. Both ports see the same array (a unified address space, program at 0).
`timescale 1ns/1ps

module tb_core #(
    parameter int          BP_MODE   = 0,
    parameter int          FWD_PRECOMP = 1,
    parameter int          MEM_WORDS = 16384,
    parameter logic [31:0] RESET_PC  = 32'h0000_1000
);
    localparam int AW = $clog2(MEM_WORDS);

    logic clk;
    logic rst_n;
    initial clk = 1'b0;
    always #5 clk = ~clk;

    logic [31:0] mem [0:MEM_WORDS-1];

    logic [31:0] imem_addr, imem_rdata, dmem_addr, dmem_wdata, dmem_rdata;
    logic        dmem_re, halted;
    logic [3:0]  dmem_we;

    logic        rvfi_valid, rvfi_trap, rvfi_halt;
    logic [63:0] rvfi_order;
    logic [31:0] rvfi_insn, rvfi_pc_rdata, rvfi_pc_wdata, rvfi_rs1_rdata, rvfi_rs2_rdata, rvfi_rd_wdata;
    logic [31:0] rvfi_mem_addr, rvfi_mem_rdata, rvfi_mem_wdata;
    logic [4:0]  rvfi_rs1_addr, rvfi_rs2_addr, rvfi_rd_addr;
    logic [3:0]  rvfi_mem_rmask, rvfi_mem_wmask;

`ifdef SINGLE_CYCLE
    rv32i_core_1cyc #(.RESET_PC(RESET_PC), .RVFI_EN(1)) dut (
`else
    rv32i_core #(.RESET_PC(RESET_PC), .BP_MODE(BP_MODE), .FWD_PRECOMP(FWD_PRECOMP), .RVFI_EN(1)) dut (
`endif
        .clk, .rst_n, .imem_addr, .imem_rdata, .dmem_addr, .dmem_re, .dmem_we, .dmem_wdata, .dmem_rdata,
        .halted, .rvfi_valid, .rvfi_order, .rvfi_insn, .rvfi_trap, .rvfi_halt, .rvfi_pc_rdata, .rvfi_pc_wdata,
        .rvfi_rs1_addr, .rvfi_rs2_addr, .rvfi_rs1_rdata, .rvfi_rs2_rdata, .rvfi_rd_addr, .rvfi_rd_wdata,
        .rvfi_mem_addr, .rvfi_mem_rmask, .rvfi_mem_wmask, .rvfi_mem_rdata, .rvfi_mem_wdata
    );

    // ---- memory
    assign imem_rdata = mem[imem_addr[AW+1:2]];
    assign dmem_rdata = dmem_re ? mem[dmem_addr[AW+1:2]] : 32'hDEAD_BEEF;   // poison when not reading

    // Writes are ignored while reset is asserted: the core's flops hold random values until the first reset edge
    // (Verilator randomises them), and a memory must not act on outputs that are not yet defined.
    always @(posedge clk) begin
        if (rst_n && dmem_we[0]) mem[dmem_addr[AW+1:2]][7:0]   <= dmem_wdata[7:0];
        if (rst_n && dmem_we[1]) mem[dmem_addr[AW+1:2]][15:8]  <= dmem_wdata[15:8];
        if (rst_n && dmem_we[2]) mem[dmem_addr[AW+1:2]][23:16] <= dmem_wdata[23:16];
        if (rst_n && dmem_we[3]) mem[dmem_addr[AW+1:2]][31:24] <= dmem_wdata[31:24];
    end

    // ---- run control
    string hexfile, tracefile, statsfile, vcdfile, dumpfile;
    int    maxcycles;
    int    trace_fd;
    longint cycles, instret, lu_stalls, ex_redirects, id_redirects, drain;
    bit    started, finished;

    initial begin
        if (!$value$plusargs("hex=%s", hexfile)) begin
            $display("TB ERROR: +hex=<file> is required");
            $finish;
        end
        if (!$value$plusargs("maxcycles=%d", maxcycles)) maxcycles = 2000000;
        for (int i = 0; i < MEM_WORDS; i++) mem[i] = 32'h0;
        $readmemh(hexfile, mem);
        trace_fd = 0;
        if ($value$plusargs("trace=%s", tracefile)) trace_fd = $fopen(tracefile, "w");
        if ($value$plusargs("vcd=%s", vcdfile)) begin
            $dumpfile(vcdfile);
            $dumpvars(0, tb_core);
        end
        rst_n = 1'b0;
        repeat (4) @(posedge clk);
        #1 rst_n = 1'b1;
        started = 1'b1;
    end

    // ---- counters and trace (sampled on the rising edge, before the DUT's own update: same values the flops see)
    always @(posedge clk) begin
        if (started && !finished) begin
            cycles <= cycles + 1;
            if (rvfi_valid) instret <= instret + 1;
            if (dut.stall_d) lu_stalls <= lu_stalls + 1;
            if (dut.redirect_ex) ex_redirects <= ex_redirects + 1;
            if (dut.redirect_id) id_redirects <= id_redirects + 1;
            if (rvfi_valid && trace_fd != 0)
                $fwrite(trace_fd, "%0d %08x %08x %08x %0d %08x %0d %08x %0d %08x %08x %x %x %08x %08x %0d %0d\n",
                        rvfi_order, rvfi_pc_rdata, rvfi_insn, rvfi_pc_wdata, rvfi_rs1_addr, rvfi_rs1_rdata,
                        rvfi_rs2_addr, rvfi_rs2_rdata, rvfi_rd_addr, rvfi_rd_wdata, rvfi_mem_addr, rvfi_mem_rmask,
                        rvfi_mem_wmask, rvfi_mem_rdata, rvfi_mem_wdata, rvfi_halt ? 1 : 0, rvfi_trap ? 1 : 0);
            if (rvfi_valid && rvfi_halt) finished <= 1'b1;
            if (cycles >= maxcycles) begin
                $display("TB TIMEOUT after %0d cycles", cycles);
                finished <= 1'b1;
            end
        end
        if (finished) begin
            drain <= drain + 1;
            if (drain == 3) begin
                if (trace_fd != 0) $fclose(trace_fd);
                if ($value$plusargs("dump=%s", dumpfile)) begin
                    int dfd;
                    dfd = $fopen(dumpfile, "w");
                    for (int i = 0; i < MEM_WORDS; i++) $fwrite(dfd, "%08x\n", mem[i]);
                    $fclose(dfd);
                end
                $display("TB DONE cycles=%0d instret=%0d lu_stalls=%0d ex_redirects=%0d id_redirects=%0d",
                         cycles, instret, lu_stalls, ex_redirects, id_redirects);
                if ($value$plusargs("stats=%s", statsfile)) begin
                    int sfd;
                    sfd = $fopen(statsfile, "w");
                    $fwrite(sfd, "cycles=%0d\ninstret=%0d\nlu_stalls=%0d\nex_redirects=%0d\nid_redirects=%0d\nbp_mode=%0d\n",
                            cycles, instret, lu_stalls, ex_redirects, id_redirects, BP_MODE);
                    $fclose(sfd);
                end
                $finish;
            end
        end
    end
endmodule
