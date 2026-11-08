"""Mede, só lendo, o custo das consultas que os especialistas da F1 fariam a cada vela fechada. Não grava nada."""
import json, resource, sqlite3, sys, time
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "/home/ubuntu/mneme/robo")
import pandas as pd
from mneme.dados.armazem import ArmazemVelas
from mneme.dados.eventos import ArmazemEventos
from mneme.laboratorio.confluencia import decidir, grade_de_sinais

R = "/home/ubuntu/mneme/robo/dados/mercado"
JANELA = {1: 4, 5: 12, 15: 30}
velas, eventos = ArmazemVelas(R), ArmazemEventos(R)
agora = datetime.now(timezone.utc).replace(second=0, microsecond=0)
t = {}


def medir(nome, f):
    i = time.perf_counter(); r = f(); t.setdefault(nome, []).append(time.perf_counter() - i); return r


for par in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
    for candle, dias in JANELA.items():
        v = medir(f"velas_{candle}m", lambda: velas.ler(par, inicio=agora - timedelta(days=dias), como_de=agora))
        g = medir(f"tecnicas_{candle}m", lambda: grade_de_sinais(v, candle))
        modelo = json.load(open(f"/home/ubuntu/mneme/robo/dados/modelos/motor/{par}_expiracao_fixa_{candle}m_{candle}m.json"))
        medir("confluencia_decidir", lambda: decidir(modelo, g.iloc[-1]))
    for tipo, janela in (("trades", 15), ("livro", 15), ("funding", 24 * 60), ("open_interest", 24 * 60), ("previsoes", 120)):
        medir(f"eventos_{tipo}", lambda: eventos.ler(tipo, par, inicio=agora - timedelta(minutes=janela), como_de=agora))
c = sqlite3.connect("file:/home/ubuntu/mneme/robo/dados/operacao/diario.db?mode=ro", uri=True)
medir("diario_contexto", lambda: c.execute("SELECT * FROM contexto WHERE ativo IN ('ETH','estrategia:ETHUSDT|expiracao_fixa|5m|5m') AND criado_em <= ? AND valido_ate > ?", (agora.isoformat(), agora.isoformat())).fetchall())
medir("calendario", lambda: eventos.ler("calendario", "GLOBAL", inicio=agora - timedelta(days=1), como_de=agora))
total_por_minuto = 0
for k, vs in sorted(t.items()):
    print(f"{k:24s} n={len(vs):2d} média={sum(vs)/len(vs)*1000:8.1f} ms  máx={max(vs)*1000:8.1f} ms")
# Num minuto típico fecham as velas de 1 min dos 3 ativos; a cada 5 min também as de 5; a cada 15 também as de 15.
med = {k: sum(v) / len(v) for k, v in t.items()}
por_vela = {c_: med[f"velas_{c_}m"] + med[f"tecnicas_{c_}m"] + med["confluencia_decidir"] for c_ in JANELA}
fluxo = sum(med[f"eventos_{x}"] for x in ("trades", "livro", "funding", "open_interest", "previsoes")) + med["diario_contexto"] + med["calendario"]
seg_por_dia = 3 * (1440 * (por_vela[1] + fluxo) + 288 * (por_vela[5] + fluxo) + 96 * (por_vela[15] + fluxo))
print(f"pior minuto (1+5+15 fechando juntos, 3 ativos): {3 * (por_vela[1] + por_vela[5] + por_vela[15] + 3 * fluxo):.1f} s")
print(f"CPU por dia: {seg_por_dia:.0f} s = {seg_por_dia / 864:.1f}% de um núcleo")
print(f"pico de RAM: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
