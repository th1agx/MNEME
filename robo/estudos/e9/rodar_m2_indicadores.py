"""M2-C: reação dos pares e do ouro à surpresa de indicadores americanos, só com eventos antes de 2026-02-01.

Os retornos são medidos do lado do dólar (EUR/USD e GBP/USD com o sinal trocado; ouro também, como ativo contra o dólar),
para que "mesmo sinal" signifique: surpresa positiva, dólar mais forte. Registro em estudos/e9/registro_m2.json (parte C).

    MNEME_DADOS_MERCADO=dados/mercado python estudos/e9/rodar_m2_indicadores.py dados/e9/m2_indicadores.json
"""

import json
import os
import sys

import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.dados.eventos import ArmazemEventos
from mneme.dados.resultados_macro import surpresas
from mneme.laboratorio.estudo_eventos import reacoes, resumir, volatilidade_em_torno

FIM = pd.Timestamp("2026-02-01", tz="UTC")
LADO_DO_DOLAR = {"EURUSD": -1, "GBPUSD": -1, "USDJPY": 1, "USDCAD": 1, "XAUUSD": -1}

raiz = os.getenv("MNEME_DADOS_MERCADO", "dados/mercado")
bruto = pd.DataFrame()
for r in (raiz, f"{raiz}/fluxo"):
    bruto = ArmazemEventos(r).ler("resultados_macro", "GLOBAL")
    if not bruto.empty:
        break
tabela = surpresas(bruto)
tabela = tabela[(tabela["ocorrido_em"] < FIM) & tabela["surpresa_z"].notna()].drop_duplicates("ocorrido_em")
print("eventos com surpresa antes de 2026-02-01:", len(tabela), tabela["classe"].value_counts().to_dict())
armazem, saida = ArmazemVelas(raiz), {}
for par, s in LADO_DO_DOLAR.items():
    v = armazem.ler(par, fim=FIM.to_pydatetime())
    r = reacoes(tabela, v)
    for h in (5, 15, 60):
        r[f"retorno_{h}"] = r[f"retorno_{h}"] * s
    resumo = resumir(r)
    saida[par] = {"volatilidade": volatilidade_em_torno(tabela, v), "resumo": resumo.to_dict("records")}
    print(f"\n{par}: movimento 15 min depois do evento / sem evento = {saida[par]['volatilidade']['razao']:.2f}")
    for l in resumo.itertuples():
        print(f"  {l.classe:20} {l.horizonte:>3}min n={l.eventos:3} corr={l.correlacao:+.2f} p_aj={l.p_ajustado:.2f} mesmo_sinal={l.mesmo_sinal:.0%} fortes={l.fortes} alinhado={l.retorno_fortes_alinhado_bps:+.1f}bps")
open(sys.argv[1], "w").write(json.dumps(saida, indent=1, default=str))
