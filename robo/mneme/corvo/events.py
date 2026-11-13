from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone

import numpy as np

from .gate import canonical_url

_STOP_WORDS = frozenset("a an and as at before by for from how in into near of on or over says say said the their to with after this that".split())
_JANELA_SEGUNDOS = 48 * 3600


def _instante(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _termos(titulo: object) -> frozenset[str]:
    texto = unicodedata.normalize("NFKD", str(titulo or "").casefold())
    texto = "".join(letra for letra in texto if not unicodedata.combining(letra))
    return frozenset(palavra for palavra in re.findall(r"[a-z0-9]+", texto) if palavra not in _STOP_WORDS)


def _jaccard(a: object, b: object) -> float:
    esquerdo, direito = _termos(a), _termos(b)
    return len(esquerdo & direito) / len(esquerdo | direito) if esquerdo and direito else 0.0


def _normalizar(artigos: list[dict]) -> list[dict]:
    normalizados, urls = [], set()
    for artigo in artigos:
        url = str(artigo.get("url") or "").strip()
        fonte = str(artigo.get("fonte") or "").strip()
        titulo = str(artigo.get("titulo") or "").strip()
        publicado = _instante(artigo.get("publicado_em"))
        recebido = _instante(artigo.get("recebido_em"))
        temas = artigo.get("hugin_temas")
        if isinstance(temas, np.ndarray):
            temas = temas.tolist()
        if not url or not fonte or not titulo or publicado is None or recebido is None or not isinstance(temas, (list, tuple, set, frozenset)):
            continue
        canon = canonical_url(url)
        if canon in urls:
            continue
        urls.add(canon)
        normalizados.append({**artigo, "url": canon, "_publicado": publicado, "_recebido": recebido, "_temas": frozenset(temas)})
    return sorted(normalizados, key=lambda linha: (linha["_publicado"], linha["url"]))


def _compativeis(artigo: dict, membros: list[dict]) -> bool:
    return bool(membros) and all(
        artigo["_temas"] & membro["_temas"]
        and abs((artigo["_publicado"] - membro["_publicado"]).total_seconds()) <= _JANELA_SEGUNDOS
        and _jaccard(artigo["titulo"], membro["titulo"]) >= 0.55
        for membro in membros
    )


def _id_evento(url: str) -> str:
    return "evt_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def _chave_historica(artigo: dict) -> str:
    # Dados anteriores ao Munin não têm ID de evento: cada URL vira um grupo congelado.
    return str(artigo.get("event_id") or _id_evento(artigo["url"]))


def _metadados(grupo: list[dict], evento_id: str) -> dict:
    recebidos = [linha["_recebido"] for linha in grupo]
    return {
        "event_id": evento_id,
        "event_available_at": max(recebidos),
        "event_first_received_at": min(recebidos),
        "event_source_ids": sorted({linha["fonte"] for linha in grupo}),
        "event_confirmation_status": "nao_confirmado",
        "event_source_independence": "nao_avaliada",
        "munin_versao": "munin-events-v1",
    }


def anotar_eventos_candidatos(artigos: list[dict], historico: list[dict] | None = None) -> list[dict]:
    """Anota candidatos Munin sem reescrever associações já persistidas.

    Grupos históricos ficam congelados. Um artigo novo só entra num grupo se passar
    as regras de tema, janela e similaridade contra todos os membros; assim uma
    notícia ponte não altera silenciosamente IDs já gravados. Esses metadados não
    confirmam a alegação nem a independência entre fontes.
    """
    novos = [dict(artigo, _indice_novo=indice) for indice, artigo in enumerate(artigos)]
    historicos = _normalizar([dict(artigo) for artigo in (historico or [])])
    urls_historicas = {linha["url"] for linha in historicos}
    preparados_novos = [linha for linha in _normalizar(novos) if linha["url"] not in urls_historicas]

    grupos: dict[str, list[dict]] = {}
    for linha in historicos:
        grupos.setdefault(_chave_historica(linha), []).append(linha)

    grupos_por_novo: dict[int, str] = {}
    preparados_novos.sort(key=lambda linha: (linha["_recebido"], linha["_publicado"], linha["url"]))
    for linha in preparados_novos:
        candidatos = sorted(evento_id for evento_id, membros in grupos.items() if _compativeis(linha, membros))
        if candidatos:
            evento_id = candidatos[0]
        else:
            evento_id = _id_evento(linha["url"])
            grupos.setdefault(evento_id, [])
        grupos[evento_id].append(linha)
        grupos_por_novo[linha["_indice_novo"]] = evento_id

    resultado = []
    for indice, artigo in enumerate(novos):
        artigo.pop("_indice_novo", None)
        if indice in grupos_por_novo:
            evento_id = grupos_por_novo[indice]
            artigo.update(_metadados(grupos[evento_id], evento_id))
        resultado.append(artigo)
    return resultado
