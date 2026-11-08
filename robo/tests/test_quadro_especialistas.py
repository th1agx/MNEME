from datetime import timedelta

import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.dados.eventos import ArmazemEventos
from mneme.motor.diario import Diario
from mneme.quadro.esquema import impressao
from quadro_dados import AGORA, gravar_eventos, montar, velas


def analisar(coord, usar_cache=True, agora=AGORA + timedelta(seconds=20)):
    config, fonte = coord._config()
    (mercado, ativo, candle), estrategias = next(iter(coord.grupos(config).items()))
    vela = pd.Timestamp(AGORA) - pd.Timedelta(minutes=1)
    op = coord.oportunidade(mercado, ativo, candle, vela, estrategias)
    return op, *coord.analisar(op, mercado, ativo, candle, vela, estrategias, config, fonte, usar_cache, pd.Timestamp(agora))


def por(evs, especialista, natureza=None):
    return [e for e in evs if e.especialista == especialista and (natureza is None or e.natureza == natureza)]


def test_todos_respondem_e_passam_no_esquema(tmp_path):
    coord, _, _ = montar(tmp_path)
    op, evs, res, pedidos = analisar(coord)
    assert {p["especialista"] for p in pedidos if p["situacao"] == "ok"} == {"technical", "quant", "order_flow", "market_intel", "knowledge", "risco"}
    assert all(e.dados_ate <= op.momento for e in evs)


def test_nada_do_futuro_entra(tmp_path):
    """Velas e eventos gravados depois do momento não mudam nenhuma evidência do momento."""
    coord, dados, v = montar(tmp_path)
    _, antes, res_antes, _ = analisar(coord, usar_cache=False)
    futuro = velas(n=len(v) + 120)
    ArmazemVelas(dados / "mercado").gravar("ETHUSDT", futuro, AGORA + timedelta(hours=3))
    gravar_eventos(ArmazemEventos(dados / "mercado"), "ETHUSDT", ate=AGORA + timedelta(hours=3))  # tudo chega depois do momento
    d = Diario(dados / "operacao" / "diario.db")
    d.gravar_contexto("n-futura", "ETH", "noticia", {"sentimento": -1, "titulo": "futura"}, "llm:x", pd.Timestamp(AGORA) + pd.Timedelta(minutes=10),
                      pd.Timestamp(AGORA) + pd.Timedelta(hours=6))
    _, depois, res_depois, _ = analisar(coord, usar_cache=False)
    assert impressao(antes, res_antes) == impressao(depois, res_depois)


def test_quant_separa_escore_previsao_bruta_e_calibrada(tmp_path):
    coord, _, _ = montar(tmp_path)
    _, evs, _, _ = analisar(coord)
    escore = por(evs, "quant", "escore_modelo")
    assert len(escore) == 1 and escore[0].calibracao["metodo"] == "nao_calibrada" and escore[0].confianca is None
    assert escore[0].desempenho_medido["periodo"] == "desenvolvimento"
    previsoes = {e.afirmacao["versao_prob"]: e for e in por(evs, "quant", "previsao_modelo")}
    assert set(previsoes) == {"bruta", "calibrada_no_treino"}
    assert previsoes["bruta"].afirmacao["prob_sobe"] == 0.58 and previsoes["calibrada_no_treino"].afirmacao["prob_sobe"] == 0.52
    # Calibrada no treino não vira confiança: falta validar ao vivo.
    assert previsoes["calibrada_no_treino"].confianca is None and previsoes["calibrada_no_treino"].calibracao["validada"] is False
    assert all("abertura(t+1min)" in e.alvo_estatistico for e in escore + list(previsoes.values()))


def test_previsao_que_chega_tarde_demais_fica_de_fora(tmp_path):
    coord, dados, _ = montar(tmp_path, com_eventos=False)
    vela = AGORA - timedelta(minutes=1)
    ArmazemEventos(dados / "mercado").gravar("previsoes", "ETHUSDT", [{"modelo": "m", "horizonte": 15, "ocorrido_em": vela, "recebido_em": AGORA + timedelta(seconds=40),
                                                                       "prob_sobe_bruta": 0.6, "prob_sobe": 0.55, "direcao": 1}])
    _, evs, _, _ = analisar(coord)
    assert por(evs, "quant", "previsao_modelo") == []


def test_fluxo_mede_agressao_e_registra_falta_de_dado(tmp_path):
    coord, _, _ = montar(tmp_path)
    fluxo = por(analisar(coord)[1], "order_flow")[0]
    assert fluxo.afirmacao["negocios"] > 0 and -1 <= fluxo.afirmacao["agressao"] <= 1 and "desequilibrio_5" in fluxo.afirmacao
    vazio, _, _ = montar(tmp_path / "b", com_eventos=False)
    assert por(analisar(vazio)[1], "order_flow")[0].afirmacao["sem_dado"] == ["trades"]


def test_agenda_usa_hora_de_chegada(tmp_path):
    coord, _, _ = montar(tmp_path)
    evento = [e for e in por(analisar(coord)[1], "market_intel") if e.tipo_afirmacao == "evento"][0]
    assert [x["nome"] for x in evento.afirmacao["eventos"]] == ["CPI"] and evento.afirmacao["alto_impacto"]


def test_cache_da_o_mesmo_que_ler_do_zero(tmp_path):
    coord, _, _ = montar(tmp_path)
    _, com_cache, r1, _ = analisar(coord, usar_cache=True)
    _, sem_cache, r2, _ = analisar(coord, usar_cache=False)
    assert impressao(com_cache, r1) == impressao(sem_cache, r2)


def test_varios_mercados_e_modalidades_no_mesmo_ciclo(tmp_path):
    coord, _, _ = montar(tmp_path, estrategias=(("expiracao_fixa", 5, 5), ("expiracao_fixa", 5, 15), ("com_stop", 5, 60)))
    op, evs, res, _ = analisar(coord)
    assert len(op.modalidades) == 3 and len(por(evs, "quant", "escore_modelo")) == 3 and len(por(evs, "risco")) == 3
