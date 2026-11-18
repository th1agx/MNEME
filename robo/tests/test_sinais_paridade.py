from mneme.digitais.servidor_sinais import tempo_grafico


def test_card_recebe_o_timeframe_da_estrategia_junto_com_a_paridade():
    assert tempo_grafico("EURJPY|expiracao_fixa|15m|15m") == "15m"
    assert tempo_grafico("EURUSD|expiracao_fixa|5m|5m") == "5m"
