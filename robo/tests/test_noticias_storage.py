from datetime import datetime, timezone

import pandas as pd
import pytest

from mneme.dados.eventos import ArmazemEventos


PUBLICADO = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
RECEBIDO = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)


def _noticia(**sobrescritos):
    return {
        "id": "artigo-1",
        "publicado_em": PUBLICADO,
        "ocorrido_em": None,
        "recebido_em": RECEBIDO,
        "fonte": "fed",
        "titulo": "FOMC policy rate decision",
        "ativos": ["JUROS_EUA"],
        "sentimento": 0,
        "tipo": "publicacao_institucional",
        "suspeito": False,
        **sobrescritos,
    }


def test_noticia_sem_ocorrido_em_grava_e_filtra_pela_chegada(tmp_path):
    armazem = ArmazemEventos(tmp_path)

    assert armazem.gravar("noticias", "GLOBAL", [_noticia()]) == 1
    armazenada = armazem.ler("noticias", "GLOBAL", inicio=datetime(2026, 11, 9, tzinfo=timezone.utc))

    assert len(armazenada) == 1
    assert pd.isna(armazenada.loc[0, "ocorrido_em"])
    assert armazenada.loc[0, "publicado_em"] == pd.Timestamp(PUBLICADO)
    assert armazenada.loc[0, "recebido_em"] == pd.Timestamp(RECEBIDO)


def test_noticia_fica_particionada_no_dia_em_que_chegou(tmp_path):
    armazem = ArmazemEventos(tmp_path)
    armazem.gravar("noticias", "GLOBAL", [_noticia()])

    pasta_chegada = tmp_path / "fluxo" / "noticias" / "GLOBAL" / "2026-11-10"
    assert list(pasta_chegada.glob("*.parquet"))
    assert not (tmp_path / "fluxo" / "noticias" / "GLOBAL" / "2026-11-01").exists()


def test_como_de_exclui_noticia_que_ainda_nao_tinha_chegado(tmp_path):
    armazem = ArmazemEventos(tmp_path)
    armazem.gravar("noticias", "GLOBAL", [_noticia()])

    antes = armazem.ler("noticias", "GLOBAL", como_de=datetime(2026, 11, 10, 11, 59, tzinfo=timezone.utc))
    depois = armazem.ler("noticias", "GLOBAL", como_de=RECEBIDO)

    assert antes.empty
    assert len(depois) == 1


def test_inicio_e_fim_de_noticias_usam_recebido_em(tmp_path):
    armazem = ArmazemEventos(tmp_path)
    armazem.gravar("noticias", "GLOBAL", [_noticia()])

    antes_da_chegada = armazem.ler("noticias", "GLOBAL", fim=datetime(2026, 11, 10, 11, tzinfo=timezone.utc))
    depois_da_chegada = armazem.ler("noticias", "GLOBAL", inicio=datetime(2026, 11, 10, 11, tzinfo=timezone.utc))

    assert antes_da_chegada.empty
    assert len(depois_da_chegada) == 1


def test_le_registro_antigo_particionado_por_ocorrido_em_com_corte_de_chegada(tmp_path):
    raiz = tmp_path / "fluxo" / "noticias" / "GLOBAL" / "2026-11-01"
    raiz.mkdir(parents=True)
    pd.DataFrame([_noticia(ocorrido_em=PUBLICADO)]).to_parquet(raiz / "parte-legada.parquet", index=False)
    armazem = ArmazemEventos(tmp_path)

    lidas = armazem.ler("noticias", "GLOBAL", inicio=datetime(2026, 11, 9, tzinfo=timezone.utc), como_de=RECEBIDO)

    assert len(lidas) == 1


def test_noticia_sem_recebimento_real_e_recusada(tmp_path):
    armazem = ArmazemEventos(tmp_path)

    with pytest.raises(ValueError, match="recebido_em"):
        armazem.gravar("noticias", "GLOBAL", [_noticia(recebido_em=None)])
