"""A2 do E9 v2: hipóteses tipadas, num vocabulário fechado, registradas antes do teste num arquivo que só cresce.

Quem propõe (o dossiê, a LLM ou uma pessoa) só escolhe dentro do vocabulário. O que não cabe é recusado inteiro: texto livre
não vira experimento. Toda hipótese leva a impressão da régua e a hora do registro. O teste confirmatório só usa decisões
posteriores ao registro, porque a ideia nasceu olhando os dias anteriores. A hipótese contrária entra junto.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .regua import ATUAL, REGUAS, Regua

TIPOS = ("filtro", "selecao")  # parametro, atributo, modelo e estrategia entram quando o executor souber medi-los
REGIMES = tuple(f"{v}-{t}" for v in ("vol baixa", "vol media", "vol alta") for t in ("alta", "baixa", "lateral"))
# Só dimensões conhecidas no momento da decisão. A força em quintil usa o período todo e por isso fica de fora.
VOCABULARIO: dict[str, tuple] = {
    "regime": REGIMES,
    "tendencia": ("alta", "baixa", "lateral"),
    "vol_quintil": (1.0, 2.0, 3.0, 4.0, 5.0),
    "faixa_hora": tuple(f"{h:02d}-{h + 4:02d}h" for h in range(0, 24, 4)),
    "noticia": ("a favor", "contra", "neutra", "sem notícia"),
}
REGRAS_DE_SELECAO = {"acima_do_empate_ontem": "abaixo_do_empate_ontem", "abaixo_do_empate_ontem": "acima_do_empate_ontem"}
RIVAIS = ("olhar_o_futuro", "selecao", "acaso", "regime", "custo", "artefato_de_dado", "causa_comum", "causalidade_invertida")
ESTRATEGIA = re.compile(r"^[A-Z]{3,10}\|(expiracao_fixa|com_stop)\|\d{1,3}m\|\d{1,4}m$")
ORIGENS = ("dossie", "llm", "dono", "pessoa", "contraria", "enumeracao")


class FORA_DO_VOCABULARIO(ValueError):  # noqa: N801 - o nome diz o que aconteceu
    pass


class LimiteDoMes(Exception):
    """A régua limita as hipóteses confirmatórias do mês: mais testes, menos poder para cada um."""


@dataclass(frozen=True)
class Hipotese:
    tipo: str
    escopo: dict
    mudanca: dict
    previsao: str
    derrubaria: str
    rivais: tuple[str, ...]
    motivo: str
    origem: str
    regua: str
    registrada_em: str
    dados_a_partir_de: str
    contraria_de: str | None = None
    tipo_de_afirmacao: str = "previsao"
    id: str = field(default="")

    def __post_init__(self):
        chave = json.dumps({"tipo": self.tipo, "escopo": self.escopo, "mudanca": self.mudanca}, sort_keys=True, ensure_ascii=False)
        object.__setattr__(self, "id", "h-" + hashlib.sha256(chave.encode()).hexdigest()[:12])


def _texto(valor, limite: int = 300) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()[:limite]


def validar(bruta: dict, origem: str, quando: datetime, regua: Regua | None = None) -> Hipotese:
    regua = regua or REGUAS[ATUAL]
    erros = []
    tipo = bruta.get("tipo")
    if tipo not in TIPOS:
        erros.append("tipo")
    escopo = dict(bruta.get("escopo") or {})
    if set(escopo) - {"estrategia"} or ("estrategia" in escopo and not ESTRATEGIA.match(str(escopo["estrategia"]))):
        erros.append("escopo")
    mudanca = dict(bruta.get("mudanca") or {})
    if tipo == "filtro":
        dimensao, valores = mudanca.get("dimensao"), mudanca.get("operar_se")
        permitidos = VOCABULARIO.get(dimensao)
        if permitidos is None or not isinstance(valores, list) or not valores:
            erros.append("mudanca")
        else:
            valores = [float(x) if dimensao == "vol_quintil" and isinstance(x, (int, float)) else x for x in valores]
            if any(x not in permitidos for x in valores) or len(set(valores)) == len(permitidos):
                erros.append("mudanca")  # valor inventado, ou filtro que não tira nada
            else:
                mudanca = {"dimensao": dimensao, "operar_se": sorted(set(valores), key=permitidos.index)}
    elif tipo == "selecao" and (set(mudanca) != {"regra"} or mudanca["regra"] not in REGRAS_DE_SELECAO):
        erros.append("mudanca")
    previsao, derrubaria = _texto(bruta.get("previsao")), _texto(bruta.get("derrubaria"))
    if not previsao or not derrubaria:
        erros.append("previsao")
    rivais = tuple(dict.fromkeys(bruta.get("rivais") or []))
    if len(rivais) < 2 or any(r not in RIVAIS for r in rivais):
        erros.append("rivais")
    if origem not in ORIGENS:
        erros.append("origem")
    if erros:
        raise FORA_DO_VOCABULARIO(f"hipótese recusada: {', '.join(erros)}")
    momento = quando.isoformat()
    return Hipotese(tipo, escopo, mudanca, previsao, derrubaria, rivais, _texto(bruta.get("motivo")), origem, regua.impressao(), momento, momento,
                    bruta.get("contraria_de"))


def contraria(h: Hipotese, quando: datetime) -> Hipotese:
    """A explicação oposta: o complemento do filtro, ou a regra de seleção invertida. Ela é testada do mesmo jeito."""
    if h.tipo == "filtro":
        permitidos = VOCABULARIO[h.mudanca["dimensao"]]
        mudanca = {"dimensao": h.mudanca["dimensao"], "operar_se": [x for x in permitidos if x not in h.mudanca["operar_se"]]}
    else:
        mudanca = {"regra": REGRAS_DE_SELECAO[h.mudanca["regra"]]}
    momento = quando.isoformat()
    return Hipotese(h.tipo, h.escopo, mudanca, f"o oposto de: {h.previsao}"[:300], f"o oposto de: {h.derrubaria}"[:300], h.rivais,
                    f"contrária de {h.id}", "contraria", h.regua, momento, momento, h.id)


class Registro:
    """Arquivo JSONL só de acréscimo. Uma hipótese, uma linha, para sempre: as rejeitadas também ficam."""

    def __init__(self, caminho: Path | str, regua: Regua | None = None):
        self.caminho, self.regua = Path(caminho), regua or REGUAS[ATUAL]

    def todas(self) -> list[dict]:
        if not self.caminho.exists():
            return []
        return [json.loads(l) for l in self.caminho.read_text(encoding="utf-8").splitlines() if l.strip()]

    def registrar(self, h: Hipotese, exploratoria: bool = False) -> bool:
        existentes = self.todas()
        if any(x["id"] == h.id for x in existentes):
            return False
        mes = h.registrada_em[:7]
        if not exploratoria and sum(1 for x in existentes if not x["exploratoria"] and x["registrada_em"][:7] == mes) >= self.regua.confirmatorias_por_mes:
            raise LimiteDoMes(f"já são {self.regua.confirmatorias_por_mes} confirmatórias em {mes}")
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps({**asdict(h), "rivais": list(h.rivais), "exploratoria": exploratoria}, ensure_ascii=False) + "\n")
        return True
