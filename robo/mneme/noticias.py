"""Notícias: coleta por feeds abertos, classificação por regras e medidas de atenção, sempre pela hora em que a informação chegou.

Texto externo é dado, nunca instrução. Nada aqui decide: tudo vira evidência para o processo central. Sem confirmação, um texto
nunca vira fato; a regra na dúvida é "reportagem", que ainda precisa de outra fonte.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx
import numpy as np
import pandas as pd

from .corvo.gate import Decision, IntakeGate, NewsItem, Pressure, canonical_url

AGENTE = {"user-agent": "MNEME-news-collector/0.1"}
MAX_BYTES_FEED = 5_000_000
MAX_IDADE_OFICIAL_SEG = 7 * 24 * 3600
_CONFIABILIDADE = {"alta": 0.9, "media": 0.7, "baixa": 0.5}


@dataclass(frozen=True)
class Fonte:
    id: str
    url: str
    categoria: str  # oficial, portal ou cripto
    confiabilidade: str  # alta, media ou baixa; é a nota inicial, a ser medida pelo histórico


FONTES = (
    Fonte("fed", "https://www.federalreserve.gov/feeds/press_all.xml", "oficial", "alta"),
    Fonte("ecb", "https://www.ecb.europa.eu/rss/press.html", "oficial", "alta"),
    Fonte("bea", "https://apps.bea.gov/rss/rss.xml", "oficial", "alta"),
)
FONTES_HABILITADAS = frozenset(fonte.id for fonte in FONTES)


def filtrar_fontes_habilitadas(noticias: pd.DataFrame) -> pd.DataFrame:
    """Mantém só fontes aprovadas para coleta, atributos e interpretação no MNEME."""
    if noticias.empty:
        return noticias
    if "fonte" not in noticias:
        return noticias.iloc[0:0]
    return noticias.loc[noticias["fonte"].isin(FONTES_HABILITADAS)]

ATIVOS = {
    "BTC": r"\bBTC\b|\bbitcoin\b", "ETH": r"\bETH\b|\bether\b|\bethereum\b", "SOL": r"\bSOL\b|\bsolana\b",
    "EURUSD": r"\bEUR/?USD\b|\beuro\b", "USD": r"\bdollar\b|\bd[oó]lar\b|\bUSD\b|\bDXY\b", "OURO": r"\bgold\b|\bouro\b",
    "JUROS_EUA": r"\bfed\b|\bfomc\b|\bfederal reserve\b|\btreasury yields?\b|\bpowell\b", "ACOES_EUA": r"\bs&p ?500\b|\bnasdaq\b|\bwall street\b",
}
_CASO_EXATO = {"SOL", "ETH", "BTC"}  # "sol" minúsculo é outra palavra em português
TEMAS = {
    "juros": r"\brate (cut|hike)s?\b|\binterest rates?\b|\bjuros\b|\bcopom\b|\bfomc\b", "inflacao": r"\binflation\b|\bcpi\b|\bpce\b|\binfla[cç][aã]o\b|\bipca\b",
    "emprego": r"\bpayrolls?\b|\bjobs report\b|\bunemployment\b|\bemprego\b", "regulacao": r"\bsec\b|\bregulat|\blawsuit\b|\bban\b|\bcftc\b|\bbill\b",
    "etf": r"\betfs?\b", "hack": r"\bhack|\bexploit\b|\bdrain|\bbreach\b", "listagem": r"\blist(s|ing|ed)\b|\bdelist", "geopolitica": r"\bwar\b|\btariffs?\b|\bsanctions?\b|\belection\b|\bguerra\b|\belei[cç]",
    "mineracao_e_rede": r"\bhalving\b|\bmining\b|\bupgrade\b|\bfork\b|\boutage\b",
}
_TIPOS = (
    ("opiniao", r"\bopinion\b|\bopini[aã]o\b|\bwhy i\b|\bi think\b|\bcommentary\b|\bexplained\b|\banalyst says\b|\banalysts? (say|said|think|believe)\b"),
    ("previsao", r"\bprice prediction\b|\bforecast\b|\bcould (hit|reach)\b|\bwill (hit|reach)\b|\bexpected to\b|\bpoised to\b|\bprevis[aã]o\b"),
    ("rumor", r"\brumou?rs?\b|\breportedly\b|\bsources? (say|said)\b|\bunconfirmed\b|\bleak(s|ed)?\b|\bsegundo fontes\b|\bboato\b"),
    ("em_desenvolvimento", r"\bbreaking\b|\bdeveloping\b|\bpreliminary\b|\bparcial\b|\bpreliminar\b|\bprobes?\b|\bmay\b"),
    ("especulacao", r"\bcould\b|\bmight\b|\bspeculat|\bpode\b"),
)
_SUSPEITO = re.compile(r"ignore (all |your |previous )|disregard (all|previous)|system prompt|you are now|ignore suas instru|buy now|100x", re.I)
_POSITIVO = re.compile(r"\b(surge|soar|rally|gain|jump|record high|approve|bullish|inflows?|beats?|sobe|alta|recorde)\w*\b", re.I)
_NEGATIVO = re.compile(r"\b(plunge|crash|drop|slump|hack|exploit|lawsuit|ban|bearish|outflows?|miss(es)?|sell-?off|despenca|queda|cai)\w*\b", re.I)


def limpar(texto: str | None, limite: int = 2000) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", html.unescape(texto or ""))
    return re.sub(r"\s+", " ", sem_tags).strip()[:limite]


def _ativos(texto: str) -> list[str]:
    achados = []
    for ativo, padrao in ATIVOS.items():
        bandeira = 0 if ativo in _CASO_EXATO else re.I
        # A forma por extenso vale em qualquer caixa; a sigla, só em maiúsculas.
        if re.search(padrao, texto, bandeira) or (ativo in _CASO_EXATO and re.search(padrao.split("|", 1)[1], texto, re.I)):
            achados.append(ativo)
    return achados


def classificar(titulo: str, resumo: str, categoria: str) -> dict:
    """Classifica o tipo de evidência sem tratar a identidade da fonte como confirmação."""
    texto = f"{titulo} {resumo}"
    tipo = next((nome for nome, padrao in _TIPOS if re.search(padrao, titulo, re.I)),
                "publicacao_institucional" if categoria == "oficial" else "reportagem")
    positivos, negativos = len(_POSITIVO.findall(titulo)), len(_NEGATIVO.findall(titulo))
    temas = [t for t, p in TEMAS.items() if re.search(p, texto, re.I)]
    ativos = _ativos(texto)
    return {"tipo": tipo, "ativos": ativos, "temas": temas, "sentimento": int(np.sign(positivos - negativos)),
            "relevante": bool(ativos or temas), "suspeito": bool(_SUSPEITO.search(texto))}


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        data = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        try:
            data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
        except ValueError:
            return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def ler_feed(corpo: bytes | str, fonte: Fonte, agora: datetime) -> list[dict]:
    """Aceita RSS/Atom sem inventar data de publicação ou de ocorrência ausente."""
    instante_recebimento = pd.Timestamp(agora)
    if instante_recebimento.tzinfo is None:
        raise ValueError("a hora de coleta precisa ter fuso horário")
    dados = corpo if isinstance(corpo, bytes) else corpo.encode("utf-8")
    if len(dados) > MAX_BYTES_FEED:
        raise ValueError("feed excede o limite de tamanho")
    # XML permits declarations in UTF-16/32, where an ASCII byte search misses DTD/ENTITY.
    # Decode those encodings only for this guard; in ASCII-compatible encodings the
    # prohibited markup retains its ASCII bytes.
    if dados.startswith((b"\x00\x00\xfe\xff", b"\xff\xfe\x00\x00")):
        texto_xml = dados.decode("utf-32")
    elif dados.startswith((b"\xfe\xff", b"\xff\xfe")):
        texto_xml = dados.decode("utf-16")
    elif dados.startswith(b"\x00\x00\x00<"):
        texto_xml = dados.decode("utf-32-be")
    elif dados.startswith(b"<\x00\x00\x00"):
        texto_xml = dados.decode("utf-32-le")
    elif dados.startswith(b"\x00<"):
        texto_xml = dados.decode("utf-16-be")
    elif dados.startswith(b"<\x00"):
        texto_xml = dados.decode("utf-16-le")
    else:
        texto_xml = dados.decode("ascii", errors="ignore")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", texto_xml, re.I):
        raise ValueError("feed com DOCTYPE/ENTITY recusado")
    raiz = ET.fromstring(dados)
    itens = []
    for e in raiz.iter():
        nome = e.tag.rsplit("}", 1)[-1]
        if nome not in ("item", "entry"):
            continue
        campos: dict[str, str] = {}
        for filho in e:
            chave = filho.tag.rsplit("}", 1)[-1]
            campos.setdefault(chave, (filho.text or filho.get("href") or ""))
        titulo = limpar(campos.get("title"), 300)
        if not titulo:
            continue
        link = (campos.get("link") or campos.get("guid") or campos.get("id") or "").strip()
        partes = urlsplit(link)
        try:
            porta = partes.port
        except ValueError:
            continue
        if partes.scheme.lower() != "https" or not partes.hostname or partes.username or partes.password or porta not in (None, 443):
            continue
        link = canonical_url(link)
        publicada = _data(campos.get("pubDate") or campos.get("published") or campos.get("updated") or campos.get("date"))
        resumo = limpar(campos.get("description") or campos.get("summary") or campos.get("encoded"))
        publicado_em = pd.Timestamp(publicada) if publicada is not None else pd.NaT
        futuro = publicada is not None and pd.Timestamp(publicada) > instante_recebimento
        itens.append({"id": hashlib.sha256(link.encode()).hexdigest()[:20], "publicado_em": publicado_em, "ocorrido_em": pd.NaT,
                      "recebido_em": instante_recebimento, "fonte": fonte.id,
                      "categoria": fonte.categoria, "confiabilidade": fonte.confiabilidade, "titulo": titulo, "resumo": resumo, "url": link,
                      "hash_titulo_sha256": hashlib.sha256(" ".join(unicodedata.normalize("NFKC", titulo).casefold().split()).encode("utf-8")).hexdigest(),
                      "publicacao_apos_recebimento": bool(futuro), "source_independence": "unverified",
                      **classificar(titulo, resumo, fonte.categoria)})
    return itens


class ColetorNoticias:
    def __init__(self, cliente: httpx.Client | None = None, fontes: tuple[Fonte, ...] = FONTES,
                 relogio: Callable[[], datetime] | None = None):
        self.cliente = cliente or httpx.Client(timeout=20, headers=AGENTE, follow_redirects=True)
        self.fontes = fontes
        self.relogio = relogio or (lambda: datetime.now(timezone.utc))

    def coletar(self, agora: datetime) -> tuple[list[dict], dict[str, str]]:
        """Coleta em série uma vez por rodada e passa cada artigo pelo Hugin local do MNEME."""
        instante = pd.Timestamp(agora)
        if instante.tzinfo is None:
            raise ValueError("a hora de coleta precisa ter fuso horário")
        noticias, estado = [], {}
        agora_gate = [instante.timestamp()]
        gate = IntakeGate(clock=lambda: agora_gate[0])
        for fonte in self.fontes:
            descartes: Counter[str] = Counter()
            try:
                with self.cliente.stream("GET", fonte.url) as resposta:
                    resposta.raise_for_status()
                    partes = bytearray()
                    for parte in resposta.iter_bytes():
                        partes.extend(parte)
                        if len(partes) > MAX_BYTES_FEED:
                            raise ValueError("feed excede o limite de tamanho")
                recebido = self.relogio()
                instante_recebimento = pd.Timestamp(recebido)
                if instante_recebimento.tzinfo is None:
                    raise ValueError("a hora real de recebimento precisa ter fuso horário")
                agora_gate[0] = instante_recebimento.timestamp()
                itens = ler_feed(bytes(partes), fonte, recebido)
                aceitos = []
                for artigo in itens:
                    publicada = artigo["publicado_em"]
                    if pd.isna(publicada):
                        descartes["data_ausente"] += 1
                        continue
                    if artigo["publicacao_apos_recebimento"]:
                        descartes["data_futura"] += 1
                        continue
                    item = NewsItem(fonte.id, artigo["url"], artigo["titulo"], publicada.timestamp(), artigo["resumo"],
                                    _CONFIABILIDADE[fonte.confiabilidade], MAX_IDADE_OFICIAL_SEG)
                    veredito = gate.admit(item, Pressure.NORMAL)
                    if veredito.decision is Decision.DROP:
                        descartes[veredito.reason] += 1
                        continue
                    artigo.update({"hugin_veredito": veredito.decision.value, "hugin_motivo": veredito.reason,
                                   "hugin_relevancia": veredito.relevance, "hugin_temas": list(veredito.topics),
                                   "hugin_versao": "hugin-v1"})
                    aceitos.append(artigo)
                noticias.extend(aceitos)
                total_descartes = sum(descartes.values())
                motivos = ", ".join(f"{motivo}={quantidade}" for motivo, quantidade in sorted(descartes.items()))
                estado[fonte.id] = f"ok: {len(aceitos)} aceitas; {total_descartes} descartadas" + (f" ({motivos})" if motivos else "")
            except (httpx.HTTPError, ET.ParseError, ValueError, UnicodeError) as erro:
                estado[fonte.id] = f"falhou: {erro.__class__.__name__}"
        return noticias, estado


def agrupar_eventos(noticias: pd.DataFrame, parecido: float = 0.6, janela_horas: int = 24) -> pd.Series:
    """Agrupa manchetes por hora de chegada; cobertura agrupada não prova confirmação independente."""
    if "recebido_em" not in noticias:
        return pd.Series(dtype="int64", index=noticias.index)
    noticias = noticias[noticias["recebido_em"].notna()]
    if noticias.empty:
        return pd.Series(dtype="int64", index=noticias.index)
    palavras = noticias["titulo"].str.lower().str.findall(r"[a-zà-ú0-9]{4,}").map(set)
    grupos, ativos = [], []
    tempos = noticias["recebido_em"]
    for i, (conjunto, tempo) in enumerate(zip(palavras, tempos)):
        ativos = [g for g in ativos if tempo - g[2] <= pd.Timedelta(hours=janela_horas)]
        grupo = next((g[0] for g in ativos if conjunto and len(conjunto & g[1]) / len(conjunto | g[1]) >= parecido), None)
        if grupo is None:
            grupo = i
            ativos.append((grupo, conjunto, tempo))
        grupos.append(grupo)
    return pd.Series(grupos, index=noticias.index)


def medidas_de_atencao(textos: pd.DataFrame, ativo: str, indice: pd.DatetimeIndex, janela: str = "60min", base_dias: int = 7) -> pd.DataFrame:
    """Atenção a um ativo em cada instante, só com o que já tinha chegado: volume, anomalia, sentimento, fontes e rumores.

    Serve a notícias e a redes sociais. Muitas menções de poucos autores aparecem em `concentracao`: volume não é relevância.
    """
    colunas = ["mencoes", "anomalia", "sentimento", "fontes", "concentracao", "fracao_rumor"]
    vazio = pd.DataFrame(0.0, index=indice, columns=colunas)
    if textos.empty:
        return vazio
    sobre = textos[textos["ativos"].map(lambda a: ativo in list(a))]
    if "recebido_em" not in sobre:
        return vazio
    sobre = sobre[sobre["recebido_em"].notna()]
    if sobre.empty:
        return vazio
    chegada = sobre["recebido_em"]
    tabela = pd.DataFrame({"um": 1.0, "sentimento": sobre["sentimento"].to_numpy(dtype=float), "rumor": sobre["tipo"].isin(["rumor", "especulacao"]).to_numpy(dtype=float),
                           "fonte": sobre["fonte"].to_numpy()}, index=pd.DatetimeIndex(chegada)).sort_index()
    largura = pd.Timedelta(janela)
    base = pd.Timedelta(days=base_dias)
    tempos = tabela.index.as_unit("ns").asi8
    instantes = pd.DatetimeIndex(indice).as_unit("ns").asi8
    fim = np.searchsorted(tempos, instantes, side="right")
    ini = np.searchsorted(tempos, instantes - largura.value, side="right")
    ini_base = np.searchsorted(tempos, instantes - base.value, side="right")
    n = (fim - ini).astype(float)
    media_base = (fim - ini_base) * (largura / base)
    sentimento = tabela["sentimento"].to_numpy()
    soma = np.concatenate([[0.0], np.cumsum(np.nan_to_num(sentimento))])
    validos = np.concatenate([[0.0], np.cumsum(~np.isnan(sentimento))])
    rumores = np.concatenate([[0.0], np.cumsum(tabela["rumor"].to_numpy())])
    com_sentimento = validos[fim] - validos[ini]
    # Muitos instantes têm a mesma janela: fontes e concentração são calculadas uma vez para cada janela distinta.
    codigos = pd.factorize(tabela["fonte"])[0]
    janelas, posicao = np.unique(np.column_stack([ini, fim]), axis=0, return_inverse=True)
    por_janela = np.zeros((len(janelas), 2))
    for i, (a, b) in enumerate(janelas):
        if b > a:
            contagem = np.bincount(codigos[a:b])
            por_janela[i] = (np.count_nonzero(contagem), contagem.max() / (b - a))
    posicao = np.ravel(posicao)
    return pd.DataFrame({"mencoes": n, "anomalia": (n - media_base) / np.sqrt(np.maximum(media_base, 1.0)),
                         "sentimento": np.divide(soma[fim] - soma[ini], com_sentimento, out=np.zeros(len(n)), where=com_sentimento > 0),
                         "fontes": por_janela[posicao, 0], "concentracao": por_janela[posicao, 1],
                         "fracao_rumor": np.divide(rumores[fim] - rumores[ini], n, out=np.zeros(len(n)), where=n > 0)}, index=indice, columns=colunas)


def com_noticias(x: pd.DataFrame, noticias: pd.DataFrame, par: str, base_dias: int = 7) -> pd.DataFrame:
    """Colunas `n_` para os modelos, em cada vela já fechada. Antes de a coleta começar é falta de dado, nunca zero.

    A anomalia só vale com a base completa, porque o primeiro lote lido dos feeds chega todo de uma vez. Sem menção, não existe sentimento.
    """
    colunas = {"mencoes": "n_mencoes", "anomalia": "n_anomalia", "sentimento": "n_sentimento", "fontes": "n_fontes", "concentracao": "n_concentracao", "fracao_rumor": "n_fracao_rumor"}
    saida = pd.DataFrame(np.nan, index=x.index, columns=list(colunas.values()))
    noticias = filtrar_fontes_habilitadas(noticias)
    if not noticias.empty:
        limpas = noticias[~noticias["suspeito"].astype(bool)] if "suspeito" in noticias else noticias
        if "recebido_em" not in limpas:
            return x.join(saida)
        limpas = limpas[limpas["recebido_em"].notna()]
        if not limpas.empty:
            inicio = limpas["recebido_em"].min()
            fechamentos = x.index + pd.Timedelta(minutes=1)
            coberto = fechamentos >= inicio
            if coberto.any():
                m = medidas_de_atencao(limpas, par.removesuffix("USDT"), fechamentos[coberto], base_dias=base_dias).rename(columns=colunas)
                m.index = x.index[coberto]
                sem_mencao = m["n_mencoes"] == 0
                m.loc[sem_mencao, ["n_sentimento", "n_concentracao", "n_fracao_rumor"]] = np.nan
                m.loc[m.index + pd.Timedelta(minutes=1) < inicio + pd.Timedelta(days=base_dias), "n_anomalia"] = np.nan
                saida.loc[m.index] = m
    return x.join(saida)
