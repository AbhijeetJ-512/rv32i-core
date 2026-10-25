#!/usr/bin/env python3
"""Draws the rv32i_5stage_core diagrams with dgm.py (in this folder): one specification -> .drawio + .png + .svg.
Run:  python3 docs/diagrams/make_diagrams.py   (needs matplotlib + pillow)"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dgm import Diagram  # noqa: E402


def architecture():
    d = Diagram("RV32I 5-stage pipelined core - microarchitecture", 1400, 700)
    d.legend = ("data", "ctrl")
    d.legend_pos = (1190, 12)
    d.group("g_if", 20, 100, 270, 345, "IF  fetch", label_pos="bottom")
    d.group("g_id", 335, 100, 300, 345, "ID  decode / register read", label_pos="bottom")
    d.group("g_ex", 690, 100, 310, 345, "EX  execute / resolve", label_pos="bottom")
    d.group("g_mem", 1050, 100, 165, 345, "MEM  data access", label_pos="bottom")
    d.group("g_wb", 1265, 100, 120, 345, "WB", label_pos="bottom")
    for i, (x, n) in enumerate([(295, "IF/\nID"), (645, "ID/\nEX"), (1008, "EX/\nMEM"), (1223, "MEM/\nWB")]):
        d.box("r%d" % i, x, 125, 34, 290, n, "io", size=9, bold=True)
    # IF
    d.box("imem", 40, 145, 230, 55, "Instruction memory", "io", sub="external, combinational read", size=12)
    d.box("pc", 40, 240, 100, 50, "PC", "block", sub="pc_f", size=12)
    d.box("pc4", 170, 240, 100, 50, "PC + 4", "block", size=12)
    d.box("pcmux", 40, 335, 230, 65, "next-PC select", "ctrl", sub="halted > EX redirect > stall >\nID redirect > PC+4", size=12)
    # ID
    d.box("dec", 350, 145, 130, 75, "Decode", "block", sub="opcode, immediate,\ncontrol, illegal/halt", size=12)
    d.box("rf", 500, 145, 125, 105, "Register file", "mem", sub="x1..x31, 2R / 1W\nwrite-first bypass", size=12)
    d.box("hz", 350, 280, 130, 90, "Hazard unit", "ctrl", sub="load-use stall;\nforward selects\nprecomputed in ID", size=11)
    d.box("idr", 500, 280, 125, 90, "ID redirect", "ctrl", sub="BP_MODE=1: JAL and\nbackward branches", size=11)
    # EX
    d.box("fw", 705, 145, 75, 100, "Forward\nmuxes A, B", "block", sub="reg / MEM / WB", size=11)
    d.box("alu", 800, 145, 110, 105, "ALU", "accent", sub="add sub slt sltu\nand or xor\nsll srl sra", size=12)
    d.box("bc", 795, 285, 100, 60, "Branch compare", "block", sub="6 conditions", size=11)
    d.box("rdx", 910, 285, 80, 100, "EX\nredirect", "ctrl", sub="targets,\nmispredict", size=10)
    # MEM
    d.box("lsu", 1060, 145, 145, 95, "Load/store unit", "block", sub="byte strobes, lane shift,\nsign-extend, misalign trap", size=11)
    d.box("dmem", 1060, 290, 145, 55, "Data memory", "io", sub="external", size=12)
    # WB
    d.box("wb", 1275, 145, 100, 70, "WB select", "block", sub="load data /\nALU / pc+4", size=11)
    # data flow
    d.arrow("e1", "pc", "imem", sside="t", dside="b", sf=0.5, df=0.2, label="imem_addr", lpos=(115, 222))
    d.arrow("e2", "pc", "pc4")
    d.arrow("e3", "pc4", "pcmux", sside="b", dside="t", sf=0.5, df=0.82, label="pc + 4", lpos=(238, 313))
    d.arrow("e4", "pcmux", "pc", sside="t", dside="b", sf=0.22, df=0.5, label="pc_n", lpos=(72, 313))
    d.arrow("e5", "imem", "r0", sside="r", dside="l", sf=0.5, df=0.1, label="")
    d.arrow("e6", "r0", "dec", sside="r", dside="l", sf=0.1, df=0.5, label="")
    d.arrow("e7", "dec", "rf", label="rs1,\nrs2", lpos=(490, 160))
    d.arrow("e8", "rf", "r1", sside="r", dside="l", sf=0.6, df=0.3, label="")
    d.arrow("e9", "dec", "r1", sside="t", dside="l", sf=0.5, df=0.05, via=[(415, 128), (637, 128)], label="control, imm, rd, pc  (-> ID/EX)", lpos=(530, 119))
    d.arrow("e10", "r1", "fw", sside="r", dside="l", sf=0.3, df=0.5, label="")
    d.arrow("e12", "fw", "alu", sside="r", dside="l", sf=0.5, df=0.5, label="")
    d.arrow("e14", "alu", "r2", sside="r", dside="l", sf=0.65, df=0.3, label="alu_result", lpos=(960, 190))
    d.arrow("e15", "r2", "lsu", sside="r", dside="l", sf=0.3, df=0.5, label="")
    d.arrow("e16", "lsu", "dmem", sside="b", dside="t", sf=0.3, df=0.3, label="addr,\nwe, wdata", lpos=(1090, 262))
    d.arrow("e17", "dmem", "lsu", sside="t", dside="b", sf=0.8, df=0.8, label="rdata", lpos=(1195, 262))
    d.arrow("e18", "lsu", "r3", sside="r", dside="l", sf=0.5, df=0.3, label="")
    d.arrow("e19", "r3", "wb", sside="r", dside="l", sf=0.3, df=0.5, label="")
    d.arrow("e20", "wb", "rf", sside="t", dside="t", sf=0.5, df=0.5, via=[(1325, 85), (562, 85)], label="register write: wd, wa, we", lpos=(950, 76))
    # forwarding
    d.arrow("f1", "r2", "fw", sside="b", dside="b", sf=0.5, df=0.65, via=[(1025, 555), (753, 555)], label="alu_result_m   (forward MEM -> EX)", lpos=(890, 546))
    d.arrow("f2", "r3", "fw", sside="b", dside="b", sf=0.5, df=0.3, via=[(1240, 590), (727, 590)], label="wb_data_w   (forward WB -> EX)", lpos=(980, 581))
    # control
    d.arrow("c1", "hz", "pcmux", kind="ctrl", sside="b", dside="b", sf=0.3, df=0.5, via=[(389, 465), (155, 465)], label="stall: hold PC and IF/ID", lpos=(272, 456))
    d.arrow("c3", "idr", "pcmux", kind="ctrl", sside="b", dside="b", sf=0.5, df=0.87, via=[(562, 490), (240, 490)], label="redirect_id, target_id   (1 bubble)", lpos=(400, 481))
    d.arrow("c2", "rdx", "pcmux", kind="ctrl", sside="b", dside="b", sf=0.5, df=0.13, via=[(957, 515), (70, 515)], label="redirect_ex, target_ex   (flushes IF/ID and ID/EX: 2 bubbles)", lpos=(520, 506))
    d.arrow("c5", "bc", "rdx", kind="ctrl", sside="r", dside="l", sf=0.5, df=0.3, label="")
    d.text("t1", 30, 625, "BP_MODE=0 resolves every control transfer in EX (2 bubbles when taken); BP_MODE=1 redirects JAL and backward branches from ID (1 bubble), repairs a misprediction from EX.\n"
                          "FWD_PRECOMP=1 compares the forwarding selects in ID and registers them, so EX receives them from flops. Memories sit outside the core, without wait states.", 11, italic=True)
    return d


def flowchart():
    d = Diagram("RV32I core - life of one instruction (operation flowchart)", 1200, 1260)
    d.legend = ("flow",)
    d.legend_pos = (1000, 12)
    C = 400   # centre column x
    W = 270
    d.box("reset", 335, 55, 400, 55, "Reset: rst_n low", "term", sub="pc_f <- RESET_PC, valid bits cleared, halted <- 0", size=12)
    d.box("if", C, 140, W, 62, "IF: fetch", "proc", sub="imem_addr = pc_f ; IF/ID <- {pc, instr}\nnext PC = pc + 4 unless redirected", size=12)
    d.box("id", C, 230, W, 62, "ID: decode, read registers", "proc", sub="rs1/rs2 (write-first bypass), immediate,\ncontrol signals, forward selects", size=12)
    d.box("dtrap", C, 322, W, 78, "ECALL / EBREAK or\nillegal encoding?", "dec", size=12)
    d.box("mark", 790, 332, 330, 58, "Mark the instruction as a trap", "proc", sub="no register, memory or PC effect of its own", size=12)
    d.box("dlu", C, 432, W, 82, "Load-use hazard?", "dec", sub="a load in EX writes rs1 / rs2", size=12)
    d.box("stall", 40, 445, 250, 62, "Stall one cycle", "proc", sub="hold PC and IF/ID,\nbubble into ID/EX", size=12)
    d.box("ex", C, 548, W, 62, "EX: execute", "proc", sub="forward operands (MEM / WB / register),\nALU, branch compare, targets", size=12)
    d.box("dred", C, 640, W, 90, "Redirect needed?", "dec", sub="JALR, taken branch (BP0), JAL (BP0),\nmisprediction (BP1)", size=11)
    d.box("flush", 790, 660, 330, 58, "Flush IF/ID and ID/EX", "proc", sub="PC <- target_ex   (2 bubbles)", size=12)
    d.box("dtex", C, 762, W, 78, "Trap marked in EX?", "dec", size=12)
    d.box("halt", 790, 772, 330, 62, "Squash younger instructions", "proc", sub="halted <- 1 ; retire with halt (and trap)", size=12)
    d.box("dmem", C, 872, W, 78, "Load or store?", "dec", size=12)
    d.box("dmis", C, 982, W, 80, "Misaligned address?", "dec", sub="half: odd, word: not multiple of 4", size=11)
    d.box("tmem", 790, 992, 330, 62, "Trap in MEM: no memory access", "proc", sub="squash younger, halted <- 1,\nretire with halt + trap", size=12)
    d.box("acc", C, 1092, W, 60, "MEM: access data memory", "proc", sub="byte strobes, lane shift, sign / zero extend", size=12)
    d.box("wb", C, 1172, W, 50, "WB: write rd (rd != x0), retire", "proc", sub="RVFI record on the trace port", size=12)
    d.box("stop", 790, 1092, 330, 55, "Core stopped", "term", sub="older instructions drain and retire first", size=12)
    d.box("done", 790, 1172, 330, 50, "Instruction retired", "term", size=12)
    # main flow
    cx = C + W / 2
    for a, b, lab in [("reset", "if", ""), ("if", "id", ""), ("id", "dtrap", ""), ("dtrap", "dlu", "no"), ("dlu", "ex", "no"), ("ex", "dred", ""),
                      ("dred", "dtex", "no"), ("dtex", "dmem", "no"), ("dmem", "dmis", "yes"), ("dmis", "acc", "no"), ("acc", "wb", "")]:
        sx = 530 if a == "reset" else cx
        d.arrow("m_" + a, a, b, kind="flow", sside="b", dside="t", sf=0.5 if a != "reset" else 0.5, df=0.5, label=lab,
                lpos=(cx + 18, (d.node(a).y + d.node(a).h + d.node(b).y) / 2) if lab else None)
    # side branches
    d.arrow("y1", "dtrap", "mark", kind="flow", sside="r", dside="l", label="yes", lpos=(740, 350), sf=0.5, df=0.4)
    d.arrow("mk", "mark", "dlu", kind="flow", sside="b", dside="t", sf=0.5, df=0.5, via=[(955, 412), (cx, 412)], label="")
    d.arrow("y2", "dlu", "stall", kind="flow", sside="l", dside="r", label="yes", lpos=(350, 460))
    d.arrow("st", "stall", "id", kind="flow", sside="t", dside="l", sf=0.5, df=0.5, via=[(165, 261)], label="retry next cycle", lpos=(110, 340))
    d.arrow("y3", "dred", "flush", kind="flow", sside="r", dside="l", label="yes", lpos=(735, 690), sf=0.5, df=0.5)
    d.arrow("fl", "flush", "dtex", kind="flow", sside="b", dside="t", sf=0.5, df=0.5, via=[(955, 742), (cx, 742)], label="")
    d.arrow("y4", "dtex", "halt", kind="flow", sside="r", dside="l", label="yes", lpos=(735, 790), sf=0.5, df=0.5)
    d.arrow("n5", "dmem", "wb", kind="flow", sside="l", dside="l", sf=0.5, df=0.5, via=[(340, 911), (340, 1197)], label="no", lpos=(360, 902))
    d.arrow("y6", "dmis", "tmem", kind="flow", sside="r", dside="l", label="yes", lpos=(735, 1010), sf=0.5, df=0.5)
    d.arrow("h1", "halt", "stop", kind="flow", sside="r", dside="r", sf=0.5, df=0.5, via=[(1160, 803), (1160, 1119)], label="")
    d.arrow("h2", "tmem", "stop", kind="flow", sside="b", dside="t", sf=0.5, df=0.5, label="")
    d.arrow("w1", "wb", "done", kind="flow", sside="r", dside="l", label="")
    d.text("note", 30, 1232, "Redirect and trap decisions are made in EX; the misalignment trap is detected in MEM from the registered address.\n"
                             "A load-use stall needs a load in EX and a redirect needs a branch or jump in EX, so the two never occur in the same cycle.", 11, italic=True)
    return d


def pipeline_timing():
    d = Diagram("RV32I pipeline timing - forwarding, load-use stall and a taken-branch flush (BP_MODE=0)", 1250, 720)
    X0, Y0, CW, CH, GAP = 255, 95, 78, 40, 28
    ncyc = 12
    rows = [("1  lw  x1, 0(x2)", {"IF": 1, "ID": 2, "EX": 3, "MEM": 4, "WB": 5}),
            ("2  add x3, x1, x4", {"IF": 2, "ID": 3, "ST": 4, "EX": 5, "MEM": 6, "WB": 7}),
            ("3  sub x5, x3, x6", {"IF": 3, "RF": 4, "ID": 5, "EX": 6, "MEM": 7, "WB": 8}),
            ("4  beq x5, x7, T", {"IF": 5, "ID": 6, "EX": 7, "MEM": 8, "WB": 9}),
            ("5  or  x8, x9, x10", {"IF": 6, "XX": 7}),
            ("6  and x11, x12, x13", {"IF": 7}),
            ("T  xor x14, x15, x16", {"IF": 8, "ID": 9, "EX": 10, "MEM": 11, "WB": 12})]
    for c in range(1, ncyc + 1):
        d.text("h%d" % c, X0 + (c - 1) * CW + CW / 2, Y0 - 30, "%d" % c, 12, True, align="center")
    d.text("hc", 20, Y0 - 30, "cycle", 12, True)
    kind = {"IF": "block", "ID": "accent", "EX": "ctrl", "MEM": "mem", "WB": "data", "ST": "bad", "RF": "block", "XX": "bad"}
    for r, (lab, st) in enumerate(rows):
        y = Y0 + r * (CH + GAP)
        d.box("L%d" % r, 20, y, 225, CH, lab, "io", size=12, bold=False, align="left")
        for stg, c in st.items():
            x = X0 + (c - 1) * CW
            text = {"ST": "ID  (stall)", "RF": "IF  (again)", "XX": "ID  x", "IF": "IF"}.get(stg, stg)
            kd = kind[stg]
            if stg == "IF" and lab.startswith("6"):
                text, kd = "IF  x", "bad"
            if stg == "IF" and lab.startswith("3"):
                text = "IF  (wasted)"
            d.box("c%d_%s" % (r, stg), x + 2, y, CW - 4, CH, text, kd, size=11, bold=True)
    gy = lambda r: Y0 + r * (CH + GAP) + CH + GAP / 2   # centre of the gap below row r
    ax = lambda c: X0 + (c - 1) * CW + CW / 2           # centre x of cycle c
    d.arrow("f1", "c0_WB", "c1_EX", kind="data", sside="b", dside="t", label="WB -> EX (x1)", lpos=(ax(5), gy(0)))
    d.arrow("f2", "c1_MEM", "c2_EX", kind="data", sside="b", dside="t", label="MEM -> EX (x3)", lpos=(ax(6), gy(1)))
    d.arrow("f3", "c2_MEM", "c3_EX", kind="data", sside="b", dside="t", label="MEM -> EX (x5)", lpos=(ax(7), gy(2)))
    d.arrow("fl", "c3_EX", "c4_XX", kind="ctrl", sside="b", dside="t", label="flush", lpos=(ax(7), gy(3)))
    d.arrow("fl2", "c4_XX", "c5_IF", kind="ctrl", sside="b", dside="t", label="", )
    ny = Y0 + 7 * (CH + GAP) + 10
    d.text("n1", 20, ny, "Cycle 3: the load is in EX and add (in ID) needs x1, so a load-use stall holds the PC and IF/ID for one cycle and a bubble enters EX; sub is fetched twice.\n"
                         "Cycle 5: the load is in WB when add reaches EX, so x1 is forwarded from WB. Cycles 6 and 7: back-to-back dependences are forwarded from MEM, no stall.\n"
                         "Cycle 7: beq resolves in EX and is taken: or (in ID) and and (in IF) are squashed (x) and the PC is loaded with T; xor is fetched in cycle 8.", 11)
    d.text("n2", 20, ny + 62, "Blue arrows: forwarding. Red slots: a stall or a squashed instruction. In BP_MODE=1 a taken backward branch would redirect from ID instead (1 bubble).", 10, italic=True)
    return d


if __name__ == "__main__":
    for name, f in (("rv32i_architecture", architecture), ("rv32i_flowchart", flowchart), ("rv32i_pipeline_timing", pipeline_timing)):
        print(name, "overflow:", f().export_all(HERE, name))
