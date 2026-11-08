"""Leitura só de leitura para os especialistas: diário do motor e eventos com cache incremental.

O quadro nunca escreve fora do próprio banco. O diário é aberto em modo só leitura, com transação curta, para não segurar
o checkpoint do WAL do motor.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd

from ..dados.eventos import CHAVES, ArmazemEventos
from ..motor.diario import Diario


class DiarioSoLeitura:
    """Usa as mesmas consultas do diário do motor, mas por uma conexão que não consegue escrever."""

    situacao_da_estrategia = Diario.situacao_da_estrategia
    contexto_vigente = Diario.contexto_vigente

    def __init__(self, caminho: Path | str):
        self.caminho = Path(caminho)
        self._local = threading.local()
        self._abertas: list[sqlite3.Connection] = []
        self._trava = threading.Lock()

    @property
    def con(self) -> sqlite3.Connection:
        """Uma conexão só de leitura por thread: os especialistas rodam em paralelo e o SQLite não divide conexão entre threads."""
        con = getattr(self._local, "con", None)
        if con is None:
            con = sqlite3.connect(f"file:{self.caminho}?mode=ro", uri=True, timeout=5, check_same_thread=False)  # só para fechar no fim
            con.row_factory = sqlite3.Row
            self._local.con = con
            with self._trava:
                self._abertas.append(con)
        return con

    def __enter__(self) -> "DiarioSoLeitura":
        return self

    def __exit__(self, *_) -> None:
        """Fecha tudo no fim do ciclo: transação curta, para não segurar o checkpoint do WAL do motor."""
        with self._trava:
            for con in self._abertas:
                con.close()
            self._abertas.clear()
        self._local = threading.local()

    def conhecida(self, chave: str) -> bool:
        return self.con.execute("SELECT 1 FROM decisoes WHERE chave = ?", (chave,)).fetchone() is not None

    def decisoes_da_vela(self, estrategias: list[str], vela: pd.Timestamp) -> list[tuple[str, str]]:
        marcas = ",".join("?" * len(estrategias))
        linhas = self.con.execute(f"SELECT chave, tipo FROM decisoes WHERE estrategia IN ({marcas}) AND vela = ?", (*estrategias, vela.isoformat()))
        return [(l["chave"], l["tipo"]) for l in linhas]


class EventosEmCache:
    """Mesmo resultado de `ArmazemEventos.ler`, mas lendo só as partes novas de cada dia e guardando uma janela curta.

    As partes do armazém nunca mudam depois de gravadas (troca atômica), e a compactação do dia cria um arquivo novo:
    por isso o caminho do arquivo identifica o conteúdo.
    """

    def __init__(self, armazem: ArmazemEventos, guardar: dict[str, pd.Timedelta]):
        self.armazem, self.guardar = armazem, guardar
        self.lidos: dict[tuple[str, str, str], set[Path]] = {}
        self.dados: dict[tuple[str, str, str], pd.DataFrame] = {}
        self._travas: dict[tuple[str, str, str], threading.Lock] = {}
        self._trava = threading.Lock()

    def _dia(self, tipo: str, par: str, dia: str, agora: pd.Timestamp) -> pd.DataFrame:
        """Uma trava por dia: quem chega enquanto outro lê espera e usa o que ele leu, em vez de reler as mesmas partes."""
        chave = (tipo, par, dia)
        with self._trava:
            trava = self._travas.setdefault(chave, threading.Lock())
        with trava:
            return self._dia_travado(chave, tipo, par, dia, agora)

    def _dia_travado(self, chave, tipo: str, par: str, dia: str, agora: pd.Timestamp) -> pd.DataFrame:
        arquivos = set(self.armazem._arquivos(tipo, par, dia))
        lidos = self.lidos.get(chave, set())
        if lidos - arquivos:  # o dia foi compactado: as partes viraram um arquivo só
            lidos, self.dados[chave] = set(), pd.DataFrame()
        novos = sorted(arquivos - lidos)
        if novos:
            partes = [self.dados.get(chave, pd.DataFrame())] + [pd.read_parquet(a) for a in novos]
            juntos = pd.concat([p for p in partes if not p.empty], ignore_index=True)
            juntos = juntos.drop_duplicates(CHAVES[tipo], keep="first")
            janela = self.guardar.get(tipo)
            if janela is not None and "ocorrido_em" in juntos and tipo != "calendario":
                juntos = juntos[juntos["ocorrido_em"] >= agora - janela]
            self.dados[chave] = juntos
            self.lidos[chave] = arquivos
        return self.dados.get(chave, pd.DataFrame())

    def ler(self, tipo: str, par: str, inicio: datetime, fim: datetime | None, como_de: datetime, agora: pd.Timestamp) -> pd.DataFrame:
        dias = pd.date_range(pd.Timestamp(inicio).normalize(), pd.Timestamp(fim or como_de).normalize(), freq="D")
        partes = [self._dia(tipo, par, f"{d:%Y-%m-%d}", agora) for d in dias]
        partes = [p for p in partes if not p.empty]
        if not partes:
            return pd.DataFrame()
        e = pd.concat(partes, ignore_index=True).drop_duplicates(CHAVES[tipo], keep="first").sort_values(CHAVES[tipo][0], ignore_index=True)
        return filtrar(e, inicio, fim, como_de)

    def esquecer_dias_velhos(self, agora: pd.Timestamp, dias: int = 2) -> None:
        limite = f"{agora - pd.Timedelta(days=dias):%Y-%m-%d}"
        with self._trava:
            velhas = [c for c in self._travas if c[2] < limite]
        for chave in velhas:
            with self._travas[chave]:
                self.dados.pop(chave, None)
                self.lidos.pop(chave, None)
            with self._trava:
                self._travas.pop(chave, None)


def filtrar(e: pd.DataFrame, inicio, fim, como_de) -> pd.DataFrame:
    """A mesma regra de `ArmazemEventos.ler`."""
    if inicio is not None:
        e = e[e["ocorrido_em"] >= pd.Timestamp(inicio)]
    if fim is not None:
        e = e[e["ocorrido_em"] < pd.Timestamp(fim)]
    if como_de is not None:
        limite = pd.Timestamp(como_de)
        e = e[(e["ocorrido_em"] <= limite) & (e["recebido_em"].isna() | (e["recebido_em"] <= limite))]
    return e.reset_index(drop=True)


class LeitorEventos:
    """Interface única dos especialistas: com cache no serviço, sem cache na reprodução (leitura fresca do armazém)."""

    def __init__(self, armazem: ArmazemEventos, cache: EventosEmCache | None = None):
        self.armazem, self.cache = armazem, cache

    def ler(self, tipo: str, par: str, inicio: datetime, como_de: datetime, fim: datetime | None = None, agora: pd.Timestamp | None = None) -> pd.DataFrame:
        if self.cache is not None:
            return self.cache.ler(tipo, par, inicio, fim, como_de, pd.Timestamp(agora or como_de))
        return self.armazem.ler(tipo, par, inicio=inicio, fim=fim, como_de=como_de)

    def agenda(self, momento: pd.Timestamp, ate: pd.Timestamp) -> pd.DataFrame:
        """Eventos do calendário marcados entre `momento` e `ate`, conhecidos até `momento`.

        O calendário guarda o evento pela hora em que acontece (futura): o corte de conhecimento é a hora de chegada.
        """
        if self.cache is not None:
            dias = pd.date_range(momento.normalize(), ate.normalize(), freq="D")
            partes = [p for p in (self.cache._dia("calendario", "GLOBAL", f"{d:%Y-%m-%d}", momento) for d in dias) if not p.empty]
            e = pd.concat(partes, ignore_index=True).drop_duplicates(CHAVES["calendario"], keep="first") if partes else pd.DataFrame()
        else:
            e = self.armazem.ler("calendario", "GLOBAL", inicio=momento, fim=ate)
        if e.empty:
            return e
        e = e[(e["ocorrido_em"] >= momento) & (e["ocorrido_em"] < ate) & (e["recebido_em"] <= momento)]
        return e.sort_values("ocorrido_em").drop_duplicates("id", keep="last").reset_index(drop=True)
