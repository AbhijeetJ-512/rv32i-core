// checker_binds - attach rv32i_checker to the core. `.*` connects by name, so the signal names in rv32i_core.sv are a
// contract with the checker (see the note at the top of the core's pipeline-control block).
bind rv32i_core rv32i_checker #(.BP_MODE(BP_MODE)) u_chk (.*, .uses1_e(g_rvfi.uses1_e), .uses2_e(g_rvfi.uses2_e));
// (uses1_e / uses2_e live in the RVFI generate block: they are decoder facts carried to EX; the checker is built with RVFI_EN=1)
