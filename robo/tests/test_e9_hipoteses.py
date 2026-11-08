"""A2: hipótese é um registro tipado, com previsão, rivais e contrária, gravado antes do teste e nunca reescrito."""

from datetime import datetime, timezone

import pytest

from mneme.e9.hipoteses import FORA_DO_VOCABULARIO, LimiteDoMes, Registro, contraria, validar
from mneme.e9.regua import REGUAS

QUANDO = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def bruta(**mudar):
    h = {"tipo": "filtro", "escopo": {"estrategia": "SOLUSDT|expiracao_fixa|1m|5m"},
         "mudanca": {"dimensao": "regime", "operar_se": ["vol media-alta", "vol media-baixa", "vol alta-alta", "vol alta-baixa"]},
         "previsao": "acerto com o filtro acima do acerto sem filtro nas duas metades", "derrubaria": "diferença dentro do placebo",
         "rivais": ["regime", "acaso"], "motivo": "SOL perde em mercado lateral"}
    h.update(mudar)
    return h


def test_hipotese_valida_tem_identidade_e_regua():
    h = validar(bruta(), "dossie", QUANDO)
    assert h.regua == REGUAS["v1"].impressao() and h.registrada_em == QUANDO.isoformat()
    assert h.dados_a_partir_de == QUANDO.isoformat()  # o teste confirmatório só usa decisões depois do registro
    assert validar(bruta(motivo="outro texto"), "llm", QUANDO).id == h.id  # mesma mudança, mesma hipótese


@pytest.mark.parametrize("estrago", [
    {"tipo": "mudar_o_risco"},
    {"mudanca": {"dimensao": "forca_quintil", "operar_se": [1]}},  # rótulo que olha o período todo: fora do vocabulário
    {"mudanca": {"dimensao": "regime", "operar_se": []}},
    {"mudanca": {"dimensao": "regime", "operar_se": ["inventado"]}},
    {"previsao": ""},
    {"rivais": ["acaso"]},
    {"rivais": ["acaso", "astrologia"]},
    {"escopo": {"estrategia": "BTCUSDT; DROP TABLE"}},
])
def test_fora_do_vocabulario_e_recusada_inteira(estrago):
    with pytest.raises(FORA_DO_VOCABULARIO):
        validar(bruta(**estrago), "llm", QUANDO)


def test_filtro_que_nao_filtra_nada_e_recusado():
    from mneme.e9.hipoteses import VOCABULARIO
    with pytest.raises(FORA_DO_VOCABULARIO):
        validar(bruta(mudanca={"dimensao": "noticia", "operar_se": list(VOCABULARIO["noticia"])}), "llm", QUANDO)


def test_contraria_e_o_complemento():
    h = validar(bruta(), "dossie", QUANDO)
    c = contraria(h, QUANDO)
    assert c.contraria_de == h.id and c.origem == "contraria"
    assert set(c.mudanca["operar_se"]) == {"vol baixa-alta", "vol baixa-baixa", "vol baixa-lateral", "vol media-lateral", "vol alta-lateral"}
    assert set(c.mudanca["operar_se"]).isdisjoint(h.mudanca["operar_se"])


def test_selecao_pela_melhor_de_ontem_e_a_contraria():
    h = validar({"tipo": "selecao", "escopo": {}, "mudanca": {"regra": "acima_do_empate_ontem"},
                 "previsao": "estratégias acima do empate ontem acertam mais hoje que as outras", "derrubaria": "diferença dentro do acaso",
                 "rivais": ["acaso", "regime"], "motivo": "pedido do dono"}, "dono", QUANDO)
    assert contraria(h, QUANDO).mudanca == {"regra": "abaixo_do_empate_ontem"}


def test_registro_so_cresce_e_recusa_repetida(tmp_path):
    r = Registro(tmp_path / "hipoteses.jsonl", REGUAS["v1"])
    h = validar(bruta(), "dossie", QUANDO)
    assert r.registrar(h) is True and r.registrar(h) is False
    antes = (tmp_path / "hipoteses.jsonl").read_text()
    r.registrar(contraria(h, QUANDO))
    assert (tmp_path / "hipoteses.jsonl").read_text().startswith(antes)
    assert [x["id"] for x in r.todas()] == [h.id, contraria(h, QUANDO).id]


def test_limite_de_confirmatorias_por_mes(tmp_path):
    r = Registro(tmp_path / "hipoteses.jsonl", REGUAS["v1"])
    for hora in range(REGUAS["v1"].confirmatorias_por_mes):
        r.registrar(validar(bruta(escopo={"estrategia": f"SOLUSDT|expiracao_fixa|1m|{hora + 1}m"}), "dossie", QUANDO))
    with pytest.raises(LimiteDoMes):
        r.registrar(validar(bruta(escopo={"estrategia": "ETHUSDT|expiracao_fixa|1m|5m"}), "dossie", QUANDO))
    # Exploratória não conta no limite, mas também nunca aprova nada.
    assert r.registrar(validar(bruta(escopo={"estrategia": "ETHUSDT|expiracao_fixa|1m|5m"}), "dossie", QUANDO), exploratoria=True)


def test_nota_das_hipoteses_no_vault(tmp_path):
    from mneme.vault import Vault, escrever_hipoteses_e9

    r = Registro(tmp_path / "hipoteses.jsonl", REGUAS["v1"])
    h = validar(bruta(motivo="SOL perde [[link]] em lateral"), "dossie", QUANDO)
    r.registrar(h)
    r.registrar(contraria(h, QUANDO))
    v = Vault(tmp_path / "vault", relogio=lambda: QUANDO)
    v.iniciar()
    assert escrever_hipoteses_e9(v, tmp_path / "hipoteses.jsonl") == 1
    texto = next(v.raiz.rglob("E9 - hipóteses registradas.md")).read_text(encoding="utf-8")
    assert h.id in texto and "contrária" in texto and "aguardando dados novos" in texto and "[[link]]" not in texto
    assert escrever_hipoteses_e9(v, tmp_path / "nao_existe.jsonl") == 0
