from __future__ import annotations

import argparse
import json
import os

from ...config import PASTA_DADOS
from .arquivo import Arquivo


def main() -> None:
    p = argparse.ArgumentParser(prog="mneme.core.pesquisa")
    p.add_argument("acao", choices=["ciclo", "listar"])
    p.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    p.add_argument("--arquivo", default=str(PASTA_DADOS / "aprendizado" / "geradas.jsonl"))
    p.add_argument("--sandbox", choices=["docker", "local"], default="docker", help="local só para desenvolvimento: sem isolamento")
    a = p.parse_args()
    arquivo = Arquivo(a.arquivo)
    if a.acao == "listar":
        for l in arquivo.todas():
            r = l.get("resultado") or {}
            medida = f"{r['sinais']} sinais · acerto {r['acerto']:.2%} · placebo {r['placebo']:.2%}" if r.get("sinais") else (l.get("motivo_falha") or "")
            print(f"{l['veredito']:>10} · {l['fase']:>11} · {l['braco']['par']} {l['braco']['minutos']} min · {l['ideia'][:60]} · {medida}")
        return
    from ...dados.armazem import ArmazemVelas
    from .ciclo import ciclo
    from .llm import Roteador
    from .sandbox import SandboxDocker, SandboxLocal

    linha = ciclo(arquivo, ArmazemVelas(a.raiz).ler, Roteador(), SandboxDocker() if a.sandbox == "docker" else SandboxLocal())
    print(json.dumps({k: linha.get(k) for k in ("fase", "braco", "fonte", "ideia", "veredito", "etapa_falha", "motivo_falha", "p", "commit")}
                     | {"acerto": (linha.get("resultado") or {}).get("acerto"), "sinais": (linha.get("resultado") or {}).get("sinais")},
                     ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
