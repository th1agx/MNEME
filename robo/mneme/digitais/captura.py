"""Captura assistida: uma pessoa opera na conta demo e anota numa planilha; o MNEME importa, valida e aprende as regras.

Não há robô na plataforma: a automação é proibida na Quotex, e na IQ Option não há API oficial. A planilha (CSV) tem
uma linha por operação, com o que a própria plataforma mostrou. Daí saem a tabela de payout por ativo e horário e as
regras observadas (expirações usadas, o que acontece no empate), que substituem as hipóteses do simulador.
"""

from __future__ import annotations

import csv
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .plataformas import ler_ativo, plataforma

COLUNAS = ("plataforma", "ativo", "direcao", "valor", "aberta_em", "expiracao_min", "preco_entrada", "preco_saida",
           "payout_pct", "resultado", "lucro", "sinal_chave", "observacao")
EXEMPLO = ("quotex", "EUR/USD", "CALL", "10", "2026-11-12T14:05:00-03:00", "5", "1.08412", "1.08431", "85", "ganho", "8.50", "",
           "exemplo: apague esta linha")


def modelo_csv(caminho: Path | str) -> Path:
    caminho = Path(caminho)
    with caminho.open("w", newline="", encoding="utf-8") as saida:
        w = csv.writer(saida)
        w.writerow(COLUNAS)
        w.writerow(EXEMPLO)
    return caminho


@dataclass
class Importacao:
    novas: int
    repetidas: int
    erros: list[str]


def _numero(texto: str) -> float:
    return float(str(texto).strip().replace(",", "."))


def _linha(bruta: dict) -> dict:
    """Valida uma linha. Qualquer campo fora do esperado recusa a linha inteira, com o motivo."""
    plat = plataforma(bruta["plataforma"])
    ativo = ler_ativo(bruta["ativo"])
    direcao = {"CALL": 1, "PUT": -1, "ALTA": 1, "BAIXA": -1}.get(bruta["direcao"].strip().upper())
    if direcao is None:
        raise ValueError(f"direção inválida: {bruta['direcao']!r} (use CALL ou PUT)")
    aberta = datetime.fromisoformat(bruta["aberta_em"].strip())
    if aberta.tzinfo is None:
        raise ValueError("aberta_em precisa do fuso, por exemplo 2026-11-12T14:05:00-03:00")
    resultado = bruta["resultado"].strip().lower()
    if resultado not in ("ganho", "perda", "empate"):
        raise ValueError(f"resultado inválido: {resultado!r} (use ganho, perda ou empate)")
    valor, lucro = _numero(bruta["valor"]), _numero(bruta["lucro"])
    payout = _numero(bruta["payout_pct"]) / 100 if str(bruta.get("payout_pct", "")).strip() else None
    if valor <= 0:
        raise ValueError("valor precisa ser positivo")
    if payout is not None and not 0 < payout < 2:
        raise ValueError(f"payout_pct fora do intervalo: {bruta['payout_pct']}")
    if resultado == "ganho" and lucro <= 0 or resultado == "perda" and lucro >= 0:
        raise ValueError(f"lucro {lucro} não combina com o resultado {resultado}")
    entrada, saida = _numero(bruta["preco_entrada"]), _numero(bruta["preco_saida"])
    movimento = (saida - entrada) * direcao
    if (resultado == "ganho" and movimento <= 0) or (resultado == "perda" and movimento > 0):
        raise ValueError("preços de entrada e saída não combinam com o resultado: confira a linha")
    return {"plataforma": plat, "ativo": ativo.simbolo, "otc": int(ativo.otc), "direcao": direcao, "valor": valor,
            "aberta_em": aberta.astimezone(timezone.utc).isoformat(), "expiracao_min": _numero(bruta["expiracao_min"]),
            "preco_entrada": entrada, "preco_saida": saida, "payout": payout, "resultado": resultado, "lucro": lucro,
            "sinal_chave": (bruta.get("sinal_chave") or "").strip() or None, "observacao": (bruta.get("observacao") or "").strip()[:300] or None}


def importar(con: sqlite3.Connection, csv_caminho: Path | str, agora: datetime | None = None) -> Importacao:
    agora = agora or datetime.now(timezone.utc)
    novas, repetidas, erros = 0, 0, []
    with Path(csv_caminho).open(encoding="utf-8-sig", newline="") as entrada:
        leitor = csv.DictReader(entrada)
        faltando = [c for c in COLUNAS if c not in (leitor.fieldnames or []) and c not in ("sinal_chave", "observacao", "payout_pct")]
        if faltando:
            return Importacao(0, 0, [f"colunas faltando: {', '.join(faltando)}"])
        for n, bruta in enumerate(leitor, start=2):
            if "exemplo" in (bruta.get("observacao") or "").lower():
                continue
            try:
                linha = _linha(bruta)
            except (ValueError, KeyError) as erro:
                erros.append(f"linha {n}: {erro}")
                continue
            chave = "|".join(str(linha[k]) for k in ("plataforma", "ativo", "otc", "direcao", "valor", "aberta_em", "expiracao_min", "preco_entrada", "preco_saida"))
            linha["id"] = hashlib.sha256(chave.encode()).hexdigest()[:16]
            cursor = con.execute(f"INSERT OR IGNORE INTO operacoes_demo ({', '.join(linha)}, arquivo, importado_em) VALUES "
                                 f"({', '.join('?' * len(linha))}, ?, ?)", (*linha.values(), Path(csv_caminho).name, agora.isoformat()))
            if cursor.rowcount:
                novas += 1
                payout = linha["payout"] if linha["payout"] is not None else (linha["lucro"] / linha["valor"] if linha["resultado"] == "ganho" else None)
                if payout:
                    con.execute("INSERT OR IGNORE INTO payouts VALUES (?, ?, ?, ?, ?, ?)",
                                (linha["plataforma"], linha["ativo"], linha["otc"], linha["aberta_em"], payout, "demo"))
            else:
                repetidas += 1
    con.commit()
    return Importacao(novas, repetidas, erros)


def payout_observado(con: sqlite3.Connection, plat: str, ativo: str, otc: bool, quando: datetime) -> tuple[float | None, str]:
    """Mediana do que foi observado no mesmo ativo e na mesma hora UTC; senão, no ativo; senão, nenhum (o simulador usa hipótese)."""
    linhas = con.execute("SELECT observado_em, payout FROM payouts WHERE plataforma = ? AND ativo = ? AND otc = ?", (plat, ativo, int(otc))).fetchall()
    if not linhas:
        return None, "sem observação"
    mesma_hora = [l["payout"] for l in linhas if datetime.fromisoformat(l["observado_em"]).hour == quando.astimezone(timezone.utc).hour]
    if len(mesma_hora) >= 3:
        return float(np.median(mesma_hora)), f"mediana de {len(mesma_hora)} observações na mesma hora"
    return float(np.median([l["payout"] for l in linhas])), f"mediana de {len(linhas)} observações do ativo"


def regras_observadas(con: sqlite3.Connection) -> dict:
    """O que as operações registradas mostram de cada plataforma. Sem registro, "desconhecido": nada é suposto."""
    saida = {}
    for (plat,) in con.execute("SELECT DISTINCT plataforma FROM operacoes_demo"):
        ops = con.execute("SELECT * FROM operacoes_demo WHERE plataforma = ?", (plat,)).fetchall()
        empates = [o for o in ops if o["resultado"] == "empate"]
        if not empates:
            empate = "desconhecido (nenhum empate registrado)"
        elif all(abs(o["lucro"]) < 1e-9 for o in empates):
            empate = f"devolve a aposta ({len(empates)} empates)"
        elif all(o["lucro"] <= -0.99 * o["valor"] for o in empates):
            empate = f"perde a aposta ({len(empates)} empates)"
        else:
            empate = f"misto ({len(empates)} empates): conferir"
        payouts = [o["payout"] for o in ops if o["payout"]]
        saida[plat] = {"operacoes": len(ops), "expiracoes_min": sorted({o["expiracao_min"] for o in ops}), "empate": empate,
                       "payout_mediano": float(np.median(payouts)) if payouts else None, "payout_min_max": [min(payouts), max(payouts)] if payouts else None,
                       "ativos": sorted({o["ativo"] + (" (OTC)" if o["otc"] else "") for o in ops})}
    return saida
