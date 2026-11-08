"""Especialistas da pista rápida (F1): funções puras, só de leitura, que transformam o que já existe em evidência.

Contrato: `especialista(ctx) -> (evidências, restrições)`. Nenhum dado com `ocorrido_em` depois do momento entra; um dado
produzido até o momento pode ter chegado até `CORTE` depois dele (por exemplo, a previsão do previsor chega uns 7 s depois).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..carteira import dia_brasilia
from ..motor.ciclo import ASSUNTOS
from ..motor.conhecimento import chave_da_estrategia
from ..motor.modalidades import Configuracao, Estrategia
from ..motor.risco import Estado, avaliar
from .esquema import Evidencia, Restricao
from .fontes import DiarioSoLeitura, LeitorEventos

CORTE = pd.Timedelta(seconds=15)
VERSAO = "f1.1"


@dataclass
class Contexto:
    oportunidade: str
    instrumento: str
    ativo: str
    mercado: str
    candle: int
    vela: pd.Timestamp          # último minuto da vela que fechou (convenção do motor)
    momento: pd.Timestamp       # vela + 1 minuto: o instante da decisão
    sinais: pd.Series           # sinal de cada técnica nesta vela
    estrategias: tuple[Estrategia, ...]
    modelos_motor: dict
    manifestos: dict
    config: Configuracao
    fonte_config: str
    eventos: LeitorEventos
    diario: DiarioSoLeitura
    kill_switch: bool
    dep_velas: str
    agora: pd.Timestamp
    extra: dict = field(default_factory=dict)

    @property
    def conhecido_ate(self) -> pd.Timestamp:
        return self.momento + CORTE

    @property
    def validade(self) -> pd.Timestamp:
        return self.momento + pd.Timedelta(minutes=self.candle)

    def evidencia(self, especialista: str, tipo: str, natureza: str, alvo: str, afirmacao: dict, origem: dict, dependencias: tuple[str, ...] = (),
                  forca: float | None = None, valido_ate: pd.Timestamp | None = None, **resto) -> Evidencia:
        return Evidencia(self.oportunidade, especialista, VERSAO, tipo, natureza, alvo, afirmacao, self.agora, self.momento,
                         valido_ate or self.validade, origem, dependencias, forca, **resto)


def _sinal(x: float) -> int:
    return int(np.sign(x)) if x == x else 0


def _alvo_direcao(ctx: Contexto, minutos: int) -> str:
    return f"fechamento(t+{minutos}min) > abertura(t+1min), {ctx.instrumento}, t = {ctx.momento.isoformat()}"


# ---------- Technical ----------

def technical(ctx: Contexto):
    ativos = {k: int(v) for k, v in ctx.sinais.items() if v}
    soma = sum(ativos.values())
    afirmacao = {"tecnicas": ativos, "a_favor_alta": sum(v > 0 for v in ativos.values()), "a_favor_baixa": sum(v < 0 for v in ativos.values()),
                 "direcao": _sinal(soma), "tempo_grafico": ctx.candle}
    return [ctx.evidencia("technical", "direcional", "regra", _alvo_direcao(ctx, ctx.candle), afirmacao,
                          {"modulo": "mneme.laboratorio.tecnicas.todas_as_tecnicas", "tempo": f"{ctx.candle}min"}, (ctx.dep_velas,),
                          forca=abs(soma) / len(ativos) if ativos else 0.0)], []


# ---------- Quant ----------

def escore_confluencia(modelo: dict, sinais: pd.Series) -> float:
    """A mesma conta de `laboratorio.confluencia.decidir`, sem o corte: o escore existe mesmo quando o motor não opera."""
    x = sinais.reindex(modelo["tecnicas"]).fillna(0).to_numpy(dtype=float)
    return float(1 / (1 + np.exp(-(modelo["intercepto"] + x @ np.asarray(modelo["pesos"])))))


def quant(ctx: Contexto):
    saida = []
    for e in ctx.estrategias:
        modelo = ctx.modelos_motor.get(e.arquivo)
        if modelo is None:
            continue
        p = escore_confluencia(modelo, ctx.sinais)
        afirmacao = {"chave": e.nome, "estrategia": e.nome, "escore_sobe": p, "corte": modelo["corte"], "passa_do_corte": abs(p - 0.5) >= modelo["corte"],
                     "direcao": 1 if p >= 0.5 else -1}
        saida.append(ctx.evidencia("quant", "direcional", "escore_modelo", _alvo_direcao(ctx, e.expiracao), afirmacao,
                                   {"modulo": "mneme.laboratorio.confluencia", "modelo": e.arquivo, "sha": modelo["_sha"]}, (ctx.dep_velas, f"modelo:{e.arquivo}@{modelo['_sha']}"),
                                   forca=abs(p - 0.5), desempenho_medido={**(modelo.get("evidencia") or {}), "treino_ate": modelo.get("ate"), "periodo": "desenvolvimento"}))
    previsoes = ctx.eventos.ler("previsoes", ctx.ativo, inicio=ctx.vela, como_de=ctx.conhecido_ate, agora=ctx.agora)
    if not previsoes.empty:
        previsoes = previsoes[previsoes["ocorrido_em"] == ctx.vela]
    for linha in previsoes.itertuples():
        m = ctx.manifestos.get(linha.modelo, {})
        metricas = m.get("metricas_fora_da_amostra", {})
        treino_ate = m.get("treino_ate")
        apos = bool(treino_ate) and ctx.momento > pd.Timestamp(treino_ate)
        base = {"modelo": linha.modelo, "horizonte": int(linha.horizonte), "recebido_em": linha.recebido_em.isoformat(), "apos_treino": apos}
        origem = {"modulo": "mneme.previsor", "artefato": linha.modelo, "hash": m.get("hash")}
        desempenho = {k: metricas.get(k) for k in ("acerto", "auc", "brier", "erro_calibracao")} | {"treino_de": m.get("treino_de"), "treino_ate": treino_ate,
                                                                                                      "periodo": "fora da amostra no treino (dobras)"}
        deps = (f"previsor:{linha.modelo}",)
        alvo = _alvo_direcao(ctx, int(linha.horizonte))
        saida.append(ctx.evidencia("quant", "direcional", "previsao_modelo", alvo, {**base, "chave": f"{linha.modelo}|bruta", "prob_sobe": float(linha.prob_sobe_bruta),
                                   "versao_prob": "bruta", "direcao": 1 if linha.prob_sobe_bruta >= 0.5 else -1}, origem, deps,
                                   forca=abs(float(linha.prob_sobe_bruta) - 0.5), desempenho_medido=desempenho))
        # A calibrada do treino não vira `confianca`: só depois de validada ao vivo, com dados posteriores ao treino.
        calibracao = {"metodo": "calibração do treino (manifesto do previsor)", "validada": False,
                      "erro_calibracao_fora_da_amostra": metricas.get("erro_calibracao_calibrado"), "brier_fora_da_amostra": metricas.get("brier_calibrado")}
        saida.append(ctx.evidencia("quant", "direcional", "previsao_modelo", alvo, {**base, "chave": f"{linha.modelo}|calibrada", "prob_sobe": float(linha.prob_sobe),
                                   "versao_prob": "calibrada_no_treino", "direcao": int(linha.direcao)}, origem, deps,
                                   forca=abs(float(linha.prob_sobe) - 0.5), calibracao=calibracao, desempenho_medido=desempenho))
    return saida, []


# ---------- Order Flow ----------

def order_flow(ctx: Contexto):
    inicio = ctx.momento - pd.Timedelta(minutes=ctx.candle)
    trades = ctx.eventos.ler("trades", ctx.ativo, inicio=inicio, como_de=ctx.conhecido_ate, fim=ctx.momento, agora=ctx.agora)
    livro = ctx.eventos.ler("livro", ctx.ativo, inicio=ctx.momento - pd.Timedelta(minutes=5), como_de=ctx.conhecido_ate, fim=ctx.momento, agora=ctx.agora)
    funding = ctx.eventos.ler("funding", ctx.ativo, inicio=ctx.momento - pd.Timedelta(days=1), como_de=ctx.conhecido_ate, fim=ctx.momento, agora=ctx.agora)
    oi = ctx.eventos.ler("open_interest", ctx.ativo, inicio=ctx.momento - pd.Timedelta(hours=1), como_de=ctx.conhecido_ate, fim=ctx.momento, agora=ctx.agora)
    afirmacao: dict = {"janela_min": ctx.candle}
    if trades.empty:
        afirmacao |= {"sem_dado": ["trades"], "direcao": 0}
        forca = None
    else:
        valor = trades["preco"] * trades["quantidade"]
        compra = float(valor[trades["comprador_agressor"]].sum())
        venda = float(valor[~trades["comprador_agressor"]].sum())
        agressao = (compra - venda) / (compra + venda) if compra + venda else 0.0
        afirmacao |= {"agressao": agressao, "negocios": int(len(trades)), "volume_usd": compra + venda, "direcao": _sinal(agressao)}
        forca = abs(agressao)
    if not livro.empty:
        u = livro.iloc[-1]
        afirmacao |= {"desequilibrio_5": float(u["desequilibrio_5"]), "desequilibrio_20": float(u["desequilibrio_20"]), "spread_bps": float(u["spread_bps"]),
                      "livro_idade_s": (ctx.momento - u["ocorrido_em"]).total_seconds()}
    if not funding.empty:
        afirmacao |= {"funding": float(funding.iloc[-1]["funding"]), "funding_idade_h": (ctx.momento - funding.iloc[-1]["ocorrido_em"]).total_seconds() / 3600}
    if len(oi) >= 2 and "open_interest" in oi:
        afirmacao |= {"variacao_oi_1h": float(oi.iloc[-1]["open_interest"] / oi.iloc[0]["open_interest"] - 1)}
    deps = tuple(f"eventos:{t}:{ctx.ativo}@{ctx.conhecido_ate.isoformat()}" for t in ("trades", "livro", "funding", "open_interest"))
    return [ctx.evidencia("order_flow", "fluxo", "observacao", f"fluxo de {ctx.instrumento} em [t-{ctx.candle}min, t), t = {ctx.momento.isoformat()}",
                          afirmacao, {"modulo": "mneme.dados.eventos"}, deps, forca=forca)], []


# ---------- Market Intelligence ----------

def market_intel(ctx: Contexto):
    noticias = [c for c in ctx.diario.contexto_vigente(ASSUNTOS.get(ctx.ativo, ()), ctx.momento) if c["tipo"] == "noticia"]
    total = sum(int(c["valor"].get("sentimento", 0)) for c in noticias)
    itens = [{"titulo": c["valor"].get("titulo", "")[:100], "sentimento": c["valor"].get("sentimento"), "origem": c["origem"], "criado_em": c["criado_em"],
              "valido_ate": c["valido_ate"]} for c in noticias[:10]]
    saida = [ctx.evidencia("market_intel", "direcional", "contexto_textual", f"sentimento das notícias vigentes sobre {ctx.ativo}, t = {ctx.momento.isoformat()}",
                           {"noticias": itens, "sentimento_total": total, "direcao": _sinal(total)}, {"modulo": "mneme.motor.leitor", "fonte": "diario.contexto"},
                           ("diario:contexto",), forca=float(min(abs(total), 3)) / 3 if noticias else None)]
    horizonte = max([ctx.candle] + [e.expiracao for e in ctx.estrategias])
    agenda = ctx.eventos.agenda(ctx.momento, ctx.momento + pd.Timedelta(minutes=horizonte + 60))
    eventos = [] if agenda.empty else [{"nome": str(r["nome"])[:80], "moeda": r["moeda"], "impacto": r["impacto"], "quando": r["ocorrido_em"].isoformat()}
                                       for _, r in agenda.iterrows()]
    saida.append(ctx.evidencia("market_intel", "evento", "observacao", f"eventos do calendário até t+{horizonte + 60}min, t = {ctx.momento.isoformat()}",
                               {"eventos": eventos, "alto_impacto": any(e["impacto"] == "High" for e in eventos)}, {"modulo": "mneme.dados.calendario"},
                               (f"eventos:calendario@{ctx.conhecido_ate.isoformat()}",)))
    return saida, []


# ---------- Knowledge ----------

def knowledge(ctx: Contexto):
    chaves = tuple(chave_da_estrategia(e) for e in ctx.estrategias)
    notas = [c for c in ctx.diario.contexto_vigente(chaves, ctx.momento) if c["tipo"] == "conhecimento"] if chaves else []
    itens = [{"estrategia": c["ativo"], "titulo": c["valor"].get("titulo", "")[:100], "nota": c["valor"].get("origem"), "confiabilidade": c["valor"].get("confiabilidade"),
              "suspeito": c["valor"].get("suspeito")} for c in notas]
    return [ctx.evidencia("knowledge", "conhecimento", "contexto_textual", f"conhecimento vigente sobre as estratégias de {ctx.ativo} {ctx.candle}min",
                          {"notas": itens}, {"modulo": "mneme.motor.conhecimento", "fonte": "rag:biblioteca"}, ("diario:contexto",),
                          valido_ate=ctx.momento + pd.Timedelta(hours=1))], []


# ---------- Risk ----------

def _regra(motivo: str) -> str:
    texto = re.sub(r"[\d.,%]+", "", motivo.split(":")[0]).strip().lower()
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento).strip("_") or "restricao"


def estado_no_momento(diario: DiarioSoLeitura, estrategia: str, momento: pd.Timestamp, banca: float, kill_switch: bool) -> Estado:
    """A carteira como estava no instante da decisão, só com o que o diário já sabia: reproduzível e sem contar a própria decisão."""
    q, t = diario.con.execute, momento.isoformat()
    dia = dia_brasilia(momento.to_pydatetime())
    operadas = "tipo = 'operada' AND decidido_em < ?"
    aberta = f"{operadas} AND (encerrado_em IS NULL OR encerrado_em > ?)"
    hoje = q(f"SELECT COUNT(*) FROM decisoes WHERE estrategia = ? AND {operadas} AND dia = ?", (estrategia, t, dia)).fetchone()[0]
    na_estrategia = q(f"SELECT 1 FROM decisoes WHERE estrategia = ? AND {aberta} LIMIT 1", (estrategia, t, t)).fetchone() is not None
    total = q(f"SELECT COUNT(*) FROM decisoes WHERE {aberta}", (t, t)).fetchone()[0]
    fechadas = f"{operadas} AND situacao = 'encerrada' AND encerrado_em <= ?"
    pnl_dia = q(f"SELECT COALESCE(SUM(pnl), 0) FROM decisoes WHERE estrategia = ? AND {fechadas} AND dia_encerramento = ?", (estrategia, t, t, dia)).fetchone()[0]
    perdas = 0
    for linha in q(f"SELECT resultado FROM decisoes WHERE estrategia = ? AND {fechadas} AND dia_encerramento = ? ORDER BY encerrado_em DESC, vela DESC", (estrategia, t, t, dia)):
        if linha["resultado"] != "perda":
            break
        perdas += 1
    saldo = pico = banca
    for linha in q(f"SELECT pnl FROM decisoes WHERE estrategia = ? AND {fechadas} ORDER BY encerrado_em, vela", (estrategia, t, t)):
        saldo += linha["pnl"]
        pico = max(pico, saldo)
    return Estado(kill_switch=kill_switch, idade_dados_min=0.0, chave_repetida=False, aberta_na_estrategia=na_estrategia, abertas_total=total,
                  operacoes_hoje=hoje, retorno_dia_pct=pnl_dia / banca * 100, perdas_seguidas=perdas,
                  drawdown_pct=(pico - saldo) / pico * 100 if pico > 0 else 100.0)


def risco(ctx: Contexto):
    """Determinístico: a mesma função `avaliar` do motor e as mesmas travas da decisão. Só registra; não executa nada."""
    evidencias, restricoes = [], []
    cfg = ctx.config
    for e in ctx.estrategias:
        modelo = ctx.modelos_motor.get(e.arquivo)
        estado = estado_no_momento(ctx.diario, e.nome, ctx.momento, cfg.banca, ctx.kill_switch)
        chave = f"{e.nome}|{ctx.vela.isoformat()}"
        aprovacao, motivos = avaliar(chave, estado, cfg.limites, cfg.risco_por_operacao)
        evidencia = (modelo or {}).get("evidencia") or {}
        expectativa = e.modalidade.expectativa(evidencia)
        travas = list(motivos)
        if modelo is None:
            travas.append("sem modelo medido nesta modalidade")
        else:
            direcao = 1 if escore_confluencia(modelo, ctx.sinais) >= 0.5 else -1
            if not e.modalidade.permite(direcao):
                travas.append("esta modalidade não permite vender")
            if evidencia.get("operacoes", 0) < cfg.min_operacoes_evidencia:
                travas.append(f"evidência curta: {evidencia.get('operacoes', 0)} operações medidas")
            if expectativa is None or expectativa <= 0:
                travas.append("expectativa não positiva nesta modalidade")
        for motivo in travas:
            restricoes.append(Restricao(ctx.oportunidade, e.nome, _regra(motivo), "veto", motivo, "", ctx.fonte_config, ctx.momento, ctx.validade))
        if not travas:
            restricoes.append(Restricao(ctx.oportunidade, e.nome, "tamanho_maximo", "teto", str(cfg.risco_por_operacao), str(cfg.risco_por_operacao),
                                        ctx.fonte_config, ctx.momento, ctx.validade))
        info = {"chave": e.nome, "estrategia": e.nome, "modalidade": e.modalidade.tipo, "expiracao": e.expiracao, "expectativa": expectativa,
                "payout": getattr(e.modalidade, "payout", None), "empate": (1 / (1 + e.modalidade.payout)) if hasattr(e.modalidade, "payout") else None,
                "custo_bps": getattr(e.modalidade, "custo_bps", None), "payout_medido": getattr(e.modalidade, "payout_medido", None),
                "estado": {k: getattr(estado, k) for k in ("abertas_total", "operacoes_hoje", "retorno_dia_pct", "perdas_seguidas", "drawdown_pct")},
                "aprovaria": not travas}
        evidencias.append(ctx.evidencia("risco", "informacao_risco", "observacao", f"estado de risco de {e.nome} em t = {ctx.momento.isoformat()}", info,
                                        {"modulo": "mneme.motor.risco.avaliar", "config": ctx.fonte_config}, ("diario:decisoes", f"config:{ctx.fonte_config}")))
    return evidencias, restricoes


ESPECIALISTAS = {"technical": technical, "quant": quant, "order_flow": order_flow, "market_intel": market_intel, "knowledge": knowledge, "risco": risco}


def sha_arquivo(caminho: Path) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()[:12]


def carregar_modelos_motor(pasta: Path) -> dict:
    modelos = {}
    for a in Path(pasta).glob("*.json"):
        m = json.loads(a.read_text(encoding="utf-8"))
        m["_sha"] = sha_arquivo(a)
        modelos[a.name] = m
    return modelos


def carregar_manifestos(pasta: Path) -> dict:
    saida = {}
    for a in Path(pasta).glob("*/manifesto.json"):
        m = json.loads(a.read_text(encoding="utf-8"))
        saida[m["id"]] = m
    return saida
