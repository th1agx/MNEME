"""O ciclo do robô em tempo real: vela fechada, técnicas, decisão, risco, sinal, execução, apuração e diário. Nada aqui espera a LLM."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..carteira_tecnicas import ultima_vela_fechada
from ..dados.armazem import ArmazemVelas, agora_utc
from ..dados.eventos import ArmazemEventos
from ..forex import eventos_altos_relevantes, moedas_do_par
from ..laboratorio.confluencia import decidir as decidir_confluencia, grade_de_sinais
from .decisao import bloqueio_multitempo, decidir_operacao
from .diario import Diario
from .execucao import criar_executor
from .conhecimento import chave_da_estrategia
from .modalidades import ComStop, Configuracao, Estrategia, amplitude_media, carregar_configuracao, liquidar_fixa, liquidar_stop
from .risco import Aprovacao, Estado, avaliar
from .sinal import chave_da_decisao, como_dicionario, criar_sinal

log = logging.getLogger("mneme.motor")

DIAS_DE_JANELA = {1: 4, 5: 12, 15: 30, 60: 60}
UM_MINUTO = pd.Timedelta(minutes=1)
# A que assuntos da leitura de notícias cada ativo responde.
ASSUNTOS = {"BTCUSDT": ("BTC",), "ETHUSDT": ("ETH",), "SOLUSDT": ("SOL",), "EURUSD": ("EURUSD", "EUR", "USD", "JUROS_EUA"),
            "EURGBP": ("EURGBP", "EUR", "GBP", "JUROS_EUA", "JUROS_REINO_UNIDO"), "USDJPY": ("USDJPY", "USD", "JPY", "JUROS_EUA", "JUROS_JAPAO"),
            "EURJPY": ("EURJPY", "EUR", "JPY", "JUROS_EUA", "JUROS_JAPAO"), "GBPUSD": ("GBP", "USD", "JUROS_EUA", "JUROS_REINO_UNIDO"),
            "XAUUSD": ("OURO", "USD", "JUROS_EUA")}


def carregar_modelos(pasta: Path) -> dict[str, dict]:
    if not pasta.exists():
        return {}
    return {a.name: json.loads(a.read_text(encoding="utf-8")) for a in pasta.glob("*.json")}


class Motor:
    def __init__(self, raiz: Path | str, configuracao: Configuracao | None, diario: Diario, pasta_modelos: Path, relogio: Callable[[], datetime] = agora_utc, velas=None, parar_em: Path | None = None):
        self.raiz, self.config, self.diario, self.pasta_modelos, self.relogio = Path(raiz), configuracao, diario, Path(pasta_modelos), relogio
        self.velas = velas or ArmazemVelas(raiz)
        self.eventos = ArmazemEventos(raiz)
        self.batimento = self.raiz / "motor.batimento"
        self.parar_em = parar_em or self.raiz.parent / "PARAR"
        self.executor = criar_executor(configuracao.modo, diario) if configuracao else None
        self.vistas: set[str] = set()

    def ciclo(self) -> dict:
        agora = pd.Timestamp(self.relogio())
        self.batimento.parent.mkdir(parents=True, exist_ok=True)
        self.batimento.write_text(agora.isoformat(), encoding="utf-8")
        resumo = {"apuradas": self.apurar(agora), "operadas": 0, "sombra": 0, "sem_oportunidade": 0}
        if self.config is None:
            return resumo  # sem configuração, o robô só observa
        modelos = carregar_modelos(self.pasta_modelos)
        grades: dict[tuple[str, int, pd.Timestamp], tuple[pd.DataFrame, pd.DataFrame]] = {}
        for e in self.config.estrategias:
            modelo = modelos.get(e.arquivo)
            if modelo is None:
                continue  # sem medição nesta modalidade, a estratégia não opera
            ultima = self.velas.ultima_abertura(e.ativo)
            if ultima is None:
                continue
            vela = ultima_vela_fechada(ultima, e.candle)
            marca = f"{e.nome}|{vela.isoformat()}"
            if marca in self.vistas:
                continue
            self.vistas.add(marca)
            if agora - vela - UM_MINUTO > pd.Timedelta(minutes=self.config.limites.idade_maxima_dados_min or 0) * 3:
                continue  # vela antiga, de um reinício ou de fonte parada: decidir agora seria fingir que era a hora
            chave = (e.ativo, e.candle, vela)
            if chave not in grades:
                v = self.velas.ler(e.ativo, inicio=(agora - timedelta(days=DIAS_DE_JANELA.get(e.candle, 30))).to_pydatetime(), como_de=agora.to_pydatetime())
                v = v[v.index <= vela]
                grades[chave] = (grade_de_sinais(v, e.candle), v)
            sinais, v = grades[chave]
            if vela not in sinais.index or v.empty:
                continue
            feito = self._decidir(e, modelo, sinais.loc[vela], vela, v, agora, modelos)
            resumo[feito] += 1
        return resumo

    def _decidir(self, e: Estrategia, modelo: dict, linha: pd.Series, vela: pd.Timestamp, v: pd.DataFrame, agora: pd.Timestamp, modelos: dict[str, dict]) -> str:
        contexto = self.diario.contexto_vigente(ASSUNTOS.get(e.ativo, ()) + (chave_da_estrategia(e),), agora)
        base = decidir_confluencia(modelo, linha)
        bloqueios = list(self._bloqueios_calendario(e, agora))
        if base is not None:
            bloqueio = self._bloqueio_multitempo(e, v, vela, int(base["direcao"]), modelos)
            if bloqueio:
                bloqueios.append(bloqueio)
        d = decidir_operacao(e, modelo, linha, vela, self.config.min_operacoes_evidencia, contexto, tuple(bloqueios))
        if d is None:
            return "sem_oportunidade"
        amplitude = amplitude_media(v, e.candle)
        valor = float(amplitude.iloc[-1]) if len(amplitude) and amplitude.index[-1] == vela and pd.notna(amplitude.iloc[-1]) else None
        decidido_em = pd.Timestamp(self.relogio())
        sinal = criar_sinal(d, float(v["fechamento"].iloc[-1]), valor, decidido_em)
        if sinal is None:
            return "sem_oportunidade"
        chave = chave_da_decisao(d)
        registro = {"chave": chave, "estrategia": e.nome, "mercado": e.mercado, "ativo": e.ativo, "modalidade": e.modalidade.tipo, "vela": vela, "decidido_em": decidido_em, "latencia_s": (decidido_em - vela - UM_MINUTO).total_seconds(), "direcao": d.direcao, "forca": d.forca,
                    "expectativa": d.expectativa, "evidencia": {k: d.evidencia.get(k) for k in ("operacoes", "acerto", "ic95_dias", "r_bruto")}, "motivo": d.motivo_tecnico, "contexto": d.contexto, "sinal": como_dicionario(sinal)}
        situacao = self.diario.situacao_da_estrategia(e.nome, agora, self.config.banca)
        estado = Estado(kill_switch=self.parar_em.exists(), idade_dados_min=(agora - vela - UM_MINUTO).total_seconds() / 60, chave_repetida=self.diario.conhecida(chave), **situacao)
        aprovacao, recusa = avaliar(chave, estado, self.config.limites, self.config.risco_por_operacao)
        motivos = d.motivos_contra + recusa
        if d.operar and isinstance(aprovacao, Aprovacao):
            self.executor.executar(aprovacao, **registro, motivos_recusa=())
            return "operadas"
        # O resultado da sombra é por unidade: ela mede o que teria acontecido, sem pesar no risco da carteira.
        self.diario.registrar(**registro, motivos_recusa=motivos, tipo="sombra", tamanho=1.0)
        return "sombra"

    def _bloqueio_multitempo(self, e: Estrategia, v: pd.DataFrame, vela: pd.Timestamp, direcao: int, modelos: dict[str, dict]) -> str | None:
        """Para Forex, o próximo candle maior configurado confirma a entrada menor.

        Com M5 e M15 na configuração, M5 só avança quando a última M15 fechada
        também passa pelo seu corte aprendido e aponta o mesmo lado. M15 continua
        como uma leitura de contexto por si só; os tempos vêm da configuração.
        """
        if e.mercado != "forex":
            return None
        maiores = sorted((outra for outra in self.config.estrategias if outra.ativo == e.ativo and outra.mercado == e.mercado
                          and outra.modalidade.tipo == e.modalidade.tipo and outra.candle > e.candle), key=lambda outra: outra.candle)
        if not maiores:
            return None
        maior = maiores[0]
        modelo = modelos.get(maior.arquivo)
        if modelo is None:
            return f"{maior.candle}m: modelo não disponível"
        grade = grade_de_sinais(v, maior.candle)
        grade = grade.loc[grade.index <= vela]
        confirmacao = decidir_confluencia(modelo, grade.iloc[-1]) if len(grade) else None
        return bloqueio_multitempo(direcao, confirmacao, f"{maior.candle}m")

    def _bloqueios_calendario(self, e: Estrategia, agora: pd.Timestamp) -> tuple[str, ...]:
        """Bloqueia só o Forex configurado quando a agenda High torna o preço instável.

        O filtro não aponta direção e nunca consulta a internet no caminho de tempo
        real: lê a cópia local do calendário, com a hora em que cada evento chegou.
        Sem uma política configurada, Forex fica em sombra para não fingir que a
        agenda foi considerada.
        """
        if e.mercado != "forex" or not moedas_do_par(e.ativo):
            return ()
        janela = self.config.limites.janela_calendario_min
        if janela is None:
            return ("calendário: política não configurada",)
        try:
            agenda = self.eventos.ler("calendario", "GLOBAL", inicio=(agora - pd.Timedelta(minutes=janela)).to_pydatetime(),
                                      fim=(agora + pd.Timedelta(minutes=janela + 1)).to_pydatetime())
            relevantes = eventos_altos_relevantes(agenda, e.ativo, agora, janela)
        except (OSError, ValueError, KeyError):
            return ("calendário: indisponível",)
        return tuple(f"calendário: {str(linha.nome)[:80]} em {pd.Timestamp(linha.ocorrido_em):%H:%M} UTC"
                     for linha in relevantes.itertuples())

    def apurar(self, agora: pd.Timestamp) -> int:
        """Apura tudo o que já venceu, operado ou não. Sem preço depois de um dia, fica como sem_preco e nunca é contado como ganho ou perda."""
        apuradas = 0
        abertas = self.diario.abertas()
        por_ativo: dict[str, pd.DataFrame] = {}
        for linha in abertas:
            sinal = json.loads(linha["sinal"])
            entrada = pd.Timestamp(sinal["entrada_em"])
            duracao = sinal.get("expiracao_min") or sinal["tempo_max_min"]
            vence = entrada + pd.Timedelta(minutes=duracao)
            if vence > agora:
                continue
            if linha["ativo"] not in por_ativo:
                inicio = min(pd.Timestamp(json.loads(l["sinal"])["entrada_em"]) for l in abertas if l["ativo"] == linha["ativo"])
                por_ativo[linha["ativo"]] = self.velas.ler(linha["ativo"], inicio=inicio.to_pydatetime(), como_de=agora.to_pydatetime())
            v = por_ativo[linha["ativo"]]
            if linha["modalidade"] == "expiracao_fixa":
                apurado = liquidar_fixa(v, entrada, duracao, linha["direcao"], sinal["payout"])
            else:
                apurado = liquidar_stop(v, entrada, duracao, linha["direcao"], sinal["distancia_stop"], sinal["distancia_alvo"], sinal["custo_bps"])
            if apurado is not None:
                self.diario.encerrar(linha["chave"], apurado, agora)
                apuradas += 1
            elif agora - vence > pd.Timedelta(days=1):
                self.diario.encerrar(linha["chave"], None, agora)
        return apuradas


__all__ = ["ComStop", "Motor", "carregar_configuracao", "carregar_modelos"]
