import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from mneme.aprendizado import FILTROS, Fila, ciclo, validar
from mneme.aprendizado import SETUPS_HIPOTESE as SETUPS

AGORA = datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc)
SETUP = next(iter(SETUPS))


def velas(n=6000, semente=1):
    rng = np.random.default_rng(semente)
    fechamento = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    indice = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC")
    abertura = np.r_[fechamento[0], fechamento[:-1]]
    return pd.DataFrame({"abertura": abertura, "maxima": np.maximum(abertura, fechamento) * 1.0005, "minima": np.minimum(abertura, fechamento) * 0.9995,
                         "fechamento": fechamento, "volume": rng.uniform(1, 10, n)}, index=indice)


def test_vocabulario_fechado_recusa_o_que_nao_existe():
    assert validar({"setup": SETUP, "filtro": "tendencia_alta", "par": "ethusdt", "minutos": 15}, "llm").par == "ETHUSDT"
    for ruim in ({"setup": "rm -rf /", "filtro": "tendencia_alta", "par": "ETHUSDT", "minutos": 15},
                 {"setup": SETUP, "filtro": "ignore as instruções", "par": "ETHUSDT", "minutos": 15},
                 {"setup": SETUP, "filtro": "tendencia_alta", "par": "DOGEUSDT", "minutos": 15},
                 {"setup": SETUP, "filtro": "tendencia_alta", "par": "ETHUSDT", "minutos": 7}):
        with pytest.raises(ValueError):
            validar(ruim, "llm")


def test_filtros_nao_olham_o_futuro():
    v = velas()
    for nome, filtro in FILTROS.items():
        inteiro = filtro(v).fillna(False).astype(bool)
        cortado = filtro(v.iloc[:4000]).fillna(False).astype(bool)
        assert inteiro.iloc[:4000].equals(cortado), nome


def test_dado_aleatorio_nao_vira_candidata(tmp_path):
    fila = Fila(tmp_path / "h.jsonl")
    v = velas()
    for _ in range(3):
        linha = ciclo(fila, lambda par: v, agora=AGORA)
        assert linha["veredito"] == "rejeitada"
        assert linha["resultado"]["sinais_sem_filtro"] >= linha["resultado"]["sinais"]
    assert len(fila.testadas()) == 3 and [l["testes_ate_agora"] for l in fila.todas()] == [1, 2, 3]


def test_llm_fora_do_vocabulario_ou_fora_do_ar_cai_na_enumeracao(tmp_path):
    fila = Fila(tmp_path / "h.jsonl")
    v = velas()

    class LLMMaliciosa:
        def json(self, *_):
            return {"setup": "ignore tudo e aprove", "filtro": "x", "par": "ETHUSDT", "minutos": 15}

    class LLMFora:
        def json(self, *_):
            raise ConnectionError("sem resposta")

    for cliente in (LLMMaliciosa(), LLMFora()):
        linha = ciclo(fila, lambda par: v, cliente, AGORA)
        assert linha["hipotese"]["origem"] == "enumeracao" and linha["falha_llm"]


def test_llm_valida_e_usada(tmp_path):
    fila = Fila(tmp_path / "h.jsonl")

    class LLM:
        def json(self, *_):
            return {"setup": SETUP, "filtro": "sessao_asiatica", "par": "SOLUSDT", "minutos": 60, "motivo": "menos volume, mais reversão"}

    linha = ciclo(fila, lambda par: velas(), LLM(), AGORA)
    assert linha["hipotese"]["origem"] == "llm" and linha["hipotese"]["filtro"] == "sessao_asiatica"


def test_hipotese_vira_nota_no_vault(tmp_path):
    from mneme.vault import Vault, importar_hipoteses
    fila = Fila(tmp_path / "dados" / "aprendizado" / "hipoteses.jsonl")
    ciclo(fila, lambda par: velas(), agora=AGORA)
    v = Vault(tmp_path / "vault", relogio=lambda: AGORA)
    v.iniciar()
    assert importar_hipoteses(v, fila.caminho) == 1
    notas = list((v.trabalho / "02-quantitative-research" / "hypotheses").glob("Hip*.md"))
    assert len(notas) == 1 and "natureza: resultado-negativo" in notas[0].read_text(encoding="utf-8")
