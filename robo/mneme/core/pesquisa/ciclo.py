"""Uma volta do E9 generativo: confirmar uma promissora pendente ou gerar, checar, rodar e medir uma ideia nova."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ...aprendizado import EXPLORACAO_ATE, PAYOUT, periodo
from ...laboratorio.backtest import apostas_direcao, medir_direcao, placebo_direcao
from . import agenda, gerador
from .arquivo import Arquivo, impressao_do_codigo
from .sandbox import SandboxDocker
from .seguranca import CodigoRecusado, validar

# A geração vê só os últimos 6 meses antes do fim da exploração: o bastante para medir e leve para a A1 (2 núcleos).
JANELA_EXPLORACAO = pd.Timedelta(days=183)


def dados_de_exploracao(v: pd.DataFrame) -> pd.DataFrame:
    return v[(v.index >= EXPLORACAO_ATE - JANELA_EXPLORACAO) & (v.index < EXPLORACAO_ATE)]


def medir(sinal: pd.Series, v: pd.DataFrame, minutos: int, payout: float = PAYOUT) -> dict:
    """A mesma medida do E9 de enumeração. Sem filtro para comparar, a referência é o placebo (mesmos momentos, direção sorteada)."""
    com = medir_direcao(apostas_direcao(v, sinal, minutos, payout), payout)
    atraso = medir_direcao(apostas_direcao(v, sinal, minutos, payout, atraso_velas=1), payout)
    placebo = placebo_direcao(v, sinal, minutos, payout, sementes=3)
    referencia = float(np.mean(placebo)) if placebo else float("nan")
    return {**com.como_dict(), "acerto_com_atraso_1min": atraso.acerto, "placebo": referencia, "acerto_sem_filtro": referencia,
            "sinais_brutos": int((sinal != 0).sum()), "de": str(v.index[0]), "ate": str(v.index[-1])}


def ciclo(arquivo: Arquivo, ler_velas: Callable[[str], pd.DataFrame], roteador, sandbox=None, rng: np.random.Generator | None = None,
          agora: datetime | None = None) -> dict:
    agora = agora or datetime.now(timezone.utc)
    sandbox = sandbox or SandboxDocker()
    rng = rng or np.random.default_rng(len(arquivo.todas()))

    pendentes = arquivo.pendentes_de_confirmacao()
    if pendentes:
        e = pendentes[0]
        braco, proposta = e["braco"], {k: e[k] for k in ("ideia", "mecanismo", "codigo", "fonte")}
        v = periodo(ler_velas(braco["par"]), "confirmacao")
        execucao = sandbox.executar(proposta["codigo"], v)
        if execucao.erro:
            return arquivo.anotar(agora, "confirmacao", braco, proposta, etapa_falha="execucao", motivo_falha=execucao.erro)
        return arquivo.anotar(agora, "confirmacao", braco, proposta, medir(execucao.sinal, v, int(braco["minutos"])))

    par, minutos = agenda.escolher(arquivo.estatisticas_por_braco(), rng)
    braco = {"par": par, "minutos": minutos}
    try:
        proposta = gerador.propor(roteador, arquivo.resumo_para_pesquisador(), par, minutos).como_dict()
    except (ConnectionError, ValueError) as erro:
        return arquivo.anotar(agora, "exploracao", braco, {"ideia": "", "codigo": ""}, etapa_falha="geracao", motivo_falha=f"{type(erro).__name__}: {erro}")
    try:
        validar(proposta["codigo"])
    except CodigoRecusado as erro:
        return arquivo.anotar(agora, "exploracao", braco, proposta, etapa_falha="seguranca", motivo_falha=str(erro))
    if impressao_do_codigo(proposta["codigo"]) in arquivo.impressoes():
        return arquivo.anotar(agora, "exploracao", braco, proposta, etapa_falha="repetida", motivo_falha="código igual a uma tentativa anterior")
    v = dados_de_exploracao(ler_velas(par))
    if v.empty:
        return arquivo.anotar(agora, "exploracao", braco, proposta, etapa_falha="dados", motivo_falha="sem velas no período de exploração")
    execucao = sandbox.executar(proposta["codigo"], v)
    if execucao.erro:
        return arquivo.anotar(agora, "exploracao", braco, proposta, etapa_falha="olha_o_futuro" if execucao.olha_o_futuro else "execucao",
                              motivo_falha=execucao.erro)
    resultado = medir(execucao.sinal, v, minutos)
    if not resultado["sinais"]:
        return arquivo.anotar(agora, "exploracao", braco, proposta, etapa_falha="sem_sinais", motivo_falha="a estratégia não gerou nenhuma aposta")
    return arquivo.anotar(agora, "exploracao", braco, proposta, resultado)
