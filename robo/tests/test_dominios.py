"""Os dois domínios (Motor 01: mercados; Motor 02: opções digitais) e os caminhos antigos, que continuam funcionando."""

import importlib


def test_caminhos_antigos_sao_o_mesmo_modulo():
    for antigo, novo in (("mneme.ao_vivo", "mneme.digitais.ao_vivo"),
                         ("mneme.conectores.binance", "mneme.mercados.adaptadores.binance"),
                         ("mneme.conectores.solana", "mneme.mercados.adaptadores.solana")):
        assert importlib.import_module(antigo) is importlib.import_module(novo), antigo


def test_modalidades_e_liquidacao_vem_de_cada_dominio():
    from mneme import liquidacao
    from mneme.digitais.liquidacao import liquidar_digital
    from mneme.digitais.modalidade import ExpiracaoFixa
    from mneme.mercados.liquidacao import liquidar_posicao
    from mneme.mercados.modalidade import ComStop
    from mneme.motor import modalidades

    assert modalidades.ExpiracaoFixa is ExpiracaoFixa and modalidades.ComStop is ComStop
    assert liquidacao.liquidar_digital is liquidar_digital and liquidacao.liquidar_posicao is liquidar_posicao
