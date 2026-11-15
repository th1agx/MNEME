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
