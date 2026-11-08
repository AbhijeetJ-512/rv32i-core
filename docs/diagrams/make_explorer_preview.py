#!/usr/bin/env python3
"""make_explorer_preview.py - animated SVG preview of docs/architecture_explorer.html for the README.

    python3 docs/diagrams/make_explorer_preview.py            # writes docs/diagrams/architecture_explorer_preview.svg

A README cannot run JavaScript, so this draws the explorer's datapath as a plain SVG that animates with SMIL and
CSS only (both work in an <img> on GitHub). The blocks, wires and pipeline registers are read from the NODES, BARS
and EDGES tables inside the explorer page, so the preview cannot drift from the page: change the page, run this again.
"""
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "architecture_explorer.html")
OUT = os.path.join(HERE, "architecture_explorer_preview.svg")

STAGES = [("IF", "Fetch", 10, 236, "if"), ("ID", "Decode", 274, 302, "id"), ("EX", "Execute", 604, 342, "ex"),
          ("MEM", "Memory", 974, 242, "mem"), ("WB", "Write-back", 1244, 252, "wb")]
TYPES = [("data", "Combinational datapath"), ("mem", "Memory port"), ("fwd", "Forwarding / bypass"),
         ("ctl", "Control & hazard"), ("trap", "Trap / halt"), ("ver", "Verification only")]
CLOCK = 1.7   # seconds per animated clock cycle, the same as the explorer at 1x


def parse(src):
    nodes = []
    block = src[src.index("const NODES={"):src.index("const BARS={")]
    for m in re.finditer(r"\n (\w+):\{x:(\d+),y:(\d+),w:(\d+),h:(\d+),t:'([^']*)',s:'([^']*)'(?:,l:\[([^\]]*)\])?([^\n]*)", block):
        nid, x, y, w, h, t, s, l, rest = m.groups()
        lines = re.findall(r"'([^']*)'", l or "")
        nodes.append(dict(id=nid, x=int(x), y=int(y), w=int(w), h=int(h), t=t, s=s, l=lines,
                          ext="ext:1" in rest, ver="ver:1" in rest))
    bars = [(m.group(1), int(m.group(2)), m.group(3)) for m in
            re.finditer(r"\n (\w+):\{x:(\d+),t:'([^']*)'", src[src.index("const BARS={"):src.index("const TYPES=")])]
    edges = []
    for m in re.finditer(r"E\('(E\d+)','(\w+)','(\w+)','(\w+)','([^']*)',(\[\[[\d,\[\]]*\]\])", src):
        pts = [tuple(map(int, p)) for p in re.findall(r"\[(\d+),(\d+)\]", m.group(6))]
        edges.append(dict(id=m.group(1), frm=m.group(2), to=m.group(3), type=m.group(4), label=m.group(5), pts=pts))
    if len(nodes) < 20 or len(bars) != 4 or len(edges) < 50:
        sys.exit("could not read the NODES / BARS / EDGES tables from %s (%d, %d, %d)" % (PAGE, len(nodes), len(bars), len(edges)))
    return nodes, bars, edges


def length(pts):
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def build(nodes, bars, edges):
    e = html.escape
    o = []
    o.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1500 832" width="1500" height="832" '
             'role="img" aria-label="Animated datapath of rv32i_core: five pipeline stages, hazard, forwarding, redirect and trap logic">')
    o.append("""<style>
svg{--bg:#E9EDF1;--surface:#FFFFFF;--surface2:#F3F6F8;--ink:#121B24;--muted:#556574;--line:#C3CDD7;--grid:#D3DBE3;
 --data:#1B5FC4;--fwd:#B86200;--ctl:#6E3FC4;--trap:#C42F38;--mem:#0F7F55;--ver:#6A7B8C;
 --if:#1B5FC4;--id:#6E3FC4;--ex:#B86200;--mem2:#0F7F55;--wb:#A0306F}
@media (prefers-color-scheme: dark){svg{--bg:#0C1219;--surface:#131B24;--surface2:#18222D;--ink:#E1E8EF;--muted:#8D9BA9;--line:#2B3947;--grid:#1B2631;
 --data:#5FA3FF;--fwd:#F0A63A;--ctl:#A986F5;--trap:#FF6B70;--mem:#3CCB8E;--ver:#8496A8;
 --if:#5FA3FF;--id:#A986F5;--ex:#F0A63A;--mem2:#3CCB8E;--wb:#F07AB8}}
.bg{fill:var(--bg)} .dot{fill:var(--grid)} .band{fill:var(--surface2);opacity:.6}
.hd{font:700 16px 'Arial Narrow','Roboto Condensed','Helvetica Neue',Arial,sans-serif;letter-spacing:.04em}
.box{fill:var(--surface);stroke:var(--line);stroke-width:1.2} .ext .box{fill:var(--surface2);stroke-dasharray:4 3} .ver .box{stroke-dasharray:2 3}
.nt{font:700 15px 'Arial Narrow','Roboto Condensed','Helvetica Neue',Arial,sans-serif;fill:var(--ink)}
.ns{font:400 10.5px ui-monospace,'SFMono-Regular',Menlo,Consolas,monospace;fill:var(--muted)}
.nl{font:400 10.5px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:var(--muted)}
.bar{fill:var(--surface2);stroke:var(--ink);stroke-opacity:.45;stroke-width:1.2}
.bt{font:600 11px ui-monospace,Menlo,Consolas,monospace;fill:var(--muted);letter-spacing:.08em}
.bnd{fill:none;stroke:var(--line);stroke-dasharray:6 5;stroke-width:1.2}
.cap{font:600 11px ui-monospace,Menlo,Consolas,monospace;fill:var(--muted);letter-spacing:.06em}
.lg{font:400 12px -apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:var(--muted)}
.ln{fill:none;stroke-width:1.6}
.t-data{stroke:var(--data)} .t-fwd{stroke:var(--fwd);stroke-width:2} .t-ctl{stroke:var(--ctl);stroke-dasharray:5 4}
.t-trap{stroke:var(--trap);stroke-dasharray:7 3} .t-mem{stroke:var(--mem);stroke-width:2} .t-ver{stroke:var(--ver);stroke-dasharray:2 4}
.p-data{fill:var(--data)} .p-fwd{fill:var(--fwd)} .p-ctl{fill:var(--ctl)} .p-trap{fill:var(--trap)} .p-mem{fill:var(--mem)} .p-ver{fill:var(--ver)}
.pulse{fill:var(--data);animation:clk %.1fs steps(1,end) infinite}
@keyframes clk{0%%{opacity:0}88%%{opacity:.55}100%%{opacity:0}}
@media (prefers-reduced-motion: reduce){.pulse{animation:none;opacity:0}}
</style>""" % CLOCK)
    o.append('<defs><pattern id="g" width="16" height="16" patternUnits="userSpaceOnUse"><circle class="dot" cx="1" cy="1" r=".9"/></pattern>')
    for t, _ in TYPES:
        o.append('<marker id="a-%s" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                 '<path d="M0 0L10 5L0 10z" class="p-%s"/></marker>' % (t, t))
    o.append("</defs>")
    o.append('<rect class="bg" width="1500" height="832"/><rect width="1500" height="790" fill="url(#g)"/>')
    for k, name, x, w, c in STAGES:
        var = "mem2" if c == "mem" else c
        o.append('<rect class="band" x="%d" y="12" width="%d" height="668" rx="4"/>' % (x, w))
        o.append('<rect x="%d" y="12" width="%d" height="4" rx="2" fill="var(--%s)"/>' % (x, w, var))
        o.append('<text class="hd" x="%d" y="40" fill="var(--%s)">%s · %s</text>' % (x + 10, var, k, name))
    o.append('<rect class="bnd" x="6" y="72" width="1488" height="618" rx="6"/>')
    o.append('<text class="cap" x="1488" y="686" text-anchor="end">rv32i_core boundary</text>')
    o.append('<text class="cap" x="1488" y="788" text-anchor="end">testbench + verification (outside the core)</text>')
    # wires, then moving signals on them
    for ed in edges:
        d = "M" + " L".join("%d %d" % p for p in ed["pts"])
        ed["d"] = d
        o.append('<path class="ln t-%s" d="%s" marker-end="url(#a-%s)"><title>%s</title></path>' % (ed["type"], d, ed["type"], e(ed["label"])))
    for ed in edges:
        L = length(ed["pts"])
        dur = max(1.2, L / 70.0)
        n = max(1, round(L / 170))
        for i in range(n):
            o.append('<circle r="3.2" class="p-%s"><animateMotion dur="%.2fs" begin="-%.2fs" repeatCount="indefinite" path="%s"/></circle>'
                     % (ed["type"], dur, dur * i / n, ed["d"]))
    # pipeline registers, flashing on each clock edge
    for _, x, t in bars:
        o.append('<rect class="bar" x="%d" y="150" width="18" height="510" rx="3"/>' % x)
        o.append('<rect class="pulse" x="%d" y="150" width="18" height="510" rx="3"/>' % x)
        o.append('<text class="bt" x="%d" y="405" transform="rotate(-90 %d 405)" text-anchor="middle">%s register</text>' % (x + 13, x + 13, e(t)))
    for n in nodes:
        cls = "n" + (" ext" if n["ext"] else "") + (" ver" if n["ver"] else "")
        o.append('<g class="%s"><rect class="box" x="%d" y="%d" width="%d" height="%d" rx="5"/>' % (cls, n["x"], n["y"], n["w"], n["h"]))
        y = n["y"] + 19
        o.append('<text class="nt" x="%d" y="%d">%s</text>' % (n["x"] + 10, y, e(n["t"])))
        y += 15
        o.append('<text class="ns" x="%d" y="%d">%s</text>' % (n["x"] + 10, y, e(n["s"])))
        for line in n["l"]:
            y += 14
            if y > n["y"] + n["h"] - 6:
                break
            o.append('<text class="nl" x="%d" y="%d">%s</text>' % (n["x"] + 10, y, e(line)))
        o.append("</g>")
    # legend
    x = 16
    for t, name in TYPES:
        o.append('<path class="ln t-%s" d="M%d 814 L%d 814" marker-end="url(#a-%s)"/>' % (t, x, x + 26, t))
        o.append('<text class="lg" x="%d" y="818">%s</text>' % (x + 34, e(name)))
        x += 44 + int(len(name) * 6.6)
    o.append('<text class="lg" x="1488" y="818" text-anchor="end">Open the interactive explorer to run programs through the pipeline</text>')
    o.append("</svg>")
    return "\n".join(o) + "\n"


def main():
    nodes, bars, edges = parse(open(PAGE, encoding="utf-8").read())
    open(OUT, "w", encoding="utf-8").write(build(nodes, bars, edges))
    print("wrote %s: %d blocks, %d registers, %d wires" % (os.path.relpath(OUT), len(nodes), len(bars), len(edges)))


if __name__ == "__main__":
    main()
