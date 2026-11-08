"""A0: a régua do E9 é travada. Mudar um critério exige versão nova, e quem avalia confere a versão registrada."""

import dataclasses

import pytest

from mneme.e9.regua import REGUAS, ReguaDiferente, amostra_minima, conferir, empate, holm, n_necessario


def test_v1_esta_travada():
    """A impressão da v1 está fixada aqui: qualquer mudança nela quebra este teste e precisa virar v2."""
    assert REGUAS["v1"].impressao() == "415b267c1275"


def test_regua_nao_muda_em_tempo_de_execucao():
    with pytest.raises(dataclasses.FrozenInstanceError):
        REGUAS["v1"].alfa = 0.5


def test_quem_avalia_recusa_regua_diferente_da_registrada():
    v1 = REGUAS["v1"]
    conferir(v1.impressao(), v1)
    outra = dataclasses.replace(v1, alfa=0.10)
    with pytest.raises(ReguaDiferente):
        conferir(v1.impressao(), outra)


def test_empate_e_amostra_batem_com_a_skill_de_poder():
    assert empate(0.85) == pytest.approx(0.5405, abs=1e-4)
    assert n_necessario(0.58, empate(0.85), 0.05, 0.8) == pytest.approx(978, abs=2)
    assert n_necessario(0.56, empate(0.85), 0.05, 0.8) == pytest.approx(4044, abs=5)


def test_amostra_minima_cresce_com_a_familia_e_com_o_poder_de_promocao():
    v1 = REGUAS["v1"]
    sozinha = amostra_minima(v1, 0.85, familia=1)
    familia = amostra_minima(v1, 0.85, familia=20)
    promocao = amostra_minima(v1, 0.85, familia=20, promocao=True)
    assert sozinha < familia < promocao


def test_holm_corrige_e_mantem_a_ordem():
    ajustados = holm([0.01, 0.04, 0.03, 0.5])
    assert ajustados == pytest.approx([0.04, 0.09, 0.09, 0.5])
    assert all(a >= p for a, p in zip(ajustados, [0.01, 0.04, 0.03, 0.5]))
