"""Arquivo de descobertas e falhas do E9 generativo: um registro que só cresce, uma linha por tentativa.

Toda tentativa entra, inclusive a que nem compilou: a falha e o motivo voltam para o pesquisador na geração seguinte,
e a contagem honesta de tentativas é o que dá sentido à estatística.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from ...laboratorio.registro import commit_atual
from ...laboratorio.validacao import holm


def impressao_do_codigo(codigo: str) -> str:
    """O mesmo código com outros comentários ou espaços é a mesma ideia."""
    sem_comentarios = re.sub(r"#[^\n]*", "", codigo)
    return hashlib.sha256(re.sub(r"\s+", "", sem_comentarios).encode()).hexdigest()[:16]


class Arquivo:
    def __init__(self, caminho: Path | str, commit: str | None = None):
        self.caminho = Path(caminho)
        self.commit = commit if commit is not None else commit_atual()

    def todas(self) -> list[dict]:
        if not self.caminho.exists():
            return []
        return [json.loads(l) for l in self.caminho.read_text(encoding="utf-8").splitlines() if l.strip()]

    def impressoes(self) -> set[str]:
        return {l["id"] for l in self.todas() if l.get("id")}

    def pendentes_de_confirmacao(self) -> list[dict]:
        linhas = self.todas()
        confirmadas = {l["id"] for l in linhas if l["fase"] == "confirmacao"}
        return [l for l in linhas if l["fase"] == "exploracao" and l.get("veredito") == "promissora" and l["id"] not in confirmadas]

    def estatisticas_por_braco(self) -> dict[tuple[str, int], dict]:
        """Tentativas e promissoras por (par, minutos): a recompensa da agenda."""
        est: dict[tuple[str, int], dict] = defaultdict(lambda: {"tentativas": 0, "promissoras": 0})
        for l in self.todas():
            if l["fase"] != "exploracao":
                continue
            b = (l["braco"]["par"], int(l["braco"]["minutos"]))
            est[b]["tentativas"] += 1
            est[b]["promissoras"] += l.get("veredito") == "promissora"
        return dict(est)

    def resumo_para_pesquisador(self, melhores: int = 5, falhas: int = 8) -> dict:
        """O que o pesquisador precisa saber para não repetir: as melhores medidas e as falhas recentes, com o motivo."""
        linhas = self.todas()
        medidas = [l for l in linhas if l.get("resultado") and l["resultado"].get("sinais")]
        top = sorted(medidas, key=lambda l: l["resultado"]["acerto"], reverse=True)[:melhores]
        return {
            "tentativas": len(linhas), "promissoras": sum(l.get("veredito") == "promissora" for l in linhas),
            "candidatas": sum(l.get("veredito") == "candidata" for l in linhas),
            "melhores_medidas": [{"ideia": l["ideia"], "par": l["braco"]["par"], "minutos": l["braco"]["minutos"], "acerto": round(l["resultado"]["acerto"], 4),
                                  "sinais": l["resultado"]["sinais"], "veredito": l.get("veredito")} for l in top],
            "falhas_recentes": [{"ideia": l["ideia"], "etapa": l["etapa_falha"], "motivo": l["motivo_falha"]} for l in linhas if l.get("etapa_falha")][-falhas:],
            "ideias_ja_tentadas": [l["ideia"] for l in linhas if l.get("ideia")][-25:],
        }

    def anotar(self, quando: datetime, fase: str, braco: dict, proposta: dict, resultado: dict | None = None,
               etapa_falha: str | None = None, motivo_falha: str | None = None) -> dict:
        from ...aprendizado import veredito  # a mesma régua do E9 de enumeração

        linha = {"id": impressao_do_codigo(proposta.get("codigo", "")), "quando": quando.isoformat(), "fase": fase, "braco": braco,
                 "fonte": proposta.get("fonte"), "ideia": proposta.get("ideia", "")[:300], "mecanismo": proposta.get("mecanismo", "")[:500],
                 "codigo": proposta.get("codigo", ""), "etapa_falha": etapa_falha, "motivo_falha": (motivo_falha or "")[:300] or None,
                 "resultado": resultado, "commit": self.commit}
        if resultado is not None and etapa_falha is None:
            anteriores = [l for l in self.todas() if l["fase"] == fase and l.get("resultado") and l.get("etapa_falha") is None]
            if fase == "confirmacao":
                p = holm([l["resultado"]["p_valor"] for l in anteriores] + [resultado["p_valor"]])[-1]
            else:
                p = resultado["p_valor"]
            linha.update({"p": p, "testes_ate_agora": len(anteriores) + 1, "veredito": veredito(resultado, p, fase)})
        else:
            linha["veredito"] = "falhou"
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.caminho.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False, default=float) + "\n")
        return linha
