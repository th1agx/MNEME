"""Teste ao vivo dos setups de direção: só grava e confere, nada vai para o Telegram até o setup se provar.

O sinal sai no fechamento da vela, como no backtest (`mneme.setups.medir`), e é conferido com o fechamento
da vela que abre `minutos` depois. Placar: `uv run python -m mneme.ao_vivo`.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pandas as pd

from ..setups import bollinger_rsi

# Candidato em observação; não passou da correção por múltiplos testes (robo/conhecimento/setups.md).
AO_VIVO = {"Bollinger + RSI (volta para a banda)": (bollinger_rsi, 15)}
JANELA = 300  # velas lidas por ciclo: aquece a média de 20 e o RSI de 14
RECENTES = 60  # velas mais novas em que procura sinal (cobre o robô parado por até 1 hora)


def ultimas_velas(con: sqlite3.Connection, par: str, quantidade: int = JANELA) -> pd.DataFrame:
    velas = pd.read_sql_query("SELECT abertura_em, abertura, maxima, minima, fechamento, volume FROM velas "
                              "WHERE par = ? ORDER BY abertura_em DESC LIMIT ?", con, params=(par, quantidade))
    velas["abertura_em"] = pd.to_datetime(velas["abertura_em"], utc=True)
    return velas.set_index("abertura_em").sort_index()


def gravar_sinais(con: sqlite3.Connection, par: str, agora: datetime) -> int:
    velas = ultimas_velas(con, par)
    if len(velas) < JANELA:
        return 0
    novos = 0
    for nome, (setup, minutos) in AO_VIVO.items():
        sinal = setup(velas).iloc[-RECENTES:]
        for quando, direcao in sinal[sinal != 0].items():
            cursor = con.execute("""INSERT OR IGNORE INTO sinais_ao_vivo
                (setup, par, minutos, vela_em, direcao, preco_entrada, gravado_em) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (nome, par, minutos, quando.isoformat(), int(direcao), float(velas.at[quando, "fechamento"]), agora.isoformat()))
            novos += cursor.rowcount
    return novos


def conferir(con: sqlite3.Connection) -> int:
    """Dá o resultado dos sinais cuja vela de saída já fechou."""
    conferidos = 0
    for linha in con.execute("SELECT * FROM sinais_ao_vivo WHERE resultado IS NULL").fetchall():
        saida_em = (datetime.fromisoformat(linha["vela_em"]) + timedelta(minutes=linha["minutos"])).isoformat()
        vela = con.execute("SELECT fechamento FROM velas WHERE par = ? AND abertura_em = ?", (linha["par"], saida_em)).fetchone()
        if vela is None:
            continue
        variacao = (vela["fechamento"] - linha["preco_entrada"]) * linha["direcao"]
        resultado = "ganhou" if variacao > 0 else "perdeu" if variacao < 0 else "empate"
        con.execute("""UPDATE sinais_ao_vivo SET preco_saida = ?, resultado = ?
            WHERE setup = ? AND par = ? AND minutos = ? AND vela_em = ?""",
            (vela["fechamento"], resultado, linha["setup"], linha["par"], linha["minutos"], linha["vela_em"]))
        conferidos += 1
    return conferidos


def placar(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Acerto por setup e par; empates não contam, como no backtest."""
    return con.execute("""SELECT setup, par, minutos,
            SUM(resultado = 'ganhou') AS ganhou, SUM(resultado = 'perdeu') AS perdeu,
            SUM(resultado IS NULL) AS aguardando, MIN(vela_em) AS desde
        FROM sinais_ao_vivo GROUP BY setup, par, minutos ORDER BY setup, par""").fetchall()


def resumo(con: sqlite3.Connection) -> str:
    linhas = placar(con)
    ganhou = sum(l["ganhou"] for l in linhas)
    total = ganhou + sum(l["perdeu"] for l in linhas)
    return f"ao vivo {ganhou}/{total}" + (f" ({ganhou / total:.0%})" if total else "")


def main() -> None:
    from .. import banco, config
    from ..estudo.velas import empate

    con = banco.abrir(config.carregar().banco)
    print(f"Empate com payout de 85%: {empate(0.85):.2f}%\n")
    for l in placar(con):
        total = l["ganhou"] + l["perdeu"]
        acerto = f"{l['ganhou'] / total:.2%}" if total else "-"
        print(f"{l['setup']} · {l['par']} · {l['minutos']} min: {l['ganhou']}/{total} = {acerto}"
              f" · aguardando {l['aguardando']} · desde {l['desde'][:16]}")


if __name__ == "__main__":
    main()
