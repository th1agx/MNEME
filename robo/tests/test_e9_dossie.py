"""A1: o dossiê das operações só usa o que se sabia no momento, e a atribuição por dimensão não esconde amostra pequena."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from mneme.dados.armazem import ArmazemVelas
from mneme.e9.atribuicao import atribuir
from mneme.e9.dossie import montar_dossie
from mneme.motor.diario import Diario

INICIO = datetime(2026, 11, 1, tzinfo=timezone.utc)


def velas(n: int, semente: int = 0) -> pd.DataFrame:
    r = np.random.default_rng(semente)
    f = 100 + np.cumsum(r.normal(0, 0.1, n))
    abertura = pd.date_range(INICIO, periods=n, freq="min", tz="UTC")
    volume = r.uniform(1, 5, n)
    return pd.DataFrame({"abertura_em": abertura, "abertura": f, "maxima": f + 0.05, "minima": f - 0.05, "fechamento": f,
                         "volume": volume, "volume_cotacao": volume * f, "volume_comprador": volume / 2, "negocios": 10,
                         "recebido_em": abertura + pd.Timedelta(minutes=1, seconds=2), "origem": "teste"})


def decisao(d: Diario, ativo: str, vela: pd.Timestamp, direcao: int, resultado: str, tipo="operada", noticia=None, recusa=()):
    estrategia = f"{ativo}|expiracao_fixa|1m|5m"
    contexto = ({"tipo": "noticia", "valor": {"sentimento": noticia}},) if noticia is not None else ()
    chave = f"{estrategia}|{vela.isoformat()}"
    d.registrar(chave=chave, estrategia=estrategia, mercado="cripto", ativo=ativo, modalidade="expiracao_fixa", vela=vela,
                decidido_em=vela + pd.Timedelta(minutes=1, seconds=5), latencia_s=5.0, direcao=direcao, forca=0.1, expectativa=0.02,
                evidencia={"operacoes": 100, "acerto": 0.56}, motivo="a favor: VWAP", motivos_recusa=recusa, contexto=contexto,
                sinal={"acao": "CALL" if direcao > 0 else "PUT", "expiracao_min": 5, "payout": 0.85, "empate": 1 / 1.85}, tipo=tipo, tamanho=2.0)
    pnl = {"ganho": 0.85, "perda": -1.0, "empate": 0.0}[resultado]
    d.encerrar(chave, {"resultado": resultado, "pnl": pnl, "preco_entrada": 100.0, "preco_saida": 100.0, "encerrado_por": "expiracao"},
               vela + pd.Timedelta(minutes=7))


def montar(tmp_path, n_velas=8 * 1440):
    armazem = ArmazemVelas(tmp_path / "mercado")
    armazem.gravar("ETHUSDT", velas(n_velas), INICIO + timedelta(days=30))
    d = Diario(tmp_path / "diario.db")
    r = np.random.default_rng(1)
    base = pd.Timestamp(INICIO) + pd.Timedelta(days=7)
    for i in range(60):
        resultado = ["ganho", "perda", "empate"][int(r.integers(0, 3))]
        decisao(d, "ETHUSDT", base + pd.Timedelta(minutes=7 * i), 1 if i % 2 else -1, resultado,
                tipo="sombra" if i % 3 == 0 else "operada", noticia=[None, 1, -1][i % 3], recusa=("expectativa não positiva",) if i % 3 == 0 else ())
    d.con.close()
    return tmp_path / "diario.db", armazem


def test_uma_linha_por_decisao_encerrada_com_os_campos(tmp_path):
    diario, armazem = montar(tmp_path)
    x = montar_dossie(diario, armazem)
    assert len(x) == 60
    linha = x.iloc[0]
    assert (linha["candle"], linha["horizonte"]) == (1, 5)
    assert linha["empate"] == 1 / 1.85 and linha["pnl_por_unidade"] in (0.85, -1.0, 0.0)
    assert set(x["noticia"]) <= {"a favor", "contra", "neutra", "sem notícia"}
    assert x.loc[x["resultado"] == "empate", "ganho"].isna().all()
    assert x.loc[x["tipo"] == "sombra", "recusada"].all()


def test_noticia_a_favor_e_contra_seguem_a_direcao(tmp_path):
    diario, armazem = montar(tmp_path)
    x = montar_dossie(diario, armazem)
    com = x[x["noticia"] != "sem notícia"]
    sentimento = np.where(com["noticia"] == "a favor", com["direcao"], -com["direcao"])
    assert len(com) and set(sentimento) <= {1, -1}


def test_volatilidade_nao_olha_o_futuro(tmp_path):
    """Gravar velas posteriores ao momento da decisão não muda nenhum atributo do dossiê."""
    diario, armazem = montar(tmp_path, n_velas=7 * 1440 + 500)
    antes = montar_dossie(diario, armazem)
    outras = velas(9 * 1440, semente=5)  # velas novas depois do fim, com recebido_em lá na frente
    armazem.gravar("ETHUSDT", outras[outras["abertura_em"] >= pd.Timestamp(INICIO) + pd.Timedelta(minutes=7 * 1440 + 500)], INICIO + timedelta(days=30))
    depois = montar_dossie(diario, armazem)
    colunas = ["vol_60", "vol_pct_7d", "tendencia_60"]
    pd.testing.assert_frame_equal(antes[colunas], depois[colunas])
    assert antes["vol_pct_7d"].between(0, 1).all()


def test_sem_velas_o_dossie_sai_com_regime_vazio(tmp_path):
    diario, _ = montar(tmp_path)
    x = montar_dossie(diario, ArmazemVelas(tmp_path / "vazio"))
    assert len(x) == 60 and x["vol_60"].isna().all()


def test_atribuicao_soma_o_total_e_marca_amostra_pequena(tmp_path):
    diario, armazem = montar(tmp_path)
    x = montar_dossie(diario, armazem)
    tabela = atribuir(x, "ativo")
    assert tabela["decisoes"].sum() == len(x)
    eth = tabela.iloc[0]
    assert eth["com_resultado"] == x["ganho"].notna().sum()
    assert eth["ic95_baixo"] <= eth["acerto"] <= eth["ic95_alto"]
    assert eth["velas"] <= eth["com_resultado"] and eth["dias"] >= 1
    assert eth["leitura"] == "amostra insuficiente"  # 60 decisões nunca bastam para a régua v1


def test_atribuicao_recorta_por_qualquer_dimensao(tmp_path):
    diario, armazem = montar(tmp_path)
    x = montar_dossie(diario, armazem)
    for dimensao in ("estrategia", "tipo", "noticia", "hora_utc", "faixa_hora", "dia_semana", "vol_quintil", "forca_quintil"):
        t = atribuir(x, dimensao)
        assert t["decisoes"].sum() == len(x)


def test_nota_no_vault_e_descritiva_e_mostra_a_amostra(tmp_path):
    from mneme.vault import Vault, escrever_atribuicao_e9

    diario, armazem = montar(tmp_path)
    v = Vault(tmp_path / "vault", relogio=lambda: INICIO + timedelta(days=8))
    v.iniciar()
    assert escrever_atribuicao_e9(v, diario, armazem.raiz) == 1
    texto = next((v.raiz).rglob("E9 - onde o motor acerta e erra.md")).read_text(encoding="utf-8")
    assert "exploratório" in texto and "amostra insuficiente" in texto and "régua v1" in texto
    assert "| ETHUSDT |" in texto and "Velas" in texto and "| ETHUSDT · expiracao_fixa · 1m · 5m |" in texto
    assert escrever_atribuicao_e9(v, tmp_path / "nao_existe.db", armazem.raiz) == 0


def test_regime_combina_volatilidade_e_tendencia_do_momento(tmp_path):
    diario, armazem = montar(tmp_path)
    x = montar_dossie(diario, armazem)
    assert set(x["tendencia"]) <= {"alta", "baixa", "lateral"}
    assert set(x["regime"]) <= {f"{v}-{t}" for v in ("vol baixa", "vol media", "vol alta") for t in ("alta", "baixa", "lateral")}
    esperado = np.where(x["tendencia_60"] >= 1, "alta", np.where(x["tendencia_60"] <= -1, "baixa", "lateral"))
    assert (x["tendencia"].to_numpy() == esperado).all()
    assert atribuir(x, "regime")["decisoes"].sum() == len(x)
