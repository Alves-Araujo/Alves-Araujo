#!/usr/bin/env python3
"""Gera um card de estatisticas (repositorios, contribuicoes e linguagens mais
usadas) em SVG, na mesma paleta do banner do perfil. Sem dependencias externas."""
import json
import os
import re
import subprocess
import sys
from collections import Counter

USER  = os.environ.get("GH_USER", "Alves-Araujo")
OUT   = os.environ.get("OUT_PATH", "assets/stats-card.svg")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

# Linguagens que o Flutter/CMake geram sozinhos nas pastas de plataforma.
# Nao foram escritas por voce, entao nao contam. Edite a vontade.
IGNORED = {"HTML", "CMake", "Swift", "Objective-C", "Kotlin", "C", "Ruby", "Batchfile", "Shell"}
MAX_LANGS = 5

W, H     = 873.0, 214.0
PAD      = 26.0
INK      = "#0a0e13"
MUTED    = "#8b949e"
BRIGHT   = "#e6edf3"
PALETTE  = ["#22e6e0", "#46b8f5", "#6f7bfa", "#a855f0", "#ff3ee0", "#a855f0",
            "#6f7bfa", "#46b8f5"]
LANG_COLORS = ["#22e6e0", "#6f7bfa", "#a855f0", "#ff3ee0", "#46b8f5"]
FONT = "system-ui,-apple-system,Segoe UI,sans-serif"


def api(path):
    cmd = ["curl", "-sL", "--max-time", "40", f"https://api.github.com{path}"]
    if TOKEN:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    try:
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    except Exception:                                  # noqa: BLE001
        return None


def contributions(user):
    try:
        page = subprocess.run(
            ["curl", "-sL", "--max-time", "40", "-H", "User-Agent: Mozilla/5.0",
             f"https://github.com/users/{user}/contributions"],
            capture_output=True, text=True, check=True).stdout
    except Exception:                                  # noqa: BLE001
        return 0
    # so os tooltips por dia; o cabecalho da pagina traz o mesmo total e
    # seria contado duas vezes por uma regex ampla
    total = 0
    for tip in re.findall(r"<tool-tip[^>]*for=\"contribution-day-component-\d+-\d+\"[^>]*>(.*?)</tool-tip>",
                          page, re.S):
        m = re.match(r"\s*(\d+|No)\s+contribution", tip)
        if m and m.group(1) != "No":
            total += int(m.group(1))
    return total


def gather(user):
    repos = api(f"/users/{user}/repos?per_page=100&type=owner") or []
    repos = [r for r in repos if not r.get("fork")]
    langs = Counter()
    for r in repos:
        data = api(f"/repos/{user}/{r['name']}/languages") or {}
        for name, size in data.items():
            if name not in IGNORED:
                langs[name] += size
    return len(repos), langs, contributions(user)


def build(n_repos, langs, contribs):
    top = langs.most_common(MAX_LANGS)
    total = sum(v for _, v in top) or 1
    rows = [(name, size / total * 100.0) for name, size in top]

    stops = "".join(
        f'<stop offset="{round((p + i / len(PALETTE)) / 2, 4)}" stop-color="{c}"/>'
        for p in (0, 1) for i, c in enumerate(PALETTE)) + '<stop offset="1" stop-color="#22e6e0"/>'

    # ---- numeros ----
    stats = [(f"{n_repos}", "Repositories"), (f"{contribs}", "Contributions"),
             (f"{len(langs)}", "Languages")]
    blocks, bx = [], PAD
    for value, label in stats:
        blocks.append(
            f'<text x="{round(bx,1)}" y="{PAD + 42}" fill="{BRIGHT}" font-size="34" '
            f'font-weight="600" font-family="{FONT}">{value}</text>'
            f'<text x="{round(bx,1)}" y="{PAD + 64}" fill="{MUTED}" font-size="12.5" '
            f'font-family="{FONT}">{label}</text>')
        bx += 178
    blocks.append(f'<text x="{W - PAD}" y="{PAD + 20}" fill="{MUTED}" font-size="12.5" '
                  f'text-anchor="end" font-family="{FONT}">last 12 months</text>')

    # ---- barra empilhada ----
    bar_y, bar_h, bar_w = 144.0, 16.0, W - PAD * 2
    segs, x = [], PAD
    for i, (_, pct) in enumerate(rows):
        seg = bar_w * pct / 100.0
        segs.append(f'<rect x="{round(x,2)}" y="{bar_y}" width="{round(max(seg,2),2)}" '
                    f'height="{bar_h}" fill="{LANG_COLORS[i % len(LANG_COLORS)]}"/>')
        x += seg
    bar = (f'<clipPath id="barClip"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" '
           f'height="{bar_h}" rx="{bar_h/2}"/></clipPath>'
           f'<g clip-path="url(#barClip)">{"".join(segs)}</g>')

    # ---- legenda ----
    legend, lx = [], PAD
    for i, (name, pct) in enumerate(rows):
        col = LANG_COLORS[i % len(LANG_COLORS)]
        legend.append(
            f'<circle cx="{round(lx+5,1)}" cy="{bar_y + 42}" r="5.5" fill="{col}"/>'
            f'<text x="{round(lx+18,1)}" y="{bar_y + 46.5}" fill="{BRIGHT}" font-size="13" '
            f'font-family="{FONT}">{name}</text>'
            f'<text x="{round(lx+18+len(name)*7.6+8,1)}" y="{bar_y + 46.5}" fill="{MUTED}" '
            f'font-size="12.5" font-family="{FONT}">{pct:.1f}%</text>')
        lx += len(name) * 7.6 + 78
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"
     role="img" aria-label="GitHub stats">
  <title>{n_repos} repositories, {contribs} contributions, {len(langs)} languages</title>
  <defs>
    <linearGradient id="flow" gradientUnits="userSpaceOnUse" x1="{-W}" y1="0" x2="{W}" y2="0">
      {stops}
      <animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="{W} 0"
                        dur="7.5s" repeatCount="indefinite"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" rx="10" fill="{INK}"/>
  <rect x="0.6" y="0.6" width="{W-1.2}" height="{H-1.2}" rx="9.4" fill="none"
        stroke="url(#flow)" stroke-width="1.2" opacity=".5"/>
  {"".join(blocks)}
  <rect x="{PAD}" y="108" width="{W - PAD*2}" height="1" fill="#1b2430"/>
  <text x="{PAD}" y="132" fill="{MUTED}" font-size="12.5" font-family="{FONT}">Most used languages</text>
  {bar}
  {"".join(legend)}
</svg>
'''


if __name__ == "__main__":
    n, langs, contribs = gather(USER)
    if not langs:
        sys.exit("nenhuma linguagem encontrada")
    svg = build(n, langs, contribs)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"{OUT} | {len(svg)} bytes | {n} repos | {contribs} contribs | "
          + ", ".join(f"{k} {v/sum(langs.values())*100:.1f}%" for k, v in langs.most_common(5)))
