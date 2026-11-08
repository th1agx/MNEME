import itertools
import json
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from mneme.motor.diario import Diario
from mneme.motor.modalidades import carregar_configuracao
from mneme.motor.risco import avaliar
from mneme.quadro.esquema import Restricao, aplicar_restricoes
from mneme.quadro.especialistas import estado_no_momento
from mneme.quadro.fontes import DiarioSoLeitura
from quadro_dados import AGORA, montar
from test_quadro_especialistas import analisar, por

M = pd.Timestamp(AGORA)


def restricoes(tmp_path, **k):
    coord, dados, _ = montar(tmp_path, **k)
    return analisar(coord)[2], dados


def test_estado_limpo_so_tem_teto(tmp_path):
    res, _ = restricoes(tmp_path)
    assert [(r.regra, r.efeito, r.limite) for r in res] == [("tamanho_maximo", "teto", "1.0")]


def test_vetos_batem_com_o_avaliar_do_motor(tmp_path):
    coord, dados, _ = montar(tmp_path)
    (dados / "PARAR").write_text("")
    _, _, res, _ = analisar(coord)
    config = carregar_configuracao(dados / "operacao.json")
    with DiarioSoLeitura(dados / "operacao" / "diario.db") as d:
        estado = estado_no_momento(d, config.estrategias[0].nome, M, config.banca, True)
    _, motivos = avaliar("x", estado, config.limites, config.risco_por_operacao)
    assert {r.valor_atual for r in res if r.efeito == "veto"} == set(motivos) and "kill switch ligado" in motivos
    assert all(r.efeito == "veto" for r in res)


def test_travas_da_modalidade_viram_veto(tmp_path):
    res, _ = restricoes(tmp_path, estrategias=(("com_stop", 5, 60),))
    # O modelo de teste compra; com_stop à vista compra, então só a expectativa decide.
    assert all(r.efeito in ("veto", "teto") for r in res)
    coord, dados, _ = montar(tmp_path / "b")
    modelo = dados / "modelos" / "motor" / "ETHUSDT_expiracao_fixa_5m_5m.json"
    m = json.loads(modelo.read_text())
    m["evidencia"] = {"operacoes": 10, "acerto": 0.4}
    modelo.write_text(json.dumps(m))
    regras = {r.regra for r in analisar(coord)[2]}
    assert {"evidencia_curta", "expectativa_nao_positiva_nesta_modalidade"} <= regras


def test_estado_no_momento_nao_conta_a_propria_decisao(tmp_path):
    """O motor grava a decisão uns segundos depois do momento: ela não pode aparecer como operação aberta ou repetida."""
    coord, dados, _ = montar(tmp_path)
    d = Diario(dados / "operacao" / "diario.db")
    nome = "ETHUSDT|expiracao_fixa|5m|5m"
    d.registrar(chave=f"{nome}|{(M - pd.Timedelta(minutes=1)).isoformat()}", estrategia=nome, mercado="cripto", ativo="ETHUSDT", modalidade="expiracao_fixa",
                vela=M - pd.Timedelta(minutes=1), decidido_em=M + pd.Timedelta(seconds=5), latencia_s=5, direcao=1, forca=0.1, expectativa=0.1, evidencia={},
                motivo="m", motivos_recusa=(), contexto=(), sinal={}, tipo="operada", tamanho=1.0)
    _, _, res, _ = analisar(coord)
    assert [r.regra for r in res] == ["tamanho_maximo"]


@pytest.mark.parametrize("semente", range(200))
def test_nenhum_consolidador_passa_por_cima_do_risco(semente):
    """Propriedade: qualquer proposta, com quaisquer restrições, sai sem operar se houver veto e nunca acima do teto."""
    g = np.random.default_rng(semente)
    restr = []
    for i in range(int(g.integers(0, 4))):
        efeito = g.choice(["veto", "teto"])
        restr.append(Restricao("op", g.choice(["A", "B", "*"]), f"r{i}", efeito, "x", str(round(float(g.uniform(0.1, 2)), 3)), "c", M, M + pd.Timedelta(minutes=5)))
    proposta = {"modalidade": g.choice(["A", "B"]), "operar": bool(g.integers(0, 2)), "tamanho": float(g.uniform(0, 10))}
    saida = aplicar_restricoes(proposta, restr)
    da_modalidade = [r for r in restr if r.modalidade in (proposta["modalidade"], "*")]
    if any(r.efeito == "veto" for r in da_modalidade):
        assert saida["operar"] is False and saida["tamanho"] == 0
    for r in da_modalidade:
        if r.efeito == "teto":
            assert saida["tamanho"] <= float(r.limite)
    assert saida["tamanho"] <= proposta["tamanho"]
