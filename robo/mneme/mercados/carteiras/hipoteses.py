"""Hipóteses de carteiras, registradas em 11/11/2026, antes de qualquer coleta nova (W1).

Nasceram olhando o histórico de 01 a 08/11/2026, por isso esse histórico não serve para testá-las: só valem dados com
hora posterior a `REGISTRADAS_EM`. O commit deste arquivo no git é a prova da data. Mudar uma hipótese depois de ver os
dados novos exige registrar outra, com data nova; esta fica como estava.

Exploração e confirmação seguem a régua do E9: primeira metade da coleta explora, segunda confirma, e só então o
simulado ao vivo. Nenhuma carteira vira sinal de compra por passar aqui: o uso previsto de H1 é filtro de risco.

    python -m mneme.mercados.carteiras.hipoteses           # grava no registro do laboratório (uma vez só)
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from ...config import PASTA_DADOS
from ...laboratorio.registro import Registro

REGISTRADAS_EM = datetime(2026, 11, 11, tzinfo=timezone.utc)


@dataclass(frozen=True)
class HipoteseCarteira:
    codigo: str
    enunciado: str
    contraria: str
    medida: str
    alvo: str
    teste: str
    minimo: str
    rivais: tuple[str, ...]
    uso_se_confirmar: str


HIPOTESES = (
    HipoteseCarteira(
        "H1", "Onda de compras de carteiras rastreadas logo depois de alta forte antecede queda do token.",
        "Depois de alta forte, o retorno do token na hora seguinte não difere do placebo.",
        "Onda: pelo menos 2 carteiras rastreadas comprando o mesmo token em 15 min. Alta forte: mais de +20% nos 60 min anteriores à primeira compra.",
        "Retorno do token de 1 a 61 min depois da primeira compra da onda, com custo de DEX de 1,2% ida e volta.",
        "Mediana contra minutos sorteados no mesmo token (placebo) com bootstrap por token; uma onda por token por hora.",
        "300 ondas na exploração e 300 na confirmação.",
        ("acaso", "selecao", "custo", "artefato_de_dado", "causa_comum"),
        "Filtro de risco: não comprar (ou sair) depois de uma onda; atributo para o E9. Nunca sinal de venda a descoberto em DEX."),
    HipoteseCarteira(
        "H2", "Carteiras com resultado líquido positivo nas primeiras N posições continuam positivas nas N seguintes.",
        "O resultado nas N seguintes não depende do resultado nas N primeiras.",
        "Posições encerradas por carteira, em ordem de fechamento, com custo de 1,2% ida e volta.",
        "Média líquida das N posições seguintes, por grupo (positivas antes contra negativas antes).",
        "Diferença entre os grupos com permutação dos rótulos; controle: carteiras sorteadas fora do ranking original.",
        "N = 15 por carteira; pelo menos 40 carteiras com 2N posições.",
        ("acaso", "selecao", "regime", "custo"),
        "Ordenar quais carteiras observar; atributo para o E9. Não é copy trading."),
    HipoteseCarteira(
        "H3", "A primeira compra de uma carteira rastreada num token ainda não negociado por outras rastreadas antecipa alta.",
        "O retorno depois da primeira compra não difere do placebo no mesmo token.",
        "Primeira compra de qualquer carteira rastreada num token sem compra rastreada nas 24 h anteriores.",
        "Retorno de 1 a 61 min e de 1 a 241 min depois da compra, com custo de 1,2% ida e volta e latência real do rastreador.",
        "Mediana contra placebo no mesmo token e contra a mesma regra aplicada às carteiras de controle sorteadas.",
        "200 primeiras compras na exploração e 200 na confirmação.",
        ("acaso", "selecao", "olhar_o_futuro", "custo", "causa_comum"),
        "Atributo para o E9 e para o mapa de previsibilidade. Só vira estratégia com confirmação e simulado ao vivo."),
)


def registrar(registro: Registro) -> int:
    """Grava cada hipótese no registro do laboratório uma vez só. Devolve quantas foram gravadas agora."""
    ja = {l["nome"] for l in registro.todos("carteiras")}
    novas = 0
    for h in HIPOTESES:
        nome = f"hipótese {h.codigo}"
        if nome in ja:
            continue
        registro.anotar("carteiras", nome, {"registradas_em": REGISTRADAS_EM.isoformat(), "so_dados_depois_de": REGISTRADAS_EM.isoformat()},
                        "sem-dados", {**asdict(h), "natureza": "hipotese", "situacao": "registrada, aguardando coleta"}, quando=REGISTRADAS_EM)
        novas += 1
    return novas


def main() -> None:
    p = argparse.ArgumentParser(prog="mneme.mercados.carteiras.hipoteses")
    p.add_argument("--registro", default=str(PASTA_DADOS / "laboratorio" / "experimentos.jsonl"))
    a = p.parse_args()
    print(f"{registrar(Registro(a.registro))} hipótese(s) gravada(s) agora; {len(HIPOTESES)} no total.")


if __name__ == "__main__":
    main()
