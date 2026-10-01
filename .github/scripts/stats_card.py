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
# METRICS_TOKEN: token pessoal com escopo "repo", para enxergar os repositorios
# privados. O GITHUB_TOKEN padrao das Actions so enxerga o proprio repositorio,
# entao sem o METRICS_TOKEN o card conta apenas os publicos.
TOKEN = os.environ.get("METRICS_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

# Linguagens que o Flutter/CMake geram sozinhos nas pastas de plataforma.
# Nao foram escritas por voce, entao nao contam. Edite a vontade.
IGNORED = {"HTML", "CMake", "Swift", "Objective-C", "Kotlin", "C", "Ruby", "Batchfile", "Shell"}
MAX_LANGS = 5

W, H     = 873.0, 118.0
PAD      = 16.0
INK      = "#0a0e13"
MUTED    = "#8b949e"
BRIGHT   = "#e6edf3"
PALETTE  = ["#22e6e0", "#46b8f5", "#6f7bfa", "#a855f0", "#ff3ee0", "#a855f0",
            "#6f7bfa", "#46b8f5"]
LANG_COLORS = ["#22e6e0", "#6f7bfa", "#a855f0", "#ff3ee0", "#46b8f5"]
FONT = "system-ui,-apple-system,Segoe UI,sans-serif"


# Desligado quando o token falha, para o fallback publico nao reenviar
# um cabecalho de autorizacao invalido e levar 401 de novo.
USAR_TOKEN = bool(TOKEN)


def api(path):
    cmd = ["curl", "-sL", "--max-time", "40", f"https://api.github.com{path}"]
    if USAR_TOKEN:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    try:
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    except Exception:                                  # noqa: BLE001
        return None


def graphql(consulta):
    """GraphQL so responde autenticado. Devolve None se nao der."""
    if not USAR_TOKEN:
        return None
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "40", "https://api.github.com/graphql",
             "-H", f"Authorization: Bearer {TOKEN}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"query": consulta})],
            capture_output=True, text=True, check=True).stdout
        d = json.loads(r)
        return d.get("data")
    except Exception:                                  # noqa: BLE001
        return None


def contribuicoes_privadas():
    """Quantas contribuicoes sairam de repositorios privados, sem revelar quais.
    Exige um token com escopo read:user; sem ele a API devolve so o publico."""
    d = graphql("{ viewer { contributionsCollection { restrictedContributionsCount } } }")
    try:
        n = d["viewer"]["contributionsCollection"]["restrictedContributionsCount"]
        return n if isinstance(n, int) and n > 0 else None
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


def listar_repos(user):
    """Com token: /user/repos enxerga publicos e privados. Sem token: so os publicos.
    Pagina ate o fim para nao travar em 100 silenciosamente."""
    global USAR_TOKEN
    publico = f"/users/{user}/repos?type=owner"
    base = "/user/repos?affiliation=owner&visibility=all" if USAR_TOKEN else publico
    while True:
        todos, pagina = [], 1
        while True:
            lote = api(f"{base}&per_page=100&page={pagina}")
            if not isinstance(lote, list):
                break
            todos += lote
            if len(lote) < 100:
                return todos
            pagina += 1
        # erro da API vem como dicionario. Se foi o token que falhou (expirado,
        # revogado), ainda da para montar o card so com os repositorios publicos.
        if base != publico:
            print("aviso: token nao listou os repositorios; usando so os publicos",
                  file=sys.stderr)
            USAR_TOKEN = False
            base = publico
            continue
        sys.exit(f"API nao devolveu a lista de repositorios: {lote}")


def gather(user):
    repos = listar_repos(user)
    # fora forks e o repositorio do proprio perfil, que nao e projeto
    repos = [r for r in repos
             if not r.get("fork") and r["name"].lower() != user.lower()]
    langs = Counter()
    for r in repos:
        data = api(f"/repos/{r['full_name']}/languages")
        if not isinstance(data, dict):
            continue
        for name, size in data.items():
            # ignora payload de erro, onde o valor e uma string
            if name not in IGNORED and isinstance(size, int):
                langs[name] += size
    privados = sum(1 for r in repos if r.get("private"))
    return len(repos), privados, langs, contributions(user), contribuicoes_privadas()


def build(n_repos, n_privados, langs, contribs, contribs_privadas):
    top = langs.most_common(MAX_LANGS)
    total = sum(v for _, v in top) or 1
    rows = [(name, size / total * 100.0) for name, size in top]

    stops = "".join(
        f'<stop offset="{round((p + i / len(PALETTE)) / 2, 4)}" stop-color="{c}"/>'
        for p in (0, 1) for i, c in enumerate(PALETTE)) + '<stop offset="1" stop-color="#22e6e0"/>'

    # ---- numeros ----
    # O detalhe publico/privado so aparece quando ha privados a contar: sem isso
    # a linha ficaria repetindo o numero grande.
    det_repos = (f"{n_repos - n_privados} public \u00b7 {n_privados} private"
                 if n_privados else "")
    det_contrib = (f"{contribs - contribs_privadas} public \u00b7 {contribs_privadas} private"
                   if contribs_privadas else "")
    stats = [(f"{n_repos}", "Repositories", det_repos),
             (f"{contribs}", "Contributions", det_contrib),
             (f"{len(langs)}", "Languages", "")]
    blocks, bx = [], PAD
    for value, label, detalhe in stats:
        blocks.append(
            f'<text x="{round(bx,1)}" y="{PAD + 24}" fill="{BRIGHT}" font-size="24" '
            f'font-weight="600" font-family="{FONT}">{value}</text>'
            f'<text x="{round(bx,1)}" y="{PAD + 40}" fill="{MUTED}" font-size="11" '
            f'font-family="{FONT}">{label}</text>')
        if detalhe:
            # ao lado do numero grande, na mesma linha de base
            dx = bx + len(value) * 14.5 + 9
            blocks.append(
                f'<text x="{round(dx,1)}" y="{PAD + 24}" fill="{MUTED}" font-size="10.5" '
                f'font-family="{FONT}">{detalhe}</text>')
        bx += 250
    blocks.append(f'<text x="{W - PAD}" y="{PAD + 10}" fill="{MUTED}" font-size="11" '
                  f'text-anchor="end" font-family="{FONT}">last 12 months</text>')

    # ---- barra empilhada ----
    bar_y, bar_h, bar_w = 76.0, 10.0, W - PAD * 2
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
            f'<circle cx="{round(lx+5,1)}" cy="{bar_y + 24}" r="4.5" fill="{col}"/>'
            f'<text x="{round(lx+18,1)}" y="{bar_y + 28}" fill="{BRIGHT}" font-size="12" '
            f'font-family="{FONT}">{name}</text>'
            f'<text x="{round(lx+18+len(name)*7.6+8,1)}" y="{bar_y + 28}" fill="{MUTED}" '
            f'font-size="12" font-family="{FONT}">{pct:.1f}%</text>')
        lx += len(name) * 7.6 + 78
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}"
     role="img" aria-label="GitHub stats">
  <title>{n_repos} repositories{f" ({det_repos})" if det_repos else ""}, {contribs} contributions{f" ({det_contrib})" if det_contrib else ""}, {len(langs)} languages</title>
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
  <rect x="{PAD}" y="66" width="{W - PAD*2}" height="1" fill="#1b2430"/>
  {bar}
  {"".join(legend)}
</svg>
'''


if __name__ == "__main__":
    n, n_priv, langs, contribs, contribs_priv = gather(USER)
    if not langs:
        sys.exit("nenhuma linguagem encontrada")
    svg = build(n, n_priv, langs, contribs, contribs_priv)
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"{OUT} | {len(svg)} bytes | {n} repos ({n_priv} privados) | "
          f"{contribs} contribs ({contribs_priv if contribs_priv else 0} privadas) | "
          + ", ".join(f"{k} {v/sum(langs.values())*100:.1f}%" for k, v in langs.most_common(5)))
