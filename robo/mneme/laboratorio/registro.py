"""Registro de experimentos: toda tentativa fica anotada, inclusive as ruins, para a correção estatística contar todas."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def impressao_dos_dados(v: pd.DataFrame) -> str:
    """Identifica o conjunto de dados usado: qualquer vela diferente muda o resultado."""
    colunas = [c for c in ("abertura", "maxima", "minima", "fechamento", "volume") if c in v]
    soma = pd.util.hash_pandas_object(v[colunas], index=True).to_numpy().tobytes()
    return hashlib.sha256(soma).hexdigest()[:16]


RAIZ = Path(__file__).resolve().parents[3]  # raiz do repositório (robo/mneme/laboratorio/registro.py)


def commit_atual() -> str:
    """Versão do código que gerou o resultado. Ordem: MNEME_COMMIT, git na pasta do código, arquivo VERSAO gravado no deploy.

    Na A1 o código não é um checkout git, então o deploy grava o hash em VERSAO. Sem nenhum dos três, "desconhecido".
    """
    if os.getenv("MNEME_COMMIT", "").strip():
        return os.environ["MNEME_COMMIT"].strip()
    try:
        saida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5, cwd=RAIZ).stdout.strip()
        if saida:
            return saida
    except (OSError, subprocess.SubprocessError):
        pass
    for arquivo in (RAIZ / "VERSAO", RAIZ / "robo" / "VERSAO"):
        if arquivo.is_file() and arquivo.read_text(encoding="utf-8").strip():
            return arquivo.read_text(encoding="utf-8").split()[0]
    return "desconhecido"


class Registro:
    def __init__(self, caminho: Path | str, commit: str | None = None):
        self.caminho = Path(caminho)
        self.commit = commit if commit is not None else commit_atual()

    def anotar(self, familia: str, nome: str, parametros: dict, dados: str, resultado: dict, quando: datetime | None = None) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        linha = {"quando": (quando or datetime.now(timezone.utc)).isoformat(), "familia": familia, "nome": nome, "parametros": parametros,
                 "dados": dados, "commit": self.commit, "resultado": resultado}
        with self.caminho.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False, default=float) + "\n")

    def todos(self, familia: str | None = None) -> list[dict]:
        if not self.caminho.exists():
            return []
        linhas = [json.loads(l) for l in self.caminho.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [l for l in linhas if familia is None or l["familia"] == familia]

    def tentativas(self, familia: str) -> int:
        """Quantas combinações diferentes já foram testadas. Repetir a mesma com os mesmos dados não conta de novo."""
        return len({(l["nome"], json.dumps(l["parametros"], sort_keys=True)) for l in self.todos(familia)})
