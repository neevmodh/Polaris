"""A tiny black-and-white diagram engine: boxes, shapes and orthogonal arrows written as SVG.

Pure black on white, no colour. Meaning is carried by shape and line style:
  process  = plain rectangle          model     = double-bordered rectangle
  data     = cylinder                 input     = parallelogram
  external = dashed rectangle         decision  = diamond
  terminal = rounded pill             output    = rectangle with a thick left bar
"""
import html, math

FS, FS_TITLE, FS_SMALL = 21, 25, 18
LH = 1.28            # line height factor
CH = 0.56            # average character width as a fraction of font size (Arial)


def est(text, fs): return len(text) * fs * CH


class Node:
    def __init__(self, d, nid, kind, x, y, w, lines, title=None, h=None, fs=FS):
        self.d, self.id, self.kind, self.x, self.y, self.w, self.fs = d, nid, kind, x, y, w, fs
        self.title, self.lines = title, lines
        pad_v = 18 if kind != "decision" else 0
        n = len(lines) + (1 if title else 0)
        need = n * fs * LH + (6 if title else 0) + 2 * pad_v + (14 if kind == "data" else 0)
        self.h = h or max(need, 64)
        if kind == "decision": self.h = h or max(need * 1.55, 110)
        inner = w - (46 if kind in ("input", "data") else 28)
        if kind == "decision": inner = w * 0.52
        for t in ([title] if title else []) + lines:
            if est(t, FS_TITLE if t == title else fs) > inner + 2:
                print(f"  WARN text may overflow  [{nid}]  {t!r}  ~{est(t, fs):.0f} > {inner:.0f}")
        d.nodes[nid] = self

    # connection points
    def pt(self, side, frac=0.5):
        x, y, w, h = self.x, self.y, self.w, self.h
        return {"l": (x, y + h * frac), "r": (x + w, y + h * frac), "t": (x + w * frac, y), "b": (x + w * frac, y + h)}[side]

    def svg(self):
        x, y, w, h, k = self.x, self.y, self.w, self.h, self.kind
        o = []
        stroke = 'stroke="#000" fill="#fff"'
        if k == "process": o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {stroke} stroke-width="2.4"/>')
        elif k == "model":
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {stroke} stroke-width="2.4"/>')
            o.append(f'<rect x="{x+7}" y="{y+7}" width="{w-14}" height="{h-14}" fill="none" stroke="#000" stroke-width="1.4"/>')
        elif k == "external": o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {stroke} stroke-width="2.2" stroke-dasharray="11 7"/>')
        elif k == "output":
            o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" {stroke} stroke-width="2.4"/>')
            o.append(f'<rect x="{x}" y="{y}" width="14" height="{h}" fill="#000"/>')
        elif k == "terminal": o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{min(h/2, 34)}" {stroke} stroke-width="2.6"/>')
        elif k == "input":
            s = 26
            o.append(f'<polygon points="{x+s},{y} {x+w},{y} {x+w-s},{y+h} {x},{y+h}" {stroke} stroke-width="2.4"/>')
        elif k == "data":
            e = 16
            o.append(f'<path d="M{x},{y+e} v{h-2*e} a{w/2},{e} 0 0 0 {w},0 v-{h-2*e} a{w/2},{e} 0 0 0 -{w},0 z" {stroke} stroke-width="2.4"/>')
            o.append(f'<path d="M{x},{y+e} a{w/2},{e} 0 0 0 {w},0" fill="none" stroke="#000" stroke-width="2.4"/>')
        elif k == "decision":
            o.append(f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" {stroke} stroke-width="2.4"/>')
        # text
        rows = ([(self.title, True)] if self.title else []) + [(t, False) for t in self.lines]
        total = len(rows) * self.fs * LH + (6 if self.title else 0)
        cy = y + (h - total) / 2 + (8 if k == "data" else 0)
        cx = x + w / 2 + (7 if k == "output" else 0)
        align = "middle"
        for t, bold in rows:
            fs = FS_TITLE if bold else self.fs
            cy += fs * LH * (0.98 if bold else 0.92)
            fam = "Arial, Helvetica, sans-serif"
            o.append(f'<text x="{cx}" y="{cy:.1f}" text-anchor="{align}" font-family="{fam}" font-size="{fs}" '
                     f'font-weight="{700 if bold else 400}" fill="#000">{html.escape(t)}</text>')
            cy += (fs * LH * 0.08) + (6 if bold else 0)
        return "\n".join(o)


class Diagram:
    def __init__(self, title, subtitle, w, h):
        self.title, self.subtitle, self.w, self.h = title, subtitle, w, h
        self.nodes, self.edges, self.extra = {}, [], []

    def node(self, nid, kind, x, y, w, lines, title=None, h=None, fs=FS):
        return Node(self, nid, kind, x, y, w, lines, title, h, fs)

    def band(self, x, y, w, h, label):
        """A labelled grouping frame (drawn first, behind everything)."""
        self.extra.append(("band", x, y, w, h, label))

    def note(self, x, y, text, anchor="start", fs=FS_SMALL, bold=False):
        self.extra.append(("note", x, y, text, anchor, fs, bold))

    def edge(self, a, sa, b, sb, label=None, dashed=False, fa=0.5, fb=0.5, via=None, lab_dx=0, lab_dy=0, both=False, lab_side=None):
        self.edges.append(dict(a=a, sa=sa, b=b, sb=sb, label=label, dashed=dashed, fa=fa, fb=fb, via=via, dx=lab_dx, dy=lab_dy, both=both))

    def _route(self, e):
        A, B = self.nodes[e["a"]], self.nodes[e["b"]]
        p0, p1 = A.pt(e["sa"], e["fa"]), B.pt(e["sb"], e["fb"])
        if e["via"]: pts = [p0] + e["via"] + [p1]
        else:
            if e["sa"] in "lr" and e["sb"] in "lr":
                if abs(p0[1] - p1[1]) < 1: pts = [p0, p1]
                else:
                    mx = (p0[0] + p1[0]) / 2
                    pts = [p0, (mx, p0[1]), (mx, p1[1]), p1]
            elif e["sa"] in "tb" and e["sb"] in "tb":
                if abs(p0[0] - p1[0]) < 1: pts = [p0, p1]
                else:
                    my = (p0[1] + p1[1]) / 2
                    pts = [p0, (p0[0], my), (p1[0], my), p1]
            elif e["sa"] in "lr":                       # horizontal out, vertical in
                pts = [p0, (p1[0], p0[1]), p1]
            else:                                       # vertical out, horizontal in
                pts = [p0, (p0[0], p1[1]), p1]
        return pts

    def svg(self):
        W, H = self.w, self.h
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
             '<defs><marker id="ah" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">'
             '<path d="M0,0 L12,6 L0,12 z" fill="#000"/></marker>'
             '<marker id="ahs" viewBox="0 0 12 12" refX="1" refY="6" markerWidth="11" markerHeight="11" orient="auto-start-reverse">'
             '<path d="M0,0 L12,6 L0,12 z" fill="#000"/></marker></defs>',
             f'<rect width="{W}" height="{H}" fill="#fff"/>',
             f'<rect x="12" y="12" width="{W-24}" height="{H-24}" fill="none" stroke="#000" stroke-width="3"/>',
             f'<text x="48" y="74" font-family="Arial, Helvetica, sans-serif" font-size="46" font-weight="800" fill="#000">{html.escape(self.title)}</text>',
             f'<text x="48" y="112" font-family="Arial, Helvetica, sans-serif" font-size="23" fill="#000">{html.escape(self.subtitle)}</text>',
             f'<line x1="48" y1="132" x2="{W-48}" y2="132" stroke="#000" stroke-width="2"/>']
        for it in self.extra:
            if it[0] == "band":
                _, x, y, w, h, label = it
                o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="#000" stroke-width="1.4" stroke-dasharray="3 6"/>')
                o.append(f'<rect x="{x+14}" y="{y-14}" width="{est(label, 19)+len(label)*1.9+30:.0f}" height="26" fill="#fff"/>')
                o.append(f'<text x="{x+24}" y="{y+6}" font-family="Arial, Helvetica, sans-serif" font-size="19" font-weight="700" letter-spacing="1.5" fill="#000">{html.escape(label)}</text>')
        for e in self.edges:
            pts = self._route(e)
            dash = ' stroke-dasharray="9 7"' if e["dashed"] else ""
            d = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
            ms = ' marker-start="url(#ahs)"' if e["both"] else ""
            o.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="2.4"{dash}{ms} marker-end="url(#ah)" stroke-linejoin="round"/>')
        for n in self.nodes.values(): o.append(n.svg())
        for e in self.edges:
            if e["label"]:
                pts = self._route(e)
                seg = max(range(len(pts) - 1), key=lambda i: abs(pts[i+1][0]-pts[i][0]) + abs(pts[i+1][1]-pts[i][1]))
                (x0, y0), (x1, y1) = pts[seg], pts[seg + 1]
                tw = est(e["label"], FS_SMALL) + 12
                if abs(y1 - y0) < 1:                       # horizontal: sit just above the line
                    mx, my = (x0 + x1) / 2 + e["dx"], y0 - 26 + e["dy"]
                    anchor, tx = "middle", mx
                    o.append(f'<rect x="{mx-tw/2:.1f}" y="{my-2:.1f}" width="{tw:.1f}" height="24" fill="#fff"/>')
                else:                                      # vertical: sit just right of the line
                    mx, my = x0 + 12 + e["dx"], (y0 + y1) / 2 + e["dy"]
                    anchor, tx = "start", mx + 4
                    o.append(f'<rect x="{mx:.1f}" y="{my-14:.1f}" width="{tw:.1f}" height="24" fill="#fff"/>')
                o.append(f'<text x="{tx:.1f}" y="{my+(15 if abs(y1-y0)<1 else 4):.1f}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{FS_SMALL}" font-style="italic" fill="#000">{html.escape(e["label"])}</text>')
        for it in self.extra:
            if it[0] == "note":
                _, x, y, text, anchor, fs, bold = it
                o.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="{fs}" font-weight="{700 if bold else 400}" fill="#000">{html.escape(text)}</text>')
        o.append(self.legend())
        o.append("</svg>")
        return "\n".join(o)

    def legend(self):
        x, y = 48, self.h - 62
        items = [("rect", "process"), ("model", "model"), ("data", "data / store"), ("input", "input"), ("external", "external"), ("output", "output")]
        o = [f'<text x="{x}" y="{y-14}" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="700" letter-spacing="1.5" fill="#000">LEGEND</text>']
        cx = x
        for kind, label in items:
            if kind == "rect": o.append(f'<rect x="{cx}" y="{y-4}" width="46" height="26" fill="#fff" stroke="#000" stroke-width="2"/>')
            if kind == "model":
                o.append(f'<rect x="{cx}" y="{y-4}" width="46" height="26" fill="#fff" stroke="#000" stroke-width="2"/><rect x="{cx+5}" y="{y+1}" width="36" height="16" fill="none" stroke="#000" stroke-width="1.2"/>')
            if kind == "data":
                o.append(f'<path d="M{cx},{y+4} v14 a23,5 0 0 0 46,0 v-14 a23,5 0 0 0 -46,0 z" fill="#fff" stroke="#000" stroke-width="2"/><path d="M{cx},{y+4} a23,5 0 0 0 46,0" fill="none" stroke="#000" stroke-width="2"/>')
            if kind == "input": o.append(f'<polygon points="{cx+9},{y-4} {cx+46},{y-4} {cx+37},{y+22} {cx},{y+22}" fill="#fff" stroke="#000" stroke-width="2"/>')
            if kind == "external": o.append(f'<rect x="{cx}" y="{y-4}" width="46" height="26" fill="#fff" stroke="#000" stroke-width="2" stroke-dasharray="6 4"/>')
            if kind == "output": o.append(f'<rect x="{cx}" y="{y-4}" width="46" height="26" fill="#fff" stroke="#000" stroke-width="2"/><rect x="{cx}" y="{y-4}" width="8" height="26" fill="#000"/>')
            o.append(f'<text x="{cx+56}" y="{y+16}" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#000">{label}</text>')
            cx += 56 + est(label, 18) + 34
        o.append(f'<line x1="{cx+10}" y1="{y+9}" x2="{cx+60}" y2="{y+9}" stroke="#000" stroke-width="2.4" marker-end="url(#ah)"/><text x="{cx+70}" y="{y+16}" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#000">data flow</text>')
        cx += 70 + 90
        o.append(f'<line x1="{cx}" y1="{y+9}" x2="{cx+50}" y2="{y+9}" stroke="#000" stroke-width="2.4" stroke-dasharray="9 7" marker-end="url(#ah)"/><text x="{cx+60}" y="{y+16}" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="#000">optional / fallback</text>')
        return "\n".join(o)
