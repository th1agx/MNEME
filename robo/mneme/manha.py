"""Relatório da manhã: uma página por dia, às 8h de Brasília, com o que o MNEME viu desde ontem.

A primeira linha diz se há algo para o dono decidir ("PRECISA DE VOCÊ") ou se é só leitura. Cada seção só aparece quando tem
conteúdo: seção vazia fica calada, para o relatório não virar ruído. Fonte que falhou aparece no fim, para nunca confundir dia
calmo com fonte quebrada. Nada aqui decide ou opera; o relatório só lê o diário, os batimentos e as fontes públicas.

    python -m mneme.manha            # imprime o relatório de agora, sem gravar
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

BRASILIA = timezone(timedelta(hours=-3))
HORA = 8
PARADO_APOS = timedelta(minutes=15)
EMPATE_85 = 1 / 1.85  # acerto mínimo para empatar com payout de 85%
MAX_ESTRATEGIAS, MAX_NOTICIAS, MAX_AGENDA = 8, 5, 8
SERVICOS = {"coleta": "mercado/coleta.batimento", "motor": "mercado/motor.batimento", "previsor": "mercado/previsor.batimento",
            "inteligencia": "mercado/inteligencia.batimento", "carteira": "mercado/carteira.batimento", "forex": "mercado/forex.batimento",
            "quadro": "quadro/quadro.batimento", "traders": "traders.batimento"}


def _limpo(texto, limite: int = 160) -> str:
    """Texto de fora (manchete, título do BC) não cria link, tabela nem marcação no relatório."""
    t = re.sub(r"[\x00-\x1f<>\[\]`|*_#]", " ", str(texto or ""))
    return re.sub(r"\s+", " ", t).strip()[:limite]


def _pct(x: float, casas: int = 1) -> str:
    return f"{x * 100:.{casas}f}%".replace(".", ",")


def montar(e: dict) -> str:
    """Monta o Markdown a partir do que foi lido. Função pura: o mesmo dado sempre dá o mesmo relatório."""
    parados = e.get("parados") or []
    pede = [f"Serviço **{nome}** sem batimento há {minutos} min." for nome, minutos in parados]
    linhas = [f"**{'PRECISA DE VOCÊ' if pede else 'SÓ LEITURA, NADA PRA DECIDIR'}**", "", f"# Relatório da manhã, {e['dia']}", ""]

    def secao(titulo: str, itens: list[str]):
        if itens:
            linhas.extend([f"## {titulo}", *[f"- {i}" for i in itens], ""])

    secao("Pra decidir hoje", pede)
    sinais = []
    for s in (e.get("sinais") or [])[:MAX_ESTRATEGIAS]:
        apurados = s["ganhos"] + s["perdas"]
        acerto = s["ganhos"] / apurados if apurados else None
        marca = "" if acerto is None else (" ✓ acima do empate" if acerto > EMPATE_85 else " ✗ abaixo do empate")
        sinais.append(f"{s['estrategia']}: {s['n']} sinais, {s['ganhos']} ganhos e {s['perdas']} perdas"
                      + ("" if acerto is None else f", acerto {_pct(acerto)}{marca}"))
    if sinais:
        sinais.append(f"Empate com payout de 85%: {_pct(EMPATE_85, 2)}. Poucas operações não são evidência.")
    secao(f"Sinais de ontem ({e.get('ontem', '')}), no simulado", sinais)
    macro = []
    if e.get("ptax"):
        p = e["ptax"]
        macro.append(f"Dólar PTAX de venda: R$ {p['valor']:.4f} em {p['data']} ({p['variacao_pct']:+.2f}% no dia)".replace(".", ","))
    if e.get("copom"):
        c = e["copom"]
        macro.append(f"Copom: {_limpo(c['titulo'])} ({c['data']})")
    secao("Dólar e juros no Brasil", macro)
    secao("Agenda de hoje (horário de Brasília)", [f"{a['hora']} · {a['moeda']} · {_limpo(a['nome'], 90)} · impacto {a['impacto']}"
                                                   for a in (e.get("agenda") or [])[:MAX_AGENDA]])
    secao("Notícias oficiais nas últimas 24 h", [f"{n['hora']} · {n['fonte']} · {_limpo(n['titulo'])}" for n in (e.get("noticias") or [])[:MAX_NOTICIAS]])
    secao("Fontes sem dado hoje", [_limpo(x) for x in e.get("sem_dado") or []])
    linhas.append("Relatório só de leitura: nenhuma linha daqui envia ordem ou muda parâmetro.")
    return "\n".join(linhas)


# ---------- leitura dos dados ----------

def parados(dados: Path, agora: datetime) -> list[tuple[str, int]]:
    saida = []
    for nome, rel in SERVICOS.items():
        arquivo = dados / rel
        if not arquivo.exists():
            continue
        idade = agora - datetime.fromtimestamp(arquivo.stat().st_mtime, timezone.utc)
        if idade > PARADO_APOS:
            saida.append((nome, int(idade.total_seconds() // 60)))
    return saida


def sinais_do_dia(diario: Path, dia: str) -> list[dict]:
    """Sinais CALL/PUT cuja entrada caiu no dia de Brasília `dia`, por estratégia, das mais ativas para as menos."""
    if not diario.exists():
        return []
    inicio = datetime.fromisoformat(dia).replace(tzinfo=BRASILIA).astimezone(timezone.utc)
    fim = inicio + timedelta(days=1)
    con = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    try:
        linhas = con.execute("SELECT estrategia, sinal, resultado FROM decisoes WHERE decidido_em >= ? AND decidido_em < ?",
                             ((inicio - timedelta(hours=1)).isoformat(), (fim + timedelta(hours=1)).isoformat())).fetchall()
    finally:
        con.close()
    contas: dict[str, dict] = {}
    for estrategia, sinal, resultado in linhas:
        s = json.loads(sinal or "{}")
        if s.get("acao") not in ("CALL", "PUT") or not s.get("entrada_em"):
            continue
        if not inicio <= datetime.fromisoformat(s["entrada_em"]) < fim:
            continue
        c = contas.setdefault(estrategia, {"estrategia": estrategia, "n": 0, "ganhos": 0, "perdas": 0})
        c["n"] += 1
        c["ganhos"] += resultado == "ganho"
        c["perdas"] += resultado == "perda"
    return sorted(contas.values(), key=lambda c: (-c["n"], c["estrategia"]))


def agenda_do_dia(mercado: Path, dia: str) -> list[dict]:
    from .dados.eventos import ArmazemEventos
    cal = ArmazemEventos(mercado).ler("calendario", "GLOBAL")
    if cal.empty or "ocorrido_em" not in cal:
        return []
    cal = cal.drop_duplicates("id", keep="last") if "id" in cal else cal
    quando = pd.to_datetime(cal["ocorrido_em"], utc=True).dt.tz_convert(BRASILIA)
    hoje = cal[(quando.dt.strftime("%Y-%m-%d") == dia) & cal.get("impacto", pd.Series(index=cal.index, dtype=str)).isin(["High", "Medium"])]
    hoje = hoje.assign(_q=quando[hoje.index]).sort_values("_q")
    return [{"hora": q.strftime("%H:%M"), "moeda": _limpo(r.get("moeda"), 6), "nome": r.get("nome"), "impacto": "alto" if r.get("impacto") == "High" else "médio"}
            for q, (_, r) in zip(hoje["_q"], hoje.iterrows())]


def noticias_oficiais(mercado: Path, agora: datetime) -> list[dict]:
    from .dados.eventos import ArmazemEventos
    from .noticias import FONTES, FONTES_HABILITADAS
    oficiais = {f.id for f in FONTES if f.categoria == "oficial"} & FONTES_HABILITADAS
    n = ArmazemEventos(mercado).ler("noticias", "GLOBAL")
    if n.empty or "recebido_em" not in n:
        return []
    n = n[n["fonte"].isin(oficiais)].drop_duplicates("id", keep="last")
    recebido = pd.to_datetime(n["recebido_em"], utc=True)
    n = n.assign(_r=recebido)[recebido >= pd.Timestamp(agora) - pd.Timedelta(hours=24)].sort_values("_r", ascending=False)
    return [{"hora": r["_r"].tz_convert(BRASILIA).strftime("%d/%m %H:%M"), "fonte": r["fonte"], "titulo": r["titulo"]} for _, r in n.iterrows()]


def coletar(dados: Path, agora: datetime, bc=None) -> dict:
    """Lê tudo o que o relatório usa. Cada fonte falha sozinha e vira uma linha em "fontes sem dado"."""
    from .dados.banco_central import BancoCentral
    bc = bc or BancoCentral()
    local = agora.astimezone(BRASILIA)
    dia, ontem = local.date().isoformat(), (local.date() - timedelta(days=1)).isoformat()
    e: dict = {"dia": dia, "ontem": ontem, "sem_dado": []}
    for chave, nome, tarefa in (("parados", "batimentos", lambda: parados(dados, agora)),
                                ("sinais", "diário", lambda: sinais_do_dia(dados / "operacao" / "diario.db", ontem)),
                                ("ptax", "PTAX do Banco Central", bc.ptax), ("copom", "Copom do Banco Central", bc.copom),
                                ("agenda", "calendário", lambda: agenda_do_dia(dados / "mercado", dia)),
                                ("noticias", "notícias", lambda: noticias_oficiais(dados / "mercado", agora))):
        try:
            e[chave] = tarefa()
        except Exception as erro:  # noqa: BLE001 - qualquer falha de uma fonte só tira a seção dela
            e[chave] = None
            e["sem_dado"].append(f"{nome}: {erro.__class__.__name__}")
    for chave, nome in (("ptax", "PTAX do Banco Central"), ("copom", "Copom do Banco Central")):
        if e.get(chave) is None and not any(x.startswith(nome) for x in e["sem_dado"]):
            e["sem_dado"].append(f"{nome}: resposta sem dado válido")
    return e


def escrever_manha(v, dados: Path, bc=None) -> int:
    """Grava a nota do dia uma vez, depois das 8h de Brasília. Chamado pelo ciclo do Vault a cada 10 minutos."""
    from .vault import Nota
    agora = v.relogio()
    local = agora.astimezone(BRASILIA)
    dia = local.date().isoformat()
    if local.hour < HORA or v.estado().get("manha") == dia:
        return 0
    corpo = montar(coletar(dados, agora, bc))
    v.escrever(Nota(f"Manhã {dia}", "06-trading-journal", "experimento", corpo, tipo="relatorio",
                    mercados=["cripto", "forex", "ouro"], relacionadas=[f"Diário {(local.date() - timedelta(days=1)).isoformat()}"]))
    v.guardar_estado(manha=dia)
    return 1


if __name__ == "__main__":
    import os

    from .config import PASTA_DADOS
    print(montar(coletar(Path(os.getenv("MNEME_DADOS", str(PASTA_DADOS))), datetime.now(timezone.utc))))
