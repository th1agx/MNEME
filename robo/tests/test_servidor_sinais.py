"""Servidor de sinais: lê o diário só para leitura, mostra só o cenário escolhido e guarda o "entrei" da pessoa."""

import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pandas as pd
import pytest

from mneme.digitais.servidor_sinais import Servidor, criar_servidor
from mneme.motor.diario import Diario

CHAVE = "k" * 32
AGORA = pd.Timestamp("2026-11-16T14:03:00Z")


def registrar(d: Diario, estrategia: str, vela: pd.Timestamp, acao: str = "CALL") -> str:
    chave = f"{estrategia}|{vela.isoformat()}"
    d.registrar(chave=chave, estrategia=estrategia, mercado="cripto", ativo=estrategia.split("|")[0], modalidade="expiracao_fixa", vela=vela,
                decidido_em=vela + pd.Timedelta(minutes=5, seconds=5), latencia_s=5.0, direcao=1 if acao == "CALL" else -1, forca=0.1,
                expectativa=0.02, evidencia={}, motivo="", motivos_recusa=(), contexto=(),
                sinal={"acao": acao, "entrada_em": (vela + pd.Timedelta(minutes=6)).isoformat(), "expiracao_min": 5, "preco_referencia": 3100.0},
                tipo="operada", tamanho=1.0)
    return chave


@pytest.fixture
def ambiente(tmp_path):
    d = Diario(tmp_path / "diario.db")
    cenario = tmp_path / "cenario.json"
    cenario.write_text(json.dumps({"estrategias": ["ETHUSDT|expiracao_fixa|5m|5m"], "cenario": "ETH 5 min"}))
    s = Servidor(tmp_path / "diario.db", cenario, tmp_path / "entradas.db", CHAVE, relogio=lambda: AGORA)
    http = criar_servidor(s, "127.0.0.1", 0)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield d, s, f"http://127.0.0.1:{http.server_address[1]}", tmp_path
    http.shutdown()


def pedir(url, chave=CHAVE, corpo=None):
    req = urllib.request.Request(url, data=None if corpo is None else json.dumps(corpo).encode(), headers={"x-mneme-chave": chave, "content-type": "application/json"},
                                 method="GET" if corpo is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_so_o_cenario_escolhido_e_so_com_a_chave(ambiente):
    d, _, base, _ = ambiente
    eth = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T13:55:00Z"))
    registrar(d, "SOLUSDT|expiracao_fixa|1m|5m", pd.Timestamp("2026-11-16T13:55:00Z"), "PUT")
    registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T12:00:00Z"))  # velho demais
    assert pedir(f"{base}/api/sinais", chave="x" * 32)[0] == 401
    status, r = pedir(f"{base}/api/sinais")
    assert status == 200 and r["agora"].startswith("2026-11-16T14:03")
    assert [s["id"] for s in r["sinais"]] == [eth]
    assert r["sinais"][0] | {} == {"id": eth, "ativo": "ETHUSDT", "direcao": "CALL", "expiracao_min": 5, "entrada_em": "2026-11-16T14:01:00+00:00",
                                   "decidido_em": "2026-11-16T14:00:05+00:00", "estrategia": "ETHUSDT|expiracao_fixa|5m|5m", "cenario": "ETH 5 min",
                                   "preco_referencia": 3100.0, "resultado": None}


def test_resultado_aparece_quando_o_motor_apura(ambiente):
    d, _, base, _ = ambiente
    eth = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T13:55:00Z"))
    d.encerrar(eth, {"resultado": "perda", "pnl": -1.0, "preco_entrada": 3100.0, "preco_saida": 3090.0, "encerrado_por": "expiracao"}, AGORA)
    assert pedir(f"{base}/api/sinais")[1]["sinais"][0]["resultado"] == "perda"


def test_placar_do_dia_e_ultimo_sinal(ambiente):
    """O card mostra o último sinal (mesmo fora da janela) e o placar desde a meia-noite de Brasília."""
    d, _, base, _ = ambiente
    ontem = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T02:00:00Z"))  # 23h de ontem em Brasília
    cedo = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T09:00:00Z"), "PUT")
    tarde = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T12:00:00Z"))
    registrar(d, "SOLUSDT|expiracao_fixa|1m|5m", pd.Timestamp("2026-11-16T13:00:00Z"))  # fora do cenário
    fim = {"pnl": 0.0, "preco_entrada": 1.0, "preco_saida": 1.0, "encerrado_por": "expiracao"}
    d.encerrar(ontem, {**fim, "resultado": "ganho"}, AGORA)
    d.encerrar(cedo, {**fim, "resultado": "perda"}, AGORA)
    d.encerrar(tarde, {**fim, "resultado": "ganho"}, AGORA)
    r = pedir(f"{base}/api/sinais")[1]
    assert r["sinais"] == []
    assert r["dia"] == {"sinais": 2, "ganhos": 1, "perdas": 1, "abertos": 0}
    assert r["ultimo"]["id"] == tarde and r["ultimo"]["direcao"] == "CALL" and r["ultimo"]["resultado"] == "ganho"


def test_sem_sinais_o_dia_fica_zerado(ambiente):
    r = pedir(f"{ambiente[2]}/api/sinais")[1]
    assert r["dia"] == {"sinais": 0, "ganhos": 0, "perdas": 0, "abertos": 0} and r["ultimo"] is None


def test_guarda_o_entrei_e_recusa_o_que_nao_e_valido(ambiente):
    d, _, base, pasta = ambiente
    eth = registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T13:55:00Z"))
    assert pedir(f"{base}/api/sinais/entrada", corpo={"sinal_id": eth, "entrou": True, "payout": 0.88, "corretora": "quotex"})[0] == 200
    assert pedir(f"{base}/api/sinais/entrada", corpo={"sinal_id": eth, "entrou": True, "payout": 88})[0] == 400  # payout é fração
    assert pedir(f"{base}/api/sinais/entrada", corpo={"sinal_id": "nao-existe", "entrou": True, "payout": 0.8})[0] == 404
    assert pedir(f"{base}/api/sinais/entrada", chave="x" * 32, corpo={"sinal_id": eth, "entrou": False})[0] == 401
    linhas = sqlite3.connect(pasta / "entradas.db").execute("SELECT sinal_id, entrou, payout, corretora FROM entradas").fetchall()
    assert linhas == [(eth, 1, 0.88, "quotex")]


def test_nao_escreve_no_diario(ambiente):
    d, _, base, pasta = ambiente
    registrar(d, "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp("2026-11-16T13:55:00Z"))
    d.con.commit()
    antes = (pasta / "diario.db").read_bytes()
    pedir(f"{base}/api/sinais")
    assert (pasta / "diario.db").read_bytes() == antes


def test_caminho_desconhecido_e_404(ambiente):
    _, _, base, _ = ambiente
    assert pedir(f"{base}/api/outra")[0] == 404


def test_leitura_do_grafico_pelo_servidor(tmp_path):
    import sys
    from pathlib import Path

    from mneme.dados.armazem import ArmazemVelas
    from mneme.laboratorio.confluencia import grade_de_sinais
    sys.path.insert(0, str(Path(__file__).parent))
    from test_e9_mapa import mercado

    v = mercado(n=6000)
    v.index = v.index + (pd.Timestamp("2026-11-10", tz="UTC") - v.index[0])
    tabela = v.reset_index(names="abertura_em").assign(recebido_em=lambda d: d["abertura_em"] + pd.Timedelta(minutes=1), origem="teste", negocios=10)
    ArmazemVelas(tmp_path / "mercado").gravar("ETHUSDT", tabela, pd.Timestamp("2026-12-01", tz="UTC").to_pydatetime())
    (tmp_path / "modelos").mkdir()
    tecnicas = list(grade_de_sinais(v.head(3000), 5).columns)
    (tmp_path / "modelos" / "ETHUSDT_expiracao_fixa_5m_5m.json").write_text(json.dumps({"tecnicas": tecnicas, "pesos": [0.1] * len(tecnicas), "intercepto": 0.0, "corte": 0.02}))
    cenario = tmp_path / "cenario.json"
    cenario.write_text(json.dumps({"estrategias": ["ETHUSDT|expiracao_fixa|5m|5m"], "cenario": "ETH 5 min"}))
    Diario(tmp_path / "diario.db")
    agora = v.index[-1] + pd.Timedelta(minutes=1, seconds=5)
    s = Servidor(tmp_path / "diario.db", cenario, tmp_path / "entradas.db", CHAVE, relogio=lambda: agora.to_pydatetime(),
                 mercado=tmp_path / "mercado", modelos=tmp_path / "modelos")
    http = criar_servidor(s, "127.0.0.1", 0)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        status, r = pedir(f"http://127.0.0.1:{http.server_address[1]}/api/leitura")
    finally:
        http.shutdown()
    assert status == 200 and r["ativo"] == "ETHUSDT" and len(r["velas"]) > 10 and r["previsao"]["cone"]
    assert s.leitura() is s.leitura()  # cache: o mesmo minuto não recalcula
