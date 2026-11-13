"""Roda o robô em laço: `uv run python -m mneme` (Ctrl+C para parar)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from . import banco, config
from .digitais import ao_vivo
from .carteira import Carteira, LimitesDia
from .ciclo import rodar_ciclo
from .mercados.adaptadores.binance import VelasBinance
from .mercados.adaptadores.solana import MercadoSolana
from .estrategias.seguir_traders import Regra
from .sinais import ProvedorIndisponivel, ProvedorSinais
from .telegram import Telegram
from .travas import travar_exclusivo

log = logging.getLogger("mneme")


def ler_configuracoes(url: str) -> tuple[Regra, LimitesDia] | None:
    """Lê a tela de Configurações do site. Sem resposta, o ciclo só observa."""
    try:
        dados = httpx.get(url, timeout=8).json()
    except (httpx.HTTPError, ValueError):
        return None
    return Regra.das_configuracoes(dados), LimitesDia(dados.get("dailyProfitTargetPct"), dados.get("dailyLossLimitPct"))


class Segredos(logging.Filter):
    """Troca tokens e chaves por *** em toda linha de log, inclusive nos tracebacks."""

    def __init__(self, segredos: list[str]):
        super().__init__()
        self.segredos = [x for x in segredos if x]

    def _limpar(self, texto: str) -> str:
        for segredo in self.segredos:
            texto = texto.replace(segredo, "***")
        return texto

    def filter(self, registro: logging.LogRecord) -> bool:
        registro.msg, registro.args = self._limpar(registro.getMessage()), None
        if registro.exc_info and not registro.exc_text:
            registro.exc_text = self._limpar(logging.Formatter().formatException(registro.exc_info))
        return True


def travar(caminho: Path):
    """Um robô de traders por banco: a segunda cópia sai em vez de operar em dobro."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    trava = caminho.open("a+")
    try:
        travar_exclusivo(trava)
    except BlockingIOError:
        trava.close()
        raise SystemExit(f"Outro robô de traders já usa {caminho.parent}; esta cópia não vai rodar.")
    return trava


def bater(batimento: Path, agora: datetime) -> None:
    """Marca que o ciclo terminou; o health check do Docker lê este arquivo."""
    batimento.write_text(agora.isoformat(), encoding="utf-8")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    # Sem o log de cada requisição: o endereço do provedor não deve aparecer na tela nem em logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    cfg = config.carregar()
    filtro = Segredos([cfg.telegram_token, cfg.signals_api_key, cfg.signals_rest_url])
    for saida in logging.getLogger().handlers:
        saida.addFilter(filtro)
    trava = travar(cfg.banco.with_name("traders.trava"))  # noqa: F841 - fica aberta enquanto o robô roda
    batimento = cfg.banco.with_name("traders.batimento")
    con = banco.abrir(cfg.banco)
    try:
        provedor: ProvedorSinais | None = ProvedorSinais(cfg.signals_rest_url, cfg.signals_api_key)
    except ProvedorIndisponivel as erro:
        log.warning(str(erro))
        provedor = None
    mercado = MercadoSolana()
    velas = VelasBinance()
    tg = Telegram(cfg.telegram_token, cfg.telegram_grupo)
    if not tg.configurado:
        log.warning("Sem TELEGRAM_BOT_TOKEN e TELEGRAM_GROUP_ID no .env: as dicas ficam na fila, sem envio.")
    vazia = Regra(None, None, None, None, None)
    log.info("Robô MNEME rodando no simulado. Banco: %s", cfg.banco)
    while True:
        inicio = time.monotonic()
        agora = datetime.now(timezone.utc)
        lidas = ler_configuracoes(cfg.configuracoes_url)
        regra, limites = lidas if lidas else (vazia, LimitesDia(None, None))
        try:
            resumo = rodar_ciclo(con, provedor, mercado, regra, limites, agora)
            try:
                dicas = tg.enviar_pendentes(con, agora)
            except Exception:  # o Telegram nunca para o robô: a fila tenta de novo no próximo ciclo
                log.exception("Envio das dicas falhou; elas seguem na fila.")
                dicas = 0
            novas_velas = sum(velas.coletar(con, par, agora) for par in cfg.pares_velas)
            sinais = sum(ao_vivo.gravar_sinais(con, par, agora) for par in cfg.pares_velas)
            ao_vivo.conferir(con)
            patrimonio = Carteira(con).patrimonio()
            con.commit()  # não deixa transação aberta entre ciclos, para o estudo poder gravar
            bater(batimento, agora)
            log.info("operações novas %d · compras %d · vendas %d · dicas %d · velas %d · sinais %d · %s · patrimônio US$ %.2f%s%s",
                     resumo.operacoes_novas, resumo.compras, resumo.vendas, dicas, novas_velas, sinais, ao_vivo.resumo(con), patrimonio,
                     "" if lidas else " · sem Configurações (só observa)",
                     "".join(f" · {aviso}" for aviso in resumo.avisos))
        except Exception:
            log.exception("Ciclo falhou; tenta de novo no próximo.")
        time.sleep(max(1, cfg.intervalo_segundos - (time.monotonic() - inicio)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
