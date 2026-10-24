// rv32i_lsu - load/store alignment logic (combinational), shared by both cores.
//   store: byte strobes and the store data moved to its byte lane
//   load : select the addressed bytes out of the 32-bit word and sign- or zero-extend
//   misaligned: halfword at an odd address, word at a non-multiple-of-4 address (no hardware support: trap)
module rv32i_lsu (
    input  logic [2:0]  funct3,       // 000 byte, 001 half, 010 word, 100 byte unsigned, 101 half unsigned
    input  logic [1:0]  addr_lo,      // address bits [1:0]
    input  logic [31:0] store_data,   // rs2 value
    input  logic [31:0] load_word,    // word returned by memory at the aligned address
    output logic [3:0]  wstrb,        // byte strobes for a store
    output logic [31:0] wdata,        // store data positioned in its lanes
    output logic [31:0] load_value,   // extended load result
    output logic        misaligned
);
    always_comb begin
        case (funct3[1:0])
            2'b00:   begin wstrb = 4'b0001 << addr_lo;           wdata = {4{store_data[7:0]}};  end
            2'b01:   begin wstrb = 4'b0011 << {addr_lo[1], 1'b0}; wdata = {2{store_data[15:0]}}; end
            default: begin wstrb = 4'b1111;                       wdata = store_data;            end
        endcase
    end

    logic [31:0] shifted;
    assign shifted = load_word >> {addr_lo, 3'b000};

    always_comb begin
        case (funct3)
            3'b000:  load_value = {{24{shifted[7]}},  shifted[7:0]};
            3'b001:  load_value = {{16{shifted[15]}}, shifted[15:0]};
            3'b100:  load_value = {24'b0, shifted[7:0]};
            3'b101:  load_value = {16'b0, shifted[15:0]};
            default: load_value = shifted;
        endcase
    end

    always_comb begin
        case (funct3[1:0])
            2'b01:   misaligned = addr_lo[0];
            2'b10:   misaligned = (addr_lo != 2'b00);
            default: misaligned = 1'b0;
        endcase
    end
endmodule
