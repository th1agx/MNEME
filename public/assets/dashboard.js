// Painel: só lê o estado do servidor (/api/stream) e envia comandos. Nenhuma regra de negócio aqui.

const SIDE = {
  comprar: { word: "Compra", cls: "buy" },
  vender: { word: "Venda", cls: "sell" },
  observar: { word: "Tese", cls: "thesis" },
};
const EV = { buy: ["Compra", "buy"], sell: ["Venda", "sell"], thesis: ["Tese", "thesis"], other: ["Outro", "thesis"] };
const CLOSE_LABEL = { trader_exit: "trader vendeu", take_profit: "alvo de lucro", stop_loss: "stop de perda", trailing_stop: "stop móvel", max_hold: "tempo máximo", manual: "venda manual" };

let state = null;
let lastSignalId = null;
let firstRender = true;
const seenRows = new Set();

const expiresAt = (g, s) => new Date(g.createdAt).getTime() - g.latencyMs + s.entry.signalTtlSeconds * 1000;
const isExpired = (g, s) => Date.now() >= expiresAt(g, s);
const scoreClass = (n) => n >= 75 ? "hi" : n >= 50 ? "mid" : "lo";

function median(values) {
  if (!values.length) return null;
  const v = [...values].sort((a, b) => a - b);
  return v[Math.floor(v.length / 2)];
}

// ---------- Topo ----------

$("kill").addEventListener("click", () => state && api("POST", state.paused ? "/api/resume" : "/api/pause"));

function tickClock() {
  $("clock").textContent = new Date().toLocaleTimeString("pt-BR", { hour12: false }) + " BRT";
}
setInterval(tickClock, 1000);
tickClock();

function renderStatus(s) {
  const c = s.connection;
  const p50 = median(s.events.slice(-30).map((e) => e.latencyMs));
  const dot = c.status !== "conectado" ? "off" : c.realtime === false ? "slow" : "";
  const feed = c.status !== "conectado" ? c.status : c.realtime === false ? `atraso de ${c.delaySeconds} s no feed` : "tempo real";
  $("status").innerHTML = `
    <span class="tag">${s.mode === "demo" ? "Demo, dados fictícios" : "Ao vivo"}</span>
    <span><span class="dot ${dot}"></span><b>${esc(feed)}</b></span>
    <span class="hide-sm">p50 <b>${p50 == null ? "—" : secs(p50)}</b></span>
    <span class="hide-sm" title="Configure no .env">Telegram <b class="${s.integrations.telegram ? "up" : "muted"}">${s.integrations.telegram ? "ligado" : "desligado"}</b></span>`;
  $("modeBadge").innerHTML = modeBadge(s.executionMode);
  const kill = $("kill");
  kill.textContent = s.paused ? "Retomar entradas" : "Pausar entradas";
  kill.title = "Pausa só novas entradas. Saídas (stop, alvo, trader vendeu) continuam funcionando.";
  kill.classList.toggle("resume", s.paused);
}

function renderNotices(s) {
  const out = [];
  if (s.executionMode === "live") out.push(`<div class="notice bad">Modo dinheiro real ativo: o bot compra e vende sozinho dentro dos limites configurados.</div>`);
  if (s.paused) out.push(`<div class="notice warn">Entradas pausadas${s.pauseReason ? `: ${esc(s.pauseReason)}` : "."} Saídas continuam ativas.</div>`);
  const stuck = s.portfolio.open.filter((p) => p.exitFailure);
  for (const p of stuck) out.push(`<div class="notice bad">Venda de ${esc(p.tokenSymbol)} falhou ${p.exitFailure.count}x (${esc(p.exitFailure.lastError)}). O bot continua tentando; você pode vender manualmente na Carteira.</div>`);
  if (s.lastError) out.push(`<div class="notice bad">${esc(s.lastError)}</div>`);
  if (s.connection.status !== "conectado" && s.connection.detail) out.push(`<div class="notice warn">${esc(s.connection.detail)}</div>`);
  const failed = s.orders.filter((o) => o.status === "failed" && Date.now() - new Date(o.createdAt).getTime() < 10 * 60_000).at(-1);
  if (failed) out.push(`<div class="notice bad">Ordem de ${failed.side === "buy" ? "compra" : "venda"} de ${esc(failed.tokenSymbol)} falhou às ${hms(failed.createdAt)}: ${esc(failed.error)}</div>`);
  $("notices").innerHTML = out.join("");
}

function renderTape(s) {
  const items = s.events.slice(-14).reverse().map((e) => {
    const [label, cls] = EV[e.eventType];
    const t = cls === "buy" ? "up" : cls === "sell" ? "down" : "muted";
    return `<span class="tick"><b>${esc(e.tokenSymbol ?? "?")}</b><span class="${t}">${label}</span> <span class="muted">${esc(e.traderHandle)}</span> ${e.amountUsd != null ? usdK(e.amountUsd) : ""}</span>`;
  });
  $("tape").innerHTML = items.length ? items.join("") + items.join("") : `<span class="muted">Sem movimentações ainda.</span>`;
}

// ---------- Último sinal ----------

function decisionText(s, g) {
  if (g.status === "ignorado") return { label: "Não entrou", value: "Bloqueado", cls: "muted" };
  if (g.action === "observar") return { label: "Ação", value: "Acompanhar", cls: "" };
  if (g.action === "vender") return { label: "Ação", value: s.executionMode === "suggest" ? "Considere sair" : "Posição encerrada", cls: "" };
  if (s.executionMode === "suggest") return { label: "Sugestão de compra", value: usd(g.amountUsd), cls: "" };
  if (g.orderId) return { label: s.executionMode === "live" ? "Comprado (real)" : "Comprado (simulado)", value: usd(g.amountUsd), cls: "up" };
  return { label: "Ordem", value: "Falhou", cls: "down" };
}

function renderSignal(s) {
  const el = $("signal");
  const g = s.signals.findLast((x) => x.status === "valido" && x.action !== "observar") ?? s.signals.at(-1);
  if (!g) {
    el.className = "pane signal";
    el.innerHTML = `<h2>Último sinal</h2><p class="empty">Quando alguém do Top comprar ou vender, a análise aparece aqui.</p>`;
    return;
  }
  const side = SIDE[g.action];
  const ignored = g.status === "ignorado";
  const expired = !ignored && g.action === "comprar" && isExpired(g, s.settings);
  const d = decisionText(s, g);
  const rank = s.top.traders.find((t) => t.handle === g.traderHandle)?.rank;
  const leftMs = expiresAt(g, s.settings) - Date.now();
  const validity = ignored || g.action !== "comprar" || s.executionMode !== "suggest" ? "" : `
    <div class="validity ${leftMs < 15000 ? "low" : ""}">
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(100, (leftMs / (s.settings.entry.signalTtlSeconds * 1000)) * 100))}%"></div></div>
      <span class="txt">${expired ? `vencido ${ago(new Date(expiresAt(g, s.settings)).toISOString())}` : `válido por ${Math.ceil(leftMs / 1000)} s`}</span>
    </div>`;
  const cons = g.consensus ? `<div class="cons-strip"><b>Consenso, ${g.consensus.traders.length} traders</b>
    <span>${g.consensus.traders.map(esc).join(", ")} compraram ${esc(g.tokenSymbol)} em até ${g.consensus.windowMinutes} min.</span></div>` : "";
  const factors = g.score ? `<div class="factors">${g.score.factors.map((f) => `
    <div class="factor"><span>${esc(f.label)}</span><span class="muted">${Math.round(f.value * f.weight)}/${f.weight}</span>
      <div class="bar"><i style="width:${Math.round(f.value * 100)}%"></i></div><small>${esc(f.detail)}</small></div>`).join("")}</div>` : "";

  el.className = "pane signal" + (ignored ? " ignored" : "") + (expired ? " expired" : "");
  el.innerHTML = `
    <h2>Último sinal <small>${ago(g.createdAt)}</small></h2>
    <div class="ticket">
      <div class="ticket-head">
        <span class="pill ${ignored ? "ignored" : expired ? "expired" : side.cls}">${side.word}</span>
        ${g.consensus && !ignored ? `<span class="pill cons">Consenso ${g.consensus.traders.length}x</span>` : ""}
        <span class="asset">${esc(g.tokenSymbol ?? "?")}</span><span class="chain">${esc(g.chain ?? "")}</span>
        ${g.score ? `<span class="score ${scoreClass(g.score.total)}" title="Score de confiança, não é probabilidade">score ${g.score.total}</span>` : ""}
      </div>
      <div class="ticket-size"><div class="lbl">${d.label}</div><div class="val ${d.cls}">${d.value}</div></div>
      ${validity}${cons}
      <div class="kv">
        <div><span>Trader</span><b>${esc(g.traderHandle)}${rank ? ` (${rank}º)` : ""}</b></div>
        <div><span>Operação dele</span><b>${usd(g.traderAmountUsd)}</b></div>
        <div><span>Preço</span><b>${price(g.priceUsd)}</b></div>
        <div><span>Atraso</span><b>${secs(g.latencyMs)}</b></div>
        <div><span>Horário</span><b>${hms(g.createdAt)}</b></div>
      </div>
      ${factors}
      <p class="why">${ignored ? "Motivo" : "Leitura"}: <b>${g.reasons.map(esc).join(" ")}</b></p>
    </div>`;

  if (lastSignalId !== null && g.id !== lastSignalId && !ignored && g.action !== "observar") {
    el.classList.remove("flash-up", "flash-down");
    void el.offsetWidth;
    el.classList.add(g.action === "comprar" ? "flash-up" : "flash-down");
  }
  lastSignalId = g.id;
}

// ---------- Fluxo ----------

function renderFlow(s) {
  const W = Math.max(280, Math.round($("flow").getBoundingClientRect().width)), H = 160, MID = (H - 18) / 2, N = 30;
  const now = Math.floor(Date.now() / 60000);
  const buckets = Array.from({ length: N }, () => ({ b: 0, s: 0 }));
  for (const e of s.events) {
    if (e.amountUsd == null || (e.eventType !== "buy" && e.eventType !== "sell")) continue;
    const i = N - 1 - (now - Math.floor(new Date(e.eventTime).getTime() / 60000));
    if (i >= 0 && i < N) buckets[i][e.eventType === "buy" ? "b" : "s"] += e.amountUsd;
  }
  const buy = buckets.reduce((a, x) => a + x.b, 0), sell = buckets.reduce((a, x) => a + x.s, 0);
  const max = Math.max(1, ...buckets.map((x) => Math.max(x.b, x.s)));
  const bw = W / N;
  let bars = "";
  buckets.forEach((x, i) => {
    const hb = (x.b / max) * (MID - 6), hs = (x.s / max) * (MID - 6);
    if (hb) bars += `<rect class="b-up" x="${i * bw + 2}" y="${MID - hb}" width="${bw - 4}" height="${hb}" rx="1"><title>${usd(x.b)} em compras</title></rect>`;
    if (hs) bars += `<rect class="b-down" x="${i * bw + 2}" y="${MID}" width="${bw - 4}" height="${hs}" rx="1"><title>${usd(x.s)} em vendas</title></rect>`;
  });
  const labels = [0, 10, 20, 29].map((i) => {
    const anchor = i === 0 ? "start" : i === 29 ? "end" : "middle";
    const x = i === 0 ? 0 : i === 29 ? W : i * bw + bw / 2;
    return `<text class="lbl" x="${x}" y="${H - 4}" text-anchor="${anchor}">${i === 29 ? "agora" : `−${N - 1 - i} min`}</text>`;
  }).join("");
  $("flow").setAttribute("viewBox", `0 0 ${W} ${H}`);
  $("flow").innerHTML = `<line class="axis" x1="0" x2="${W}" y1="${MID}" y2="${MID}"/>${bars}${labels}`;
  $("legend").innerHTML = `<span>compras <b class="up">${usdK(buy)}</b></span><span>vendas <b class="down">${usdK(sell)}</b></span><span>líquido <b class="${tone(buy - sell)}">${signedK(buy - sell)}</b></span>`;
}

// ---------- Tabela de sinais ----------

let tab = "validos";
try { tab = localStorage.getItem("mneme.tab") || "validos"; } catch {}
const TABS = [["validos", "Válidos"], ["ignorados", "Ignorados"], ["todos", "Todos"]];
$("tabs").addEventListener("click", (ev) => {
  const btn = ev.target.closest("button[data-tab]");
  if (!btn) return;
  tab = btn.dataset.tab;
  try { localStorage.setItem("mneme.tab", tab); } catch {}
  if (state) renderBlotter(state);
});

function renderBlotter(s) {
  const valid = s.signals.filter((g) => g.status === "valido");
  const counts = { validos: valid.length, ignorados: s.signals.length - valid.length, todos: s.signals.length };
  $("tabs").innerHTML = TABS.map(([k, label]) => `<button type="button" data-tab="${k}" aria-pressed="${tab === k}">${label} ${counts[k]}</button>`).join("");
  const fresh = new Set(firstRender ? [] : s.signals.filter((g) => !seenRows.has(g.id)).map((g) => g.id));
  for (const g of s.signals) seenRows.add(g.id);
  const rows = s.signals.filter((g) => tab === "todos" || (tab === "validos") === (g.status === "valido"));
  $("blotter").innerHTML = rows.slice().reverse().map((g) => {
    const side = SIDE[g.action];
    const ignored = g.status === "ignorado";
    const executed = !!g.orderId;
    const situation = ignored ? `<span class="pill ignored">ignorado</span>`
      : executed ? `<span class="pill ${side.cls}">executado</span>`
      : g.action === "comprar" && s.executionMode === "suggest" && isExpired(g, s.settings) ? `<span class="pill expired">vencido</span>`
      : g.action === "observar" ? "" : `<span class="pill ${side.cls}">${s.executionMode === "suggest" ? "ativo" : "ok"}</span>`;
    return `<tr class="${ignored ? "ignored" : ""} ${fresh.has(g.id) ? "fresh" : ""}">
      <td>${hms(g.createdAt)}</td>
      <td><span class="lado ${side.cls}">${side.word}</span></td>
      <td><b>${esc(g.tokenSymbol ?? "?")}</b>${g.consensus ? `<span class="xn" title="${esc(g.consensus.traders.join(", "))}">${g.consensus.traders.length}x</span>` : ""}</td>
      <td>${esc(g.traderHandle)}</td>
      <td class="num">${g.score ? `<span class="score ${scoreClass(g.score.total)}">${g.score.total}</span>` : "—"}</td>
      <td class="num">${g.amountUsd != null && !ignored ? usd(g.amountUsd) : "—"}</td>
      <td class="num ${g.latencyMs > s.settings.entry.maxLatencySeconds * 1000 ? "warn" : ""}">${secs(g.latencyMs)}</td>
      <td>${situation}</td>
      <td class="wrap hide-sm">${g.reasons.map(esc).join(" ")}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="9" class="empty">${tab === "ignorados" ? "Nenhum sinal ignorado." : "Nenhum sinal ainda."}</td></tr>`;
}

// ---------- Carteira ----------

$("positions").addEventListener("click", async (ev) => {
  const btn = ev.target.closest("button[data-close]");
  if (!btn || !state) return;
  const p = state.portfolio.open.find((x) => x.id === btn.dataset.close);
  const msg = `Vender agora toda a posição em ${p?.tokenSymbol ?? "este token"}${state.executionMode === "live" ? " com dinheiro real" : ""}?`;
  if (!confirm(msg)) return;
  btn.disabled = true;
  const r = await api("POST", `/api/positions/${encodeURIComponent(btn.dataset.close)}/close`);
  if (!r.ok) alert(r.data?.reason ?? "Não foi possível vender.");
});

// Meta e limite do dia ao lado do resultado, para saber quanto falta antes de o bot parar de comprar.
function dayLimitsLabel(s) {
  const l = s.settings.limits;
  const loss = `limite −${usd(l.dailyLossLimitUsd)}`;
  if (l.dailyProfitTargetUsd == null || l.dailyProfitTargetUsd <= 0) return `${loss} · sem meta`;
  const hit = s.portfolio.dayPnlUsd >= l.dailyProfitTargetUsd;
  return `${hit ? "meta atingida" : "meta"} ${usd(l.dailyProfitTargetUsd)} · ${loss}`;
}

function renderOverview(s) {
  const pf = s.portfolio;
  const context = s.executionMode === "suggest" ? "Sem execução" : s.executionMode === "paper" ? "Carteira simulada" : "Carteira real";
  const items = [
    ["Saldo livre", usd(pf.balanceUsd), context, ""],
    ["Resultado do dia", signedUsd(pf.dayPnlUsd), dayLimitsLabel(s), tone(pf.dayPnlUsd)],
    ["Capital em posições", usd(pf.exposureUsd), `${pf.open.length} ${pf.open.length === 1 ? "posição aberta" : "posições abertas"}`, ""],
    ["Traders acompanhados", String(s.top.traders.length), `Ranking ${s.settings.leaderboard.window === "all" ? "de todo o período" : s.settings.leaderboard.window.replace("d", " dias").replace("h", " horas")}`, ""],
  ];
  $("overview").innerHTML = items.map(([label, value, detail, cls]) =>
    `<div class="overview-item"><span>${esc(label)}</span><b class="${cls}">${esc(value)}</b><small>${esc(detail)}</small></div>`
  ).join("");
}

function renderPortfolio(s) {
  const pf = s.portfolio;
  $("walletLabel").innerHTML = s.executionMode === "suggest" ? "sem execução no modo sugestões"
    : pf.venue === "solana" && s.integrations.wallet ? `<a class="muted" href="https://solscan.io/account/${esc(s.integrations.wallet)}" target="_blank" rel="noopener">carteira ${esc(s.integrations.wallet.slice(0, 4))}…${esc(s.integrations.wallet.slice(-4))}</a>`
    : "simulada";
  $("kpis").innerHTML = [
    ["Saldo livre", usd(pf.balanceUsd)],
    ["Exposição", usd(pf.exposureUsd)],
    ["Resultado aberto", `<span class="${tone(pf.openPnlUsd)}">${signedUsd(pf.openPnlUsd)}</span>`],
    ["Resultado do dia", `<span class="${tone(pf.dayPnlUsd)}">${signedUsd(pf.dayPnlUsd)}</span>`],
  ].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join("");
  $("positions").innerHTML = pf.open.map((p) => `
    <tr>
      <td style="white-space:normal"><b>${esc(p.tokenSymbol ?? "?")}</b> <span class="muted">${price(p.lastPriceUsd)}</span><br><span class="muted">de ${esc(p.traderHandles.join(", "))}</span></td>
      <td class="num">${usd(p.investedUsd)}</td>
      <td class="num ${tone(p.pnlUsd)}">${signedUsd(p.pnlUsd)}<br><span class="muted">${pct(p.pnlPct)}</span></td>
      <td class="num">${p.exitFailure ? `<span class="pill sell" title="${esc(p.exitFailure.lastError)}">venda falhou ${p.exitFailure.count}x</span><br>` : ""}<button class="btn small danger" type="button" data-close="${esc(p.id)}">Vender</button></td>
    </tr>`).join("") || `<tr><td colspan="4" class="empty">Nenhuma posição aberta.</td></tr>`;

  const realized = pf.closed.reduce((a, p) => a + (p.pnlUsd ?? 0), 0);
  const wins = pf.closed.filter((p) => (p.pnlUsd ?? 0) > 0).length;
  $("closedSummary").textContent = pf.closed.length ? `${pf.closed.length} operações, ${Math.round((wins / pf.closed.length) * 100)}% com lucro, ${signedUsd(realized)}` : "";
  $("closed").innerHTML = pf.closed.map((p) => `
    <tr>
      <td>${hms(p.closedAt)}</td><td><b>${esc(p.tokenSymbol ?? "?")}</b></td><td class="hide-sm muted">${esc(p.traderHandles.join(", "))}</td>
      <td class="num">${p.entryScore ?? "—"}</td><td class="num hide-sm">${price(p.entryPriceUsd)}</td><td class="num hide-sm">${price(p.exitPriceUsd)}</td>
      <td class="num">${usd(p.investedUsd)}</td><td class="num ${tone(p.pnlUsd)}">${signedUsd(p.pnlUsd)} <span class="muted">${pct(p.pnlPct)}</span></td>
      <td class="muted">${esc(CLOSE_LABEL[p.closeReason] ?? p.closeReason)}</td>
    </tr>`).join("") || `<tr><td colspan="9" class="empty">Nenhuma posição encerrada ainda.</td></tr>`;
}

function renderCalibration(s) {
  const min = s.settings.entry.minScore;
  const at = s.calibration.atMinScore;
  const head = at.trades
    ? `<p class="muted" style="margin:0 0 6px">Com score ${min} ou mais: <b class="${at.winRate >= 0.5 ? "up" : "down"}">${Math.round(at.winRate * 100)}% de acerto</b> em ${at.trades} operações.</p>`
    : `<p class="muted" style="margin:0 0 6px">Ainda sem operações encerradas com score ${min} ou mais. A taxa de acerto real aparece aqui conforme o bot opera.</p>`;
  $("calib").innerHTML = head + s.calibration.buckets.slice().reverse().map((b) => `
    <div class="calib-row">
      <span class="${min >= b.from && min < b.to ? "" : "muted"}">${b.label}</span>
      <span class="track"><i style="width:${b.winRate == null ? 0 : Math.round(b.winRate * 100)}%"></i></span>
      <span class="num muted">${b.winRate == null ? "sem dados" : `${Math.round(b.winRate * 100)}% de ${b.trades}`}</span>
    </div>`).join("");
}

// ---------- Top e consenso ----------

function renderWatch(s) {
  const w = s.settings.leaderboard.window;
  $("watchTitle").firstChild.textContent = `Top ${s.settings.leaderboard.topN} em ${w === "all" ? "todo o período" : w.replace("d", " dias").replace("h", " horas")} `;
  $("watchUpdated").textContent = s.top.updatedAt ? `ranking das ${hms(s.top.updatedAt).slice(0, 5)}` : "";
  $("watch").innerHTML = s.top.traders.map((t) => {
    const mine = s.events.filter((e) => e.userId === t.userId || e.traderHandle === t.handle);
    const last = mine.at(-1);
    const ticks = mine.slice(-12).map((e) => `<i class="${e.eventType === "buy" ? "b" : e.eventType === "sell" ? "s" : ""}"></i>`).join("");
    return `<div class="trader">
      <span class="rk">${t.rank}</span><span class="nm">${esc(t.handle)}</span>
      <span class="pnl ${tone(t.pnlUsd)}">${signedK(t.pnlUsd)}</span>
      <span class="last"><span>${last ? `${EV[last.eventType][0].toLowerCase()} ${esc(last.tokenSymbol ?? "?")} ${ago(last.receivedAt)}` : "sem movimentos"}</span><span class="ticks" aria-hidden="true">${ticks}</span></span>
    </div>`;
  }).join("") || `<div class="empty">Carregando ranking.</div>`;
  const ch = s.top.changes.at(-1);
  $("changes").innerHTML = ch && s.top.changes.length > 1
    ? `Mudou às ${hms(ch.at).slice(0, 5)}: ${[...ch.entered.map((t) => `<span class="up">entrou ${esc(t.handle)}</span>`), ...ch.left.map((t) => `<span class="down">saiu ${esc(t.handle)}</span>`)].join(", ")}`
    : "";
}

function renderConsensus(s) {
  const e = s.settings.entry;
  $("consWindow").textContent = `${e.consensusMinTraders}+ traders em ${e.consensusWindowMinutes} min`;
  const from = Date.now() - e.consensusWindowMinutes * 60_000;
  const groups = new Map();
  for (const ev of s.events) {
    if (ev.eventType !== "buy" || new Date(ev.eventTime).getTime() < from) continue;
    const key = `${ev.chain}:${(ev.tokenAddress ?? ev.tokenSymbol ?? "?").toLowerCase()}`;
    const g = groups.get(key) ?? { symbol: ev.tokenSymbol, chain: ev.chain, traders: new Set(), usd: 0, last: 0 };
    g.traders.add(ev.traderHandle ?? ev.userId);
    g.usd += ev.amountUsd ?? 0;
    g.last = Math.max(g.last, new Date(ev.eventTime).getTime());
    groups.set(key, g);
  }
  const list = [...groups.values()].filter((g) => g.traders.size >= e.consensusMinTraders).sort((a, b) => b.traders.size - a.traders.size || b.last - a.last);
  $("cons").innerHTML = list.map((g) => `
    <div class="cons-item">
      <span><b>${esc(g.symbol ?? "?")}</b> <span class="muted">${esc(g.chain)}</span></span>
      <span><span class="n">${g.traders.size} traders</span> <span class="muted">${usdK(g.usd)}</span></span>
      <span class="who">${[...g.traders].map(esc).join(", ")}, última compra ${ago(new Date(g.last).toISOString())}</span>
    </div>`).join("") || `<div class="empty">Nenhum token com compras de ${e.consensusMinTraders} ou mais traders nos últimos ${e.consensusWindowMinutes} min.</div>`;
}

function renderTrades(s) {
  $("trades").innerHTML = s.events.slice().reverse().map((e) => {
    const [label, cls] = EV[e.eventType];
    return `<tr>
      <td>${hms(e.eventTime)}</td><td class="hide-sm muted">${hms(e.receivedAt)}</td>
      <td><span class="lado ${cls}">${label}</span></td>
      <td><b>${esc(e.tokenSymbol ?? "?")}</b> <span class="muted">${esc(e.chain)}</span></td>
      <td>${esc(e.traderHandle)}</td><td class="num">${usd(e.amountUsd)}</td>
      <td class="num ${e.latencyMs > s.settings.entry.maxLatencySeconds * 1000 ? "warn" : ""}">${secs(e.latencyMs)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="7" class="empty">Nenhum negócio do Top ainda.</td></tr>`;
}

// ---------- Alertas ----------

let alertsOn = false;
try { alertsOn = localStorage.getItem("mneme.alerts") === "on"; } catch {}
let audio = null, unread = 0, lastBeep = 0;
const alerted = new Set();

function paintAlertsBtn() {
  const btn = $("alertsBtn");
  const noPopup = !("Notification" in window) || Notification.permission === "denied";
  btn.textContent = !alertsOn ? "Ativar alertas" : noPopup ? "Alertas: só som" : "Alertas ligados";
  btn.title = alertsOn && noPopup ? "O navegador bloqueou notificações deste site. Libere nas permissões do site." : "Som e notificação para cada sinal válido";
  btn.classList.toggle("alerts-on", alertsOn);
  btn.setAttribute("aria-pressed", String(alertsOn));
}
paintAlertsBtn();

$("alertsBtn").addEventListener("click", async () => {
  alertsOn = !alertsOn;
  try { localStorage.setItem("mneme.alerts", alertsOn ? "on" : "off"); } catch {}
  if (alertsOn) {
    audio = audio ?? new AudioContext();
    if (audio.state === "suspended") await audio.resume();
    if ("Notification" in window && Notification.permission === "default") await Notification.requestPermission();
    beep(false);
  }
  paintAlertsBtn();
});

function beep(strong) {
  if (!audio || audio.state !== "running" || Date.now() - lastBeep < 1500) return;
  lastBeep = Date.now();
  (strong ? [880, 1175] : [880]).forEach((hz, i) => {
    const t = audio.currentTime + i * 0.16;
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.frequency.value = hz;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.15, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.14);
    osc.connect(gain).connect(audio.destination);
    osc.start(t);
    osc.stop(t + 0.15);
  });
}

function notifyNew(s) {
  for (const g of s.signals) {
    if (alerted.has(g.id)) continue;
    alerted.add(g.id);
    if (firstRender || !alertsOn || g.status !== "valido" || g.action === "observar") continue;
    const verb = g.action === "comprar" ? (s.executionMode === "suggest" ? "Compra" : g.orderId ? "Comprado" : "Compra") : "Venda";
    const title = (g.consensus ? `Consenso ${g.consensus.traders.length}x: ` : "") + `${verb} ${g.tokenSymbol ?? "?"}`;
    const body = `${g.traderHandle} ${g.action === "comprar" ? "comprou" : "vendeu"}.${g.amountUsd ? ` Valor: ${usd(g.amountUsd)}.` : ""}${g.score ? ` Score ${g.score.total}.` : ""}`;
    beep(!!g.consensus);
    if (document.hidden || !document.hasFocus()) {
      unread += 1;
      document.title = `(${unread}) ${title}, MNEME`;
      if ("Notification" in window && Notification.permission === "granted") {
        const n = new Notification(title, { body, tag: g.id });
        n.onclick = () => { window.focus(); n.close(); };
      }
    }
  }
}
const clearUnread = () => { unread = 0; document.title = "MNEME"; };
window.addEventListener("focus", clearUnread);
document.addEventListener("visibilitychange", () => { if (!document.hidden) clearUnread(); });

// ---------- Ciclo ----------

function renderFeedOperations(s) {
  const events = s.feedEvents ?? [];
  $("feedCount").textContent = events.length + " operações recentes";
  $("feedOperations").innerHTML = events.slice().reverse().map(e => {
    const side = e.eventType === "buy" ? ["Compra", "up"] : ["Venda", "down"];
    const top = s.top.traders.some(t => e.userId ? t.userId === e.userId : t.handle.toLowerCase() === e.traderHandle?.toLowerCase());
    return '<tr><td>' + esc(new Date(e.eventTime).toLocaleTimeString("pt-BR")) + '</td><td class="' + side[1] + '">' + side[0] + '</td><td>' + esc(e.tokenSymbol ?? "—") + '</td><td>' + esc(e.chain ?? "—") + '</td><td>' + esc(e.traderHandle ?? "—") + (top ? ' · Top' : '') + '</td><td class="num">' + usd(e.amountUsd) + '</td><td>' + (e.replay ? 'Histórico reenviado' : 'Ao vivo') + '</td></tr>';
  }).join("") || '<tr><td colspan="7" class="empty">Aguardando compras e vendas do feed.</td></tr>';
}

function render(s) {
  state = s;
  window.dispatchEvent(new CustomEvent("mneme:state", { detail: s }));
  renderStatus(s);
  renderNotices(s);
  renderTape(s);
  renderSignal(s);
  renderFlow(s);
  renderBlotter(s);
  renderOverview(s);
  renderPortfolio(s);
  renderConsensus(s);
  renderWatch(s);
  renderCalibration(s);
  renderTrades(s);
  renderFeedOperations(s);
  notifyNew(s);
  firstRender = false;
}

setInterval(() => { if (state) renderSignal(state); }, 1000);
setInterval(() => { if (state) { renderBlotter(state); renderConsensus(state); } }, 5000);
window.addEventListener("resize", () => { if (state) renderFlow(state); });

const es = new EventSource("/api/stream");
es.onmessage = (m) => render(JSON.parse(m.data));
let cloudFeedStarted = false;
es.onerror = () => {
  if (!state && !cloudFeedStarted) {
    cloudFeedStarted = true;
    es.close();
    startCloudFeed();
  }
  $("notices").innerHTML = `<div class="notice warn">Carteira, sinais e ordens aguardam conexão com o bot. O gráfico de mercado tem conexão própria.</div>`;
  if (!state) {
    $("overview").innerHTML = `<p class="empty">Carteira aguardando conexão com o bot.</p>`;
    $("status").textContent = "Bot desconectado";
  }
};
