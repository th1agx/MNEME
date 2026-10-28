import { MARKET_SYMBOLS, baseSymbol, chartOrders, orderMarkers, filterOrders, orderMarket } from "./chart-data.js";

const el = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const number = (n, digits = 4) => Number.isFinite(n) ? n.toLocaleString("pt-BR", { maximumFractionDigits: digits }) : "—";
const money = (n) => Number.isFinite(n) ? `US$ ${number(n, 2)}` : "—";
const compact = (n) => n.toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const time = (t, full = false) => new Date(t).toLocaleString("pt-BR", full
  ? { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }
  : { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
const stamp = (t) => new Date(t).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour12: false });
const names = { SOL: "Solana", BTC: "Bitcoin", ETH: "Ethereum", BNB: "BNB", XRP: "XRP", DOGE: "Dogecoin", ADA: "Cardano", AVAX: "Avalanche", LINK: "Chainlink", SUI: "Sui" };
const priceText = (n) => number(n, n < 1 ? 7 : 4);

let symbol = "SOLUSDT", interval = "1m", chartType = "candles", showOrders = true, orderFilter = "all";
let series = null, botState = null, hovered = null, geometry = null, markers = [], selectedOrder = null;
let request = null, requestSerial = 0;
const quotes = new Map();
const botOrders = () => (botState?.orders ?? []).filter((o) => o.venue === (botState?.executionMode === "live" ? "solana" : "paper"));

function setMessage(message, failure = false) {
  el("chartMessage").textContent = message;
  el("chartMessage").hidden = !message;
  el("chartMessage").classList.toggle("chart-error", failure);
}

function describeCandle(index) {
  if (!series?.candles.length) return;
  const c = series.candles[index];
  if (!c) return;
  el("chartOhlc").innerHTML = `<span>${time(c.time, true)} BRT</span><span>A <b>${priceText(c.open)}</b></span><span>Máx <b>${priceText(c.high)}</b></span><span>Mín <b>${priceText(c.low)}</b></span><span>F <b class="${c.close >= c.open ? "up" : "down"}">${priceText(c.close)}</b></span><span class="${c.complete ? "muted" : "warn"}">${c.complete ? "Fechada" : "Em formação"}</span>`;
}

function paintQuote() {
  if (!series) {
    el("chartPrice").textContent = "— USDT";
    el("chartChange").textContent = "Carregando mercado…";
    el("chartChange").className = "muted";
    el("chartHigh").textContent = el("chartLow").textContent = "—";
    return;
  }
  const candles = series.candles, last = candles.at(-1);
  const change = (last.close / candles[0].open - 1) * 100;
  el("chartPrice").textContent = `${priceText(last.close)} USDT`;
  el("chartPrice").className = last.close >= last.open ? "up" : "down";
  el("chartChange").textContent = `${change >= 0 ? "+" : ""}${number(change, 2)}% no período`;
  el("chartChange").className = change >= 0 ? "up" : "down";
  el("chartHigh").textContent = `${priceText(Math.max(...candles.map((c) => c.high)))} USDT`;
  el("chartLow").textContent = `${priceText(Math.min(...candles.map((c) => c.low)))} USDT`;
}

function drawChart() {
  const svg = el("marketChart");
  const focusedMarker = document.activeElement?.closest?.("[data-marker-key]")?.dataset.markerKey;
  if (!series) { svg.innerHTML = ""; geometry = null; return; }
  const candles = series.candles, W = Math.max(280, Math.round(svg.getBoundingClientRect().width)), H = 430;
  const left = 8, right = W - 76, top = 16, bottom = 264, width = right - left;
  const step = width / candles.length, bodyWidth = Math.max(0.7, step * .64);
  const lo = Math.min(...candles.map((c) => c.low)), hi = Math.max(...candles.map((c) => c.high));
  const padding = Math.max((hi - lo) * .14, hi * .0003), lower = lo - padding, upper = hi + padding;
  const y = (price) => bottom - (price - lower) / (upper - lower) * (bottom - top);
  const x = (i) => left + (i + .5) * step;
  const maxVolume = Math.max(1, ...candles.map((c) => c.quoteVolume));
  markers = orderMarkers(candles, botOrders(), symbol);
  const botVolumes = candles.map(() => ({ buy: 0, sell: 0 }));
  for (const m of markers) botVolumes[m.index][m.side] += m.volumeUsd;
  const maxBot = Math.max(1, ...botVolumes.map((v) => v.buy + v.sell));
  geometry = { W, H, left, right, step, x, y, top, bottom };
  let grid = "", body = "", volumes = "", botVolumeBars = "", markerSvg = "";
  for (let i = 0; i <= 4; i++) {
    const py = top + (bottom - top) * i / 4, value = upper - (upper - lower) * i / 4;
    grid += `<line class="chart-grid" x1="${left}" x2="${right}" y1="${py}" y2="${py}"/><text class="chart-axis-label" x="${right + 8}" y="${py + 4}">${priceText(value)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const index = Math.round((candles.length - 1) * i / 4), px = x(index);
    const label = candles.at(-1).time - candles[0].time >= 86_400_000
      ? new Date(candles[index].time).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", day: "2-digit", month: "2-digit" }) : time(candles[index].time);
    grid += `<line class="chart-grid" x1="${px}" x2="${px}" y1="${top}" y2="404"/><text class="chart-axis-label" x="${px}" y="422" text-anchor="${i === 0 ? "start" : i === 4 ? "end" : "middle"}">${label}</text>`;
  }
  candles.forEach((c, i) => {
    const color = c.close >= c.open ? "chart-up" : "chart-down", px = x(i);
    if (chartType === "candles") body += `<g class="${color}"><line x1="${px}" x2="${px}" y1="${y(c.high)}" y2="${y(c.low)}"/><rect x="${px - bodyWidth / 2}" y="${Math.min(y(c.open), y(c.close))}" width="${bodyWidth}" height="${Math.max(1, Math.abs(y(c.open) - y(c.close)))}"/></g>`;
    const height = c.quoteVolume / maxVolume * 48;
    volumes += `<rect class="${color} chart-volume" x="${px - bodyWidth / 2}" y="${342 - height}" width="${bodyWidth}" height="${height}"/>`;
    const vb = botVolumes[i].buy / maxBot * 30, vs = botVolumes[i].sell / maxBot * 30;
    if (vb) botVolumeBars += `<rect class="chart-up" x="${px - bodyWidth / 2}" y="${402 - vb}" width="${bodyWidth}" height="${vb}"/>`;
    if (vs) botVolumeBars += `<rect class="chart-down" x="${px - bodyWidth / 2}" y="${402 - vb - vs}" width="${bodyWidth}" height="${vs}"/>`;
  });
  if (chartType === "line") body = `<path class="chart-price-line" d="${candles.map((c, i) => `${i ? "L" : "M"}${x(i)},${y(c.close)}`).join(" ")}"/>`;
  if (showOrders) markers.forEach((m, i) => {
    const buy = m.side === "buy", py = buy ? y(candles[m.index].low) + 12 : y(candles[m.index].high) - 12;
    const label = `${buy ? "Compra" : "Venda"}, ${m.orders.length} ${m.orders.length === 1 ? "ordem" : "ordens"}, ${money(m.volumeUsd)}. Ver detalhes.`;
    markerSvg += `<g class="chart-marker ${buy ? "chart-up" : "chart-down"}" role="button" tabindex="0" aria-label="${safe(label)}" data-marker="${i}" data-marker-key="${candles[m.index].time}:${m.side}" transform="translate(${x(m.index)},${py})"><title>${safe(label)}</title><rect class="marker-hit" x="-12" y="-12" width="24" height="24"/><path d="${buy ? "M0,-5 L-5,4 L5,4 Z" : "M0,5 L-5,-4 L5,-4 Z"}"/><text y="${buy ? 17 : -10}" text-anchor="middle">${buy ? "C" : "V"}${m.orders.length > 1 ? m.orders.length : ""}</text></g>`;
  });
  const last = candles.at(-1), lastY = y(last.close), lastColor = last.close >= last.open ? "chart-up" : "chart-down";
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("aria-label", `${chartType === "candles" ? `${candles.length} velas` : "Linha de preços"} de ${baseSymbol(symbol)} / USDT, Binance Spot. Último preço ${priceText(last.close)} USDT. Use as setas para consultar abertura, máxima, mínima e fechamento.`);
  svg.innerHTML = `<defs><clipPath id="marketPriceClip"><rect x="${left}" y="0" width="${width}" height="282"/></clipPath></defs>${grid}<g clip-path="url(#marketPriceClip)">${body}<line class="chart-last-line ${lastColor}" x1="${left}" x2="${right}" y1="${lastY}" y2="${lastY}"/>${markerSvg}</g><g class="${lastColor}"><rect x="${right + 2}" y="${lastY - 10}" width="73" height="20" rx="2"/><text class="chart-last-label" x="${right + 38}" y="${lastY + 4}" text-anchor="middle">${priceText(last.close)}</text></g><text class="chart-axis-label" x="${left}" y="285">Volume Binance (USDT)</text>${volumes}<text class="chart-axis-label" x="${right + 8}" y="306">${compact(maxVolume)}</text><line class="chart-grid" x1="${left}" x2="${right}" y1="350" y2="350"/><text class="chart-axis-label" x="${left}" y="365">Volume do bot (USD)${markers.length ? "" : " · sem ordens no período"}</text>${botVolumeBars}<g id="chartCrosshair" pointer-events="none"></g>`;
  if (hovered != null) hovered = Math.min(hovered, candles.length - 1);
  describeCandle(hovered ?? candles.length - 1);
  if (focusedMarker) [...svg.querySelectorAll("[data-marker-key]")].find((m) => m.dataset.markerKey === focusedMarker)?.focus({ preventScroll: true });
}

function hoverAt(index) {
  if (!geometry || !series) return;
  hovered = Math.max(0, Math.min(series.candles.length - 1, index));
  const px = geometry.x(hovered), py = geometry.y(series.candles[hovered].close);
  el("chartCrosshair").innerHTML = `<line class="chart-crosshair" x1="${px}" x2="${px}" y1="${geometry.top}" y2="404"/><line class="chart-crosshair" x1="${geometry.left}" x2="${geometry.right}" y1="${py}" y2="${py}"/><circle class="chart-crosshair-dot" cx="${px}" cy="${py}" r="3"/>`;
  describeCandle(hovered);
}

function selectAtPointer(event) {
  if (!geometry) return;
  const bounds = el("marketChart").getBoundingClientRect();
  const px = (event.clientX - bounds.left) * geometry.W / bounds.width;
  if (px >= geometry.left && px <= geometry.right) hoverAt(Math.floor((px - geometry.left) / geometry.step));
}
el("marketChart").addEventListener("pointermove", selectAtPointer);
el("marketChart").addEventListener("pointerdown", selectAtPointer);
el("marketChart").addEventListener("pointerleave", () => {
  hovered = null;
  if (series) { el("chartCrosshair").innerHTML = ""; describeCandle(series.candles.length - 1); }
});
el("marketChart").addEventListener("keydown", (event) => {
  if (event.target.closest("[data-marker]")) {
    if (["Enter", " "].includes(event.key)) { event.preventDefault(); selectMarker(event.target.closest("[data-marker]")); }
    return;
  }
  if (!series || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  hoverAt(event.key === "Home" ? 0 : event.key === "End" ? series.candles.length - 1 : (hovered ?? series.candles.length - 1) + (event.key === "ArrowLeft" ? -1 : 1));
});

function selectMarker(target) {
  const marker = markers[Number(target.dataset.marker)];
  if (marker) { selectedOrder = marker.orders[0]; renderOrderDetail(); }
}
el("marketChart").addEventListener("click", (event) => { const marker = event.target.closest("[data-marker]"); if (marker) selectMarker(marker); });

function renderWatch() {
  const list = [...new Set(["SOLUSDT", "BTCUSDT", "ETHUSDT", symbol])];
  el("chartWatch").innerHTML = list.map((item) => {
    const token = baseSymbol(item), quote = quotes.get(item);
    return `<button type="button" class="chart-watch-item" data-market="${item}" aria-pressed="${item === symbol}"><span><b>${token}</b><small>${names[token]} · real</small></span><span>${quote ? priceText(quote.candles.at(-1).close) : "—"}<small>USDT${quote ? ` · ${time(quote.fetchedAt)}` : ""}</small></span></button>`;
  }).join("");
}

function renderOrderDetail() {
  const detail = el("chartOrderDetail");
  detail.hidden = !selectedOrder;
  if (!selectedOrder) return;
  const o = selectedOrder;
  detail.innerHTML = `<b>${o.side === "buy" ? "Compra" : "Venda"} de ${safe(o.tokenSymbol ?? "?")}</b><button type="button" class="btn small" id="closeChartDetail" aria-label="Fechar detalhes da ordem">×</button><dl><div><dt>Execução</dt><dd>${o.venue === "paper" ? "Simulada" : "Real"}</dd></div><div><dt>Hora</dt><dd>${time(o.createdAt, true)} BRT</dd></div><div><dt>Preço executado</dt><dd>${money(o.priceUsd)}</dd></div><div><dt>Quantidade</dt><dd>${number(o.quantity, 8)}</dd></div><div><dt>Valor</dt><dd>${money(o.filledUsd)}</dd></div><div><dt>Situação</dt><dd>${o.status === "filled" ? "Executada" : "Falhou"}</dd></div></dl>${o.error ? `<p class="down">${safe(o.error)}</p>` : ""}<p class="muted">${orderMarket(o) ? "Marcador no horário da execução. O preço do bot é em USD; o gráfico de referência é em USDT." : "Este token não tem um mercado suportado no gráfico. A ordem permanece disponível no histórico."}</p>`;
}
el("chartOrderDetail").addEventListener("click", (event) => { if (event.target.closest("#closeChartDetail")) { selectedOrder = null; renderOrderDetail(); } });

function renderOrders() {
  const orders = botOrders(), coinOrders = filterOrders(chartOrders(orders, symbol), "all");
  const context = !botState ? "Aguardando bot" : botState.executionMode === "live" ? "Dinheiro real" : "Simulado";
  el("chartOrderCount").textContent = String(coinOrders.length);
  el("chartCoinOrders").innerHTML = coinOrders.length ? coinOrders.slice(0, 8).map((o) => `<button type="button" class="coin-order" data-order-id="${safe(o.id)}"><span class="${o.side === "buy" ? "up" : "down"}">${o.side === "buy" ? "Compra" : "Venda"}</span><b>${money(o.filledUsd ?? o.requestedUsd)}</b><small>${time(o.createdAt)} · ${o.status === "filled" ? "executada" : "falhou"}</small></button>`).join("") : `<p class="empty">${!botState ? "Aguardando conexão com o bot para consultar ordens." : `Nenhuma ordem para ${baseSymbol(symbol)}. Os marcadores aparecem quando o bot executa nesta moeda.`}</p>`;
  el("orderContext").textContent = `${context} · últimas ${orders.length} ordens disponíveis`;
  el("chartContext").textContent = !botState ? "Velas reais da Binance em USDT. Aguardando o estado do bot para exibir ordens." : `Velas reais da Binance em USDT. Ordens do bot: ${context.toLowerCase()}${botState.mode === "demo" ? ", com dados fictícios" : ""}, em USD. Marcadores indicam o horário, não uma cotação executada na Binance.`;
  const rows = filterOrders(orders, orderFilter, el("ordersSelectedCoin").checked ? symbol : null);
  el("orderHistory").innerHTML = rows.map((o) => `<tr class="${selectedOrder?.id === o.id ? "order-selected" : ""}"><td>${time(o.createdAt, true)}</td><td><span class="lado ${o.side}">${o.side === "buy" ? "Compra" : "Venda"}</span></td><td><b>${safe(o.tokenSymbol ?? "?")}</b></td><td>${o.venue === "paper" ? "Simulada" : "Real"}</td><td class="num">${priceText(o.priceUsd)}</td><td class="num">${number(o.quantity, 8)}</td><td class="num">${money(o.filledUsd ?? o.requestedUsd)}</td><td><span class="pill ${o.status === "failed" ? "sell" : o.side}">${o.status === "filled" ? "Executada" : "Falhou"}</span></td><td><button type="button" class="btn small" data-order-id="${safe(o.id)}">Ver ordem</button>${o.error ? `<span class="order-error down">${safe(o.error)}</span>` : ""}</td></tr>`).join("") || `<tr><td colspan="9" class="empty">Nenhuma ordem neste filtro.</td></tr>`;
  for (const button of el("orderTabs").querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.dataset.orderFilter === orderFilter));
}

function showOrder(event) {
  const button = event.target.closest("[data-order-id]");
  if (!button) return;
  selectedOrder = botOrders().find((o) => o.id === button.dataset.orderId) ?? null;
  if (!selectedOrder) return;
  const market = orderMarket(selectedOrder);
  if (market && market !== symbol) changeMarket(market);
  renderOrderDetail();
  el("chartOrderDetail").scrollIntoView({ block: "nearest", behavior: "instant" });
}
el("orderHistory").addEventListener("click", showOrder);
el("chartCoinOrders").addEventListener("click", showOrder);
el("orderTabs").addEventListener("click", (event) => { const b = event.target.closest("[data-order-filter]"); if (b) { orderFilter = b.dataset.orderFilter; renderOrders(); } });
el("ordersSelectedCoin").addEventListener("change", renderOrders);

async function fetchCandles() {
  request?.abort();
  request = new AbortController();
  const controller = request;
  const serial = ++requestSerial, requestedSymbol = symbol, requestedInterval = interval;
  const timeout = setTimeout(() => controller.abort(), 12_000);
  el("chartStage").setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/market/candles?${new URLSearchParams({ symbol, interval })}`, { signal: controller.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Mercado indisponível.");
    if (serial !== requestSerial) return;
    if (data.symbol !== requestedSymbol || data.interval !== requestedInterval || !data.candles?.length) throw new Error("Histórico de mercado inválido.");
    series = data;
    quotes.set(symbol, data);
    setMessage("");
    paintQuote(); drawChart(); renderWatch();
    el("chartUpdated").textContent = `Binance Spot · ${data.candles.length} velas de ${el("chartInterval").selectedOptions[0].textContent} · atualizado ${stamp(data.fetchedAt)} BRT · a cada 10 s`;
    el("chartUpdated").className = "";
  } catch (error) {
    if (serial !== requestSerial) return;
    const message = error.name === "AbortError" ? "A Binance demorou a responder." : error.message;
    setMessage(`${message} ${series ? "Exibindo a última atualização recebida." : "Tentando novamente em 10 segundos."}`, true);
    el("chartUpdated").textContent = series ? `Dados desatualizados · última atualização ${stamp(series.fetchedAt)} BRT` : "Mercado indisponível · nova tentativa automática";
    el("chartUpdated").className = "warn";
  } finally {
    clearTimeout(timeout);
    if (serial === requestSerial) el("chartStage").setAttribute("aria-busy", "false");
  }
}

function changeMarket(nextSymbol = symbol) {
  if (!MARKET_SYMBOLS.includes(nextSymbol)) return;
  symbol = nextSymbol; el("chartSymbol").value = symbol; interval = el("chartInterval").value;
  series = null; hovered = null;
  paintQuote(); drawChart(); renderWatch(); renderOrders();
  el("chartOhlc").textContent = "Aguardando velas reais…";
  el("chartUpdated").textContent = "Buscando histórico da Binance…";
  setMessage("Carregando 180 velas da Binance…");
  void fetchCandles();
}
el("chartSymbol").addEventListener("change", () => { selectedOrder = null; renderOrderDetail(); changeMarket(el("chartSymbol").value); });
el("chartInterval").addEventListener("change", () => changeMarket());
el("chartWatch").addEventListener("click", (event) => { const b = event.target.closest("[data-market]"); if (b) { selectedOrder = null; renderOrderDetail(); changeMarket(b.dataset.market); } });
el("chartTypes").addEventListener("click", (event) => {
  const b = event.target.closest("[data-chart-type]");
  if (!b) return;
  chartType = b.dataset.chartType;
  for (const button of el("chartTypes").querySelectorAll("button")) button.setAttribute("aria-pressed", String(button === b));
  drawChart();
});
el("chartOrdersToggle").addEventListener("click", () => { showOrders = !showOrders; el("chartOrdersToggle").setAttribute("aria-pressed", String(showOrders)); drawChart(); });

function receiveState(next) { botState = next; renderOrders(); drawChart(); }
window.addEventListener("mneme:state", (event) => receiveState(event.detail));
void fetch("/api/state").then((r) => r.ok ? r.json() : null).then((s) => { if (s && !botState) receiveState(s); }).catch(() => {});
new ResizeObserver(() => drawChart()).observe(el("chartStage"));
renderWatch(); renderOrders(); void fetchCandles();
setInterval(() => { if (!document.hidden) void fetchCandles(); }, 10_000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) void fetchCandles(); });

async function refreshWatch() {
  await Promise.all(["SOLUSDT", "BTCUSDT", "ETHUSDT"].filter((s) => s !== symbol).map(async (s) => {
    try {
      const response = await fetch(`/api/market/candles?symbol=${s}&interval=1m`, { signal: AbortSignal.timeout(12_000) });
      if (response.ok) { const data = await response.json(); if (data.candles?.length) quotes.set(s, data); }
    } catch { /* Sem cotação, a lista mantém o último valor e seu horário. */ }
  }));
  renderWatch();
}
void refreshWatch();
setInterval(() => { if (!document.hidden) void refreshWatch(); }, 30_000);
