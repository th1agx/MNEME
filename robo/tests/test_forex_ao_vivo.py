"""Forex e ouro ao vivo: só velas fechadas, horário de mercado respeitado, origem marcada e nenhuma rede nos testes."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.dados.forex_ao_vivo import ColetorForex, ouro_aberto, velas_yahoo

AGORA = datetime(2026, 11, 17, 14, 7, 20, tzinfo=timezone.utc)  # terça, mercado aberto


def resposta_yahoo(inicio: datetime, n: int, buraco: int | None = None) -> dict:
    ts = [int((inicio + timedelta(minutes=i)).timestamp()) for i in range(n)]
    preco = [1.10 + i * 1e-4 for i in range(n)]
    fecha = [None if i == buraco else p + 5e-5 for i, p in enumerate(preco)]
    return {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"open": preco, "high": [p + 1e-4 for p in preco],
                                                                               "low": [p - 1e-4 for p in preco], "close": fecha, "volume": [0] * n}]}}]}}


def test_yahoo_so_entra_vela_fechada_e_sem_buraco():
    inicio = AGORA.replace(second=0) - timedelta(minutes=5)
    v = velas_yahoo(resposta_yahoo(inicio, 6, buraco=2), AGORA)
    # 6 velas: a das 14:07 ainda está aberta e a do buraco não tem fechamento.
    assert list(v["abertura_em"].dt.strftime("%H:%M")) == ["14:02", "14:03", "14:05", "14:06"]
    assert (v["origem"] == "yahoo").all() and (v["recebido_em"] == pd.Timestamp(AGORA)).all()


def test_ouro_respeita_o_horario_do_mercado():
    assert ouro_aberto(datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc))
    assert not ouro_aberto(datetime(2026, 11, 17, 22, 30, tzinfo=timezone.utc))  # pausa diária
    assert not ouro_aberto(datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))  # sábado
    assert not ouro_aberto(datetime(2026, 11, 15, 22, 30, tzinfo=timezone.utc))  # domingo antes da abertura
    assert ouro_aberto(datetime(2026, 11, 15, 23, 30, tzinfo=timezone.utc))
    assert not ouro_aberto(datetime(2026, 11, 20, 22, 30, tzinfo=timezone.utc))  # sexta depois do fechamento


class BinanceFalsa:
    def recentes(self, par, desde, agora):
        t = pd.date_range(pd.Timestamp(desde).floor("min"), pd.Timestamp(agora).floor("min") - pd.Timedelta(minutes=1), freq="min")
        return pd.DataFrame({"abertura_em": t, "abertura": 4000.0, "maxima": 4001.0, "minima": 3999.0, "fechamento": 4000.5, "volume": 2.0,
                             "volume_cotacao": 8000.0, "volume_comprador": 1.0, "negocios": 3, "recebido_em": pd.Timestamp(agora), "origem": "binance"})


def test_ciclo_grava_moedas_e_ouro_com_origem(tmp_path):
    inicio = AGORA.replace(second=0) - timedelta(minutes=10)

    def responder(pedido: httpx.Request) -> httpx.Response:
        assert "query1.finance.yahoo.com" in str(pedido.url) and "interval=1m" in str(pedido.url)
        return httpx.Response(200, json=resposta_yahoo(inicio, 11))

    armazem = ArmazemVelas(tmp_path)
    c = ColetorForex(armazem, httpx.Client(transport=httpx.MockTransport(responder)), BinanceFalsa(), relogio=lambda: AGORA, pasta=tmp_path)
    resumo = c.ciclo()
    assert resumo["EURUSD"] == 10 and resumo["USDCAD"] == 10 and resumo["XAUUSD"] > 0
    ouro = armazem.ler("XAUUSD")
    assert (ouro["origem"] == "binance:PAXGUSDT").all()
    assert c.ciclo()["EURUSD"] == 0  # a mesma vela não entra duas vezes
    assert json.loads((tmp_path / "forex.batimento").read_text())["quando"]


def test_falha_de_uma_fonte_nao_derruba_as_outras(tmp_path):
    def responder(pedido: httpx.Request) -> httpx.Response:
        if "USDJPY" in str(pedido.url):
            return httpx.Response(500)
        return httpx.Response(200, json=resposta_yahoo(AGORA.replace(second=0) - timedelta(minutes=3), 4))

    c = ColetorForex(ArmazemVelas(tmp_path), httpx.Client(transport=httpx.MockTransport(responder)), BinanceFalsa(), relogio=lambda: AGORA, pasta=tmp_path)
    resumo = c.ciclo()
    assert resumo["USDJPY"].startswith("falhou") and resumo["EURUSD"] == 3


def test_mercado_fechado_ainda_bate_o_coracao(tmp_path):
    sabado = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    vazio = {"chart": {"result": [{"timestamp": [], "indicators": {"quote": [{"open": [], "high": [], "low": [], "close": [], "volume": []}]}}]}}
    c = ColetorForex(ArmazemVelas(tmp_path / "nova"), httpx.Client(transport=httpx.MockTransport(lambda p: httpx.Response(200, json=vazio))),
                     BinanceFalsa(), relogio=lambda: sabado)
    assert c.ciclo() == {"EURUSD": 0, "GBPUSD": 0, "USDJPY": 0, "USDCAD": 0, "XAUUSD": 0}
    assert (tmp_path / "nova" / "forex.batimento").exists()
