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
# Dois papeis diferentes:
#  - TOKEN_PRIVADO: token pessoal (escopo repo e read:user). So ele enxerga os
#    repositorios privados e as contribuicoes privadas.
#  - TOKEN: qualquer token serve para autenticar as chamadas comuns e sair do
#    limite anonimo de 60 por hora, que na Actions e compartilhado entre
#    runners. O GITHUB_TOKEN padrao faz esse papel.
TOKEN_PRIVADO = os.environ.get("METRICS_TOKEN", "")
TOKEN = TOKEN_PRIVADO or os.environ.get("GITHUB_TOKEN", "")

# Linguagens que o Flutter/CMake geram sozinhos nas pastas de plataforma.
# Nao foram escritas por voce, entao nao contam. Edite a vontade.
IGNORED = {"HTML", "CMake", "Swift", "Objective-C", "Kotlin", "C", "Ruby", "Batchfile", "Shell"}
MAX_LANGS = 5

W, H     = 873.0, 118.0
PAD      = 16.0
INK      = "#0a0e13"
MUTED    = "#8b949e"
DIM      = "#5c6773"   # a separacao publico/privado, um tom abaixo do rotulo
BRIGHT   = "#e6edf3"
PALETTE  = ["#22e6e0", "#46b8f5", "#6f7bfa", "#a855f0", "#ff3ee0", "#a855f0",
            "#6f7bfa", "#46b8f5"]
LANG_COLORS = ["#22e6e0", "#6f7bfa", "#a855f0", "#ff3ee0", "#46b8f5"]
FONT = "system-ui,-apple-system,Segoe UI,sans-serif"

# Largura aproximada de um texto. Contar letras e multiplicar por um valor fixo
# erra feio em fonte proporcional: "lili" e "mwmw" tem quatro letras cada.
_ESTREITAS = set("iljtfIrJ1.,;:'!|()[] ")
_LARGAS = set("mwMW%@")


def largura(txt, tamanho):
    u = sum(0.30 if c in _ESTREITAS else 0.82 if c in _LARGAS else 0.55 for c in txt)
    return u * tamanho


def api(path):
    cmd = ["curl", "-sL", "--max-time", "40", f"https://api.github.com{path}"]
    if TOKEN:
        cmd += ["-H", f"Authorization: Bearer {TOKEN}"]
    try:
        return json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)
    except Exception:                                  # noqa: BLE001
        return None


def graphql(consulta):
    """GraphQL so responde autenticado. Devolve None se nao der."""
    if not TOKEN_PRIVADO:
        return None
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "40", "https://api.github.com/graphql",
             "-H", f"Authorization: Bearer {TOKEN_PRIVADO}",
             "-H", "Content-Type: application/json",
             "-d", json.dumps({"query": consulta})],
            capture_output=True, text=True, check=True).stdout
        d = json.loads(r)
        return d.get("data")
    except Exception:                                  # noqa: BLE001
        return None


def privados_do_arquivo():
    """Numeros privados guardados em disco, para quando nao ha token.

    Assim o workflow continua atualizando os numeros publicos todo dia sem
    precisar de nenhuma credencial guardada: o que ele nao consegue ver
    sozinho vem daqui. O arquivo tem so dois inteiros agregados, a mesma
    informacao que o card ja mostra. Regere com:
        python3 .github/scripts/private_stats.py
    """
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "private-stats.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                  # noqa: BLE001
        return {}


def contribuicoes_privadas():
    """Quantas contribuicoes sairam de repositorios privados, sem revelar quais.
    Exige um token com escopo read:user; sem ele a API devolve so o publico."""
    d = graphql("{ viewer { contributionsCollection { restrictedContributionsCount } } }")
    try:
        n = d["viewer"]["contributionsCollection"]["restrictedContributionsCount"]
        if isinstance(n, int) and n > 0:
            return n
    except Exception:                                  # noqa: BLE001
        pass
    n = privados_do_arquivo().get("contribuicoes")
    return n if isinstance(n, int) and n > 0 else None


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
    # /user/repos so funciona com token pessoal. O GITHUB_TOKEN da Actions nao
    # serve nele, entao nem tentamos: isso evita uma chamada que sempre falha.
    publico = f"/users/{user}/repos?type=owner"
    base = "/user/repos?affiliation=owner&visibility=all" if TOKEN_PRIVADO else publico
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
            print("aviso: o METRICS_TOKEN nao listou os repositorios; "
                  "usando so os publicos", file=sys.stderr)
            # se ele estiver expirado, nao adianta seguir usando: volta para o
            # GITHUB_TOKEN, que ao menos tira as chamadas do limite anonimo
            global TOKEN
            TOKEN = os.environ.get("GITHUB_TOKEN", "")
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
    if not privados:
        # sem token a listagem so traz publicos; o numero de privados vem do arquivo
        guardado = privados_do_arquivo().get("repos")
        if isinstance(guardado, int) and guardado > 0:
            privados = guardado
            repos_total = len(repos) + guardado
            return repos_total, privados, langs, contributions(user), contribuicoes_privadas()
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
    det_repos = (f"{n_repos - n_privados} public, {n_privados} private"
                 if n_privados else "")
    det_contrib = (f"{contribs - contribs_privadas} public, {contribs_privadas} private"
                   if contribs_privadas else "")
    stats = [(f"{n_repos}", "Repositories", det_repos),
             (f"{contribs}", "Contributions", det_contrib),
             (f"{len(langs)}", "Languages", "")]
    blocks, bx = [], PAD
    for value, label, detalhe in stats:
        # numero grande e, embaixo, uma linha so: rotulo e a separacao em tom
        # mais apagado. O tspan flui logo apos o rotulo, sem calcular posicao.
        # o separador fica no texto pai: espaco no inicio de um tspan e
        # descartado na renderizacao, e o detalhe cola no rotulo
        extra = (f' \u00b7 <tspan fill="{DIM}">{detalhe}</tspan>') if detalhe else ""
        blocks.append(
            f'<text x="{round(bx,1)}" y="{PAD + 24}" fill="{BRIGHT}" font-size="24" '
            f'font-weight="600" font-family="{FONT}">{value}</text>'
            f'<text x="{round(bx,1)}" y="{PAD + 41}" fill="{MUTED}" font-size="10.5" '
            f'font-family="{FONT}">{label}{extra}</text>')
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
        # a porcentagem vai num tspan, entao fica sempre a mesma distancia do
        # nome, qualquer que seja a largura dele
        legend.append(
            f'<circle cx="{round(lx+5,1)}" cy="{bar_y + 24}" r="4.5" fill="{col}"/>'
            f'<text x="{round(lx+18,1)}" y="{bar_y + 28}" fill="{BRIGHT}" font-size="12" '
            f'font-family="{FONT}">{name} <tspan fill="{MUTED}">{pct:.1f}%</tspan></text>')
        lx += 18 + largura(f"{name} {pct:.1f}%", 12) + 26
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
