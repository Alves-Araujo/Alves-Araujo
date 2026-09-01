#!/usr/bin/env python3
"""Gera um grafico de contribuicoes do GitHub em SVG animado,
na mesma paleta do banner do perfil. Sem dependencias externas."""
import html as _html
import os
import re
import subprocess
import sys
from datetime import date

USER = os.environ.get("GH_USER", "Alves-Araujo")
OUT  = os.environ.get("OUT_PATH", "assets/contribution-graph.svg")

CELL, GAP           = 12.0, 3.6
PAD_L, PAD_T        = 32.0, 28.0
PAD_R, PAD_B        = 18.0, 38.0
PITCH               = CELL + GAP
PALETTE             = ["#22e6e0", "#46b8f5", "#6f7bfa", "#a855f0",
                       "#ff3ee0", "#a855f0", "#6f7bfa", "#46b8f5"]
LEVEL_OPACITY       = {1: 0.42, 2: 0.62, 3: 0.82, 4: 1.0}
EMPTY, INK, MUTED   = "#151b23", "#0a0e13", "#8b949e"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def fetch(user):
    url = f"https://github.com/users/{user}/contributions"
    try:
        page = subprocess.run(
            ["curl", "-sL", "--max-time", "40", "-H", "User-Agent: Mozilla/5.0", url],
            capture_output=True, text=True, check=True).stdout
    except Exception as exc:                       # noqa: BLE001
        sys.exit(f"falha ao buscar contribuicoes: {exc}")

    cells = []
    for td in re.findall(r"<td[^>]*data-date=[^>]*>", page):
        gid = re.search(r'id="contribution-day-component-(\d+)-(\d+)"', td)
        dt  = re.search(r'data-date="(\d{4})-(\d{2})-(\d{2})"', td)
        lv  = re.search(r'data-level="(\d)"', td)
        if not (gid and dt and lv):
            continue
        cells.append(dict(row=int(gid.group(1)), col=int(gid.group(2)),
                          date=date(*map(int, dt.groups())), level=int(lv.group(1))))
    if not cells:
        sys.exit("nenhuma celula encontrada - o HTML do GitHub mudou?")

    counts = {}
    for tip in re.findall(r"<tool-tip[^>]*for=\"contribution-day-component-(\d+)-(\d+)\"[^>]*>(.*?)</tool-tip>",
                          page, re.S):
        n = re.match(r"\s*(\d+|No)\s+contribution", _html.unescape(tip[2]))
        if n:
            counts[(int(tip[0]), int(tip[1]))] = 0 if n.group(1) == "No" else int(n.group(1))
    for c in cells:
        c["count"] = counts.get((c["row"], c["col"]), 0)
    return cells


def build(cells):
    cols  = max(c["col"] for c in cells) + 1
    width = round(PAD_L + cols * PITCH - GAP + PAD_R, 1)
    height= round(PAD_T + 7 * PITCH - GAP + PAD_B, 1)
    total = sum(c["count"] for c in cells)

    stops = "".join(
        f'<stop offset="{round((p + i / len(PALETTE)) / 2, 4)}" stop-color="{c}"/>'
        for p in (0, 1) for i, c in enumerate(PALETTE)) + '<stop offset="1" stop-color="#22e6e0"/>'

    # rotulos de mes: primeira semana em que o mes aparece
    seen, months = set(), []
    for c in sorted(cells, key=lambda c: (c["col"], c["row"])):
        key = (c["date"].year, c["date"].month)
        if key not in seen and c["date"].day <= 7:
            seen.add(key)
            months.append((c["col"], MONTHS[c["date"].month - 1]))

    parts = []
    for col, label in months:
        if col > cols - 3:
            continue
        parts.append(f'<text x="{round(PAD_L + col * PITCH, 1)}" y="{PAD_T - 10}" '
                     f'fill="{MUTED}" font-size="10" font-family="system-ui,sans-serif">{label}</text>')
    for row, label in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        parts.append(f'<text x="0" y="{round(PAD_T + row * PITCH + CELL - 2.5, 1)}" '
                     f'fill="{MUTED}" font-size="9" font-family="system-ui,sans-serif">{label}</text>')

    quiet, live = [], []
    for c in cells:
        x = round(PAD_L + c["col"] * PITCH, 1)
        y = round(PAD_T + c["row"] * PITCH, 1)
        if c["level"] == 0:
            quiet.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.6"/>')
        else:
            op = LEVEL_OPACITY[c["level"]]
            # onda de brilho percorrendo da esquerda para a direita
            delay = round((c["col"] / cols) * 5.0, 2)
            live.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.6" opacity="{op}">'
                f'<animate attributeName="opacity" values="{op};{min(1, round(op * 1.45, 2))};{op}" '
                f'dur="5s" begin="-{delay}s" repeatCount="indefinite"/></rect>')

    legend = []
    lx = width - PAD_R - 5 * PITCH - 74
    ly = height - PAD_B + 16
    legend.append(f'<text x="{round(lx, 1)}" y="{round(ly + CELL - 2.5, 1)}" fill="{MUTED}" '
                  f'font-size="9.5" font-family="system-ui,sans-serif">Less</text>')
    legend.append(f'<rect x="{round(lx + 30, 1)}" y="{round(ly, 1)}" width="{CELL}" height="{CELL}" '
                  f'rx="2.6" fill="{EMPTY}"/>')
    for i, lv in enumerate((1, 2, 3, 4)):
        legend.append(f'<rect x="{round(lx + 30 + (i + 1) * PITCH, 1)}" y="{round(ly, 1)}" '
                      f'width="{CELL}" height="{CELL}" rx="2.6" fill="url(#flow)" '
                      f'opacity="{LEVEL_OPACITY[lv]}"/>')
    legend.append(f'<text x="{round(lx + 30 + 5 * PITCH + 6, 1)}" y="{round(ly + CELL - 2.5, 1)}" '
                  f'fill="{MUTED}" font-size="9.5" font-family="system-ui,sans-serif">More</text>')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}"
     role="img" aria-label="{total} contributions in the last year">
  <title>{total} contributions in the last year</title>
  <defs>
    <linearGradient id="flow" gradientUnits="userSpaceOnUse" x1="{-width}" y1="0" x2="{width}" y2="0">
      {stops}
      <animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="{width} 0"
                        dur="7.5s" repeatCount="indefinite"/>
    </linearGradient>
    <filter id="cellGlow" x="-120%" y="-120%" width="340%" height="340%">
      <feGaussianBlur stdDeviation="2.6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>

  <rect width="{width}" height="{height}" rx="10" fill="{INK}"/>
  <rect x="0.6" y="0.6" width="{width - 1.2}" height="{height - 1.2}" rx="9.4"
        fill="none" stroke="url(#flow)" stroke-width="1.2" opacity=".5"/>

  {"".join(parts)}

  <g fill="{EMPTY}">{"".join(quiet)}</g>
  <g fill="url(#flow)" filter="url(#cellGlow)">{"".join(live)}</g>

  <text x="{PAD_L}" y="{round(height - PAD_B + 26, 1)}" fill="{MUTED}" font-size="10.5"
        font-family="system-ui,sans-serif">{total} contributions in the last year</text>
  {"".join(legend)}
</svg>
'''


if __name__ == "__main__":
    svg = build(fetch(USER))
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"{OUT} | {len(svg)} bytes")
