"""Eventos de alta frequência em Parquet: partes curtas durante o dia, um arquivo só depois que o dia fecha."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

# Coluna que identifica cada evento, para recuperações que se sobrepõem não duplicarem nada.
CHAVES = {"trades": ["agg_id"], "livro": ["ocorrido_em"], "derivativos": ["ocorrido_em"], "liquidacoes": ["ocorrido_em", "lado", "preco", "quantidade"],
          "funding": ["ocorrido_em"], "open_interest": ["ocorrido_em"], "calendario": ["id", "previsao"], "previsoes": ["modelo", "ocorrido_em"],
          "noticias": ["id"], "social": ["id"], "resultados_macro": ["id", "resultado", "consenso", "anterior"],
          "carteira": ["estrategia", "tempo", "ocorrido_em"]}


class ArmazemEventos:
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz) / "fluxo"
        self._contador = 0

    def _pasta(self, tipo: str, par: str) -> Path:
        return self.raiz / tipo / par

    def gravar(self, tipo: str, par: str, linhas: list[dict]) -> int:
        """Grava uma parte nova em cada dia presente. A troca é atômica: parte pela metade nunca fica visível."""
        if not linhas:
            return 0
        eventos = pd.DataFrame(linhas)
        for coluna in ("ocorrido_em", "recebido_em"):
            valores = eventos[coluna] if coluna in eventos else [pd.NaT] * len(eventos)
            eventos[coluna] = pd.to_datetime(valores, utc=True).astype("datetime64[ms, UTC]")
        if tipo == "noticias" and eventos["recebido_em"].isna().any():
            raise ValueError("noticias requer recebido_em real para manter o corte point-in-time")
        particao = "recebido_em" if tipo == "noticias" else "ocorrido_em"
        for dia, grupo in eventos.groupby(eventos[particao].dt.strftime("%Y-%m-%d")):
            pasta = self._pasta(tipo, par) / str(dia)
            pasta.mkdir(parents=True, exist_ok=True)
            self._contador += 1
            destino = pasta / f"parte-{grupo[particao].iloc[0]:%H%M%S}-{os.getpid()}-{self._contador}.parquet"
            temporario = destino.with_suffix(".tmp")
            grupo.to_parquet(temporario, index=False, compression="zstd")
            os.replace(temporario, destino)
        return len(eventos)

    def _arquivos(self, tipo: str, par: str, dia: str | None = None) -> list[Path]:
        pasta = self._pasta(tipo, par)
        if not pasta.exists():
            return []
        arquivos = sorted(a for a in pasta.iterdir() if a.suffix == ".parquet" and (dia is None or a.stem == dia))
        for sub in sorted(p for p in pasta.iterdir() if p.is_dir() and (dia is None or p.name == dia)):
            arquivos.extend(sorted(sub.glob("*.parquet")))
        return arquivos

    @staticmethod
    def _dia(arquivo: Path) -> str:
        return arquivo.stem if arquivo.stem[:2] == "20" else arquivo.parent.name

    def _unir(self, tipo: str, arquivos: list[Path]) -> pd.DataFrame:
        if not arquivos:
            return pd.DataFrame()
        juntos = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
        return juntos.drop_duplicates(CHAVES[tipo], keep="first").sort_values(CHAVES[tipo][0], ignore_index=True)

    def ler(self, tipo: str, par: str, inicio: datetime | None = None, fim: datetime | None = None,
            como_de: datetime | None = None) -> pd.DataFrame:
        """Eventos de `inicio` até antes de `fim`. Com `como_de`, só o que já tinha chegado naquele instante."""
        arquivos = self._arquivos(tipo, par)
        if tipo != "noticias":
            arquivos = [a for a in arquivos
                        if (inicio is None or self._dia(a) >= f"{inicio:%Y-%m-%d}") and (fim is None or self._dia(a) <= f"{fim:%Y-%m-%d}")]
        eventos = self._unir(tipo, arquivos)
        if eventos.empty:
            return eventos
        coluna_tempo = "recebido_em" if tipo == "noticias" else "ocorrido_em"
        if inicio is not None:
            eventos = eventos[eventos[coluna_tempo] >= pd.Timestamp(inicio)]
        if fim is not None:
            eventos = eventos[eventos[coluna_tempo] < pd.Timestamp(fim)]
        if como_de is not None:
            limite = pd.Timestamp(como_de)
            if tipo == "noticias":
                eventos = eventos[eventos["recebido_em"].notna() & (eventos["recebido_em"] <= limite)]
            else:
                eventos = eventos[(eventos["ocorrido_em"] <= limite) & (eventos["recebido_em"].isna() | (eventos["recebido_em"] <= limite))]
        return eventos.reset_index(drop=True)

    def ultimo(self, tipo: str, par: str, coluna: str):
        """Maior valor gravado de `coluna`, olhando só o dia mais recente."""
        arquivos = self._arquivos(tipo, par)
        if not arquivos:
            return None
        dia = max(self._dia(a) for a in arquivos)
        return self._unir(tipo, [a for a in arquivos if self._dia(a) == dia])[coluna].max()

    def compactar(self, agora: datetime) -> int:
        """Junta as partes de cada dia já fechado em um arquivo só e apaga as partes depois de gravar."""
        hoje = f"{agora:%Y-%m-%d}"
        feitos = 0
        if not self.raiz.exists():
            return 0
        for pasta_tipo in (p for p in self.raiz.iterdir() if p.is_dir()):  # a raiz também guarda o arquivo de batimento
            for pasta_par in (p for p in pasta_tipo.iterdir() if p.is_dir()):
                for sub in [p for p in pasta_par.iterdir() if p.is_dir() and p.name < hoje]:
                    tipo = pasta_tipo.name
                    destino = pasta_par / f"{sub.name}.parquet"
                    temporario = destino.with_name(f"{destino.stem}-{os.getpid()}.tmp")
                    try:
                        arquivos = ([destino] if destino.exists() else []) + sorted(sub.glob("*.parquet"))
                        self._unir(tipo, arquivos).to_parquet(temporario, index=False, compression="zstd")
                        os.replace(temporario, destino)
                        shutil.rmtree(sub)
                    except FileNotFoundError:
                        # Outro processo compactou este dia ao mesmo tempo: o trabalho já está feito.
                        temporario.unlink(missing_ok=True)
                        continue
                    feitos += 1
        return feitos

    def limpar(self, tipo: str, dias: int, agora: datetime) -> int:
        """Apaga o que for mais velho que `dias`. Devolve quantos dias foram apagados, somando os pares."""
        corte = f"{agora - timedelta(days=dias):%Y-%m-%d}"
        apagados = 0
        pasta_tipo = self.raiz / tipo
        if not pasta_tipo.exists():
            return 0
        for pasta_par in (p for p in pasta_tipo.iterdir() if p.is_dir()):
            for item in list(pasta_par.iterdir()):
                dia = item.stem if item.is_file() else item.name
                if dia < corte:
                    shutil.rmtree(item) if item.is_dir() else item.unlink()
                    apagados += 1
        return apagados

    def tamanho_por_dia(self, tipo: str, par: str) -> dict[str, int]:
        tamanhos: dict[str, int] = {}
        for arquivo in self._arquivos(tipo, par):
            dia = self._dia(arquivo)
            tamanhos[dia] = tamanhos.get(dia, 0) + arquivo.stat().st_size
        return tamanhos
