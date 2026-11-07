"""OpenMP para o LightGBM e o XGBoost no macOS, sem Homebrew.

No Linux (Oracle, Docker, CI) a libgomp do sistema resolve. No Mac, as rodas do PyPI procuram `@rpath/libomp.dylib`
em pastas do Homebrew. O scikit-learn já traz uma libomp dentro do próprio pacote: aqui ela é copiada para dentro do
ambiente virtual com o nome que o LightGBM procura e carregada antes dele. Nada é instalado fora do `.venv`.
"""

from __future__ import annotations

import ctypes
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

DO_SISTEMA = (Path("/opt/homebrew/opt/libomp/lib/libomp.dylib"), Path("/usr/local/opt/libomp/lib/libomp.dylib"))


def destino() -> Path:
    return Path(sys.prefix) / "lib" / "mneme-openmp" / "libomp.dylib"


def da_biblioteca() -> Path | None:
    """A libomp que vem dentro do scikit-learn, sem importar o pacote."""
    spec = importlib.util.find_spec("sklearn")
    if spec is None or spec.origin is None:
        return None
    caminho = Path(spec.origin).parent / ".dylibs" / "libomp.dylib"
    return caminho if caminho.exists() else None


def preparar(plataforma: str = sys.platform) -> Path | None:
    """Devolve a libomp carregada, ou None quando não precisa (Linux, Homebrew presente) ou não há como."""
    if plataforma != "darwin" or any(p.exists() for p in DO_SISTEMA):
        return None
    alvo = destino()
    origem = da_biblioteca()
    try:
        if origem and (not alvo.exists() or alvo.stat().st_mtime < origem.stat().st_mtime):
            alvo.parent.mkdir(parents=True, exist_ok=True)
            temporario = alvo.with_suffix(".tmp")
            shutil.copy2(origem, temporario)
            # O nome interno precisa ser o que o LightGBM pede; a assinatura muda junto, então assina de novo (ad hoc).
            subprocess.run(["install_name_tool", "-id", "@rpath/libomp.dylib", str(temporario)], check=True, capture_output=True)
            subprocess.run(["codesign", "--force", "--sign", "-", str(temporario)], check=True, capture_output=True)
            temporario.replace(alvo)
        if not alvo.exists():
            return None
        ctypes.CDLL(str(alvo), mode=ctypes.RTLD_GLOBAL)
        return alvo
    except (OSError, subprocess.CalledProcessError):
        return None  # sem a libomp, o próprio LightGBM explica o erro ao ser importado
