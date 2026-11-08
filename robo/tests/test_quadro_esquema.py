import pandas as pd
import pytest

from mneme.quadro.esquema import ErroEsquema, Evidencia, Instrumento, Oportunidade, impressao

M = pd.Timestamp("2026-11-07 12:00", tz="UTC")


def ev(**k):
    base = dict(oportunidade="op", especialista="quant", versao="1", tipo_afirmacao="direcional", natureza="previsao_modelo",
                alvo_estatistico="fechamento(t+15) > abertura(t+1)", afirmacao={"direcao": 1}, criada_em=M, dados_ate=M,
                valido_ate=M + pd.Timedelta(minutes=5), origem={"modulo": "x"})
    return Evidencia(**{**base, **k})


def test_evidencia_valida_passa():
    ev().validar(M)


@pytest.mark.parametrize("mudanca, texto", [
    ({"origem": {}}, "origem"),
    ({"dados_ate": M + pd.Timedelta(seconds=1)}, "posterior"),
    ({"valido_ate": M}, "vencida"),
    ({"tipo_afirmacao": "palpite"}, "tipo"),
    ({"natureza": "opiniao"}, "natureza"),
    ({"alvo_estatistico": ""}, "alvo"),
    ({"confianca": 0.6}, "calibração"),
    ({"confianca": 1.5, "calibracao": {"validada": True}}, "fora"),
])
def test_esquema_recusa(mudanca, texto):
    with pytest.raises(ErroEsquema, match=texto):
        ev(**mudanca).validar(M)


def test_confianca_so_com_calibracao_validada():
    ev(confianca=0.55, calibracao={"metodo": "isotonica", "validada": True}).validar(M)


def test_instrumentos_de_varios_mercados():
    assert Instrumento.do_ativo("cripto", "ETHUSDT").id == "binance:spot:ETHUSDT"
    eur = Instrumento.do_ativo("forex", "EURUSD")
    assert (eur.base, eur.cotacao, eur.sessao) == ("EUR", "USD", "forex")
    assert Instrumento.do_ativo("ouro", "XAUUSD").id == "dukascopy:spot:XAUUSD"


@pytest.mark.parametrize("op", [
    Oportunidade(("quotex:opcao_digital:EURUSD",), "vela_fechada", M, ({"tipo": "expiracao_fixa", "expiracao": 1, "payout": 0.85},), (1, 5), 1),
    Oportunidade(("binance:spot:BTCUSDT", "okx:spot:BTCUSDT"), "discrepancia", M, ({"tipo": "arbitragem", "pernas": 2},), (1,)),
    Oportunidade(("binance:spot:ETHUSDT", "binance:perpetuo:ETHUSDT"), "relogio", M, ({"tipo": "carry", "pernas": 2},), (480,)),
    Oportunidade(("jupiter:pool:abc",), "onchain", M, ({"tipo": "posicao", "stop": None},), (60,)),
    Oportunidade(("dukascopy:spot:XAUUSD",), "evento_calendario", M, ({"tipo": "posicao"},), (15, 60)),
])
def test_mesmo_esquema_para_qualquer_mercado_e_modalidade(op):
    op.validar()
    assert op.id.endswith(M.isoformat())


def test_id_e_impressao_estaveis():
    assert ev().id == ev(criada_em=M + pd.Timedelta(seconds=9), pedido={"segundos": 3}).id
    assert impressao([ev()]) == impressao([ev(criada_em=M + pd.Timedelta(seconds=9))])
    assert impressao([ev()]) != impressao([ev(afirmacao={"direcao": -1})])
