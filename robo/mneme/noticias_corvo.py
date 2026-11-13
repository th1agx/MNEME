"""Offline, in-memory adapter for CORVO v0 preview articles.

The caller must supply a locally reviewed source policy that permits
``preview_em_memoria``. The policy is configuration, not independently verified
proof of terms compliance. CORVO v0 is unsigned: matching IDs and hashes checks
internal consistency only, not who produced the record. The adapter preserves raw
titles as untrusted data and never writes to the live store or model feature path.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .noticias import classificar, limpar

VERSAO_CORVO = "corvo-mneme-preview-v0"
VERSAO_ADAPTADOR = "mneme-corvo-preview-v0"
_USO_PREVIEW = "preview_em_memoria"
_ID_ARTIGO = re.compile(r"^art_[a-f0-9]{20}$")
_ID_FONTE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
_HASH_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TIPOS_EVIDENCIA = {"reportagem", "opiniao", "previsao", "rumor", "em_desenvolvimento", "especulacao", "publicacao_institucional"}
_PARAMETROS_RASTREAMENTO = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid", "ref", "cmpid"}


@dataclass(frozen=True)
class AutorizacaoFonteCorvo:
    """Evidência de que uma fonte permite exatamente o preview local em memória."""

    hosts: frozenset[str]
    termos_url: str
    revisado_por: str
    revisado_em: datetime
    usos_autorizados: frozenset[str]


def _instante_utc(value: object) -> datetime | None:
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
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _politica_valida(policy: object) -> bool:
    if not isinstance(policy, AutorizacaoFonteCorvo) or not isinstance(policy.revisado_por, str):
        return False
    if not isinstance(policy.hosts, frozenset) or not isinstance(policy.usos_autorizados, frozenset):
        return False
    try:
        terms = urlsplit(policy.termos_url)
        terms_port = terms.port
    except (TypeError, ValueError):
        return False
    reviewed = _instante_utc(policy.revisado_em)
    if not all(isinstance(host, str) for host in policy.hosts):
        return False
    hosts = {host.lower() for host in policy.hosts}
    valid_hosts = all(
        host
        and re.fullmatch(r"[a-z0-9.-]+", host)
        and not host.startswith(".")
        and not host.endswith(".")
        and ".." not in host
        for host in hosts
    )
    return bool(
        isinstance(policy.termos_url, str)
        and terms.scheme.lower() == "https"
        and terms.hostname
        and terms_port in (None, 443)
        and not terms.username
        and not terms.password
        and policy.revisado_por.strip()
        and reviewed is not None
        and _USO_PREVIEW in policy.usos_autorizados
        and hosts
        and valid_hosts
    )


def _host_https(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value or len(value) > 2048:
        return None
    try:
        parts = urlsplit(value)
        host = parts.hostname
        _ = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
        return None
    return value, host.lower()


def _url_canonicalizada(url: str) -> str:
    """Reproduz a canonicalização de URL usada no contrato de exportação CORVO."""
    parts = urlsplit(url.strip())
    query = urlencode(sorted(
        (key, value)
        for key, value in parse_qsl(parts.query)
        if key.lower() not in _PARAMETROS_RASTREAMENTO
    ))
    netloc = parts.netloc.lower().removeprefix("www.")
    return urlunsplit((parts.scheme.lower(), netloc, parts.path.rstrip("/"), query, ""))


def _hash_titulo(title: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", title).casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utf8_valido(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def adaptar_preview_corvo(
    artigos: Iterable[object],
    *,
    recebido_no_mneme_em: datetime,
    politicas: Mapping[str, AutorizacaoFonteCorvo],
) -> tuple[list[dict], dict[str, int]]:
    """Validate CORVO v0 records into isolated MNEME preview entries.

    ``recebido_em`` in CORVO is not the arrival time in MNEME. The caller must pass
    MNEME's actual import time; ``ocorrido_em`` stays unknown. This function never
    writes, fetches a URL, calls an LLM, or creates model features.
    """
    recebido_mneme = _instante_utc(recebido_no_mneme_em)
    if recebido_mneme is None:
        raise ValueError("recebido_no_mneme_em precisa ter fuso horário")

    aceitos: list[dict] = []
    rejeitados: dict[str, int] = {}
    vistos: dict[str, tuple[str, str, str]] = {}

    def rejeitar(motivo: str) -> None:
        rejeitados[motivo] = rejeitados.get(motivo, 0) + 1

    for artigo in artigos:
        if not isinstance(artigo, dict):
            rejeitar("esquema_invalido")
            continue
        source = artigo.get("fonte")
        policy = politicas.get(source) if isinstance(source, str) else None
        if not _politica_valida(policy):
            rejeitar("fonte_sem_autorizacao")
            continue
        assert isinstance(policy, AutorizacaoFonteCorvo)
        revisao_em = _instante_utc(policy.revisado_em)
        if revisao_em is None or revisao_em > recebido_mneme:
            rejeitar("fonte_sem_autorizacao")
            continue
        raw_url = artigo.get("url")
        if isinstance(raw_url, str) and not _utf8_valido(raw_url):
            rejeitar("texto_utf8_invalido")
            continue
        url = _host_https(raw_url)
        if url is None or url[1] not in {host.lower() for host in policy.hosts}:
            rejeitar("url_fora_da_fonte")
            continue

        article_id = artigo.get("id")
        title = artigo.get("titulo")
        title_hash = artigo.get("hash_titulo_sha256")
        evidence_type = artigo.get("tipo_evidencia")
        verdict = artigo.get("veredito_hugin")
        if (
            artigo.get("record_type") != "article"
            or artigo.get("versao_preview") != VERSAO_CORVO
            or artigo.get("ocorrido_em") is not None
            or not isinstance(evidence_type, str)
            or evidence_type not in _TIPOS_EVIDENCIA
            or artigo.get("estado_alegacao") != "nao_confirmada_independentemente"
            or not isinstance(verdict, str)
            or verdict not in {"hot", "buffer"}
            or artigo.get("verificacao_injecao") != "pendente_no_destino"
            or artigo.get("texto_externo_nao_confiavel") is not True
            or artigo.get("resumo") != ""
            or not isinstance(article_id, str)
            or not _ID_ARTIGO.fullmatch(article_id)
            or not isinstance(title_hash, str)
            or not _HASH_SHA256.fullmatch(title_hash)
            or not _ID_FONTE.fullmatch(source)
            or not isinstance(title, str)
            or not title.strip()
            or len(title) > 400
        ):
            rejeitar("versao_ou_esquema_invalido")
            continue

        if not _utf8_valido(title):
            rejeitar("texto_utf8_invalido")
            continue

        canonical_url = _url_canonicalizada(url[0])
        expected_id = "art_" + hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:20]
        if article_id != expected_id or title_hash != _hash_titulo(title):
            rejeitar("integridade_invalida")
            continue

        identity = (canonical_url, title_hash, source)
        previous_identity = vistos.get(article_id)
        if previous_identity is not None:
            rejeitar("duplicado" if previous_identity == identity else "conflito_de_identidade")
            continue

        corvo_received = _instante_utc(artigo.get("recebido_em"))
        published = None if artigo.get("publicado_em") is None else _instante_utc(artigo.get("publicado_em"))
        if corvo_received is None or (artigo.get("publicado_em") is not None and published is None):
            rejeitar("timestamp_invalido")
            continue
        if corvo_received > recebido_mneme:
            rejeitar("ordem_temporal_invalida")
            continue
        # Check the untrusted original title before HTML cleanup or truncation.
        suspicious = classificar(title, "", "portal")["suspeito"]
        clean_title = limpar(title, 300)
        if not clean_title:
            rejeitar("titulo_invalido")
            continue
        suspicious = bool(suspicious or classificar(clean_title, "", "portal")["suspeito"])
        vistos[article_id] = identity

        aceitos.append({
            "record_type": "article_preview",
            "versao_preview": VERSAO_ADAPTADOR,
            "corvo_article_id": article_id,
            "id": f"corvo_{article_id}",
            "fonte": f"corvo:{source}",
            "host_fonte": url[1],
            "url": url[0],
            "titulo_original_nao_confiavel": title,
            "hash_titulo_sha256": title_hash,
            "publicado_em": published,
            "recebido_no_corvo_em": corvo_received,
            "recebido_no_mneme_em": recebido_mneme,
            "available_at": recebido_mneme,
            "ocorrido_em": None,
            "titulo": clean_title,
            "resumo": "",
            "tipo_evidencia_corvo": artigo["tipo_evidencia"],
            "estado_alegacao": artigo["estado_alegacao"],
            "veredito_hugin": artigo["veredito_hugin"],
            "politica_fonte": {
                "host_permitido": url[1],
                "termos_url": policy.termos_url,
                "revisado_por": policy.revisado_por.strip(),
                "revisado_em": revisao_em,
                "uso_autorizado": _USO_PREVIEW,
            },
            "publicacao_apos_recebimento": published is not None and published > recebido_mneme,
            "source_independence": "unverified",
            "suspeito": bool(suspicious),
            "texto_externo_nao_confiavel": True,
            # The v0 preview is unsigned; matching hashes only checks internal consistency.
            "proveniencia_autenticada": False,
            "armazenado_ou_enviado": False,
        })

    return aceitos, rejeitados
