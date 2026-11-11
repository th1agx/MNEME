"""Banco do Motor 02: operações registradas nas contas demo, payouts observados e a conciliação com a referência."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS operacoes_demo (
    id TEXT PRIMARY KEY,               -- impressão do conteúdo: importar o mesmo registro duas vezes não duplica
    plataforma TEXT NOT NULL,
    ativo TEXT NOT NULL,
    otc INTEGER NOT NULL,
    direcao INTEGER NOT NULL CHECK (direcao IN (1, -1)),
    valor REAL NOT NULL CHECK (valor > 0),
    aberta_em TEXT NOT NULL,           -- UTC
    expiracao_min REAL NOT NULL CHECK (expiracao_min > 0),
    preco_entrada REAL NOT NULL,
    preco_saida REAL NOT NULL,
    payout REAL,                       -- fração mostrada pela plataforma na hora (0,85 = 85%)
    resultado TEXT NOT NULL CHECK (resultado IN ('ganho', 'perda', 'empate')),
    lucro REAL NOT NULL,               -- lucro líquido que a plataforma mostrou, na moeda da conta
    sinal_chave TEXT,                  -- chave do sinal do MNEME que motivou a operação, se houver
    observacao TEXT,
    arquivo TEXT NOT NULL,
    importado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payouts (
    plataforma TEXT NOT NULL,
    ativo TEXT NOT NULL,
    otc INTEGER NOT NULL,
    observado_em TEXT NOT NULL,
    payout REAL NOT NULL CHECK (payout > 0 AND payout < 2),
    origem TEXT NOT NULL,
    PRIMARY KEY (plataforma, ativo, otc, observado_em)
);
CREATE TABLE IF NOT EXISTS conciliacao (
    id TEXT PRIMARY KEY REFERENCES operacoes_demo(id),
    referencia TEXT NOT NULL,
    entrada_referencia REAL,
    saida_referencia REAL,
    divergencia_entrada_bps REAL,
    divergencia_saida_bps REAL,
    entrada_dentro_da_vela INTEGER,
    resultado_referencia TEXT,
    concorda INTEGER,
    conciliado_em TEXT NOT NULL
);
"""


def abrir(caminho: Path | str) -> sqlite3.Connection:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con
