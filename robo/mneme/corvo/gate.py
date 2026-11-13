"""Hugin determinístico integrado ao coletor de notícias do MNEME.

Adaptado de ``engine/corvo_engine/intake/gate.py`` do repositório CORVO.
Esta cópia conserva o filtro puro do CORVO, mas o resultado é gravado no Parquet do MNEME
no mesmo ciclo `mneme.inteligencia`; não há segundo serviço nem fila. HOT e BUFFER indicam
prioridade de admissão, e os dois resultados admitidos seguem para o mesmo Parquet.
Texto externo é dado, nunca instrução. Um descarte significa apenas que o item não
passou pelo filtro para uso preditivo.
"""
from __future__ import annotations

import re
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# O CORVO só grava o que PODE MEXER EM MERCADO (cripto, ações, câmbio, juros, commodities) ou em risco geopolítico/físico que chega a
# mercado. Pesos são hipóteses a medir (ver docs/corvo/CODEX_BRIEF_COLETA.md). Notícia que não casa nenhum tema é descartada.
# Regra de escrita: termos ESPECÍFICOS. Palavra solta ("gold", "war", "fed", "troops") traz muito falso positivo.
_R = re.IGNORECASE
TOPICS: dict[str, tuple[float, re.Pattern[str]]] = {
    # política monetária (não "Fed aprova aplicação de banco": isso é rotina e vai para o ruído)
    "banco_central": (1.0, re.compile(r"\b(fomc|federal open market committee|rate (cuts?|hikes?|decisions?|rises?|increase[ds]?|maintained|held)|bank rate|policy rate|key rates?|discount rate|quantitative (easing|tightening)|dot plot|monetary policy (decision|decisions|statement|summary|meeting)|copom|selic|pboc)\b", _R)),
    "banco_central_contexto": (0.7, re.compile(r"\b(interest rates?|treasury yields?|bond yields?|yield curve|juros)\b", _R)),
    "banco_central_fala": (0.45, re.compile(r"\b(monetary policy|pol[ií]tica monet[aá]ria|powell|lagarde|ueda|bailey|boj)\b", _R)),
    "banco_central_lideranca": (0.9, re.compile(r"\b(lagarde|powell|ueda|bailey|fed chair|ecb president|governor)\b.{0,60}\b(step(s|ped)? down|resign\w*|succe\w+|nominat\w*|replace\w*)", _R | re.S)),
    "dados_macro": (0.9, re.compile(r"\b(inflation|cpi|ppi|pce|gdp|payrolls?|nonfarm|unemployment|jobless|retail sales|pmi|recession|jobs (report|data|added)|added [\d,]+ jobs|job (gains|losses|growth)|infla[cç][aã]o|pib|desemprego|recess[aã]o)\b", _R)),
    "comercio": (0.9, re.compile(r"\b(tariffs?|sanctions?|embargo|export (ban|controls?)|trade (war|deal|talks|surplus|deficit)|san[cç][aã]o|san[cç][oõ]es|tarifas?)\b", _R)),
    # commodity só com contexto de preço/oferta (senão "gold" é karatê e "oil" é ONG)
    "energia": (0.9, re.compile(r"\b(oil (price|prices|output|production|supply|exports?|market|cuts?)|crude( oil)?|brent|wti|opec\+?|natural gas|lng|gold (price|prices|rally|record|futures|reserves)|copper (price|prices)|lithium (price|prices)|wheat (price|prices|exports?)|strait of hormuz|pipelines?|refiner(y|ies)|tankers?|cargo vessel|shipping lanes?|petr[oó]leo|g[aá]s natural)\b", _R)),
    "geopolitica": (0.5, re.compile(r"\b(war|guerra|invasion|air ?strikes?|missiles?|drone (attacks?|strikes?)|drones? (hit|struck|strike|attack)|(struck|hit|targeted) by (a |\d+ )?drones?|russian drones|blasts? (heard|hit|rock)|explosions? heard|shelling|naval blockade|blockade|bloqueio|houthis?|red sea|gulf of oman|taiwan strait|south china sea|ceasefire|cessar-fogo|troops? (to )?(deploy\w*|enter|cross|mass\w*|withdraw\w*)|nuclear (deal|talks|programme|program|test|weapons?|inspections?)|coup|golpe)\b", _R)),
    "conflito_chave": (0.95, re.compile(
        r"(?=.*\b(iran|hormuz|persian gulf|gulf of oman|red sea|bab el-mandeb|suez|taiwan|south china sea|strait of malacca)\b)"
        r"(?=.*\b(war|air ?strikes?|strikes?|missiles?|drones?|blockade|escalat\w*|ceasefire|nuclear|troops|shelling|explosions?|blasts? (heard|hit|rock)|shipping|vessel|tanker)\b)", _R | re.S)),
    "conflito_regional": (0.5, re.compile(
        r"(?=.*\b(russia|russian|ukraine|kyiv|saudi|houthis?|yemen|israel|gaza|lebanon|syria|north korea)\b)"
        r"(?=.*\b(war|air ?strikes?|strikes?|missiles?|drones?|blockade|attacks?|escalat\w*|ceasefire|nuclear|troops|shelling|explosions?)\b)", _R | re.S)),
    "catastrofe": (0.9, re.compile(r"\b(earthquake|tsunami|hurricane|typhoon|cyclone|terremoto|furac[aã]o|tuf[aã]o)\b", _R)),
    "infraestrutura": (0.75, re.compile(
        r"\b(explosions?|fires?|blackouts?|outages?|cyberattacks?|ransomware|hacked|inc[eê]ndio|explos[aã]o|apag[aã]o)\b.{0,70}\b(refiner\w*|plants?|factor(y|ies)|ports?|pipelines?|(power )?grids?|energy network|nationwide|semiconductors?|mines?|terminals?|airports?|exchanges?|data cent(er|re)s?|refinaria|usina|porto|oleoduto)\b"
        r"|\b(refiner\w*|plants?|factor(y|ies)|ports?|pipelines?|(power )?grids?|energy network|power network|semiconductors?|mines?|terminals?|airports?|data cent(er|re)s?|refinaria|usina|porto|oleoduto)\b.{0,70}\b(explosions?|fires?|blackouts?|outages?|cyberattacks?|ransomware|hacked|shut ?down|strikes?|damaged?|inc[eê]ndio|explos[aã]o|apag[aã]o)\b", _R | re.S)),
    "cripto": (0.85, re.compile(r"\b(bitcoin etfs?|ether etfs?|spot etfs?|etf (flows?|outflows?|inflows?)|crypto (hack|exploit|regulation|ban|exchange)s?|exchange (hack|insolvency|halts?)|stablecoin|depeg|halving|sec (sues|approves|charges)|cftc|ofac|binance|coinbase|tether|mexc|exploit|rug ?pull|liquidat(ed|ions?))\b", _R)),
    "empresas": (0.8, re.compile(r"\b(bankruptcy|chapter 11|default(s|ed)?|bank (run|runs|collapse|failure|lockout)|banking (crisis|scandal)|bailout|downgrade|credit rating|moody'?s|fitch|delist(ing|ed)?|fal[eê]ncia|recupera[cç][aã]o judicial)\b", _R)),
    "empresas_corrente": (0.6, re.compile(r"\b(merger|acquisition|takeover|earnings|guidance|ipo|buybacks?)\b", _R)),
    "politica": (0.7, re.compile(r"\b(government (collapses?|falls)|prime minister (resigns?|ousted)|snap election|state of emergency|martial law|elei[cç][aã]o antecipada)\b", _R)),
    "politica_fraca": (0.5, re.compile(r"\b(impeach(ment|ed)?|ousted president|president resigns?)\b", _R)),
    "mercado": (0.75, re.compile(r"\b(s&p ?500|nasdaq|dow jones|dxy|dollar index|vix|circuit breakers?|(stocks?|shares|equities|markets?|wall street) (rout|slump|swoons?|plunges?|tumbles?|sinks?|slides?|surges?|rall(y|ies)|climbs?)|(trillions?|billions?) wiped|wiped (off|from)|market (crash|rout|selloff|sell-off|value)|flash crash|queda das bolsas|bolsa despenca)\b", _R)),
}
# Ruído: o que parece notícia, mas não muda preço de nada (esporte, celebridade, opinião, rotina de órgão regulador, ajuda humanitária).
_NOISE = re.compile(
    r"\b(sponsored|advertorial|giveaway|horoscope|celebrity|publieditorial|opinion|editorial|podcast|newsletter|quiz|recipe|lifestyle|"
    r"fashion|travel guide|gossip|football|soccer|cricket|nba|nfl|olympics|oscars|grammys|world cup|price prediction|price analysis|"
    r"how to|what is|explained|live blog|obituary|review:|"
    r"enforcement actions?|approval of application|survey of consumer finances|banknotes?|office space|appointment of|"
    r"minutes of the (?!federal open market).{0,60}(committee|group|forum|taskforce)|industry forum|green notice|statistical notice|market notice|"
    r"questionnaire|transcript|remit for|dates for|blood bank|karate|funeral|war crimes|humanitarian|refugees?|undocumented|"
    r"war (secretary|department|room|memorial)|children|women and girls|rights chief|peacekeeping|aid teams|nuclear waste|schools?|fscs|fee tariff|armed attack on police)\b",
    _R,
)
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "cmpid"}
_WORD = re.compile(r"[a-zà-ú0-9]{3,}", re.I)


class Decision(str, Enum):
    HOT = "hot"
    BUFFER = "buffer"
    DROP = "drop"


class Pressure(str, Enum):
    """Nível de pressão usado somente para ajustar os limiares do filtro."""
    NORMAL = "normal"
    ECONOMY = "economy"
    CRITICAL = "critical"


@dataclass(frozen=True)
class NewsItem:
    source_id: str
    url: str
    title: str
    published_at: float  # epoch s
    text: str = ""
    source_reliability: float = 0.5  # 0-1, nota inicial a ser medida pelo histórico
    max_age_s: float | None = None  # janela de frescor desta fonte (oficial vale por mais tempo); None = padrão do portão


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str
    relevance: float = 0.0
    topics: tuple[str, ...] = ()


@dataclass
class GateConfig:
    max_age_s: float = 24 * 3600  # padrão para imprensa; fontes oficiais usam janela própria (catálogo)
    per_source_per_hour: int = 30
    near_dup_jaccard: float = 0.7
    dedup_window: int = 5000
    # HOT é admissão prioritária; BUFFER é admissão de menor prioridade, também persistida pelo MNEME.
    hot_min: dict[Pressure, float] = field(default_factory=lambda: {Pressure.NORMAL: 0.91, Pressure.ECONOMY: 0.95, Pressure.CRITICAL: 0.95})
    buffer_min: dict[Pressure, float] = field(default_factory=lambda: {Pressure.NORMAL: 0.5, Pressure.ECONOMY: 0.6, Pressure.CRITICAL: 0.95})


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    q = urlencode(sorted((k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING))
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), p.path.rstrip("/"), q, ""))


def _tokens(title: str) -> frozenset[str]:
    return frozenset(w.lower() for w in _WORD.findall(title))


def _hits(blob: str) -> list[tuple[float, str]]:
    return [(w, name) for name, (w, rx) in TOPICS.items() if rx.search(blob)]


def score(item: NewsItem) -> tuple[float, tuple[str, ...]]:
    """Relevância 0-1 para MERCADO. O título decide; tema achado só no resumo vale 50% (nunca chega ao banco) (resumo de feed traz muita palavra solta)."""
    if _NOISE.search(f"{item.title} {item.text[:300]}"):
        return 0.0, ()
    hits, factor = _hits(item.title), 1.0
    if not hits:
        hits, factor = _hits(item.text[:500]), 0.5
    if not hits:
        return 0.0, ()
    best = max(w for w, _ in hits)
    bonus = min(0.15, 0.05 * (len(hits) - 1))  # tema cruzado (ex.: guerra + petróleo) pesa mais
    rel = min(1.0, (best + bonus) * factor * (0.6 + 0.4 * item.source_reliability))
    return round(rel, 3), tuple(sorted(n for _, n in hits))


class IntakeGate:
    def __init__(self, config: GateConfig | None = None, clock=time.time) -> None:
        self.cfg = config or GateConfig()
        self._clock = clock
        self._seen_url: OrderedDict[str, None] = OrderedDict()
        self._seen_tok: OrderedDict[frozenset[str], None] = OrderedDict()
        self._quota: dict[str, list[float]] = {}
        self.stats: Counter[str] = Counter()

    def _remember(self, url_key: str, toks: frozenset[str]) -> None:
        self._seen_url[url_key] = None
        self._seen_tok[toks] = None
        for d in (self._seen_url, self._seen_tok):
            while len(d) > self.cfg.dedup_window:
                d.popitem(last=False)

    def _near_dup(self, toks: frozenset[str]) -> bool:
        if len(toks) < 4:
            return False
        return any(len(toks & o) / len(toks | o) >= self.cfg.near_dup_jaccard for o in self._seen_tok)

    def _within_quota(self, source: str, now: float) -> bool:
        window = [t for t in self._quota.get(source, []) if now - t < 3600]
        ok = len(window) < self.cfg.per_source_per_hour
        if ok:
            window.append(now)
        self._quota[source] = window
        return ok

    def admit(self, item: NewsItem, pressure: Pressure = Pressure.NORMAL) -> Verdict:
        v = self._decide(item, pressure)
        self.stats[f"{v.decision.value}:{v.reason}"] += 1
        return v

    def _decide(self, item: NewsItem, pressure: Pressure) -> Verdict:
        now = self._clock()
        if not item.title.strip() or not item.url:
            return Verdict(Decision.DROP, "malformed")
        # Relevância ANTES da idade: "stale" passa a contar só notícia que importava e ficou velha (informação útil para ajustar a janela).
        rel, topics = score(item)
        if rel < self.cfg.buffer_min[pressure]:
            return Verdict(Decision.DROP, "irrelevant" if rel == 0 else "below_threshold", rel, topics)
        if now - item.published_at > (item.max_age_s or self.cfg.max_age_s):
            return Verdict(Decision.DROP, "stale", rel, topics)
        key, toks = canonical_url(item.url), _tokens(item.title)
        if key in self._seen_url:
            return Verdict(Decision.DROP, "duplicate_url")
        if self._near_dup(toks):
            return Verdict(Decision.DROP, "near_duplicate")
        # a cota só é gasta por item que seria admitido, para lixo não consumir a vez de notícia boa
        if not self._within_quota(item.source_id, now):
            return Verdict(Decision.DROP, "source_quota", rel, topics)
        self._remember(key, toks)
        if rel >= self.cfg.hot_min[pressure]:
            return Verdict(Decision.HOT, "relevant", rel, topics)
        return Verdict(Decision.BUFFER, "batch_later", rel, topics)
