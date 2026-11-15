"""Servidor dos sinais do cenário escolhido para o card da extensão do Chrome (Motor 02). Tudo fica na VPS.

Escuta só dentro da VPS (o compose publica em 127.0.0.1:8787); a extensão chega por um túnel SSH a partir do Mac
(`colaborar/tunel-sinais.sh`). Nenhuma porta abre para a internet e nada passa pela Cloudflare.

- GET  /api/sinais          sinais dos últimos 30 minutos das estratégias de `dados/digitais/cenario.json`, com o resultado
- POST /api/sinais/entrada  o que a pessoa fez: entrou ou não e o payout que a corretora mostrou (captura assistida)

Lê o diário do motor só para leitura. O "entrei" fica em `dados/digitais/entradas.db`. Nada aqui opera: quem clica na
corretora é sempre a pessoa. A chave de leitura vem do `.env` (`MNEME_SINAIS_LER`).

    python -m mneme.digitais.servidor_sinais
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..config import PASTA_DADOS

log = logging.getLogger("mneme.sinais")
JANELA = timedelta(minutes=30)
CORRETORAS = {"quotex", "iqoption", "outra"}


class ErroPedido(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status


class Servidor:
    def __init__(self, diario: Path, cenario: Path, entradas: Path, chave: str, relogio=lambda: datetime.now(timezone.utc)):
        self.diario, self.cenario, self.entradas, self.chave, self.relogio = Path(diario), Path(cenario), Path(entradas), chave, relogio
        self.entradas.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.entradas) as con:
            con.execute("CREATE TABLE IF NOT EXISTS entradas (sinal_id TEXT PRIMARY KEY, entrou INTEGER NOT NULL, payout REAL, corretora TEXT, registrado_em TEXT NOT NULL)")

    def autorizado(self, chave: str | None) -> bool:
        return len(self.chave) >= 24 and chave is not None and hmac.compare_digest(chave, self.chave)

    def _diario(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.diario}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def sinais(self) -> dict:
        agora = self.relogio()
        cenario = json.loads(self.cenario.read_text(encoding="utf-8"))
        estrategias = list(cenario.get("estrategias", []))
        saida = []
        if estrategias:
            con = self._diario()
            try:
                marcas = ",".join("?" * len(estrategias))
                linhas = con.execute(f"SELECT chave, estrategia, ativo, decidido_em, sinal, situacao, resultado FROM decisoes "
                                     f"WHERE estrategia IN ({marcas}) ORDER BY decidido_em DESC LIMIT 100", estrategias).fetchall()
            finally:
                con.close()
            limite = agora - JANELA
            for l in linhas:
                s = json.loads(l["sinal"])
                if s.get("acao") not in ("CALL", "PUT") or datetime.fromisoformat(s["entrada_em"]) < limite:
                    continue
                saida.append({"id": l["chave"], "ativo": l["ativo"], "direcao": s["acao"], "expiracao_min": int(s["expiracao_min"]),
                              "entrada_em": s["entrada_em"], "decidido_em": l["decidido_em"], "estrategia": l["estrategia"],
                              "cenario": str(cenario.get("cenario", ""))[:120], "preco_referencia": s.get("preco_referencia"),
                              "resultado": l["resultado"] if l["situacao"] == "encerrada" else None})
        return {"agora": agora.isoformat(), "sinais": saida}

    def registrar_entrada(self, corpo: dict) -> None:
        sinal_id, entrou, payout = corpo.get("sinal_id"), corpo.get("entrou"), corpo.get("payout")
        if not isinstance(sinal_id, str) or not 0 < len(sinal_id) <= 120 or not isinstance(entrou, bool):
            raise ErroPedido(400, "entrada inválida")
        if payout is not None and not (isinstance(payout, (int, float)) and 0 < payout <= 1):
            raise ErroPedido(400, "o payout é uma fração (0,87 para 87%)")
        con = self._diario()
        try:
            if con.execute("SELECT 1 FROM decisoes WHERE chave = ?", (sinal_id,)).fetchone() is None:
                raise ErroPedido(404, "sinal desconhecido")
        finally:
            con.close()
        corretora = corpo.get("corretora") if corpo.get("corretora") in CORRETORAS else "outra"
        with sqlite3.connect(self.entradas) as con:
            con.execute("INSERT OR REPLACE INTO entradas VALUES (?, ?, ?, ?, ?)",
                        (sinal_id, int(entrou), payout, corretora, self.relogio().isoformat()))


def criar_servidor(s: Servidor, endereco: str, porta: int) -> ThreadingHTTPServer:
    class Pedido(BaseHTTPRequestHandler):
        def _responder(self, status: int, corpo: dict) -> None:
            dados = json.dumps(corpo, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("cache-control", "no-store")
            self.send_header("content-length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def _tratar(self, metodo: str) -> None:
            try:
                if not s.autorizado(self.headers.get("x-mneme-chave")):
                    raise ErroPedido(401, "chave inválida")
                if metodo == "GET" and self.path.split("?")[0] == "/api/sinais":
                    return self._responder(200, s.sinais())
                if metodo == "POST" and self.path == "/api/sinais/entrada":
                    tamanho = min(int(self.headers.get("content-length") or 0), 4096)
                    try:
                        corpo = json.loads(self.rfile.read(tamanho) or b"{}")
                    except json.JSONDecodeError:
                        raise ErroPedido(400, "JSON inválido") from None
                    s.registrar_entrada(corpo if isinstance(corpo, dict) else {})
                    return self._responder(200, {"ok": True})
                raise ErroPedido(404, "caminho desconhecido")
            except ErroPedido as e:
                self._responder(e.status, {"erro": str(e)})
            except Exception:
                log.exception("pedido falhou")
                self._responder(500, {"erro": "falha interna"})

        def do_GET(self):  # noqa: N802 - nome exigido pelo http.server
            self._tratar("GET")

        def do_POST(self):  # noqa: N802
            self._tratar("POST")

        def log_message(self, *_):  # sem um log por pedido: a extensão consulta a cada 2 s
            pass

    return ThreadingHTTPServer((endereco, porta), Pedido)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    dados = Path(os.getenv("MNEME_DADOS", str(PASTA_DADOS)))
    chave = os.getenv("MNEME_SINAIS_LER", "")
    if len(chave) < 24:
        raise SystemExit("Defina MNEME_SINAIS_LER no .env (a mesma chave colada nas opções da extensão).")
    s = Servidor(dados / "operacao" / "diario.db", dados / "digitais" / "cenario.json", dados / "digitais" / "entradas.db", chave)
    porta = int(os.getenv("MNEME_SINAIS_PORTA", "8787"))
    log.info("servidor de sinais na porta %s (só acessível dentro da VPS ou pelo túnel SSH)", porta)
    criar_servidor(s, "0.0.0.0", porta).serve_forever()  # dentro do contêiner; o compose publica só em 127.0.0.1


if __name__ == "__main__":
    main()
