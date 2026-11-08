"""Resumo diário do quadro, só descritivo: cobertura, falhas, latência, conflitos e o poder de cada fonte sozinha."""

from __future__ import annotations

import json
from math import sqrt

from .banco import Quadro


def _wilson(acertos: int, n: int) -> tuple[float, float]:
    if not n:
        return float("nan"), float("nan")
    p, z = acertos / n, 1.96
    centro, margem = (p + z * z / (2 * n)) / (1 + z * z / n), z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centro - margem, centro + margem


def resumo(quadro: Quadro, dia: str) -> dict:
    q = quadro.con.execute
    ops = q("SELECT estado, COUNT(*) n FROM oportunidades WHERE substr(momento, 1, 10) = ? GROUP BY estado", (dia,)).fetchall()
    pedidos = q("SELECT p.especialista, p.situacao, COUNT(*) n, AVG(p.segundos) media, MAX(p.segundos) maximo FROM pedidos p "
                "JOIN oportunidades o ON o.id = p.oportunidade WHERE substr(o.momento, 1, 10) = ? GROUP BY 1, 2", (dia,)).fetchall()
    ligadas = q("SELECT COUNT(DISTINCT d.oportunidade) FROM decisoes_motor d JOIN oportunidades o ON o.id = d.oportunidade WHERE substr(o.momento, 1, 10) = ?",
                (dia,)).fetchone()[0]
    # Poder de cada fonte sozinha: direção afirmada contra a direção apurada no horizonte do próprio alvo.
    fontes = {}
    for e in q("SELECT e.especialista, e.natureza, e.afirmacao, e.alvo_estatistico, o.tempo_grafico, o.id FROM evidencias e JOIN oportunidades o ON o.id = e.oportunidade "
               "WHERE substr(o.momento, 1, 10) = ? AND e.tipo_afirmacao IN ('direcional', 'fluxo')", (dia,)):
        a = json.loads(e["afirmacao"])
        direcao = a.get("direcao") or 0
        if not direcao:
            continue
        h = int(e["alvo_estatistico"].split("t+")[1].split("min")[0]) if "t+" in e["alvo_estatistico"] else e["tempo_grafico"]
        real = q("SELECT direcao FROM apuracoes WHERE oportunidade = ? AND horizonte = ?", (e["id"], h)).fetchone()
        if real is None or not real["direcao"]:
            continue
        nome = f"{e['especialista']}:{e['natureza']}" + (f":{a['versao_prob']}" if a.get("versao_prob") else "") + (":apos_treino" if a.get("apos_treino") else "")
        f = fontes.setdefault(nome, [0, 0])
        f[0] += int(direcao == real["direcao"])
        f[1] += 1
    conflitos = q("SELECT COUNT(*) FROM (SELECT e.oportunidade FROM evidencias e JOIN oportunidades o ON o.id = e.oportunidade WHERE substr(o.momento, 1, 10) = ? "
                  "AND e.tipo_afirmacao IN ('direcional', 'fluxo') AND json_extract(e.afirmacao, '$.direcao') IN (1, -1) GROUP BY e.oportunidade "
                  "HAVING MIN(json_extract(e.afirmacao, '$.direcao')) = -1 AND MAX(json_extract(e.afirmacao, '$.direcao')) = 1)", (dia,)).fetchone()[0]
    total = sum(o["n"] for o in ops)
    return {"dia": dia, "oportunidades": total, "por_estado": {o["estado"]: o["n"] for o in ops}, "ligadas_ao_motor": ligadas, "com_conflito": conflitos,
            "pedidos": [{"especialista": p["especialista"], "situacao": p["situacao"], "n": p["n"], "media_s": round(p["media"], 3), "max_s": round(p["maximo"], 3)} for p in pedidos],
            "fontes": {k: {"acertos": a, "n": n, "acerto": a / n, "ic95": _wilson(a, n)} for k, (a, n) in sorted(fontes.items())},
            "ausentes": ["XGBoost ao vivo (só nos estudos)", "previsão de volatilidade ao vivo (sem artefato em produção)", "Forex e ouro ao vivo (sem fonte)"]}
