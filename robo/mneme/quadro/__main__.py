"""Serviço do quadro de evidências (sombra): `python -m mneme.quadro rodar | reproduzir --amostra 20 | resumo --dia AAAA-MM-DD`.

Lê dados só de leitura e escreve só em `MNEME_QUADRO`. Começa 20 s depois de cada minuto, quando o motor já decidiu.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from pathlib import Path

import pandas as pd

from ..config import PASTA_DADOS
from ..dados.armazem import agora_utc
from .banco import Quadro
from .coordenador import Coordenador
from .relatorio import resumo

log = logging.getLogger("mneme.quadro")
DESLOCAMENTO_S = 20


def montar() -> tuple[Coordenador, Path]:
    raiz = Path(os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado")))
    dados = raiz.parent
    pasta = Path(os.getenv("MNEME_QUADRO", str(dados / "quadro")))
    quadro = Quadro(pasta / "quadro.db")
    coord = Coordenador(raiz, quadro, os.getenv("MNEME_DIARIO", str(dados / "operacao" / "diario.db")), os.getenv("MNEME_OPERACAO", str(dados / "operacao.json")),
                        os.getenv("MNEME_MODELOS_MOTOR", str(dados / "modelos" / "motor")), os.getenv("MNEME_MODELOS", str(dados / "modelos")))
    return coord, pasta


def rodar(coord: Coordenador, pasta: Path) -> None:
    batimento = pasta / "quadro.batimento"
    coord.aquecer()
    while True:
        espera = (DESLOCAMENTO_S - time.time() % 60) % 60
        time.sleep(espera or 60)
        inicio = time.monotonic()
        try:
            r = coord.ciclo()
            r["apuradas"] = coord.apurar()
            r["ligadas"] = coord.ligar(pd.Timestamp(agora_utc()) - pd.Timedelta(hours=2))
            r["segundos"] = round(time.monotonic() - inicio, 2)
            batimento.write_text(agora_utc().isoformat(), encoding="utf-8")
            log.info(json.dumps(r, ensure_ascii=False))
        except Exception:
            log.exception("Ciclo do quadro falhou; tenta no próximo minuto.")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    p = argparse.ArgumentParser(prog="mneme.quadro")
    p.add_argument("comando", choices=["rodar", "reproduzir", "resumo"])
    p.add_argument("--amostra", type=int, default=20)
    p.add_argument("--dia", default=f"{agora_utc():%Y-%m-%d}")
    a = p.parse_args()
    coord, pasta = montar()
    if a.comando == "rodar":
        rodar(coord, pasta)
    elif a.comando == "reproduzir":
        ids = [l["id"] for l in coord.quadro.con.execute("SELECT id FROM oportunidades")]
        sorteio = random.Random(0).sample(ids, min(a.amostra, len(ids)))
        resultados = [coord.reproduzir(i) for i in sorteio]
        print(json.dumps({"sorteadas": len(sorteio), "identicas": sum(r[0] for r in resultados),
                          "diferentes": [i for i, r in zip(sorteio, resultados) if not r[0]]}, ensure_ascii=False))
    else:
        print(json.dumps(resumo(coord.quadro, a.dia), ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
