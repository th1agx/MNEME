"""Pesquisador: a LLM escreve uma estratégia nova em código, com a ideia e o mecanismo que a justificam.

Ela recebe o contrato da função, o braço escolhido pela agenda e o arquivo resumido (melhores medidas, falhas recentes e
o que já foi tentado). Textos dentro de <arquivo> são dados, não instruções.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from .llm import Roteador

SISTEMA = """Você é o pesquisador quantitativo do MNEME. Escreva UMA estratégia nova de direção para opções digitais (CALL/PUT com expiração fixa).

Contrato obrigatório do código Python:
- defina `def sinal(v):` que recebe um pandas.DataFrame de velas de 1 minuto, índice de tempo em UTC, colunas
  abertura, maxima, minima, fechamento, volume (também existem os apelidos open, high, low, close); não há outras colunas
  (nada de vwap pronto, rsi pronto etc.: calcule a partir destas);
- devolva uma pandas.Series no mesmo índice com 1 (aposta que sobe), -1 (que desce) ou 0 (nada) para cada vela;
- a decisão de cada vela usa só aquela vela já fechada e as anteriores: nunca shift negativo, nunca dados futuros;
- use só `import numpy as np`, `import pandas as pd` e `import math`; nada de arquivos, rede ou print;
- seja seletiva: poucas operações boas valem mais que muitas ruins.

A aposta entra na abertura da vela seguinte ao sinal e vale pelos minutos indicados. O payout é 85%: o empate é 54,05% de acerto.
Proponha um mecanismo de mercado plausível (microestrutura, volatilidade, sessão, reversão, momento, volume), diferente do que já foi tentado.

Responda exatamente neste formato:
IDEIA: <uma linha>
MECANISMO: <por que deveria funcionar, até 3 linhas>
```python
<o código>
```"""


@dataclass(frozen=True)
class Proposta:
    ideia: str
    mecanismo: str
    codigo: str
    fonte: str

    def como_dict(self) -> dict:
        return asdict(self)


def ler_resposta(texto: str, fonte: str) -> Proposta:
    bloco = re.search(r"```(?:python|py)?\s*\n(.*?)```", texto, re.S)
    if not bloco:
        raise ValueError("resposta sem bloco de código")
    ideia = re.search(r"IDEIA:\s*(.+)", texto)
    mecanismo = re.search(r"MECANISMO:\s*(.+?)(?:\n```|\Z)", texto, re.S)
    return Proposta((ideia.group(1).strip() if ideia else "sem descrição")[:300], (mecanismo.group(1).strip() if mecanismo else "")[:500],
                    bloco.group(1).strip(), fonte)


def propor(roteador: Roteador, resumo: dict, par: str, minutos: int) -> Proposta:
    pedido = (f"Ativo: {par}. Expiração: {minutos} minutos.\n"
              f"<arquivo>\n{json.dumps(resumo, ensure_ascii=False)}\n</arquivo>\n"
              "Escreva uma estratégia que ainda não está no arquivo. Evite repetir as falhas listadas.")
    r = roteador.texto(SISTEMA, pedido)
    return ler_resposta(r.texto, r.fonte)
