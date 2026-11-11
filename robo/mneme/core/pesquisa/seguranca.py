"""Checagem estática do código gerado, antes de qualquer execução. Recusa inteiro o que sair do contrato.

O contrato: um módulo que define `sinal(v)`, recebe as velas de 1 minuto (abertura, maxima, minima, fechamento, volume)
e devolve uma Series com -1, 0 ou 1 por vela. Só numpy, pandas e math. Sem arquivos, rede, processos ou introspecção.
A sandbox (container sem rede e com limites) é a segunda barreira; esta é a primeira.
"""

from __future__ import annotations

import ast

IMPORTS_PERMITIDOS = {"numpy", "pandas", "math"}
NOMES_PROIBIDOS = {"open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "dir", "getattr", "setattr",
                   "delattr", "input", "breakpoint", "help", "memoryview", "type", "object", "super", "classmethod", "staticmethod",
                   "exit", "quit", "print"}
TAMANHO_MAXIMO = 8000
# Arquivos, serialização e avaliação de texto pelas bibliotecas permitidas.
ATRIBUTOS_PROIBIDOS = {"load", "loads", "save", "savez", "savetxt", "loadtxt", "fromfile", "tofile", "genfromtxt", "memmap", "to_csv",
                       "to_parquet", "to_pickle", "to_json", "to_sql", "to_hdf", "to_feather", "to_excel", "to_clipboard", "eval", "query",
                       "pipe", "ctypeslib", "testing", "f2py", "distutils"}


class CodigoRecusado(ValueError):
    pass


def validar(codigo: str) -> None:
    if len(codigo) > TAMANHO_MAXIMO:
        raise CodigoRecusado(f"código com mais de {TAMANHO_MAXIMO} caracteres")
    try:
        arvore = ast.parse(codigo)
    except SyntaxError as erro:
        raise CodigoRecusado(f"erro de sintaxe: {erro.msg} (linha {erro.lineno})") from None
    tem_sinal = False
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name.split(".")[0] not in IMPORTS_PERMITIDOS:
                    raise CodigoRecusado(f"import não permitido: {a.name}")
        elif isinstance(no, ast.ImportFrom):
            if (no.module or "").split(".")[0] not in IMPORTS_PERMITIDOS or no.level:
                raise CodigoRecusado(f"import não permitido: {no.module}")
        elif isinstance(no, ast.Name) and no.id in NOMES_PROIBIDOS:
            raise CodigoRecusado(f"nome não permitido: {no.id}")
        elif isinstance(no, ast.Attribute) and no.attr.startswith("_"):
            raise CodigoRecusado(f"atributo privado não permitido: {no.attr}")
        elif isinstance(no, ast.Attribute) and (no.attr in ATRIBUTOS_PROIBIDOS or no.attr.startswith("read_")):
            raise CodigoRecusado(f"entrada e saída não permitidas: {no.attr}")
        elif isinstance(no, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await)):
            raise CodigoRecusado(f"construção não permitida: {type(no).__name__}")
        elif isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "shift":
            argumento = no.args[0] if no.args else next((k.value for k in no.keywords if k.arg == "periods"), None)
            if isinstance(argumento, ast.UnaryOp) and isinstance(argumento.op, ast.USub):
                raise CodigoRecusado("shift negativo: olha o futuro")
        elif isinstance(no, ast.FunctionDef) and no.name == "sinal":
            tem_sinal = True
    if not tem_sinal:
        raise CodigoRecusado("falta a função sinal(v)")
