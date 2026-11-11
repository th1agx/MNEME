"""Caminho antigo, mantido para compatibilidade: o placar ao vivo agora fica em `mneme.digitais.ao_vivo`.

É um apelido exato do módulo novo (o mesmo objeto em sys.modules), então importar, usar nomes privados e
`monkeypatch` funcionam pelos dois caminhos.
"""
import sys

from .digitais import ao_vivo as _modulo

sys.modules[__name__] = _modulo

if __name__ == "__main__":  # `python -m mneme.ao_vivo` continua funcionando
    _modulo.main()
