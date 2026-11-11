"""Roteador de LLM para o pesquisador: API compatível com OpenAI quando houver chave, Ollama local como reserva.

Configuração (no .env ou no ambiente):
    MNEME_LLM_API_URL     ex.: https://api.deepseek.com/v1, https://api.groq.com/openai/v1,
                          https://generativelanguage.googleapis.com/v1beta/openai
    MNEME_LLM_API_KEY     a chave do provedor (nunca vai para o código nem para os registros)
    MNEME_LLM_API_MODELO  o modelo do provedor
    MNEME_LLM_URL         Ollama local (padrão http://127.0.0.1:11434)
    MNEME_LLM_MODELO_LOCAL  modelo local (padrão qwen2.5:3b)

Só sai do servidor o que está no pedido: o contrato da função, resumos de resultados e o código gerado antes. Chaves,
carteiras e o .env nunca entram no pedido.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Resposta:
    texto: str
    fonte: str  # "api:<modelo>" ou "local:<modelo>"


class Roteador:
    def __init__(self, cliente: httpx.Client | None = None, ambiente: dict | None = None):
        env = ambiente if ambiente is not None else os.environ
        self.api_url = (env.get("MNEME_LLM_API_URL") or "").rstrip("/")
        self.api_chave = env.get("MNEME_LLM_API_KEY") or ""
        self.api_modelo = env.get("MNEME_LLM_API_MODELO") or ""
        self.local_url = (env.get("MNEME_LLM_URL") or "http://127.0.0.1:11434").rstrip("/")
        self.local_modelo = env.get("MNEME_LLM_MODELO_LOCAL") or "qwen2.5:3b"
        self.cliente = cliente or httpx.Client(timeout=900)

    @property
    def tem_api(self) -> bool:
        return bool(self.api_url and self.api_chave and self.api_modelo)

    def texto(self, sistema: str, usuario: str, temperatura: float = 0.7) -> Resposta:
        """Tenta a API; se faltar configuração ou ela falhar, usa o modelo local. Falha das duas: exceção."""
        erros = []
        if self.tem_api:
            try:
                r = self.cliente.post(f"{self.api_url}/chat/completions", headers={"Authorization": f"Bearer {self.api_chave}"},
                                      json={"model": self.api_modelo, "temperature": temperatura, "max_tokens": 1800,
                                            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]})
                r.raise_for_status()
                return Resposta(r.json()["choices"][0]["message"]["content"], f"api:{self.api_modelo}")
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as erro:
                erros.append(f"api: {type(erro).__name__}")
        try:
            r = self.cliente.post(f"{self.local_url}/api/chat", json={
                "model": self.local_modelo, "stream": False, "think": False,
                "options": {"temperature": temperatura, "num_ctx": 6144, "num_predict": 1200},
                "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]})
            r.raise_for_status()
            return Resposta(r.json()["message"]["content"], f"local:{self.local_modelo}")
        except (httpx.HTTPError, KeyError, ValueError) as erro:
            erros.append(f"local: {type(erro).__name__}")
        raise ConnectionError("; ".join(erros))
