import json
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from mneme.laboratorio.registro import Registro
from mneme.mercados.carteiras import auditoria, hipoteses


def banco(tmp_path, retornos_extra=()):
    caminho = tmp_path / "mneme.db"
    con = sqlite3.connect(caminho)
    con.executescript("""
        CREATE TABLE operacoes_traders (event_id TEXT PRIMARY KEY, trader_id TEXT, trader TEXT, lado TEXT, rede TEXT, token TEXT,
                                        simbolo TEXT, valor_usd REAL, quando TEXT, recebido_em TEXT);
        CREATE TABLE resultados_traders (event_id TEXT PRIMARY KEY, trader_id TEXT, trader TEXT, rede TEXT, token TEXT,
                                         retorno_pct REAL, aberta_em TEXT, fechada_em TEXT);""")
    rng = np.random.default_rng(1)
    base = pd.Timestamp("2026-11-03T12:00:00Z")
    for i in range(200):
        t = base + pd.Timedelta(minutes=int(i * 7))
        con.execute("INSERT INTO operacoes_traders VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (f"o{i}", f"t{i % 20}", f"trader{i % 20}", "buy" if i % 2 else "sell", "solana", f"tok{i % 5}", "X", 1000.0,
                     t.isoformat(), (t + pd.Timedelta(seconds=30)).isoformat()))
    for i in range(160):  # 20 carteiras com 8 posições cada, retornos sem vantagem
        t = base + pd.Timedelta(minutes=int(i * 9))
        con.execute("INSERT INTO resultados_traders VALUES (?,?,?,?,?,?,?,?)",
                    (f"r{i}", f"t{i % 20}", f"trader{i % 20}", "solana", f"tok{i % 5}", float(rng.normal(0, 10)), t.isoformat(),
                     (t + pd.Timedelta(minutes=40)).isoformat()))
    for j, r in enumerate(retornos_extra):
        con.execute("INSERT INTO resultados_traders VALUES (?,?,?,?,?,?,?,?)",
                    (f"x{j}", "t0", "trader0", "solana", "tok0", r, base.isoformat(), (base + pd.Timedelta(minutes=5)).isoformat()))
    con.commit()
    con.close()
    return caminho


def test_preco_corrompido_e_marcado_e_nao_entra_no_ranking(tmp_path):
    caminho = banco(tmp_path, retornos_extra=(468663.6,))
    r = auditoria.auditar(caminho, None)
    assert len(r["qualidade"]["suspeitos"]) == 1
    assert r["ranking"]["geral"]["n"] == 160  # o suspeito fica fora, mas continua no banco
    con = sqlite3.connect(caminho)
    assert con.execute("SELECT COUNT(*) FROM resultados_traders").fetchone()[0] == 161


def test_sem_vantagem_vira_resultado_negativo_registrado_com_impressao(tmp_path):
    reg = Registro(tmp_path / "experimentos.jsonl", commit="abc1234")
    r = auditoria.auditar(banco(tmp_path), None, reg)
    assert r["ranking"]["carteiras_com_minimo"] == 20 and r["natureza"] == "resultado-negativo"
    linha = reg.todos("carteiras")[0]
    assert linha["nome"] == "auditoria do histórico" and linha["commit"] == "abc1234" and len(linha["dados"]) == 16
    assert linha["resultado"]["natureza"] == "resultado-negativo"


def test_auditoria_e_reproduzivel(tmp_path):
    caminho = banco(tmp_path)
    a, b = auditoria.auditar(caminho, None), auditoria.auditar(caminho, None)
    assert json.dumps(a, default=str, sort_keys=True) == json.dumps(b, default=str, sort_keys=True)


def test_timing_compara_com_placebo_no_mesmo_token(tmp_path):
    ops, _ = auditoria.carregar(banco(tmp_path))
    indice = pd.date_range("2026-11-03T08:00Z", periods=2000, freq="1min")
    precos = {f"tok{k}": pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(k).normal(0, 0.002, 2000))), index=indice) for k in range(5)}
    t = auditoria.timing(ops, precos)
    assert t["compras_com_preco"] > 50 and t["placebo_depois60"]["n"] == t["compras_com_preco"]


def test_hipoteses_sao_registradas_uma_vez_com_a_data_do_registro(tmp_path):
    reg = Registro(tmp_path / "experimentos.jsonl", commit="abc1234")
    assert hipoteses.registrar(reg) == 3 and hipoteses.registrar(reg) == 0
    linhas = reg.todos("carteiras")
    assert [l["nome"] for l in linhas] == ["hipótese H1", "hipótese H2", "hipótese H3"]
    assert all(l["quando"].startswith("2026-11-11") and l["resultado"]["natureza"] == "hipotese" for l in linhas)
    assert hipoteses.REGISTRADAS_EM == datetime(2026, 11, 11, tzinfo=timezone.utc)


def test_vault_respeita_a_natureza_do_estudo(tmp_path):
    from mneme.vault import Vault, importar_experimentos
    reg = Registro(tmp_path / "experimentos.jsonl", commit="abc1234")
    auditoria.auditar(banco(tmp_path), None, reg)
    hipoteses.registrar(reg)
    v = Vault(tmp_path / "vault", relogio=lambda: datetime(2026, 11, 11, 18, tzinfo=timezone.utc))
    v.iniciar()
    assert importar_experimentos(v, reg.caminho) == 4
    notas = {n.name: n.read_text(encoding="utf-8") for n in (v.trabalho / "02-quantitative-research" / "experiments").glob("*.md")}
    assert "natureza: resultado-negativo" in next(t for n, t in notas.items() if "auditoria" in n)
    assert sum("natureza: hipotese" in t for t in notas.values()) == 3
