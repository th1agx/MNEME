from datetime import datetime, timezone
import hashlib
from io import BytesIO

import numpy as np
import pandas as pd

from mneme.corvo.events import anotar_eventos_candidatos


def test_munin_anota_candidato_e_usa_a_chegada_mais_tardia():
    artigos = [
        {
            "id": "a1", "fonte": "fed", "url": "https://fed.example/a",
            "titulo": "Bitcoin ETF inflows hit new record", "hugin_temas": ["cripto"],
            "publicado_em": datetime(2026, 11, 12, 10, tzinfo=timezone.utc),
            "recebido_em": datetime(2026, 11, 12, 10, 1, tzinfo=timezone.utc),
        },
        {
            "id": "a2", "fonte": "ecb", "url": "https://ecb.example/b",
            "titulo": "Bitcoin ETF inflows surge to record", "hugin_temas": ["cripto"],
            "publicado_em": datetime(2026, 11, 12, 10, 2, tzinfo=timezone.utc),
            "recebido_em": datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc),
        },
    ]

    anotados = anotar_eventos_candidatos(artigos)

    assert anotados[0]["event_id"] == anotados[1]["event_id"]
    assert anotados[0]["event_available_at"] == datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc)
    assert anotados[1]["event_available_at"] == datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc)
    assert anotados[0]["event_confirmation_status"] == "nao_confirmado"
    assert anotados[0]["event_source_independence"] == "nao_avaliada"


def test_munin_mantem_id_do_artigo_que_chegou_primeiro_mesmo_com_publicacao_tardia():
    anterior = {
        "id": "a1", "fonte": "fed", "url": "https://fed.example/a",
        "titulo": "Bitcoin ETF inflows hit new record", "hugin_temas": ["cripto"],
        "publicado_em": datetime(2026, 11, 12, 10, 2, tzinfo=timezone.utc),
        "recebido_em": datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc),
    }
    tardia = {
        "id": "a2", "fonte": "ecb", "url": "https://ecb.example/b",
        "titulo": "Bitcoin ETF inflows hit historic record", "hugin_temas": ["cripto"],
        "publicado_em": datetime(2026, 11, 12, 10, 1, tzinfo=timezone.utc),
        "recebido_em": datetime(2026, 11, 12, 10, 10, tzinfo=timezone.utc),
    }

    anotado = anotar_eventos_candidatos([tardia], [anterior])[0]

    assert anotado["event_id"] == "evt_" + hashlib.sha256(anterior["url"].encode()).hexdigest()[:20]


def test_munin_le_temas_de_historico_carregado_do_parquet():
    anterior = {
        "id": "a1", "fonte": "fed", "url": "https://fed.example/a",
        "titulo": "Bitcoin ETF inflows hit new record", "hugin_temas": ["cripto"],
        "publicado_em": datetime(2026, 11, 12, 10, tzinfo=timezone.utc),
        "recebido_em": datetime(2026, 11, 12, 10, 1, tzinfo=timezone.utc),
    }
    conteudo = BytesIO()
    pd.DataFrame([anterior]).to_parquet(conteudo, index=False)
    conteudo.seek(0)
    historico = pd.read_parquet(conteudo).to_dict("records")
    assert isinstance(historico[0]["hugin_temas"], np.ndarray)
    novo = {
        "id": "a2", "fonte": "ecb", "url": "https://ecb.example/b",
        "titulo": "Bitcoin ETF inflows surge to record", "hugin_temas": ["cripto"],
        "publicado_em": datetime(2026, 11, 12, 10, 2, tzinfo=timezone.utc),
        "recebido_em": datetime(2026, 11, 12, 10, 5, tzinfo=timezone.utc),
    }

    anotado = anotar_eventos_candidatos([novo], historico)[0]

    assert anotado["event_id"] == "evt_" + hashlib.sha256(anterior["url"].encode()).hexdigest()[:20]


def test_munin_nao_divide_grupo_historico_ao_chegar_artigo_ponte():
    def artigo(id_, path, titulo, publicado, recebido):
        return {
            "id": id_, "fonte": id_, "url": f"https://news.example/{path}",
            "titulo": titulo, "hugin_temas": ["cripto"],
            "publicado_em": datetime(2026, 11, 12, 10, publicado, tzinfo=timezone.utc),
            "recebido_em": datetime(2026, 11, 12, 10, recebido, tzinfo=timezone.utc),
        }

    a = artigo("a", "a", "Bitcoin ETF inflows hit a record", 0, 2)
    c = artigo("c", "c", "Bitcoin ETF inflows hit new record today", 40, 3)
    b = artigo("b", "b", "Bitcoin ETF inflows hit a record during shocking market movement", 20, 45)
    historico = anotar_eventos_candidatos([a, c])
    assert historico[0]["event_id"] == historico[1]["event_id"]

    novo = anotar_eventos_candidatos([b], historico)[0]

    assert novo["event_id"] != historico[0]["event_id"]
