from datetime import datetime, timedelta, timezone

from mneme import banco
from mneme.carteira import Carteira, LimitesDia, bloqueio_do_dia, dia_brasilia
from mneme.ciclo import rodar_ciclo
from mneme.conectores.solana import Mercado, ler_mercado
from mneme.estrategias.seguir_traders import Acerto, Regra, Sinal, decidir_entrada, decidir_saida
from mneme.sinais import Operacao, ProvedorIndisponivel, ler_operacoes

AGORA = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)
REGRA = Regra(min_acerto_pct=80, min_operacoes=5, min_traders=2, janela_minutos=3, tamanho_compra_pct=1)
SEM_LIMITES = LimitesDia(None, None)


def sinal(trader, lado, minuto=0):
    return Sinal(trader, lado, (AGORA + timedelta(minutes=minuto)).isoformat())


class TestSeguirTraders:
    acertos = {"a": Acerto(10, 9), "b": Acerto(6, 5), "c": Acerto(10, 3), "d": Acerto(2, 2)}

    def test_entra_com_maioria_de_alto_acerto(self):
        entrada = decidir_entrada([sinal("a", "buy"), sinal("b", "buy"), sinal("c", "sell")], self.acertos, REGRA)
        assert entrada.entrar and entrada.compradores == ["a", "b"]

    def test_ignora_baixo_acerto_e_amostra_pequena(self):
        entrada = decidir_entrada([sinal("a", "buy"), sinal("c", "buy"), sinal("d", "buy")], self.acertos, REGRA)
        assert not entrada.entrar and entrada.compradores == ["a"]

    def test_vale_a_ultima_operacao_de_cada_trader(self):
        entrada = decidir_entrada([sinal("a", "buy"), sinal("b", "buy"), sinal("b", "sell", 1)], self.acertos, REGRA)
        assert not entrada.entrar and entrada.vendedores == ["b"]

    def test_regra_incompleta_so_observa(self):
        regra = Regra(80, 5, 2, None, 1)
        assert regra.faltando() == ["janela de tempo"]
        assert not decidir_entrada([sinal("a", "buy"), sinal("b", "buy")], self.acertos, regra).entrar

    def test_sai_quando_mais_da_metade_vende(self):
        assert not decidir_saida(["a", "b"], {"a"})
        assert decidir_saida(["a", "b", "c"], {"a", "c"})
        assert not decidir_saida([], {"a"})


class TestDia:
    def test_dia_vira_a_meia_noite_de_brasilia(self):
        assert dia_brasilia(datetime(2026, 11, 1, 2, 59, tzinfo=timezone.utc)) == "2026-10-31"
        assert dia_brasilia(datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)) == "2026-11-01"

    def test_meta_e_limite_bloqueiam_compras(self):
        assert bloqueio_do_dia(LimitesDia(2, 1), 2.1).startswith("Meta do dia")
        assert bloqueio_do_dia(LimitesDia(2, 1), -1.5).startswith("Limite de perda")
        assert bloqueio_do_dia(LimitesDia(None, None), 50) is None


class TestCarteira:
    def test_compra_e_venda_com_taxa_e_slippage(self):
        con = banco.abrir(":memory:")
        carteira = Carteira(con)
        assert carteira.comprar("solana", "T", "TKN", 1.0, 1, ["a"], "teste", AGORA)
        resultado = carteira.vender("solana", "T", 1.0, "teste", AGORA)
        # Mesmo preço na entrada e na saída: perde só taxa e slippage das duas pontas.
        assert round(resultado, 2) == -1.19
        assert carteira.patrimonio() < 200_000


class TestLeitura:
    def test_le_operacoes_validas_e_recentes(self):
        corpo = {"alerts": [
            {"eventId": "1", "userId": "a", "alertType": "buy", "tokenAddress": "T", "chain": "solana",
             "execTs": AGORA.isoformat(), "token": "TKN", "tradeUsd": "$1,200"},
            {"eventId": "2", "userId": "a", "alertType": "buy", "tokenAddress": "T", "chain": "solana",
             "execTs": (AGORA - timedelta(minutes=10)).isoformat()},
            {"eventId": "3", "userId": "a", "alertType": "buy", "tokenAddress": "T", "chain": "solana", "replay": True,
             "execTs": AGORA.isoformat()},
        ]}
        ops = ler_operacoes(corpo, AGORA)
        assert [op.event_id for op in ops] == ["1"] and ops[0].valor_usd == 1200

    def test_escolhe_o_par_com_mais_liquidez_na_rede(self):
        corpo = {"pairs": [
            {"chainId": "solana", "baseToken": {"address": "T"}, "priceUsd": "1", "liquidity": {"usd": 10}},
            {"chainId": "solana", "baseToken": {"address": "T"}, "priceUsd": "2", "liquidity": {"usd": 900}},
            {"chainId": "bsc", "baseToken": {"address": "T"}, "priceUsd": "3", "liquidity": {"usd": 9999}},
        ]}
        assert ler_mercado(corpo, "T", "solana").preco_usd == 2


class ProvedorFalso:
    def __init__(self, operacoes=None, erro=None):
        self.operacoes, self.erro = operacoes or [], erro

    def operacoes_recentes(self, agora):
        if self.erro:
            raise self.erro
        return self.operacoes


class MercadoFalso:
    def __init__(self, preco=1.0):
        self.preco = preco

    def mercado(self, token, rede):
        return Mercado(self.preco, 100_000, 0)


def op(event_id, trader, lado, minuto, token="T", rede="solana"):
    return Operacao(event_id, trader, trader, lado, rede, token, "TKN", 100, AGORA + timedelta(minutes=minuto))


def treinar(con, trader, ganhos, perdas):
    """Grava resultados encerrados para o trader já ter acerto medido."""
    for i in range(ganhos + perdas):
        con.execute("""INSERT INTO resultados_traders (event_id, trader_id, trader, rede, token, retorno_pct, aberta_em, fechada_em)
            VALUES (?, ?, ?, 'solana', 'X', ?, ?, ?)""", (f"{trader}{i}", trader, trader, 5 if i < ganhos else -5,
                                                         AGORA.isoformat(), AGORA.isoformat()))


class TestCiclo:
    def test_compra_com_consenso_e_vende_quando_a_maioria_sai(self):
        con = banco.abrir(":memory:")
        treinar(con, "a", 9, 1)
        treinar(con, "b", 9, 1)
        compra = rodar_ciclo(con, ProvedorFalso([op("1", "a", "buy", 0), op("2", "b", "buy", 0)]), MercadoFalso(1.0),
                             REGRA, SEM_LIMITES, AGORA + timedelta(minutes=1))
        assert compra.compras == 1
        venda = rodar_ciclo(con, ProvedorFalso([op("3", "a", "sell", 2), op("4", "b", "sell", 2)]), MercadoFalso(1.5),
                            REGRA, SEM_LIMITES, AGORA + timedelta(minutes=3))
        assert venda.vendas == 1
        assert Carteira(con).patrimonio() > 200_000

    def test_sem_provedor_ainda_confere_saidas(self):
        con = banco.abrir(":memory:")
        treinar(con, "a", 9, 1)
        treinar(con, "b", 9, 1)
        rodar_ciclo(con, ProvedorFalso([op("1", "a", "buy", 0), op("2", "b", "buy", 0)]), MercadoFalso(),
                    REGRA, SEM_LIMITES, AGORA + timedelta(minutes=1))
        # As vendas chegaram num ciclo anterior em que o preço faltou; agora o provedor caiu.
        for event_id, trader in (("3", "a"), ("4", "b")):
            con.execute("""INSERT INTO operacoes_traders VALUES (?, ?, ?, 'sell', 'solana', 'T', 'TKN', 100, ?, ?)""",
                        (event_id, trader, trader, (AGORA + timedelta(minutes=2)).isoformat(), AGORA.isoformat()))
        resumo = rodar_ciclo(con, ProvedorFalso(erro=ProvedorIndisponivel("sem créditos")), MercadoFalso(),
                             REGRA, SEM_LIMITES, AGORA + timedelta(minutes=3))
        assert not resumo.provedor_ok and resumo.vendas == 1

    def test_mede_o_acerto_de_qualquer_trader(self):
        con = banco.abrir(":memory:")
        rodar_ciclo(con, ProvedorFalso([op("1", "z", "buy", 0)]), MercadoFalso(1.0), REGRA, SEM_LIMITES, AGORA)
        rodar_ciclo(con, ProvedorFalso([op("2", "z", "sell", 1)]), MercadoFalso(2.0), REGRA, SEM_LIMITES, AGORA + timedelta(minutes=1))
        linha = con.execute("SELECT retorno_pct FROM resultados_traders WHERE trader_id = 'z'").fetchone()
        assert linha["retorno_pct"] > 90

    def test_nao_compra_fora_de_solana(self):
        con = banco.abrir(":memory:")
        treinar(con, "a", 9, 1)
        treinar(con, "b", 9, 1)
        resumo = rodar_ciclo(con, ProvedorFalso([op("1", "a", "buy", 0, rede="bsc"), op("2", "b", "buy", 0, rede="bsc")]),
                             MercadoFalso(), REGRA, SEM_LIMITES, AGORA + timedelta(minutes=1))
        assert resumo.compras == 0


class TestDicasEVelas:
    def test_textos_das_dicas(self):
        from mneme.telegram import texto_entrada, texto_saida
        entrada = texto_entrada("BONK", 3, 87.4, 4.2, AGORA)
        assert entrada.splitlines()[0] == "🟢 $BONK · ENTRADA" and "acerto médio 87%" in entrada and "+4,20% 24h" in entrada
        saida = texto_saida("BONK", 2, 3, -1.5, AGORA)
        assert "2 de 3 traders" in saida and "❌ Resultado da operação: -1,50%" in saida and "12:00" in saida

    def test_compra_e_venda_entram_na_fila_de_dicas(self):
        con = banco.abrir(":memory:")
        treinar(con, "a", 9, 1)
        treinar(con, "b", 9, 1)
        rodar_ciclo(con, ProvedorFalso([op("1", "a", "buy", 0), op("2", "b", "buy", 0)]), MercadoFalso(1.0),
                    REGRA, SEM_LIMITES, AGORA + timedelta(minutes=1))
        rodar_ciclo(con, ProvedorFalso([op("3", "a", "sell", 2), op("4", "b", "sell", 2)]), MercadoFalso(1.5),
                    REGRA, SEM_LIMITES, AGORA + timedelta(minutes=3))
        textos = [linha["texto"].splitlines()[0] for linha in con.execute("SELECT texto FROM dicas ORDER BY id")]
        assert textos == ["🟢 $TKN · ENTRADA", "🔴 $TKN · SAÍDA"]

    def test_dica_velha_expira_e_sem_token_fica_na_fila(self):
        from mneme.telegram import Telegram, enfileirar
        con = banco.abrir(":memory:")
        enfileirar(con, "velha", AGORA - timedelta(minutes=30))
        enfileirar(con, "nova", AGORA)
        assert Telegram("", "").enviar_pendentes(con, AGORA) == 0
        situacoes = [linha["situacao"] for linha in con.execute("SELECT situacao FROM dicas ORDER BY id")]
        assert situacoes == ["expirada", "pendente"]

    def test_le_velas_da_binance(self):
        from mneme.conectores.binance import ler_velas
        ms = int(AGORA.timestamp() * 1000)
        linhas = ler_velas([[ms, "1.0", "2.0", "0.5", "1.5", "100", ms + 59_999, "150", 42, "0", "0", "0"]])
        assert linhas == [(AGORA.isoformat(), 1.0, 2.0, 0.5, 1.5, 100.0, 42)]


class TestEstudoVelas:
    def test_empate_da_aposta_de_direcao(self):
        from mneme.estudo.velas import empate
        assert round(empate(0.85), 2) == 54.05

    def test_atributos_nao_olham_o_futuro(self):
        import numpy as np
        import pandas as pd
        from mneme.estudo.velas import montar
        indice = pd.date_range("2026-10-01", periods=300, freq="min", tz="UTC")
        precos = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.1, 300))
        velas = pd.DataFrame({"abertura": precos, "maxima": precos + 0.1, "minima": precos - 0.1, "fechamento": precos,
                              "volume": 1.0 + np.arange(300) % 7, "negocios": 10 + np.arange(300) % 5}, index=indice)
        x, _ = montar(velas, 5)
        alterado = velas.copy()
        alterado.iloc[-1, alterado.columns.get_loc("fechamento")] *= 2  # muda só a última vela
        x2, _ = montar(alterado, 5)
        comum = x.index.intersection(x2.index)
        pd.testing.assert_frame_equal(x.loc[comum], x2.loc[comum])


class TestSetups:
    def _velas(self, n=3000, semente=7):
        import numpy as np
        import pandas as pd
        indice = pd.date_range("2026-10-01", periods=n, freq="min", tz="UTC")
        fechamento = 100 * np.exp(np.cumsum(np.random.default_rng(semente).normal(0, 0.001, n)))
        abertura = np.r_[fechamento[0], fechamento[:-1]]
        return pd.DataFrame({"abertura": abertura, "maxima": np.maximum(abertura, fechamento) * 1.0005,
                             "minima": np.minimum(abertura, fechamento) * 0.9995, "fechamento": fechamento,
                             "volume": 1.0, "negocios": 1}, index=indice)

    def test_nenhum_setup_olha_o_futuro(self):
        from mneme.setups import SETUPS
        velas = self._velas()
        corte = velas.index[2000]
        for nome, setup in SETUPS.items():
            inteiro = setup(velas).loc[:corte]
            cortado = setup(velas.loc[:corte])
            assert (inteiro == cortado.reindex(inteiro.index).fillna(0)).all(), nome

    def test_engolfo_de_alta(self):
        import pandas as pd
        from mneme.setups import engolfo
        v = pd.DataFrame({"abertura": [10, 9.5], "fechamento": [9.6, 10.2], "maxima": [10.1, 10.3], "minima": [9.4, 9.4]})
        assert engolfo(v).tolist() == [0, 1]

    def test_medir_conta_acertos_e_ignora_empates(self):
        import pandas as pd
        from mneme.setups import medir
        v = pd.DataFrame({"fechamento": [10.0, 11.0, 11.0, 12.0, 12.0]})
        sinal = pd.Series([1, 1, -1, 0, 0])
        n, acerto, _, _ = medir(v, sinal, 1)
        assert n == 2 and acerto == 50.0


class TestAoVivo:
    def montar(self, monkeypatch, minutos_de_velas=300, minutos_da_aposta=15):
        import pandas as pd

        from mneme import ao_vivo

        con = banco.abrir(":memory:")
        inicio = AGORA - timedelta(minutes=minutos_de_velas)
        con.executemany("INSERT INTO velas VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        [("SOLUSDT", (inicio + timedelta(minutes=i)).isoformat(), 100 + i, 101 + i, 99 + i, 100 + i, 1, 1)
                         for i in range(minutos_de_velas)])

        def aposta_que_sobe(velas):
            sinal = pd.Series(0, index=velas.index)
            sinal.iloc[-20] = 1
            return sinal

        monkeypatch.setattr(ao_vivo, "AO_VIVO", {"teste": (aposta_que_sobe, minutos_da_aposta)})
        return con, ao_vivo

    def test_grava_uma_vez_e_confere_depois_do_tempo(self, monkeypatch):
        con, ao_vivo = self.montar(monkeypatch)
        assert ao_vivo.gravar_sinais(con, "SOLUSDT", AGORA) == 1
        assert ao_vivo.gravar_sinais(con, "SOLUSDT", AGORA) == 0
        assert ao_vivo.conferir(con) == 1
        linha = con.execute("SELECT * FROM sinais_ao_vivo").fetchone()
        assert (linha["preco_entrada"], linha["preco_saida"], linha["resultado"]) == (380, 395, "ganhou")
        assert ao_vivo.resumo(con) == "ao vivo 1/1 (100%)"

    def test_espera_a_vela_de_saida_fechar(self, monkeypatch):
        con, ao_vivo = self.montar(monkeypatch, minutos_da_aposta=30)
        ao_vivo.gravar_sinais(con, "SOLUSDT", AGORA)
        assert ao_vivo.conferir(con) == 0
        assert ao_vivo.placar(con)[0]["aguardando"] == 1

    def test_sem_historico_suficiente_nao_grava(self, monkeypatch):
        con, ao_vivo = self.montar(monkeypatch, minutos_de_velas=100)
        assert ao_vivo.gravar_sinais(con, "SOLUSDT", AGORA) == 0


class TestOperacao:
    def test_segunda_copia_do_robo_nao_roda(self, tmp_path):
        import pytest

        from mneme.__main__ import travar

        primeira = travar(tmp_path / "traders.trava")
        with pytest.raises(SystemExit):
            travar(tmp_path / "traders.trava")
        primeira.close()
        travar(tmp_path / "traders.trava").close()

    def test_batimento_grava_a_hora_do_ciclo(self, tmp_path):
        from mneme.__main__ import bater

        bater(tmp_path / "traders.batimento", AGORA)
        assert (tmp_path / "traders.batimento").read_text() == AGORA.isoformat()
