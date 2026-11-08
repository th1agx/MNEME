"""Banco do quadro (SQLite, WAL). Evidências e restrições são só de acréscimo: nada é reescrito nem apagado."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pandas as pd

from .esquema import Evidencia, Oportunidade, Restricao

ESQUEMA = """
CREATE TABLE IF NOT EXISTS oportunidades (
    id TEXT PRIMARY KEY, instrumentos TEXT NOT NULL, gatilho TEXT NOT NULL, tempo_grafico INTEGER, momento TEXT NOT NULL,
    modalidades TEXT NOT NULL, horizontes TEXT NOT NULL, aberta_por TEXT NOT NULL, versao_esquema INTEGER NOT NULL, aberta_em TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'aberta', impressao TEXT
);
CREATE INDEX IF NOT EXISTS oportunidades_momento ON oportunidades (momento);
CREATE TABLE IF NOT EXISTS evidencias (
    id TEXT PRIMARY KEY, oportunidade TEXT NOT NULL, especialista TEXT NOT NULL, versao TEXT NOT NULL, tipo_afirmacao TEXT NOT NULL,
    natureza TEXT NOT NULL, alvo_estatistico TEXT NOT NULL, afirmacao TEXT NOT NULL, forca REAL, confianca REAL, calibracao TEXT NOT NULL,
    desempenho_medido TEXT, criada_em TEXT NOT NULL, dados_ate TEXT NOT NULL, valido_ate TEXT NOT NULL, origem TEXT NOT NULL,
    dependencias TEXT NOT NULL, pedido TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS evidencias_oportunidade ON evidencias (oportunidade);
CREATE TABLE IF NOT EXISTS restricoes (
    id TEXT PRIMARY KEY, oportunidade TEXT NOT NULL, modalidade TEXT NOT NULL, regra TEXT NOT NULL, efeito TEXT NOT NULL,
    valor_atual TEXT NOT NULL, limite TEXT NOT NULL, fonte_config TEXT NOT NULL, momento TEXT NOT NULL, valido_ate TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS restricoes_oportunidade ON restricoes (oportunidade);
CREATE TABLE IF NOT EXISTS pedidos (
    oportunidade TEXT NOT NULL, especialista TEXT NOT NULL, situacao TEXT NOT NULL, segundos REAL NOT NULL, orcamento_s REAL NOT NULL,
    erro TEXT, quando TEXT NOT NULL, PRIMARY KEY (oportunidade, especialista)
);
CREATE TABLE IF NOT EXISTS decisoes_motor (
    oportunidade TEXT NOT NULL, chave TEXT NOT NULL, tipo TEXT NOT NULL, PRIMARY KEY (oportunidade, chave)
);
CREATE TABLE IF NOT EXISTS apuracoes (
    oportunidade TEXT NOT NULL, horizonte INTEGER NOT NULL, entrada REAL, saida REAL, retorno REAL, direcao INTEGER,
    volatilidade REAL, apurada_em TEXT NOT NULL, PRIMARY KEY (oportunidade, horizonte)
);
"""


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str, sort_keys=True)


class Quadro:
    def __init__(self, caminho: Path | str, limite_disco: float = 0.85):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self.limite_disco = limite_disco
        self.con = sqlite3.connect(self.caminho, timeout=30)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(ESQUEMA)

    def disco_cheio(self) -> bool:
        uso = shutil.disk_usage(self.caminho.parent)
        return uso.used / uso.total > self.limite_disco

    def conhecida(self, oportunidade_id: str) -> bool:
        return self.con.execute("SELECT 1 FROM oportunidades WHERE id = ?", (oportunidade_id,)).fetchone() is not None

    def gravar(self, op: Oportunidade, evidencias: list[Evidencia], restricoes: list[Restricao], pedidos: list[dict], impressao: str,
               agora: pd.Timestamp) -> bool:
        """Tudo da oportunidade numa transação só. Devolve False se já existia (idempotente)."""
        with self.con:
            cur = self.con.execute("INSERT OR IGNORE INTO oportunidades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'aberta', ?)",
                                   (op.id, _j(op.instrumentos), op.gatilho, op.tempo_grafico, op.momento.isoformat(), _j(op.modalidades),
                                    _j(op.horizontes), op.aberta_por, op.versao_esquema, agora.isoformat(), impressao))
            if cur.rowcount == 0:
                return False
            self.con.executemany("INSERT OR IGNORE INTO evidencias VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                (e.id, e.oportunidade, e.especialista, e.versao, e.tipo_afirmacao, e.natureza, e.alvo_estatistico, _j(e.afirmacao), e.forca,
                 e.confianca, _j(e.calibracao), _j(e.desempenho_medido), pd.Timestamp(e.criada_em).isoformat(), pd.Timestamp(e.dados_ate).isoformat(),
                 pd.Timestamp(e.valido_ate).isoformat(), _j(e.origem), _j(list(e.dependencias)), _j(e.pedido)) for e in evidencias])
            self.con.executemany("INSERT OR IGNORE INTO restricoes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                (r.id, r.oportunidade, r.modalidade, r.regra, r.efeito, r.valor_atual, r.limite, r.fonte_config,
                 pd.Timestamp(r.momento).isoformat(), pd.Timestamp(r.valido_ate).isoformat()) for r in restricoes])
            self.con.executemany("INSERT OR IGNORE INTO pedidos VALUES (?, ?, ?, ?, ?, ?, ?)", [
                (op.id, p["especialista"], p["situacao"], p["segundos"], p["orcamento_s"], p.get("erro"), agora.isoformat()) for p in pedidos])
        return True

    def ligar_motor(self, oportunidade_id: str, chaves: list[tuple[str, str]]) -> int:
        with self.con:
            cur = self.con.executemany("INSERT OR IGNORE INTO decisoes_motor VALUES (?, ?, ?)", [(oportunidade_id, c, t) for c, t in chaves])
        return cur.rowcount

    def sem_ligacao(self, desde: pd.Timestamp) -> list[sqlite3.Row]:
        return self.con.execute("SELECT o.id, o.instrumentos, o.tempo_grafico, o.momento, o.modalidades FROM oportunidades o WHERE o.momento >= ? "
                                "AND NOT EXISTS (SELECT 1 FROM decisoes_motor d WHERE d.oportunidade = o.id)", (desde.isoformat(),)).fetchall()

    def a_apurar(self, ate: pd.Timestamp) -> list[sqlite3.Row]:
        return self.con.execute("SELECT id, instrumentos, momento, horizontes FROM oportunidades WHERE estado = 'aberta' AND momento <= ?",
                                (ate.isoformat(),)).fetchall()

    def gravar_apuracao(self, oportunidade_id: str, linhas: list[dict], agora: pd.Timestamp, estado: str) -> None:
        with self.con:
            self.con.executemany("INSERT OR IGNORE INTO apuracoes VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
                (oportunidade_id, l["horizonte"], l.get("entrada"), l.get("saida"), l.get("retorno"), l.get("direcao"), l.get("volatilidade"),
                 agora.isoformat()) for l in linhas])
            self.con.execute("UPDATE oportunidades SET estado = ? WHERE id = ?", (estado, oportunidade_id))

    def evidencias(self, oportunidade_id: str) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM evidencias WHERE oportunidade = ?", (oportunidade_id,)).fetchall()

    def oportunidade(self, oportunidade_id: str) -> sqlite3.Row | None:
        return self.con.execute("SELECT * FROM oportunidades WHERE id = ?", (oportunidade_id,)).fetchone()
