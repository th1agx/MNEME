"""O contexto econômico pode vetar uma entrada, mas não escolhe a direção."""

import pandas as pd

from mneme.digitais.modalidade import ExpiracaoFixa
from mneme.motor.decisao import bloqueio_multitempo, decidir_operacao
from mneme.motor.modalidades import Estrategia


def test_evento_de_alto_impacto_veta_uma_decisao_tecnica_que_era_valida():
    estrategia = Estrategia("forex", "EURUSD", 5, 5, ExpiracaoFixa(0.85, True))
    modelo = {"tecnicas": ["teste"], "pesos": [1.0], "intercepto": 0.0, "corte": 0.01,
              "evidencia": {"operacoes": 300, "acerto": 0.60}}

    decisao = decidir_operacao(estrategia, modelo, pd.Series({"teste": 1}), pd.Timestamp("2026-11-18T13:00:00Z"), 200,
                               bloqueios=("calendário: CPI US em 20 min",))

    assert decisao is not None
    assert not decisao.operar
    assert "calendário: CPI US em 20 min" in decisao.motivos_contra


def test_timeframe_maior_precisa_confirmar_a_direcao_da_entrada():
    assert bloqueio_multitempo(1, {"direcao": 1}, "15m") is None
    assert bloqueio_multitempo(1, None, "15m") == "15m: sem confluência suficiente"
    assert bloqueio_multitempo(1, {"direcao": -1}, "15m") == "15m: direção contrária"
