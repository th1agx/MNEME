"""Sandbox: roda o código gerado longe do MNEME e devolve só a série de sinais.

Em produção, um container descartável da própria imagem do robô, **sem rede**, só leitura, com memória, CPU, processos e
tempo limitados. Ele recebe apenas as velas do período sendo medido (nunca o futuro nem a área selada) e o código; não
recebe chaves, banco ou dados de mercado além disso. O executor também calcula o sinal em prefixos dos dados: se o
sinal de uma vela muda quando o futuro é escondido, o código olha o futuro e é recusado.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EXECUTOR = r'''
import builtins, json, math, sys, traceback
import numpy as np
import pandas as pd

PERMITIDOS = {"numpy", "pandas", "math"}
_import = builtins.__import__
def _import_seguro(nome, *a, **k):
    if nome.split(".")[0] not in PERMITIDOS:
        raise ImportError(f"import não permitido: {nome}")
    return _import(nome, *a, **k)

SEGUROS = {n: getattr(builtins, n) for n in ("abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len", "list", "max",
           "min", "pow", "range", "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip", "isinstance",
           "map", "filter", "ValueError", "ZeroDivisionError", "Exception", "True", "False", "None")}
SEGUROS["__import__"] = _import_seguro

pasta = sys.argv[1]
saida = {"erro": None}
try:
    v = pd.read_parquet(f"{pasta}/velas.parquet")
    ns = {"__builtins__": SEGUROS, "np": np, "pd": pd, "math": math}
    exec(compile(open(f"{pasta}/codigo.py").read(), "codigo_gerado", "exec"), ns)

    # Apelidos em inglês dos mesmos dados: modelos pequenos insistem em close/high. Não muda nenhum valor.
    APELIDOS = {"open": "abertura", "high": "maxima", "low": "minima", "close": "fechamento"}

    def rodar(dados):
        dados = dados.copy()
        for apelido, coluna in APELIDOS.items():
            if coluna in dados and apelido not in dados:
                dados[apelido] = dados[coluna]
        try:
            s = ns["sinal"](dados)
        except KeyError as erro:
            raise KeyError(f"{erro}; colunas disponíveis: {', '.join(map(str, dados.columns))}") from None
        s = pd.Series(s, index=dados.index) if not isinstance(s, pd.Series) else s.reindex(dados.index)
        return np.sign(pd.to_numeric(s, errors="coerce").fillna(0)).astype("int8")

    completo = rodar(v)
    mudancas = 0
    for fracao in (0.5, 0.8):
        corte = int(len(v) * fracao)
        parcial = rodar(v.iloc[:corte])
        mudancas += int((parcial.to_numpy() != completo.iloc[:corte].to_numpy()).sum())
    completo.rename("sinal").to_frame().to_parquet(f"{pasta}/sinal.parquet")
    saida.update({"mudancas_com_futuro_escondido": mudancas, "sinais": int((completo != 0).sum())})
except Exception as erro:
    saida["erro"] = f"{type(erro).__name__}: {erro}"[:300]
open(f"{pasta}/saida.json", "w").write(json.dumps(saida))
'''


@dataclass(frozen=True)
class Execucao:
    sinal: pd.Series | None
    erro: str | None
    olha_o_futuro: bool = False


class _Base:
    tempo_limite = 300

    def _comando(self, pasta: Path) -> list[str]:
        raise NotImplementedError

    def executar(self, codigo: str, velas: pd.DataFrame) -> Execucao:
        pasta = Path(tempfile.mkdtemp(prefix="e9gen_"))
        try:
            os.chmod(pasta, 0o777)
            velas.to_parquet(pasta / "velas.parquet")
            (pasta / "codigo.py").write_text(codigo, encoding="utf-8")
            (pasta / "executor.py").write_text(EXECUTOR, encoding="utf-8")
            for f in pasta.iterdir():
                os.chmod(f, 0o644)
            try:
                subprocess.run(self._comando(pasta), capture_output=True, timeout=self.tempo_limite, check=False)
            except subprocess.TimeoutExpired:
                return Execucao(None, f"tempo esgotado ({self.tempo_limite} s)")
            if not (pasta / "saida.json").exists():
                return Execucao(None, "a sandbox não devolveu resultado")
            saida = json.loads((pasta / "saida.json").read_text(encoding="utf-8"))
            if saida["erro"]:
                return Execucao(None, saida["erro"])
            if saida["mudancas_com_futuro_escondido"]:
                return Execucao(None, f"olha o futuro: {saida['mudancas_com_futuro_escondido']} velas mudam quando o futuro é escondido", True)
            return Execucao(pd.read_parquet(pasta / "sinal.parquet")["sinal"], None)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)


class SandboxDocker(_Base):
    """Container descartável, sem rede, só leitura, com limites. A imagem é a do robô (tem numpy e pandas)."""

    def __init__(self, imagem: str = "robo-motor:latest", memoria: str = "768m", cpus: str = "0.5", tempo_limite: int = 300):
        self.imagem, self.memoria, self.cpus, self.tempo_limite = imagem, memoria, cpus, tempo_limite

    def _comando(self, pasta: Path) -> list[str]:
        return ["nice", "-n", "15", "docker", "run", "--rm", "--network", "none", "--read-only", "--tmpfs", "/tmp:size=64m",
                "--memory", self.memoria, "--cpus", self.cpus, "--pids-limit", "64", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "-v", f"{pasta}:/trabalho", self.imagem, ".venv/bin/python", "/trabalho/executor.py", "/trabalho"]


class SandboxLocal(_Base):
    """Só para testes e desenvolvimento: outro processo Python, sem o isolamento do container."""

    def _comando(self, pasta: Path) -> list[str]:
        return [sys.executable, str(pasta / "executor.py"), str(pasta)]
