"""Relatório da manhã: só fala o que tem conteúdo, chama o dono só quando há o que decidir e lê o dia certo de Brasília."""

from datetime import datetime, timezone

import pandas as pd

from mneme.dados.banco_central import ler_copom, ler_ptax
from mneme.manha import escrever_manha, montar, sinais_do_dia
from mneme.motor.diario import Diario


def test_dia_calmo_e_so_leitura_e_secoes_vazias_ficam_caladas():
    r = montar({"dia": "2026-11-17", "ontem": "2026-11-16", "parados": [], "sinais": [], "sem_dado": []})
    assert r.splitlines()[0] == "**SÓ LEITURA, NADA PRA DECIDIR**"
    assert "## " not in r  # nenhuma seção sem conteúdo


def test_servico_parado_chama_o_dono_e_fonte_falha_aparece():
    r = montar({"dia": "2026-11-17", "parados": [("motor", 42)], "sem_dado": ["PTAX do Banco Central: ConnectError"]})
    assert r.splitlines()[0] == "**PRECISA DE VOCÊ**"
    assert "motor" in r and "## Fontes sem dado hoje" in r and "ConnectError" in r


def test_sinais_contra_o_empate_e_texto_de_fora_nao_vira_marcacao():
    r = montar({"dia": "2026-11-17", "ontem": "2026-11-16",
                "sinais": [{"estrategia": "ETHUSDT|expiracao_fixa|5m|5m", "n": 20, "ganhos": 11, "perdas": 9}],
                "copom": {"titulo": "282ª reunião [[link]] | <b>Selic</b>", "data": "2026-11-04"},
                "ptax": {"valor": 5.7324, "data": "2026-11-16", "variacao_pct": 1.43}})
    assert "acerto 55,0% ✓ acima do empate" in r and "54,05%" in r
    assert "[[" not in r and "<b>" not in r and "R$ 5,7324" in r and "+1,43%" in r


def test_ptax_e_copom_do_banco_central():
    assert ler_ptax([{"data": "13/11/2026", "valor": "5.6518"}, {"data": "16/11/2026", "valor": "5.7324"}]) == \
        {"data": "2026-11-16", "valor": 5.7324, "variacao_pct": (5.7324 / 5.6518 - 1) * 100}
    assert ler_ptax([{"data": "16/11/2026", "valor": "x"}, {"data": "17/11/2026", "valor": "5"}]) is None
    c = ler_copom({"conteudo": [{"nro_reuniao": 282, "dataReferencia": "2026-11-04", "titulo": "282ª reunião - Copom mantém a Selic"}]})
    assert c == {"reuniao": 282, "data": "2026-11-04", "titulo": "282ª reunião - Copom mantém a Selic"}
    assert ler_copom({"conteudo": []}) is None


def _sinal(d: Diario, vela: str, resultado: str | None):
    v = pd.Timestamp(vela)
    chave = f"ETH|{v.isoformat()}"
    d.registrar(chave=chave, estrategia="ETHUSDT|expiracao_fixa|5m|5m", mercado="cripto", ativo="ETHUSDT", modalidade="expiracao_fixa", vela=v,
                decidido_em=v + pd.Timedelta(minutes=5), latencia_s=1.0, direcao=1, forca=0.1, expectativa=0.0, evidencia={}, motivo="",
                motivos_recusa=(), contexto=(), sinal={"acao": "CALL", "entrada_em": (v + pd.Timedelta(minutes=6)).isoformat(), "expiracao_min": 5},
                tipo="operada", tamanho=1.0)
    if resultado:
        d.encerrar(chave, {"resultado": resultado, "pnl": 0.0, "preco_entrada": 1.0, "preco_saida": 1.0, "encerrado_por": "expiracao"}, v + pd.Timedelta(minutes=12))


def test_dia_de_brasilia(tmp_path):
    d = Diario(tmp_path / "diario.db")
    _sinal(d, "2026-11-16T02:30:00Z", "ganho")  # entrada 23h36 do dia 15 em Brasília: fica de fora
    _sinal(d, "2026-11-16T12:00:00Z", "ganho")
    _sinal(d, "2026-11-17T02:40:00Z", "perda")  # 23h46 do dia 16 em Brasília: entra
    assert sinais_do_dia(tmp_path / "diario.db", "2026-11-16") == [{"estrategia": "ETHUSDT|expiracao_fixa|5m|5m", "n": 2, "ganhos": 1, "perdas": 1}]


class _BC:
    def ptax(self):
        return {"valor": 5.7, "data": "2026-11-16", "variacao_pct": 0.1}

    def copom(self):
        raise OSError("fora do ar")


class _Vault:
    def __init__(self, agora):
        self.agora, self.estado_, self.notas = agora, {}, []

    def relogio(self):
        return self.agora

    def estado(self):
        return self.estado_

    def guardar_estado(self, **kw):
        self.estado_.update(kw)

    def escrever(self, nota):
        self.notas.append(nota)


def test_grava_uma_vez_por_dia_depois_das_8h(tmp_path):
    v = _Vault(datetime(2026, 11, 17, 10, 50, tzinfo=timezone.utc))  # 7h50 em Brasília: ainda não
    assert escrever_manha(v, tmp_path, _BC()) == 0
    v.agora = datetime(2026, 11, 17, 11, 5, tzinfo=timezone.utc)
    assert escrever_manha(v, tmp_path, _BC()) == 1 and escrever_manha(v, tmp_path, _BC()) == 0
    nota = v.notas[0]
    assert nota.titulo == "Manhã 2026-11-17" and "Copom do Banco Central: OSError" in nota.corpo and "R$ 5,7000" in nota.corpo
