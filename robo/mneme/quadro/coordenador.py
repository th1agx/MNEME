"""Coordenador-sombra (F1): abre a oportunidade, pede a cada especialista com orçamento de tempo e grava tudo. Não decide.

Pedidos são fixos na F1 (todos os especialistas, sempre). Falha ou tempo esgotado de um especialista vira registro e não
para os outros. O motor não lê nada daqui.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TempoEsgotado
from pathlib import Path

import numpy as np
import pandas as pd

from ..carteira_tecnicas import ultima_vela_fechada
from ..dados.armazem import ArmazemVelas, agora_utc
from ..dados.eventos import ArmazemEventos
from ..laboratorio.confluencia import grade_de_sinais
from ..motor.ciclo import DIAS_DE_JANELA
from ..motor.modalidades import carregar_configuracao
from .banco import Quadro
from .esquema import ErroEsquema, Instrumento, Oportunidade, impressao
from .especialistas import CORTE, ESPECIALISTAS, Contexto, carregar_manifestos, carregar_modelos_motor, sha_arquivo
from .fontes import DiarioSoLeitura, EventosEmCache, LeitorEventos

HORIZONTES = (1, 5, 15, 60)
GUARDAR = {"trades": pd.Timedelta(minutes=30), "livro": pd.Timedelta(minutes=30), "previsoes": pd.Timedelta(hours=3),
           "funding": pd.Timedelta(days=2), "open_interest": pd.Timedelta(hours=3)}


class Coordenador:
    def __init__(self, raiz_mercado: Path | str, quadro: Quadro, diario: Path | str, operacao: Path | str, modelos_motor: Path | str,
                 modelos: Path | str, relogio=agora_utc, velas=None, eventos: ArmazemEventos | None = None, usar_cache: bool = True,
                 orcamento_s: float = 2.0, orcamento_total_s: float = 10.0, especialistas: dict | None = None):
        self.raiz = Path(raiz_mercado)
        self.quadro, self.caminho_diario, self.operacao = quadro, Path(diario), Path(operacao)
        self.pasta_motor, self.pasta_modelos = Path(modelos_motor), Path(modelos)
        self.relogio = relogio
        self.velas = velas or ArmazemVelas(self.raiz)
        self.armazem = eventos or ArmazemEventos(self.raiz)
        self.cache = EventosEmCache(self.armazem, GUARDAR) if usar_cache else None
        self.orcamento_s, self.orcamento_total_s = orcamento_s, orcamento_total_s
        self.especialistas = especialistas or ESPECIALISTAS
        self.executor = ThreadPoolExecutor(max_workers=len(self.especialistas), thread_name_prefix="especialista")

    # ---------- montagem ----------

    def aquecer(self) -> None:
        """Lê antes do primeiro ciclo as partes do dia que os especialistas vão pedir: o primeiro minuto não estoura o orçamento."""
        config, _ = self._config()
        if config is None or self.cache is None:
            return
        agora = pd.Timestamp(self.relogio())
        for ativo in sorted({a for (_, a, _) in self.grupos(config)}):
            for tipo, janela in GUARDAR.items():
                self.cache.ler(tipo, ativo, (agora - janela).to_pydatetime(), None, agora.to_pydatetime(), agora)

    def _config(self):
        config = carregar_configuracao(self.operacao)
        return config, (f"{self.operacao.name}@{sha_arquivo(self.operacao)}" if self.operacao.exists() else "sem_config")

    def grupos(self, config) -> dict[tuple[str, str, int], tuple]:
        """Uma oportunidade por instrumento e tempo gráfico; as estratégias desse par viram modalidades candidatas."""
        saida: dict[tuple[str, str, int], list] = {}
        for e in config.estrategias:
            saida.setdefault((e.mercado, e.ativo, e.candle), []).append(e)
        return {k: tuple(v) for k, v in saida.items()}

    @staticmethod
    def oportunidade(mercado: str, ativo: str, candle: int, vela: pd.Timestamp, estrategias) -> Oportunidade:
        inst = Instrumento.do_ativo(mercado, ativo)
        modalidades = tuple({"tipo": e.modalidade.tipo, "estrategia": e.nome, "expiracao": e.expiracao, "local": inst.local} for e in estrategias)
        return Oportunidade((inst.id,), "vela_fechada", vela + pd.Timedelta(minutes=1), modalidades, HORIZONTES, candle)

    def _contexto(self, op: Oportunidade, mercado, ativo, candle, vela, estrategias, config, fonte_config, leitor, diario, agora) -> Contexto:
        momento = op.momento
        inicio = (momento - pd.Timedelta(days=DIAS_DE_JANELA.get(candle, 30))).to_pydatetime()
        # A vela fecha no momento, mas chega uns segundos depois: vale o mesmo corte de conhecimento dos eventos.
        v = self.velas.ler(ativo, inicio=inicio, como_de=(momento + CORTE).to_pydatetime())
        v = v[v.index <= vela]
        sinais = grade_de_sinais(v, candle)
        if v.empty or vela not in sinais.index:
            raise ErroEsquema("sem velas suficientes no momento")
        dep = f"velas:{ativo}:1m@{v.index[-1].isoformat()}:{len(v)}"
        return Contexto(op.id, op.instrumentos[0], ativo, mercado, candle, vela, momento, sinais.loc[vela], tuple(estrategias),
                        carregar_modelos_motor(self.pasta_motor), carregar_manifestos(self.pasta_modelos), config, fonte_config, leitor, diario,
                        (self.raiz.parent / "PARAR").exists(), dep, agora)

    # ---------- análise ----------

    def analisar(self, op: Oportunidade, mercado, ativo, candle, vela, estrategias, config, fonte_config, usar_cache: bool, agora: pd.Timestamp):
        leitor = LeitorEventos(self.armazem, self.cache if usar_cache else None)
        evidencias, restricoes, pedidos = [], [], []
        with DiarioSoLeitura(self.caminho_diario) as diario:
            ctx = self._contexto(op, mercado, ativo, candle, vela, estrategias, config, fonte_config, leitor, diario, agora)
            inicio_total = time.monotonic()
            futuros = {nome: (time.monotonic(), self.executor.submit(f, ctx)) for nome, f in self.especialistas.items()}
            for nome, (inicio, futuro) in futuros.items():
                restante = max(0.0, self.orcamento_total_s - (time.monotonic() - inicio_total))
                pedido = {"especialista": nome, "orcamento_s": self.orcamento_s}
                try:
                    evs, res = futuro.result(timeout=min(self.orcamento_s + 0.5, restante) if restante else 0.001)
                    for e in evs:
                        e.validar(op.momento)
                    for r in res:
                        r.validar()
                    gasto = time.monotonic() - inicio
                    pedido |= {"situacao": "ok" if gasto <= self.orcamento_s else "acima_do_orcamento", "segundos": gasto}
                    for e in evs:
                        e.pedido = {"segundos": round(gasto, 3), "situacao": pedido["situacao"]}
                    evidencias += evs
                    restricoes += res
                except TempoEsgotado:
                    pedido |= {"situacao": "tempo_esgotado", "segundos": time.monotonic() - inicio}
                except Exception as erro:  # um especialista com defeito nunca derruba os outros
                    pedido |= {"situacao": "erro", "segundos": time.monotonic() - inicio, "erro": f"{type(erro).__name__}: {erro}"[:300]}
                pedidos.append(pedido)
        return evidencias, restricoes, pedidos

    def ciclo(self) -> dict:
        agora = pd.Timestamp(self.relogio())
        resumo = {"novas": 0, "conhecidas": 0, "sem_dado": 0, "erros": 0, "disco_cheio": False}
        config, fonte_config = self._config()
        if config is None:
            return resumo
        if self.quadro.disco_cheio():
            resumo["disco_cheio"] = True
            return resumo
        for (mercado, ativo, candle), estrategias in self.grupos(config).items():
            ultima = self.velas.ultima_abertura(ativo)
            if ultima is None:
                resumo["sem_dado"] += 1
                continue
            vela = ultima_vela_fechada(ultima, candle)
            if agora - vela - pd.Timedelta(minutes=1) > pd.Timedelta(minutes=3 * candle + 3):
                resumo["sem_dado"] += 1  # fonte parada (Forex e ouro sem dado ao vivo caem aqui)
                continue
            op = self.oportunidade(mercado, ativo, candle, vela, estrategias)
            if self.quadro.conhecida(op.id):
                resumo["conhecidas"] += 1
                continue
            try:
                evs, res, pedidos = self.analisar(op, mercado, ativo, candle, vela, estrategias, config, fonte_config, True, agora)
            except Exception as erro:
                resumo["erros"] += 1
                print(json.dumps({"erro": f"{type(erro).__name__}: {erro}"[:300], "oportunidade": op.id}, ensure_ascii=False), flush=True)
                continue
            if self.quadro.gravar(op, evs, res, pedidos, impressao(evs, res), agora):
                resumo["novas"] += 1
        if self.cache is not None:
            self.cache.esquecer_dias_velhos(agora)
        return resumo

    # ---------- ligação, apuração, reprodução ----------

    def ligar(self, desde: pd.Timestamp) -> int:
        ligadas = 0
        with DiarioSoLeitura(self.caminho_diario) as diario:
            for linha in self.quadro.sem_ligacao(desde):
                vela = pd.Timestamp(linha["momento"]) - pd.Timedelta(minutes=1)
                nomes = [m["estrategia"] for m in json.loads(linha["modalidades"])]
                chaves = diario.decisoes_da_vela(nomes, vela)
                if chaves:
                    ligadas += self.quadro.ligar_motor(linha["id"], chaves)
        return ligadas

    def apurar(self) -> int:
        """Rótulos para a F3: entrada na abertura do minuto do momento, saída no fechamento `h` minutos depois (a convenção do motor)."""
        agora = pd.Timestamp(self.relogio())
        feitas = 0
        maior = max(HORIZONTES)
        for linha in self.quadro.a_apurar(agora - pd.Timedelta(minutes=maior + 2)):
            ativo = json.loads(linha["instrumentos"])[0].split(":")[-1]
            momento = pd.Timestamp(linha["momento"])
            v = self.velas.ler(ativo, inicio=momento.to_pydatetime(), fim=(momento + pd.Timedelta(minutes=maior + 1)).to_pydatetime(), como_de=agora.to_pydatetime())
            linhas = []
            for h in json.loads(linha["horizontes"]):
                fim = momento + pd.Timedelta(minutes=h - 1)
                if momento not in v.index or fim not in v.index:
                    linhas.append({"horizonte": h})
                    continue
                entrada, saida = float(v.at[momento, "abertura"]), float(v.at[fim, "fechamento"])
                passos = np.diff(np.log(v.loc[momento:fim, "fechamento"].to_numpy(dtype=float)))
                linhas.append({"horizonte": h, "entrada": entrada, "saida": saida, "retorno": saida / entrada - 1,
                               "direcao": int(np.sign(saida - entrada)), "volatilidade": float(passos.std()) if len(passos) > 1 else None})
            completa = all(l.get("entrada") is not None for l in linhas)
            self.quadro.gravar_apuracao(linha["id"], linhas, agora, "apurada" if completa else "sem_dado")
            feitas += 1
        return feitas

    def reproduzir(self, oportunidade_id: str) -> tuple[bool, str, str]:
        """Recalcula do zero, sem cache, com o que existia no momento, e compara a impressão digital com a gravada."""
        linha = self.quadro.oportunidade(oportunidade_id)
        config, fonte_config = self._config()
        mercado, ativo, candle = None, json.loads(linha["instrumentos"])[0].split(":")[-1], linha["tempo_grafico"]
        estrategias = [e for e in config.estrategias if e.ativo == ativo and e.candle == candle]
        mercado = estrategias[0].mercado
        vela = pd.Timestamp(linha["momento"]) - pd.Timedelta(minutes=1)
        op = self.oportunidade(mercado, ativo, candle, vela, estrategias)
        gravadas = self.quadro.evidencias(oportunidade_id)
        agora = pd.Timestamp(gravadas[0]["criada_em"]) if gravadas else pd.Timestamp(self.relogio())
        evs, res, _ = self.analisar(op, mercado, ativo, candle, vela, estrategias, config, fonte_config, False, agora)
        nova = impressao(evs, res)
        return nova == linha["impressao"], nova, linha["impressao"]
