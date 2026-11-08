from datetime import timedelta

import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.motor.diario import Diario
from mneme.quadro.banco import Quadro
from mneme.quadro.coordenador import Coordenador
from quadro_dados import AGORA, montar, velas


def test_reproducao_depois_de_reiniciar_da_o_mesmo(tmp_path):
    coord, dados, _ = montar(tmp_path)
    coord.ciclo()
    op_id = coord.quadro.con.execute("SELECT id FROM oportunidades").fetchone()[0]
    # Um processo novo, sem cache, mais tarde e com dados novos chegando depois do momento.
    ArmazemVelas(dados / "mercado").gravar("ETHUSDT", velas(n=6 * 24 * 60 + 90), AGORA + timedelta(hours=2))
    novo = Coordenador(dados / "mercado", Quadro(dados / "quadro" / "quadro.db"), dados / "operacao" / "diario.db", dados / "operacao.json",
                       dados / "modelos" / "motor", dados / "modelos", relogio=lambda: AGORA + timedelta(hours=2), usar_cache=False)
    igual, nova, gravada = novo.reproduzir(op_id)
    assert igual, (nova, gravada)


def test_decisao_do_motor_e_ligada(tmp_path):
    coord, dados, _ = montar(tmp_path)
    coord.ciclo()
    nome, vela = "ETHUSDT|expiracao_fixa|5m|5m", pd.Timestamp(AGORA) - pd.Timedelta(minutes=1)
    Diario(dados / "operacao" / "diario.db").registrar(chave=f"{nome}|{vela.isoformat()}", estrategia=nome, mercado="cripto", ativo="ETHUSDT",
                                                        modalidade="expiracao_fixa", vela=vela, decidido_em=vela + pd.Timedelta(seconds=65), latencia_s=5,
                                                        direcao=1, forca=0.1, expectativa=0.1, evidencia={}, motivo="m", motivos_recusa=(), contexto=(), sinal={},
                                                        tipo="sombra", tamanho=1.0)
    assert coord.ligar(pd.Timestamp(AGORA) - pd.Timedelta(hours=1)) == 1
    assert coord.quadro.con.execute("SELECT chave, tipo FROM decisoes_motor").fetchall()[0][1] == "sombra"


def test_apuracao_usa_a_convencao_do_motor(tmp_path):
    coord, dados, v = montar(tmp_path)
    coord.ciclo()
    mais = velas(n=len(v) + 90)
    ArmazemVelas(dados / "mercado").gravar("ETHUSDT", mais, AGORA + timedelta(hours=2))
    coord.relogio = lambda: AGORA + timedelta(hours=2)
    assert coord.apurar() == 1
    linhas = dict((h, (e, s, d)) for h, e, s, d in coord.quadro.con.execute("SELECT horizonte, entrada, saida, direcao FROM apuracoes").fetchall())
    serie = mais.set_index("abertura_em")
    momento = pd.Timestamp(AGORA)
    for h in (1, 5, 15, 60):
        entrada, saida = serie.at[momento, "abertura"], serie.at[momento + pd.Timedelta(minutes=h - 1), "fechamento"]
        assert linhas[h][:2] == (entrada, saida) and linhas[h][2] == (1 if saida > entrada else -1)
    assert coord.quadro.con.execute("SELECT estado FROM oportunidades").fetchone()[0] == "apurada"
