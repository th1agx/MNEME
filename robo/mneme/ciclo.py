"""Um ciclo do robô: lê o mercado, mede os traders, decide saídas e entradas e grava tudo."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import acerto, telegram
from .carteira import Carteira, LimitesDia, bloqueio_do_dia
from .mercados.adaptadores.solana import Mercado, MercadoSolana
from .estrategias.seguir_traders import Regra, Sinal, decidir_entrada, decidir_saida
from .sinais import Operacao, ProvedorIndisponivel, ProvedorSinais

log = logging.getLogger("mneme")

MAX_CONSULTAS_PRECO = 30


@dataclass
class Resumo:
    provedor_ok: bool = True
    operacoes_novas: int = 0
    compras: int = 0
    vendas: int = 0
    avisos: list[str] = field(default_factory=list)


def _decisao(con: sqlite3.Connection, rede: str, token: str, simbolo: str, acao: str, motivo: str, agora: datetime) -> None:
    con.execute("INSERT INTO decisoes (rede, token, simbolo, acao, motivo, quando) VALUES (?, ?, ?, ?, ?, ?)",
                (rede, token, simbolo, acao, motivo, agora.isoformat()))


def rodar_ciclo(con: sqlite3.Connection, provedor: ProvedorSinais | None, mercado: MercadoSolana,
                regra: Regra, limites: LimitesDia, agora: datetime) -> Resumo:
    resumo = Resumo()
    carteira = Carteira(con)

    # 1. Operações novas dos traders. Sem o provedor, segue sem entradas, mas ainda confere as saídas.
    operacoes: list[Operacao] = []
    if provedor is None:
        resumo.provedor_ok = False
        resumo.avisos.append("Provedor de sinais não configurado no .env.")
    else:
        try:
            operacoes = provedor.operacoes_recentes(agora)
        except ProvedorIndisponivel as erro:
            resumo.provedor_ok = False
            resumo.avisos.append(str(erro))
    novas: list[Operacao] = []
    for op in operacoes:
        cursor = con.execute("""INSERT OR IGNORE INTO operacoes_traders
            (event_id, trader_id, trader, lado, rede, token, simbolo, valor_usd, quando, recebido_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (op.event_id, op.trader_id, op.trader, op.lado, op.rede, op.token, op.simbolo, op.valor_usd,
             op.quando.isoformat(), agora.isoformat()))
        if cursor.rowcount:
            novas.append(op)
    resumo.operacoes_novas = len(novas)

    # 2. Preços: posições abertas primeiro, depois tokens de Solana, com teto de consultas por ciclo.
    posicoes = carteira.posicoes()
    pedidos: dict[tuple[str, str], None] = {}
    for p in posicoes:
        pedidos[(p["rede"], p["token"])] = None
    for op in sorted(novas, key=lambda o: o.rede != "solana"):
        pedidos[(op.rede, op.token)] = None
    precos: dict[tuple[str, str], Mercado] = {}
    for rede, token in list(pedidos)[:MAX_CONSULTAS_PRECO]:
        info = mercado.mercado(token, rede)
        if info:
            precos[(rede, token)] = info

    # 3. Mede o acerto de todo trader, esteja ou não no ranking.
    for op in sorted(novas, key=lambda o: o.quando):
        info = precos.get((op.rede, op.token))
        if info:
            acerto.registrar(con, op, info.preco_usd, agora)
    for p in posicoes:
        info = precos.get((p["rede"], p["token"]))
        if info:
            carteira.marcar(p["rede"], p["token"], info.preco_usd)

    # 4. Saídas: a maioria dos traders da entrada vendeu.
    for p in carteira.posicoes():
        traders = json.loads(p["traders_entrada"])
        venderam = {linha["trader_id"] for linha in con.execute(
            "SELECT DISTINCT trader_id FROM operacoes_traders WHERE lado = 'sell' AND rede = ? AND token = ? AND quando >= ?",
            (p["rede"], p["token"], p["aberta_em"]))}
        if not decidir_saida(traders, venderam):
            continue
        info = precos.get((p["rede"], p["token"]))
        if not info:
            _decisao(con, p["rede"], p["token"], p["simbolo"], "observar", "Saída confirmada, mas sem preço; tenta no próximo ciclo.", agora)
            continue
        vendidos = sum(1 for t in traders if t in venderam)
        motivo = f"{vendidos} de {len(traders)} traders de alto acerto da entrada venderam."
        resultado = carteira.vender(p["rede"], p["token"], info.preco_usd, motivo, agora)
        resumo.vendas += 1
        telegram.enfileirar(con, telegram.texto_saida(p["simbolo"], vendidos, len(traders), resultado, agora), agora)
        _decisao(con, p["rede"], p["token"], p["simbolo"], "vender", f"{motivo} Resultado: {resultado:+.2f}%.", agora)

    # 5. Entradas: só tokens de Solana com operação nova neste ciclo.
    faltando = regra.faltando()
    acertos = acerto.acertos(con, agora)
    retorno_dia = carteira.retorno_do_dia_pct(agora)
    bloqueio = bloqueio_do_dia(limites, retorno_dia)
    janela = (agora - timedelta(minutes=regra.janela_minutos or 5)).isoformat()
    tokens = {(op.rede, op.token): op.simbolo for op in novas if op.rede == "solana"}
    for (rede, token), simbolo in tokens.items():
        sinais = [Sinal(l["trader_id"], l["lado"], l["quando"]) for l in con.execute(
            "SELECT trader_id, lado, quando FROM operacoes_traders WHERE rede = ? AND token = ? AND quando >= ?", (rede, token, janela))]
        entrada = decidir_entrada(sinais, acertos, regra)
        info = precos.get((rede, token))
        if faltando:
            acao, motivo = "observar", f"Regra incompleta. Preencha em Configurações: {', '.join(faltando)}."
        elif not entrada.entrar:
            acao, motivo = "observar", (f"{len(entrada.compradores)} comprador(es) e {len(entrada.vendedores)} vendedor(es) de alto acerto; "
                                        f"aguardando {regra.min_traders} ou mais, em maioria.")
        elif carteira.posicao(rede, token):
            acao, motivo = "observar", "Já há posição neste token."
        elif bloqueio:
            acao, motivo = "observar", bloqueio
        elif not info:
            acao, motivo = "observar", "Sem preço de mercado para o token."
        elif regra.min_liquidez_usd and (info.liquidez_usd or 0) < regra.min_liquidez_usd:
            acao, motivo = "observar", f"Liquidez abaixo do mínimo de US$ {regra.min_liquidez_usd:,.0f}."
        else:
            taxa_media = sum(acertos[t].taxa_pct for t in entrada.compradores) / len(entrada.compradores)
            motivo = f"{len(entrada.compradores)} traders de alto acerto comprando (acerto médio {taxa_media:.0f}%)."
            comprou = carteira.comprar(rede, token, simbolo, info.preco_usd, regra.tamanho_compra_pct or 0,
                                       entrada.compradores, motivo, agora)
            acao = "comprar" if comprou else "observar"
            if comprou:
                resumo.compras += 1
                telegram.enfileirar(con, telegram.texto_entrada(simbolo, len(entrada.compradores), taxa_media,
                                                                info.variacao_24h_pct, agora), agora)
            else:
                motivo = "Consenso confirmado, mas sem saldo para a compra."
        _decisao(con, rede, token, simbolo, acao, motivo, agora)

    con.commit()
    return resumo
