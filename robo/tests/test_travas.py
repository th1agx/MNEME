from __future__ import annotations

import pytest


def test_trava_exclusiva_nao_bloqueante(tmp_path):
    from mneme.travas import travar_exclusivo

    caminho = tmp_path / "ciclo.trava"
    with caminho.open("a+") as primeira:
        travar_exclusivo(primeira)
        with caminho.open("a+") as segunda:
            with pytest.raises(BlockingIOError):
                travar_exclusivo(segunda)

    with caminho.open("a+") as terceira:
        travar_exclusivo(terceira)
