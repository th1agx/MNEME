import csv
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from mneme.digitais import banco, captura, conciliacao, placar
from mneme.digitais.plataformas import ler_ativo

AGORA = datetime(2026, 11, 12, 18, tzinfo=timezone.utc)


def planilha(tmp_path, linhas, nome="demo.csv"):
    caminho = tmp_path / nome
    with caminho.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(captura.COLUNAS)
        for l in linhas:
            w.writerow(l)
    return caminho


def op(hora="14:05:00", direcao="CALL", entrada="1.08412", saida="1.08431", resultado="ganho", lucro="8.50", payout="85", ativo="EUR/USD",
       plataforma="quotex", sinal=""):
    return (plataforma, ativo, direcao, "10", f"2026-11-12T{hora}-03:00", "5", entrada, saida, payout, resultado, lucro, sinal, "")


def test_ler_ativo_como_a_plataforma_escreve():
    assert ler_ativo("EUR/USD").simbolo == "EURUSD" and not ler_ativo("EUR/USD").otc
    a = ler_ativo("EUR/USD (OTC)")
    assert a.otc and a.referencia is None
    assert ler_ativo("BTC/USD").referencia == "BTCUSDT"


def test_importa_valida_e_nao_duplica(tmp_path):
    con = banco.abrir(tmp_path / "d.db")
    csv_ = planilha(tmp_path, [op(), op("14:15:00", "PUT", "1.08500", "1.08480"), op("14:25:00", resultado="perda", lucro="8.50"),
                               op("14:35:00", direcao="TALVEZ"), captura.EXEMPLO])
    r = captura.importar(con, csv_, AGORA)
    assert (r.novas, r.repetidas, len(r.erros)) == (2, 0, 2)
    assert any("lucro" in e for e in r.erros) and any("direção" in e for e in r.erros)
    assert captura.importar(con, csv_, AGORA).repetidas == 2
    linha = con.execute("SELECT * FROM operacoes_demo ORDER BY aberta_em").fetchone()
    assert linha["aberta_em"].startswith("2026-11-12T17:05") and linha["direcao"] == 1  # convertido para UTC


def test_precos_que_contradizem_o_resultado_sao_recusados(tmp_path):
    con = banco.abrir(tmp_path / "d.db")
    r = captura.importar(con, planilha(tmp_path, [op(entrada="1.08431", saida="1.08412")]), AGORA)
    assert r.novas == 0 and "não combinam" in r.erros[0]


def test_regras_e_payout_vem_so_do_que_foi_observado(tmp_path):
    con = banco.abrir(tmp_path / "d.db")
    assert captura.regras_observadas(con) == {}
    captura.importar(con, planilha(tmp_path, [op(), op("14:15:00", entrada="1.08400", saida="1.08400", resultado="empate", lucro="0"),
                                              op("15:15:00", payout="80", lucro="8.00", entrada="1.0841", saida="1.0850")]), AGORA)
    regras = captura.regras_observadas(con)["quotex"]
    assert regras["empate"].startswith("devolve") and regras["expiracoes_min"] == [5.0]
    valor, origem = captura.payout_observado(con, "quotex", "EURUSD", False, datetime(2026, 11, 12, 17, 30, tzinfo=timezone.utc))
    assert valor == pytest.approx(0.85) and "ativo" in origem
    assert captura.payout_observado(con, "iqoption", "EURUSD", False, AGORA) == (None, "sem observação")


def test_conciliacao_compara_com_a_referencia_e_ignora_otc(tmp_path):
    con = banco.abrir(tmp_path / "d.db")
    captura.importar(con, planilha(tmp_path, [op(), op("14:15:00", ativo="EUR/USD (OTC)")]), AGORA)
    indice = pd.date_range("2026-11-12T17:00Z", periods=60, freq="1min")
    precos = np.linspace(1.0840, 1.0846, 60)
    v = pd.DataFrame({"abertura": precos, "fechamento": precos + 0.00001, "maxima": precos + 0.00005, "minima": precos - 0.00005}, index=indice)
    r = conciliacao.conciliar(con, lambda serie, inicio, fim: v, AGORA)
    assert r == {"conciliadas_agora": 1, "sem_referencia_otc_ou_ativo": 1, "sem_vela_de_referencia": 0}
    c = con.execute("SELECT * FROM conciliacao").fetchone()
    assert c["referencia"] == "EURUSD" and c["resultado_referencia"] == "ganho" and c["concorda"] == 1
    assert abs(c["divergencia_entrada_bps"]) < 5


def test_placar_separa_os_niveis_de_fidelidade(tmp_path):
    con = banco.abrir(tmp_path / "d.db")
    captura.importar(con, planilha(tmp_path, [op(sinal="ETHUSDT|expiracao_fixa|5m|5m|2026-11-12T17:00"), op("14:15:00", resultado="perda", lucro="-10",
                                                                                                       entrada="1.0845", saida="1.0840")]), AGORA)
    diario = tmp_path / "diario.db"
    d = sqlite3.connect(diario)
    d.execute("CREATE TABLE decisoes (modalidade TEXT, resultado TEXT, motivos_recusa TEXT)")
    d.executemany("INSERT INTO decisoes VALUES ('expiracao_fixa', ?, '[]')", [("ganho",)] * 58 + [("perda",)] * 42)
    d.commit()
    d.close()
    p = placar.placar(con, diario)
    demo = p["registrado-demo"]["quotex"]
    assert demo["operacoes"] == 2 and demo["acerto"] == 0.5 and demo["so_sinais_do_mneme"]["operacoes"] == 1
    assert p["calibrado"]["quotex"].startswith("indisponível")
    assert p["aproximacao-referencia"]["acerto"] == pytest.approx(0.58) and "hipotético" in p["aproximacao-referencia"]["fonte"]
    assert "expectativa_com_payout_observado_quotex" in p["aproximacao-referencia"]
