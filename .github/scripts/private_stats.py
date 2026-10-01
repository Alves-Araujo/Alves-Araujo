#!/usr/bin/env python3
"""Grava .github/private-stats.json com os numeros dos repositorios privados.

Rode na sua maquina, nao no workflow:

    python3 .github/scripts/private_stats.py

Ele usa o token que o `gh` ja tem autenticado, entao nenhuma credencial nova e
criada e nada e guardado na nuvem. O arquivo gerado tem so dois inteiros
agregados -- quantos repositorios privados e quantas contribuicoes vieram
deles -- que e exatamente a informacao que o card ja exibe. Nenhum nome de
repositorio, nenhum commit, nenhum conteudo.

O card (stats_card.py) le esse arquivo quando roda sem token, que e o caso do
workflow diario. Assim os numeros publicos continuam se atualizando sozinhos e
os privados vem daqui, sem precisar guardar um token em segredo de repositorio.

A contagem de contribuicoes privadas exige o escopo read:user. Se faltar, o
script grava so o numero de repositorios e avisa.
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "..", "private-stats.json")


def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("METRICS_TOKEN")
    if t:
        return t
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:                                  # noqa: BLE001
        sys.exit("nao achei um token: rode `gh auth login` antes")


def api(caminho, tok):
    r = subprocess.run(["curl", "-sL", "--max-time", "40",
                        f"https://api.github.com{caminho}",
                        "-H", f"Authorization: Bearer {tok}"],
                       capture_output=True, text=True, check=True).stdout
    return json.loads(r)


def graphql(consulta, tok):
    r = subprocess.run(["curl", "-s", "--max-time", "40",
                        "https://api.github.com/graphql",
                        "-H", f"Authorization: Bearer {tok}",
                        "-H", "Content-Type: application/json",
                        "-d", json.dumps({"query": consulta})],
                       capture_output=True, text=True, check=True).stdout
    return json.loads(r)


def main():
    tok = token()

    usuario = api("/user", tok).get("login", "")
    privados, pagina = 0, 1
    while True:
        lote = api(f"/user/repos?affiliation=owner&visibility=private"
                   f"&per_page=100&page={pagina}", tok)
        if not isinstance(lote, list):
            sys.exit(f"a API nao devolveu a lista de repositorios: {lote}")
        privados += sum(1 for r in lote
                        if not r.get("fork") and r["name"].lower() != usuario.lower())
        if len(lote) < 100:
            break
        pagina += 1

    dados = {"repos": privados}

    d = graphql("{ viewer { contributionsCollection "
                "{ restrictedContributionsCount } } }", tok)
    n = (d.get("data") or {}).get("viewer", {}) \
        .get("contributionsCollection", {}).get("restrictedContributionsCount")
    if isinstance(n, int) and n > 0:
        dados["contribuicoes"] = n
    else:
        print("aviso: nao consegui contar as contribuicoes privadas.\n"
              "       Para incluir esse numero, rode uma vez:\n"
              "         gh auth refresh -h github.com -s read:user\n"
              "       e rode este script de novo.", file=sys.stderr)

    with open(SAIDA, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(f"{os.path.normpath(SAIDA)} | {json.dumps(dados)}")


if __name__ == "__main__":
    main()
