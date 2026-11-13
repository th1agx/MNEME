"""Bloqueios de arquivo exclusivos e sem espera, portáveis entre POSIX e Windows."""

from __future__ import annotations

import errno
import os
from typing import TextIO


def travar_exclusivo(arquivo: TextIO) -> None:
    """Adquire uma trava exclusiva sem esperar; conflitos viram ``BlockingIOError``."""
    if os.name == "nt":
        import msvcrt

        arquivo.flush()
        arquivo.seek(0, os.SEEK_END)
        if arquivo.tell() == 0:
            arquivo.write("\0")
            arquivo.flush()
        arquivo.seek(0)
        try:
            msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as erro:
            conflitos = {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
            if erro.errno in conflitos:
                raise BlockingIOError(errno.EWOULDBLOCK, "arquivo já está bloqueado") from erro
            raise
        return

    import fcntl

    fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
