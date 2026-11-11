"""Motor 02 (opções digitais) pela linha de comando.

    python -m mneme.digitais modelo [--saida planilha.csv]   # planilha para anotar as operações da demo
    python -m mneme.digitais importar planilha.csv            # importa, valida e grava (não duplica)
    python -m mneme.digitais conciliar                        # compara com o preço de referência
    python -m mneme.digitais placar                           # resultados por nível de fidelidade e regras observadas
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..config import PASTA_DADOS
from . import banco


def main() -> None:
    p = argparse.ArgumentParser(prog="mneme.digitais")
    p.add_argument("acao", choices=["modelo", "importar", "conciliar", "placar"])
    p.add_argument("csv", nargs="?")
    p.add_argument("--saida", default="operacoes_demo.csv")
    p.add_argument("--banco", default=str(PASTA_DADOS / "digitais" / "digitais.db"))
    p.add_argument("--raiz", default=os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    p.add_argument("--diario", default=str(PASTA_DADOS / "operacao" / "diario.db"))
    a = p.parse_args()
    if a.acao == "modelo":
        from .captura import modelo_csv
        print(f"Planilha criada: {modelo_csv(a.saida)}")
        return
    con = banco.abrir(a.banco)
    if a.acao == "importar":
        if not a.csv:
            p.error("informe o arquivo CSV")
        from .captura import importar
        r = importar(con, a.csv)
        print(f"{r.novas} nova(s), {r.repetidas} já importada(s).")
        for erro in r.erros:
            print("  recusada:", erro)
    elif a.acao == "conciliar":
        from ..dados.armazem import ArmazemVelas
        from .conciliacao import conciliar
        armazem = ArmazemVelas(a.raiz)
        print(json.dumps(conciliar(con, lambda serie, inicio, fim: armazem.ler(serie, inicio, fim)), ensure_ascii=False))
    else:
        from .placar import placar
        print(json.dumps(placar(con, a.diario), ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
