import sqlite3
import time
from datetime import timedelta

import pandas as pd
import pytest

from mneme.motor.diario import Diario
from mneme.quadro.especialistas import ESPECIALISTAS
from mneme.quadro.fontes import DiarioSoLeitura
from quadro_dados import AGORA, montar


def lento(ctx):
    time.sleep(3)
    return [], []


def quebrado(ctx):
    raise RuntimeError("defeito de propósito")


def test_especialista_lento_ou_quebrado_nao_para_os_outros(tmp_path):
    coord, _, _ = montar(tmp_path, especialistas={**ESPECIALISTAS, "lento": lento, "quebrado": quebrado})
    coord.orcamento_s, coord.orcamento_total_s = 0.5, 6
    assert coord.ciclo()["novas"] == 1
    situacoes = dict(coord.quadro.con.execute("SELECT especialista, situacao FROM pedidos").fetchall())
    assert situacoes["lento"] == "tempo_esgotado" and situacoes["quebrado"] == "erro" and situacoes["technical"] in ("ok", "acima_do_orcamento")
    assert coord.quadro.con.execute("SELECT COUNT(*) FROM evidencias WHERE especialista = 'technical'").fetchone()[0] == 1


def test_mesma_vela_nao_duplica(tmp_path):
    coord, _, _ = montar(tmp_path)
    assert coord.ciclo()["novas"] == 1
    n = coord.quadro.con.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0]
    assert coord.ciclo() == {"novas": 0, "conhecidas": 1, "sem_dado": 0, "erros": 0, "disco_cheio": False}
    assert coord.quadro.con.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0] == n


def test_diario_so_leitura_nao_escreve(tmp_path):
    _, dados, _ = montar(tmp_path)
    with DiarioSoLeitura(dados / "operacao" / "diario.db") as d:
        with pytest.raises(sqlite3.OperationalError):
            d.con.execute("INSERT INTO contexto VALUES ('x', 'a', 'b', '{}', 'o', 'c', 'v')")


def test_so_escreve_na_propria_pasta(tmp_path):
    coord, dados, _ = montar(tmp_path)
    motor = Diario(dados / "operacao" / "diario.db")  # como na A1: o motor mantém o diário aberto (com -wal e -shm)
    motor.gravar_contexto("n1", "ETH", "noticia", {"sentimento": 1}, "llm:x", pd.Timestamp(AGORA) - pd.Timedelta(hours=1), pd.Timestamp(AGORA) + pd.Timedelta(hours=5))
    antes = {p: p.stat().st_mtime_ns for p in dados.rglob("*") if p.is_file() and "quadro" not in p.parts}
    coord.ciclo()
    coord.apurar()
    coord.ligar(pd.Timestamp(AGORA) - pd.Timedelta(hours=1))
    depois = {p: p.stat().st_mtime_ns for p in dados.rglob("*") if p.is_file() and "quadro" not in p.parts}
    assert {p for p in depois if p.suffix != ".db-shm"} == {p for p in antes if p.suffix != ".db-shm"}
    mudados = [p for p in antes if p in depois and antes[p] != depois[p] and p.suffix not in (".db-shm",)]
    assert mudados == []
    motor.con.close()


def test_disco_cheio_para_de_gravar(tmp_path):
    coord, _, _ = montar(tmp_path)
    coord.quadro.limite_disco = 0.0
    assert coord.ciclo()["disco_cheio"] is True
    assert coord.quadro.con.execute("SELECT COUNT(*) FROM oportunidades").fetchone()[0] == 0


def test_fonte_parada_fica_sem_dado(tmp_path):
    coord, _, _ = montar(tmp_path)
    coord.relogio = lambda: AGORA + timedelta(hours=2)
    assert coord.ciclo()["sem_dado"] == 1


def test_cache_le_cada_parte_uma_vez_mesmo_em_paralelo(tmp_path, monkeypatch):
    """Um especialista que estoura o tempo continua lendo; a próxima oportunidade não pode reler as mesmas partes."""
    from concurrent.futures import ThreadPoolExecutor

    coord, _, _ = montar(tmp_path)
    lidas, original = [], pd.read_parquet

    def lenta(caminho, *a, **k):
        lidas.append(str(caminho))
        time.sleep(0.01)
        return original(caminho, *a, **k)

    monkeypatch.setattr(pd, "read_parquet", lenta)
    momento = pd.Timestamp(AGORA)
    ler = lambda _: coord.cache.ler("trades", "ETHUSDT", momento - pd.Timedelta(minutes=10), momento, momento, momento)
    with ThreadPoolExecutor(4) as ex:
        resultados = list(ex.map(ler, range(4)))
    assert lidas and len(lidas) == len(set(lidas))
    assert all(r.equals(resultados[0]) for r in resultados)


def test_aquecer_le_antes_do_primeiro_ciclo(tmp_path, monkeypatch):
    coord, _, _ = montar(tmp_path)
    coord.aquecer()
    lidas, original = [], pd.read_parquet
    monkeypatch.setattr(pd, "read_parquet", lambda c, *a, **k: lidas.append(str(c)) or original(c, *a, **k))
    momento = pd.Timestamp(AGORA)
    coord.cache.ler("trades", "ETHUSDT", momento - pd.Timedelta(minutes=10), momento, momento, momento)
    assert not [c for c in lidas if "/trades/" in c]


def test_compose_permite_desligar_o_quadro_sem_tocar_no_resto():
    """Só sobe quando pedido (perfil), não volta sozinho depois de parado, não depende de nada e ninguém depende dele."""
    import yaml
    from pathlib import Path

    servicos = yaml.safe_load((Path(__file__).parent.parent / "compose.yaml").read_text(encoding="utf-8"))["services"]
    quadro = servicos["quadro"]
    assert quadro["profiles"] == ["sombra"] and quadro["restart"] == "unless-stopped"
    assert "depends_on" not in quadro and "./dados:/dados:ro" in quadro["volumes"]
    for nome, s in servicos.items():
        if nome != "quadro":
            assert "quadro" not in str(s.get("depends_on", "")) and "profiles" not in s
            assert not any("quadro" in str(v) for v in s.get("volumes", []))
