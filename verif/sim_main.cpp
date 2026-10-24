// sim_main.cpp - timing-loop main for the Verilated testbench (spec D-007).
// Beyond the standard loop its only job is writing coverage.dat, which Verilator 5.020's
// generated --binary main never does. Everything else in this project is SystemVerilog.
#include <memory>
#include <string>

#include "verilated.h"
#include "Vtb_core.h"

int main(int argc, char** argv) {
    const std::unique_ptr<VerilatedContext> ctx{new VerilatedContext};
    ctx->commandArgs(argc, argv);
    ctx->traceEverOn(true);  // needed for the VCD the testbench opens with $dumpfile
    const std::unique_ptr<Vtb_core> top{new Vtb_core{ctx.get()}};

    while (!ctx->gotFinish()) {
        top->eval();
        if (!top->eventsPending()) break;
        ctx->time(top->nextTimeSlot());
    }
    top->final();

#if VM_COVERAGE
    std::string path = "coverage.dat";
    const std::string arg = ctx->commandArgsPlusMatch("cov_file");  // "+cov_file=<path>"
    if (arg.size() > 10) path = arg.substr(10);
    ctx->coveragep()->write(path.c_str());
#endif
    return 0;
}
