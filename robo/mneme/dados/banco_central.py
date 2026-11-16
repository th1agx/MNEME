"""Banco Central do Brasil: dólar PTAX e a última decisão do Copom, pelas APIs abertas do BC (sem cadastro e sem custo).

- PTAX de venda: série 1 do SGS, um valor por dia útil, publicado no fim da tarde.
- Copom: o título do último comunicado e a data da reunião. A API não traz a hora da publicação; por isso o comunicado
  entra só como contexto do relatório da manhã, nunca como notícia com horário (não se inventa hora).

Texto do BC é dado, nunca instrução: o título é limpo e cortado antes de ir para qualquer lugar.
"""

from __future__ import annotations

import re
from datetime import date, datetime

import httpx

URL_PTAX = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados/ultimos/2?formato=json"
URL_COPOM = "https://www.bcb.gov.br/api/servico/sitebcb/copom/comunicados?quantidade=1"
AGENTE = {"user-agent": "MNEME-macro/0.1"}


def ler_ptax(dados: list[dict]) -> dict | None:
    """Os dois últimos valores da série viram {data, valor, variacao_pct}. Sem dois valores válidos, não há PTAX."""
    pontos = []
    for p in dados[-2:]:
        try:
            pontos.append((datetime.strptime(str(p["data"]), "%d/%m/%Y").date(), float(str(p["valor"]).replace(",", "."))))
        except (KeyError, ValueError):
            return None
    if len(pontos) < 2 or pontos[-1][1] <= 0 or pontos[-2][1] <= 0:
        return None
    (_, antes), (dia, valor) = pontos
    return {"data": dia.isoformat(), "valor": valor, "variacao_pct": (valor / antes - 1) * 100}


def ler_copom(dados: dict) -> dict | None:
    try:
        c = dados["conteudo"][0]
        dia = date.fromisoformat(str(c["dataReferencia"])[:10])
        reuniao = int(c["nro_reuniao"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    titulo = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f<>\[\]`|]", " ", str(c.get("titulo", "")))).strip()[:160]
    return {"reuniao": reuniao, "data": dia.isoformat(), "titulo": titulo} if titulo else None


class BancoCentral:
    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente or httpx.Client(timeout=15, headers=AGENTE, follow_redirects=True)

    def ptax(self) -> dict | None:
        return ler_ptax(self.cliente.get(URL_PTAX).raise_for_status().json())

    def copom(self) -> dict | None:
        return ler_copom(self.cliente.get(URL_COPOM).raise_for_status().json())
