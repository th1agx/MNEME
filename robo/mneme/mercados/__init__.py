"""Motor 01: mercados tradicionais (cripto à vista e futuros, outras corretoras, Forex, ouro, DEX, arbitragem e carry).

Domínio próprio, sobre o núcleo comum do MNEME (dados, ciclo de decisão, Risk Engine e diário). Aqui ficam o que é
específico desses mercados: liquidação com stop, alvo e tempo, modalidade com custo, e os adaptadores de corretora e de
rede (`adaptadores/`). Nas próximas etapas: executores de demo oficiais (Binance Spot e Futures), futuros com funding,
e Forex e ouro com BID e ASK.
"""
