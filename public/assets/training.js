const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value) || 0);
const unitPrice = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 8 }).format(Number(value) || 0);
const quantity = (value) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 6 }).format(Number(value) || 0);
const pct = (value) => value == null ? "-" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const safe = (value) => String(value ?? "-").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const plural = (count, one, many) => `${Number(count) || 0} ${Number(count) === 1 ? one : many}`;
const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
const patternName = (value) => ({
  large_buy: "Compra de alto valor", crowd_buy: "Compra em grupo", large_and_crowd_buy: "Alto valor + grupo",
  large_sell: "Venda de alto valor", crowd_sell: "Venda em grupo", sell_batch: "Venda em lote",
  consensus_buy: "Maioria de alto acerto comprando", consensus_exit: "Maioria de alto acerto vendeu",
  consensus_wait: "Aguardando consenso",
  repeat_buy: "Recompras do mesmo trader", mixed_flow: "Fluxo conflitante", unconfirmed: "Sem confirmacao",
}[value] ?? value ?? "-");
let current = null;
let selectedBotId = "mneme-paper";
let priceRefreshTimer = null;
let dashboardRefreshTimer = null;
let pendingCapitalEventId = null;

// Meta e limite vêm de Configurações; sem meta definida, a coluna diz isso em vez de inventar um número.
function dailyTargetLabel(item, execution) {
  const target = execution?.dailyTargetPct;
  const loss = execution?.dailyLossLimitPct;
  const lossText = loss ? ` · limite -${pct(loss)}` : "";
  if (!target) return `Sem meta definida${lossText}`;
  return item.dailyTargetReached ? `Atingida hoje · compras pausadas${lossText}` : `${pct(item.dailyReturnPct)} de ${pct(target)}${lossText}`;
}

// Tempo médio que os traders ficam na operação, em minutos, horas ou dias.
function holdLabel(minutes) {
  if (minutes == null) return "—";
  if (minutes < 60) return `${Math.max(1, Math.round(minutes))} min`;
  if (minutes < 24 * 60) return `${(minutes / 60).toFixed(1).replace(".", ",")} h`;
  return `${(minutes / 1440).toFixed(1).replace(".", ",")} dias`;
}

function render(data) {
  current = data;
  const flow = data.top50Flow ?? {};
  const flowStatus = document.querySelector("#top50FlowStatus");
  flowStatus.textContent = `Fluxo Top 50 · ${flow.windowMinutes ?? 5} min: ${plural(flow.activeTraders, "trader ativo", "traders ativos")} · ${flow.buyers ?? 0} compradores / ${flow.sellers ?? 0} vendedores`;
  flowStatus.title = `Compradores: ${flow.buyers ?? 0} (${money(flow.buyVolumeUsd)}) · Vendedores: ${flow.sellers ?? 0} (${money(flow.sellVolumeUsd)})`;
  const allPositions = data.positions ?? [];
  const wallets = (data.wallets ?? []).map((item) => {
    const openPositions = allPositions.filter((position) => position.botId === item.botId);
    const marketValueUsd = openPositions.reduce((sum, position) => sum + position.quantity * (position.markPriceUsd ?? position.entryPriceUsd), 0);
    const unrealizedPnlUsd = openPositions.reduce((sum, position) => sum + position.quantity * (position.markPriceUsd ?? position.entryPriceUsd) - position.costUsd, 0);
    const equityUsd = item.cashUsd + marketValueUsd;
    return {
      ...item,
      marketValueUsd,
      unrealizedPnlUsd,
      totalPnlUsd: item.realizedPnlUsd + unrealizedPnlUsd,
      equityUsd,
      returnPct: item.initialUsd > 0 ? (equityUsd - item.initialUsd) / item.initialUsd * 100 : 0,
      openPositions: openPositions.length,
    };
  }).sort((a, b) => b.totalPnlUsd - a.totalPnlUsd);
  data.wallets = wallets;
  if (!wallets.some((item) => item.botId === selectedBotId) && wallets[0]) selectedBotId = wallets[0].botId;
  const wallet = wallets.find((item) => item.botId === selectedBotId);
  const bots = data.bots ?? [];
  const botName = (id) => bots.find((bot) => bot.id === id)?.name ?? id;
  document.querySelector("#botComparison").innerHTML = wallets.length ? wallets.map((item) => `<tr class="bot-row ${item.botId === selectedBotId ? "selected" : ""}" data-bot-id="${safe(item.botId)}">
    <td><button type="button" class="bot-pick" data-bot-id="${safe(item.botId)}" aria-pressed="${item.botId === selectedBotId}">${safe(botName(item.botId))}</button></td>
    <td class="num ${tone(item.totalPnlUsd)}"><b>${money(item.totalPnlUsd)}</b></td><td class="num ${tone(item.returnPct)}">${pct(item.returnPct)}</td>
    <td class="num hide-sm">${money(item.equityUsd)}</td><td class="num hide-sm ${tone(item.dailyPnlUsd)}">${money(item.dailyPnlUsd)}</td>
    <td class="num hide-sm">${item.openPositions}</td><td class="num hide-sm">${item.closedTrades}</td>
    <td class="hide-sm">${item.haltedAt ? `<span class="halted" title="${safe(item.haltReason)}">Pausado</span>` : `<span class="state-on">Operando</span>`}</td></tr>`).join("")
    : `<tr><td colspan="8" class="empty">As carteiras aparecem quando o Worker iniciar.</td></tr>`;
  const positions = (data.positions ?? []).filter((item) => item.botId === selectedBotId);
  const orders = (data.orders ?? []).filter((item) => item.botId === selectedBotId);
  const incidents = (data.incidents ?? []).filter((item) => item.botId === selectedBotId);
  const patterns = (data.patterns ?? []).filter((item) => item.botId === selectedBotId);
  const summary = [
    ["Patrimônio", money(wallet?.equityUsd), `Capital alocado ${money(wallet?.initialUsd ?? data.paperCapital?.totalAllocatedUsd)}`, ""],
    ["Caixa disponível", money(wallet?.cashUsd), `Exposição ${money(wallet?.marketValueUsd)} · ${pct(wallet?.equityUsd > 0 ? wallet.marketValueUsd / wallet.equityUsd * 100 : 0)}`, ""],
    ["PnL realizado", money(wallet?.realizedPnlUsd), `${plural(wallet?.closedTrades, "trade fechado", "trades fechados")}${wallet?.winRatePct == null ? "" : ` · win rate ${pct(wallet.winRatePct)}`}`, tone(wallet?.realizedPnlUsd)],
    ["PnL não realizado", money(wallet?.unrealizedPnlUsd), `${plural(wallet?.openPositions, "posição aberta", "posições abertas")} · marcado a mercado`, tone(wallet?.unrealizedPnlUsd)],
  ];
  document.querySelector("#selectedBotName").textContent = botName(selectedBotId);
  document.querySelector("#trainingSummary").innerHTML = summary.map(([label, value, note, valueTone]) => `<div class="training-kpi"><span>${safe(label)}</span><b class="${valueTone}">${safe(value)}</b><small>${safe(note)}</small></div>`).join("");
  const capitalButton = document.querySelector("#addCapitalButton");
  capitalButton.disabled = !data.capitalControlReady;
  capitalButton.title = "Aporte simulado: entra no caixa e no capital alocado, não conta como PnL";
  document.querySelector("#capitalBot").innerHTML = wallets.map((item) => `<option value="${safe(item.botId)}">${safe(botName(item.botId))}</option>`).join("");
  document.querySelector("#capitalBot").value = selectedBotId;
  const capitalEvents = data.capitalEvents ?? [];
  document.querySelector("#capitalEventCount").textContent = capitalEvents.length;
  document.querySelector("#capitalRows").innerHTML = capitalEvents.length ? capitalEvents.map((event) => `<tr>
    <td>${new Date(event.createdAt).toLocaleString("pt-BR")}</td><td>${safe(botName(event.botId))}</td><td class="num positive">+${money(event.amountUsd)}</td></tr>`).join("")
    : `<tr><td colspan="3" class="empty">Nenhum aporte registrado.</td></tr>`;
  const profile = bots.find((bot) => bot.id === selectedBotId);
  const thousands = (value) => `US$ ${(Number(value) / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`;
  const ruleChips = profile ? [
    `Acerto mínimo do trader: ${profile.minWinRatePct == null ? "não definido" : `${pct(profile.minWinRatePct)}`}`,
    `Amostra mínima: ${profile.minClosedTrades == null ? "não definida" : `${profile.minClosedTrades} operações`}`,
    `Compradores de alto acerto: ${profile.minTraders == null ? "não definido" : `${profile.minTraders}+ em maioria`}`,
    `Janela: ${profile.windowMinutes == null ? "não definida" : `${profile.windowMinutes} min`}`,
    `Tamanho: ${profile.orderSizePct == null ? "não definido" : `${pct(profile.orderSizePct)} / entrada`}`,
    `Liquidez mín.: ${profile.minLiquidityUsd == null ? "sem filtro" : thousands(profile.minLiquidityUsd)}`,
    "Saída: quando a maioria dos traders da entrada vende",
  ] : [];
  const incomplete = profile && [profile.minWinRatePct, profile.minClosedTrades, profile.minTraders, profile.windowMinutes, profile.orderSizePct].some((value) => value == null);
  const waiting = !positions.length && !(wallet?.closedTrades);
  document.querySelector("#trainingExplanation").innerHTML = `<div class="rule-chips">${ruleChips.map((chip) => `<span>${safe(chip)}</span>`).join("")}</div>
    <p>${incomplete ? `<b>Regra incompleta: o robô só observa.</b> <a href="/configuracoes">Preencha em Configurações</a>. ` : waiting ? "Sem posições abertas · aguardando a maioria dos traders de alto acerto comprar o mesmo token. " : ""}Entra quando a maioria dos traders de alto acerto compra; sai quando a maioria deles vende. PnL não realizado é marcado a mercado e realizado no fechamento. <a href="#trainingRules" class="rules-link">Parâmetros completos</a></p>`;

  const headerLabels = {
    "#": "#", "Conta": "Conta", "Resultado total": "Lucro/prejuízo total", "Realizado": "Já realizado (vendas)", "Em aberto": "Ainda em aberto",
    "Retorno": "Retorno sobre capital", "Hoje": "Resultado de hoje", "Meta diária": "Meta diária", "Estado": "Estado",
    "Acerto": "Vendas com lucro", "Fechadas": "Vendas fechadas", "Abertas": "Posições abertas",
  };
  document.querySelectorAll("#walletRows").forEach((body) => body.closest("table").querySelectorAll("thead th").forEach((th) => { if (headerLabels[th.textContent.trim()]) th.textContent = headerLabels[th.textContent.trim()]; }));
  const setHeaders = (bodyId, labels) => document.querySelector(`#${bodyId}`).closest("table").querySelectorAll("thead th").forEach((th, index) => { if (labels[index]) th.textContent = labels[index]; });
  setHeaders("positionRows", ["Conta", "Ativo", "Rede", "Quantidade atual", "Preço médio de compra", "Preço usado agora", "Custo total (inclui taxa)", "Valor atual da posição", "Ganho/perda em aberto", "Variação da posição"]);
  setHeaders("orderRows", ["Executada", "Conta", "Lado", "Ativo", "Rede", "Preço por unidade", "Valor da ordem", "Taxa", "Padrão detectado", "Lucro/prejuízo desta venda", "Situação"]);

  const query = document.querySelector("#walletSearch").value.trim().toLowerCase();
  const visible = wallets.filter((item) => item.trader.toLowerCase().includes(query));
  document.querySelector("#walletRows").innerHTML = visible.length ? visible.map((item, index) => `<tr>
    <td>${index + 1}</td><td>${safe(item.trader)}</td><td class="num ${tone(item.totalPnlUsd)}">${money(item.totalPnlUsd)}</td>
    <td class="num ${tone(item.realizedPnlUsd)}">${money(item.realizedPnlUsd)}</td><td class="num ${tone(item.unrealizedPnlUsd)}">${money(item.unrealizedPnlUsd)}</td>
    <td class="num ${tone(item.returnPct)}">${pct(item.returnPct)}</td><td class="num ${tone(item.dailyPnlUsd)}">${money(item.dailyPnlUsd)}<small>${pct(item.dailyReturnPct)}</small></td>
    <td><div class="goal-meter"><span style="width:${Math.max(0, Math.min(100, Number(item.dailyTargetProgressPct) || 0))}%"></span></div><small>${dailyTargetLabel(item, data.execution)}</small></td>
    <td>${item.haltedAt ? `<span class="halted" title="${safe(item.haltReason)}">Pausada</span>` : "Ativa"}</td>
    <td class="num">${pct(item.winRatePct)}</td><td class="num">${item.closedTrades}</td><td class="num">${item.openPositions}</td></tr>`).join("") : `<tr><td colspan="12" class="empty">${wallets.length ? "Nenhum resultado para este filtro." : "A carteira aparece quando o Worker iniciar."}</td></tr>`;

  const performance = (data.patternPerformance ?? []).filter((row) => row.botId === selectedBotId);
  document.querySelector("#patternPerformanceRows").innerHTML = performance.length ? performance.map((row) => `<tr>
    <td>${safe(patternName(row.pattern))}</td><td class="num">${row.closedTrades}</td><td class="num">${pct(row.winRatePct)}</td>
    <td class="num ${tone(row.realizedPnlUsd)}">${money(row.realizedPnlUsd)}</td><td class="num ${tone(row.averagePnlUsd)}">${money(row.averagePnlUsd)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">Ainda nao ha saidas fechadas para comparar.</td></tr>`;

  const signalEvents = data.signalEvents ?? [];
  document.querySelector("#signalEventCount").textContent = `Exibindo ${signalEvents.length} · máx. 100`;
  document.querySelector("#signalEventRows").innerHTML = signalEvents.length ? signalEvents.map((signal) => `<tr>
    <td>${new Date(signal.signalAt).toLocaleString("pt-BR")}<small>recebido ${new Date(signal.observedAt).toLocaleTimeString("pt-BR")}</small></td>
    <td>${safe(signal.trader)}</td><td>${signal.matchedTop50 ? `Top #${Number(signal.sourceRank)}` : `<span class="unmatched-signal">Sem vínculo com o Top 50</span>`}</td>
    <td class="${signal.side === "buy" ? "positive" : "negative"}">${signal.side === "buy" ? "Compra" : "Venda"}</td>
    <td><b>${safe(signal.symbol)}</b></td><td>${safe(signal.chain)}</td><td class="num">${signal.amountUsd == null ? "—" : money(signal.amountUsd)}</td>
    <td>${signal.matchedTop50 ? "Incluído na leitura" : "Não entra no consenso"}</td></tr>`).join("")
    : `<tr><td colspan="8" class="empty">Nenhuma movimentação válida foi registrada pelo ciclo da nuvem nos últimos sete dias.</td></tr>`;

  document.querySelector("#patternCount").textContent = `${patterns.length} decisões`;
  document.querySelector("#patternRows").innerHTML = patterns.length ? patterns.map((pattern) => `<tr>
    <td>${new Date(pattern.observedAt).toLocaleString("pt-BR")}</td><td><b>${safe(pattern.symbol)}</b><small>${safe(pattern.chain)}</small></td>
    <td class="${pattern.action === "buy" ? "positive" : pattern.action === "sell" ? "negative" : ""}">${pattern.action === "buy" ? "Compra paper" : pattern.action === "sell" ? "Venda paper" : "Observar"}</td>
    <td>${safe(pattern.reason)}</td><td class="num">${Number(pattern.buyers) || 0}</td><td class="num">${Number(pattern.sellers) || 0}</td>
    <td class="num">${Number(pattern.buyers) + Number(pattern.sellers) ? `${Number(pattern.score) || 0}%` : "—"}</td></tr>`).join("")
    : `<tr><td colspan="7" class="empty">Ainda não há decisão registrada. Se houver sinal do Top 50 associado, o motivo aparecerá aqui.</td></tr>`;

  const accuracy = data.traderAccuracy;
  const ranked = accuracy?.top ?? [];
  document.querySelector("#traderAccuracyCount").textContent = `${plural(accuracy?.measuredTraders, "trader", "traders")} · ${plural(accuracy?.qualifiedTraders, "conta", "contam")}`;
  document.querySelector("#traderAccuracySummary").textContent = accuracy
    ? `Últimos ${accuracy.windowDays} dias: ${plural(accuracy.measuredTraders, "trader medido", "traders medidos")} em ${plural(accuracy.closedTrades, "operação fechada", "operações fechadas")}; ${plural(accuracy.withSampleTraders, "tem", "têm")} a amostra mínima e ${plural(accuracy.qualifiedTraders, "passa", "passam")} na taxa de acerto de Configurações. Tempo médio na operação: ${holdLabel(accuracy.averageHoldMinutes)} no geral, ${holdLabel(accuracy.qualifiedAverageHoldMinutes)} entre os de alto acerto.`
    : "O acerto de cada trader é medido pelas operações que ele encerra nos últimos 30 dias.";
  document.querySelector("#traderAccuracyRows").innerHTML = ranked.length ? ranked.map((trader) => `<tr>
    <td>${safe(trader.trader)}</td><td class="num">${Number(trader.closedTrades) || 0}</td><td class="num">${pct(trader.winRatePct)}</td>
    <td class="num">${holdLabel(trader.averageHoldMinutes)}</td><td class="${trader.qualified ? "positive" : ""}">${trader.qualified ? "Sim, alto acerto" : "Não, abaixo da taxa"}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">Nenhum trader com a amostra mínima ainda. O acerto aparece quando os traders do Top encerram operações.</td></tr>`;

  document.querySelector("#incidentCount").textContent = incidents.length;
  document.querySelector("#incidentRows").innerHTML = incidents.length ? incidents.map((incident) => {
    const details = incident.diagnostics ?? {};
    const recent = details.last24h ?? {};
    const summary = `Patrimonio ${money(details.equityUsd)}; saldo ${money(details.cashUsd)}; posicoes abertas ${Number(details.openPositions) || 0}; trades 24h ${Number(recent.trades) || 0}; ganhos/perdas ${Number(recent.wins) || 0}/${Number(recent.losses) || 0}; taxas ${money(recent.feesUsd)}; resultado realizado 24h ${money(recent.realizedPnlUsd)}.`;
    return `<tr><td>${new Date(incident.occurredAt).toLocaleString("pt-BR")}</td><td>${safe(incident.trader)}</td><td>${safe(incident.summary)}</td><td>${safe(summary)}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="empty">Nenhuma carteira zerada.</td></tr>`;

  document.querySelector("#positionCount").textContent = positions.length;
  document.querySelector("#positionRows").innerHTML = positions.length ? positions.map((position) => {
    const marketValue = position.quantity * (position.markPriceUsd ?? position.entryPriceUsd);
    const returnPct = position.costUsd > 0 ? position.unrealizedPnlUsd / position.costUsd * 100 : null;
    return `<tr>
      <td>${safe(position.trader)}</td><td><b>${safe(position.symbol)}</b></td><td>${safe(position.chain)}</td>
      <td class="num">${quantity(position.quantity)}</td><td class="num">${unitPrice(position.entryPriceUsd)}</td><td class="num">${position.markPriceUsd == null ? "Sem cotação" : unitPrice(position.markPriceUsd)}</td>
      <td class="num">${money(position.costUsd)}</td><td class="num">${money(marketValue)}</td>
      <td class="num ${tone(position.unrealizedPnlUsd)}">${money(position.unrealizedPnlUsd)}</td>
      <td class="num ${tone(returnPct)}">${pct(returnPct)}</td></tr>`;
  }).join("") : `<tr><td colspan="10" class="empty">Nenhuma posicao aberta.</td></tr>`;

  document.querySelector("#orderCount").textContent = `${orders.length} recentes`;
  document.querySelector("#orderRows").innerHTML = orders.length ? orders.map((order) => `<tr>
    <td>${new Date(order.executedAt).toLocaleString("pt-BR")}</td><td>${safe(order.trader)}</td>
    <td class="${order.side === "buy" ? "positive" : "negative"}">${order.side === "buy" ? "Compra" : "Venda"}</td>
    <td><b>${safe(order.symbol)}</b></td><td>${safe(order.chain)}</td><td class="num">${unitPrice(order.priceUsd)}</td>
    <td class="num">${money(order.notionalUsd)}</td><td class="num">${money(order.feeUsd)}</td>
    <td>${safe(patternName(order.patternType))}<small>forca ${Number(order.patternScore) || 0}/100</small></td>
    <td class="${tone(order.realizedPnlUsd)}">${order.realizedPnlUsd == null ? "-" : money(order.realizedPnlUsd)}</td>
    <td>${order.status === "filled" ? "Executada" : safe(order.reason ?? "Ignorada")}</td></tr>`).join("") : `<tr><td colspan="11" class="empty">Nenhuma movimentacao registrada.</td></tr>`;
  const history = data.dailyHistory ?? [];
  document.querySelector("#historyRows").innerHTML = history.length ? history.map((row) => `<tr><td>${safe(row.day)}</td><td>${safe(botName(row.botId))}</td>
    <td class="num">${money(row.equityUsd)}</td><td class="num ${tone(row.pnlUsd)}">${money(row.pnlUsd)}</td><td class="num ${tone(row.returnPct)}">${pct(row.returnPct)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">O histórico diário será registrado pelo Worker.</td></tr>`;
  document.querySelector("#trainingStatus").textContent = `Atualizado ${new Date(data.generatedAt).toLocaleTimeString("pt-BR")} · Preços ${data.pricesCheckedAt ? new Date(data.pricesCheckedAt).toLocaleTimeString("pt-BR") : "—"}`;
  document.querySelector("#trainingStatus").classList.remove("error");
}

async function refresh() {
  try {
    const response = await fetch("/api/training", { headers: { accept: "application/json" }, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Nao foi possivel carregar o treino.");
    data.pricesCheckedAt ??= current?.pricesCheckedAt;
    render(data);
  } catch (error) {
    const status = document.querySelector("#trainingStatus");
    status.textContent = error instanceof Error ? error.message : "Nao foi possivel carregar o treino.";
    status.classList.add("error");
  }
}

async function refreshPrices() {
  if (document.hidden) return;
  try {
    const response = await fetch("/api/training/prices", { headers: { accept: "application/json" }, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Cotações temporariamente indisponíveis.");
    if (!current) return;
    const livePositions = new Map((data.positions ?? []).map((position) => [
      `${position.botId}:${position.chain.toLowerCase()}:${position.address.toLowerCase()}`, position,
    ]));
    for (const position of current.positions ?? []) {
      const live = livePositions.get(`${position.botId}:${position.chain.toLowerCase()}:${position.address.toLowerCase()}`);
      if (!live) continue;
      position.markPriceUsd = live.priceUsd;
      position.unrealizedPnlUsd = live.unrealizedPnlUsd;
    }
    for (const wallet of current.wallets ?? []) {
      const previousUnrealized = wallet.unrealizedPnlUsd;
      const positions = (current.positions ?? []).filter((position) => position.botId === wallet.botId);
      wallet.marketValueUsd = positions.reduce((sum, position) => sum + position.quantity * position.markPriceUsd, 0);
      wallet.unrealizedPnlUsd = positions.reduce((sum, position) => sum + position.unrealizedPnlUsd, 0);
      wallet.totalPnlUsd = wallet.realizedPnlUsd + wallet.unrealizedPnlUsd;
      wallet.equityUsd = wallet.cashUsd + wallet.marketValueUsd;
      wallet.returnPct = wallet.initialUsd > 0 ? (wallet.equityUsd - wallet.initialUsd) / wallet.initialUsd * 100 : 0;
      wallet.dailyPnlUsd += wallet.unrealizedPnlUsd - previousUnrealized;
      wallet.dailyReturnPct = wallet.initialUsd > 0 ? wallet.dailyPnlUsd / wallet.initialUsd * 100 : 0;
    }
    current.pricesCheckedAt = data.checkedAt;
    render(current);
  } catch (error) {
    const status = document.querySelector("#trainingStatus");
    status.textContent = error instanceof Error ? error.message : "Cotações temporariamente indisponíveis.";
    status.classList.add("error");
  }
}

document.querySelector("#walletSearch").addEventListener("input", () => { if (current) render(current); });
document.querySelector("#trainingExplanation").addEventListener("click", (event) => {
  if (!event.target.closest(".rules-link")) return;
  document.querySelector("#trainingRules").open = true;
});
document.querySelector("#botComparison").addEventListener("click", (event) => {
  const button = event.target.closest("[data-bot-id]");
  if (!button || !current) return;
  selectedBotId = button.dataset.botId;
  render(current);
});
const capitalDialog = document.querySelector("#capitalDialog");
document.querySelector("#addCapitalButton").addEventListener("click", () => {
  if (!current?.capitalControlReady) return;
  document.querySelector("#capitalBot").value = selectedBotId;
  document.querySelector("#capitalMessage").textContent = "";
  document.querySelector("#capitalMessage").className = "capital-message";
  capitalDialog.showModal();
});
document.querySelector("#closeCapitalDialog").addEventListener("click", () => capitalDialog.close());
document.querySelector("#cancelCapitalDialog").addEventListener("click", () => capitalDialog.close());
document.querySelector("#capitalForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = document.querySelector("#submitCapital");
  const message = document.querySelector("#capitalMessage");
  const amountUsd = Number(document.querySelector("#capitalAmount").value);
  button.disabled = true;
  message.textContent = "Registrando aporte no D1…";
  message.className = "capital-message";
  if (!pendingCapitalEventId) pendingCapitalEventId = crypto.randomUUID();
  try {
    const response = await fetch("/api/training", {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ botId: document.querySelector("#capitalBot").value, amountUsd, eventId: pendingCapitalEventId }),
      cache: "no-store",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error ?? "Não foi possível registrar o aporte.");
    pendingCapitalEventId = null;
    capitalDialog.close();
    const notice = document.querySelector("#capitalNotice");
    notice.textContent = result.duplicate ? "Este aporte já estava registrado; não foi adicionado novamente." : `${money(amountUsd)} adicionados à carteira paper; o aporte não foi contado como lucro.`;
    notice.classList.add("visible");
    window.setTimeout(() => notice.classList.remove("visible"), 7000);
    await refresh();
  } catch (error) {
    message.textContent = error instanceof Error ? error.message : "Não foi possível registrar o aporte.";
    message.className = "capital-message error";
  } finally {
    button.disabled = false;
  }
});
void refresh();
void refreshPrices();
const scheduleDashboardRefresh = () => {
  if (dashboardRefreshTimer) clearTimeout(dashboardRefreshTimer);
  if (document.hidden) return;
  dashboardRefreshTimer = setTimeout(async () => {
    await refresh();
    scheduleDashboardRefresh();
  }, 15_000);
};
const schedulePriceRefresh = () => {
  if (priceRefreshTimer) clearTimeout(priceRefreshTimer);
  if (document.hidden) return;
  priceRefreshTimer = setTimeout(async () => {
    await refreshPrices();
    schedulePriceRefresh();
  }, 10_000);
};
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    if (dashboardRefreshTimer) clearTimeout(dashboardRefreshTimer);
    if (priceRefreshTimer) clearTimeout(priceRefreshTimer);
    return;
  }
  void refresh();
  void refreshPrices();
  scheduleDashboardRefresh();
  schedulePriceRefresh();
});
scheduleDashboardRefresh();
schedulePriceRefresh();
