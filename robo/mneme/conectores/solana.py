"""Caminho antigo, mantido para compatibilidade: o adaptador agora fica em `mneme.mercados.adaptadores.solana`.

É um apelido exato do módulo novo (o mesmo objeto em sys.modules), então importar, usar nomes privados e
`monkeypatch` funcionam pelos dois caminhos.
"""
import sys

from ..mercados.adaptadores import solana as _modulo

sys.modules[__name__] = _modulo
