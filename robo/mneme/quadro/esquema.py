"""Esquema do quadro: instrumento, oportunidade, evidência e restrição. Genérico por mercado, gatilho e modalidade."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

import pandas as pd

VERSAO = 1
TIPOS_AFIRMACAO = {"direcional", "distribuicao", "volatilidade", "nivel_preco", "fluxo", "evento", "discrepancia_preco",
                   "comportamento_carteiras", "conhecimento", "informacao_risco"}
NATUREZAS = {"observacao", "regra", "escore_modelo", "previsao_modelo", "probabilidade_calibrada", "contexto_textual"}
GATILHOS = {"vela_fechada", "evento_calendario", "discrepancia", "fluxo", "onchain", "relogio"}
EFEITOS = {"veto", "teto"}
# De onde vêm os preços de cada mercado hoje. Os outros mercados entram com o próprio conector, sem mudar o esquema.
LOCAL_POR_MERCADO = {"cripto": ("binance", "spot"), "forex": ("dukascopy", "spot"), "ouro": ("dukascopy", "spot")}


class ErroEsquema(ValueError):
    pass


def _iso(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").isoformat() if pd.Timestamp(t).tzinfo else pd.Timestamp(t).tz_localize("UTC").isoformat()


@dataclass(frozen=True)
class Instrumento:
    id: str
    mercado: str
    classe: str
    local: str
    base: str
    cotacao: str
    sessao: str

    @staticmethod
    def do_ativo(mercado: str, ativo: str) -> "Instrumento":
        local, classe = LOCAL_POR_MERCADO.get(mercado, (mercado, "spot"))
        base, cotacao = (ativo[:-4], "USDT") if ativo.endswith("USDT") else (ativo[:3], ativo[3:])
        return Instrumento(f"{local}:{classe}:{ativo}", mercado, classe, local, base, cotacao, "24x7" if mercado == "cripto" else mercado)


@dataclass
class Oportunidade:
    instrumentos: tuple[str, ...]
    gatilho: str
    momento: pd.Timestamp
    modalidades: tuple[dict, ...]
    horizontes: tuple[int, ...]
    tempo_grafico: int | None = None
    aberta_por: str = "coordenador-sombra"
    versao_esquema: int = VERSAO

    @property
    def id(self) -> str:
        return "|".join([",".join(self.instrumentos), self.gatilho, str(self.tempo_grafico or "-"), _iso(self.momento)])

    def validar(self) -> None:
        if not self.instrumentos:
            raise ErroEsquema("oportunidade sem instrumento")
        if self.gatilho not in GATILHOS:
            raise ErroEsquema(f"gatilho desconhecido: {self.gatilho}")
        if any(not m.get("tipo") for m in self.modalidades):
            raise ErroEsquema("modalidade sem tipo")


@dataclass
class Evidencia:
    oportunidade: str
    especialista: str
    versao: str
    tipo_afirmacao: str
    natureza: str
    alvo_estatistico: str
    afirmacao: dict
    criada_em: pd.Timestamp
    dados_ate: pd.Timestamp
    valido_ate: pd.Timestamp
    origem: dict
    dependencias: tuple[str, ...] = ()
    forca: float | None = None
    confianca: float | None = None
    calibracao: dict = field(default_factory=lambda: {"metodo": "nao_calibrada", "validada": False})
    desempenho_medido: dict | None = None
    pedido: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        chave = json.dumps([self.oportunidade, self.especialista, self.tipo_afirmacao, self.natureza, self.alvo_estatistico,
                            self.afirmacao.get("chave", "")], ensure_ascii=False)
        return hashlib.sha256(chave.encode()).hexdigest()[:20]

    def validar(self, momento: pd.Timestamp) -> None:
        if self.tipo_afirmacao not in TIPOS_AFIRMACAO:
            raise ErroEsquema(f"tipo de afirmação desconhecido: {self.tipo_afirmacao}")
        if self.natureza not in NATUREZAS:
            raise ErroEsquema(f"natureza desconhecida: {self.natureza}")
        if not self.alvo_estatistico:
            raise ErroEsquema("evidência sem alvo estatístico")
        if not self.origem or not self.origem.get("modulo"):
            raise ErroEsquema("evidência sem origem")
        if pd.Timestamp(self.dados_ate) > pd.Timestamp(momento):
            raise ErroEsquema("evidência usa dado posterior ao momento da decisão")
        if pd.Timestamp(self.valido_ate) <= pd.Timestamp(momento):
            raise ErroEsquema("evidência já nasce vencida")
        if self.confianca is not None:
            if not self.calibracao.get("validada"):
                raise ErroEsquema("confiança só com calibração validada fora da amostra")
            if not 0 <= self.confianca <= 1:
                raise ErroEsquema("confiança fora de [0, 1]")

    def conteudo(self) -> dict:
        """O que a evidência afirma, sem hora de criação nem latência: serve para conferir a reprodução."""
        d = {k: v for k, v in asdict(self).items() if k not in ("criada_em", "pedido")}
        return json.loads(json.dumps(d, default=str, ensure_ascii=False, sort_keys=True))


@dataclass
class Restricao:
    """Só o especialista de risco cria. Veto impede a operação; teto limita o tamanho. Nada passa por cima disso."""
    oportunidade: str
    modalidade: str
    regra: str
    efeito: str
    valor_atual: str
    limite: str
    fonte_config: str
    momento: pd.Timestamp
    valido_ate: pd.Timestamp

    @property
    def id(self) -> str:
        return hashlib.sha256(json.dumps([self.oportunidade, self.modalidade, self.regra]).encode()).hexdigest()[:20]

    def validar(self) -> None:
        if self.efeito not in EFEITOS:
            raise ErroEsquema(f"efeito desconhecido: {self.efeito}")


# O conhecimento do RAG é regravado de hora em hora no diário com os mesmos ids (motor/conhecimento.py): o de um momento
# passado não pode ser reconstruído. Ele fica fora da impressão de reprodução até a F2 tornar esse contexto só de acréscimo.
FORA_DA_REPRODUCAO = ("knowledge",)


def impressao(evidencias: list[Evidencia], restricoes: list[Restricao] = ()) -> str:
    """Impressão digital do que foi afirmado num momento. Igual na reprodução = mesmas evidências."""
    itens = sorted(json.dumps(e.conteudo(), sort_keys=True) for e in evidencias if e.especialista not in FORA_DA_REPRODUCAO)
    itens += sorted(json.dumps({k: str(v) for k, v in asdict(r).items()}, sort_keys=True) for r in restricoes)
    return hashlib.sha256("\n".join(itens).encode()).hexdigest()


def aplicar_restricoes(proposta: dict, restricoes: list[Restricao]) -> dict:
    """Filtro final, para qualquer Coordenador futuro: veto zera a operação e teto limita o tamanho. Nunca afrouxa nada."""
    saida = dict(proposta)
    da_modalidade = [r for r in restricoes if r.modalidade in (proposta.get("modalidade"), "*")]
    if any(r.efeito == "veto" for r in da_modalidade):
        saida["operar"], saida["tamanho"] = False, 0.0
        return saida
    tetos = [float(r.limite) for r in da_modalidade if r.efeito == "teto"]
    if tetos:
        saida["tamanho"] = min(float(saida.get("tamanho", 0.0)), *tetos)
    return saida
