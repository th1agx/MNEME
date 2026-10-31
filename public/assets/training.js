const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value) || 0);
const unitPrice = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 8 }).format(Number(value) || 0);
const quantity = (value) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 6 }).format(Number(value) || 0);
const pct = (value) => value == null ? "-" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const safe = (value) => String(value ?? "-").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
const patternName = (value) => ({
  large_buy: "Compra de alto valor", crowd_buy: "Compra em grupo", large_and_crowd_buy: "Alto valor + grupo",
  large_sell: "Venda de alto valor", crowd_sell: "Venda em grupo", sell_batch: "Venda em lote",
  mixed_flow: "Fluxo conflitante", unconfirmed: "Sem confirmacao",
}[value] ?? value ?? "-");
let current = null;
let selectedBotId = "mneme-paper-conservative";
let priceRefreshTimer = null;
let dashboardRefreshTimer = null;
let pendingCapitalEventId = null;

function render(data) {
  current = data;
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
  const rankedWallets = wallets;
  const leaderBotId = rankedWallets.length > 1 && rankedWallets[0].totalPnlUsd !== rankedWallets[1].totalPnlUsd ? rankedWallets[0].botId : null;
  document.querySelector("#botComparison").innerHTML = wallets.map((item) => `<button class="bot-card ${item.botId === selectedBotId ? "selected" : ""}" type="button" data-bot-id="${safe(item.botId)}" aria-pressed="${item.botId === selectedBotId}">
    <span class="bot-card-title">${safe(botName(item.botId))}</span><strong class="${tone(item.totalPnlUsd)}">${money(item.totalPnlUsd)}</strong><small>resultado acumulado (realizado + em aberto) · ${pct(item.returnPct)}</small>
    <span class="bot-card-stats"><span>Patrimônio <b>${money(item.equityUsd)}</b></span><span>Hoje <b class="${tone(item.dailyPnlUsd)}">${money(item.dailyPnlUsd)}</b></span><span>Em aberto <b class="${tone(item.unrealizedPnlUsd)}">${money(item.unrealizedPnlUsd)}</b></span></span>
    <small>${item.botId === leaderBotId ? "Maior resultado acumulado agora · " : leaderBotId === null ? "Empate no resultado acumulado · " : ""}${item.closedTrades} vendas fechadas · ${item.openPositions} posições abertas · ${item.haltedAt ? "pausado" : "ativo"}</small></button>`).join("");
  document.querySelector("#botTabs").innerHTML = wallets.map((item) => `<button type="button" role="tab" data-bot-id="${safe(item.botId)}" aria-selected="${item.botId === selectedBotId}" class="bot-tab ${item.botId === selectedBotId ? "selected" : ""}">${safe(botName(item.botId))}</button>`).join("");
  const positions = (data.positions ?? []).filter((item) => item.botId === selectedBotId);
  const orders = (data.orders ?? []).filter((item) => item.botId === selectedBotId);
  const incidents = (data.incidents ?? []).filter((item) => item.botId === selectedBotId);
  const patterns = (data.patterns ?? []).filter((item) => item.botId === selectedBotId);
  const summary = [
    ["Capital total aportado", money(wallet?.initialUsd ?? data.paperCapital?.totalAllocatedUsd)],
    ["Saldo para novas compras", money(wallet?.cashUsd)],
    ["Valor das posições abertas", money(wallet?.marketValueUsd)],
    ["Patrimônio atual", money(wallet?.equityUsd)],
    ["Resultado já realizado", money(wallet?.realizedPnlUsd)],
    ["Resultado ainda em aberto", money(wallet?.unrealizedPnlUsd)],
  ];
  document.querySelector("#trainingSummary").innerHTML = summary.map(([label, value]) => `<div class="training-kpi"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");
  const capitalButton = document.querySelector("#addCapitalButton");
  capitalButton.disabled = !data.capitalControlReady;
  capitalButton.title = data.capitalControlReady ? "Adicionar saldo simulado à carteira selecionada" : "Configure o Secret TRAINING_ADMIN_KEY nas configurações do projeto Pages";
  document.querySelector("#capitalControlHelp").textContent = data.capitalControlReady
    ? "Aporte simulado entra no saldo e no capital aportado, não como lucro."
    : "Para habilitar, configure TRAINING_ADMIN_KEY como Secret de pelo menos 32 caracteres no projeto Pages. O aporte será simulado e não contará como lucro.";
  document.querySelector("#capitalBot").innerHTML = wallets.map((item) => `<option value="${safe(item.botId)}">${safe(botName(item.botId))}</option>`).join("");
  document.querySelector("#capitalBot").value = selectedBotId;
  const capitalEvents = data.capitalEvents ?? [];
  document.querySelector("#capitalEventCount").textContent = capitalEvents.length;
  document.querySelector("#capitalRows").innerHTML = capitalEvents.length ? capitalEvents.map((event) => `<tr>
    <td>${new Date(event.createdAt).toLocaleString("pt-BR")}</td><td>${safe(botName(event.botId))}</td><td class="num positive">+${money(event.amountUsd)}</td></tr>`).join("")
    : `<tr><td colspan="3" class="empty">Nenhum aporte registrado.</td></tr>`;
  const positionLines = positions.map((position) => `${safe(position.symbol)}: custo de ${money(position.costUsd)}; valor agora de ${money(position.costUsd + position.unrealizedPnlUsd)}; variação aberta de ${money(position.unrealizedPnlUsd)}.`).join(" ");
  const profile = bots.find((bot) => bot.id === selectedBotId);
  const profileRules = profile ? `Regras desta carteira: compra individual a partir de ${money(profile.largeSignalUsd)} ou grupo de ${profile.crowdMinimumTraders}+ traders com ${money(profile.crowdMinimumVolumeUsd)}; limite de ${profile.maxAssetExposurePct}% por ativo e ${profile.maxPortfolioExposurePct}% total; intervalo de ${profile.buyCooldownMinutes} min por ativo.` : "";
  document.querySelector("#trainingExplanation").innerHTML = `<b>${safe(botName(selectedBotId))}:</b> ${profileRules} Mesmo fluxo de alertas e cotações do outro bot, com regras e carteira separadas. O patrimônio soma saldo disponível e posições. O resultado em aberto é estimado e só vira realizado na venda. ${positionLines || "Ainda não há posições abertas."}<span>Resultado de hoje: <b>${money(wallet?.dailyPnlUsd)}</b> (${pct(wallet?.dailyReturnPct)}). Valores de simulação; o score é uma heurística, não probabilidade de lucro.</span>`;

  const headerLabels = {
    "#": "#", "Conta": "Conta", "Resultado total": "Lucro/prejuízo total", "Realizado": "Já realizado (vendas)", "Em aberto": "Ainda em aberto",
    "Retorno": "Retorno sobre capital", "Hoje": "Resultado de hoje", "Meta diária 30%": "Meta diária (referência)", "Estado": "Estado",
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
    <td><div class="goal-meter"><span style="width:${Math.max(0, Math.min(100, Number(item.dailyTargetProgressPct) || 0))}%"></span></div><small>${item.dailyTargetReached ? "Atingida hoje" : `${pct(item.dailyReturnPct)} de 30%`}</small></td>
    <td>${item.haltedAt ? `<span class="halted" title="${safe(item.haltReason)}">Pausada</span>` : "Ativa"}</td>
    <td class="num">${pct(item.winRatePct)}</td><td class="num">${item.closedTrades}</td><td class="num">${item.openPositions}</td></tr>`).join("") : `<tr><td colspan="12" class="empty">${wallets.length ? "Nenhum resultado para este filtro." : "A carteira aparece quando o Worker iniciar."}</td></tr>`;

  const performance = (data.patternPerformance ?? []).filter((row) => row.botId === selectedBotId);
  document.querySelector("#patternPerformanceRows").innerHTML = performance.length ? performance.map((row) => `<tr>
    <td>${safe(patternName(row.pattern))}</td><td class="num">${row.closedTrades}</td><td class="num">${pct(row.winRatePct)}</td>
    <td class="num ${tone(row.realizedPnlUsd)}">${money(row.realizedPnlUsd)}</td><td class="num ${tone(row.averagePnlUsd)}">${money(row.averagePnlUsd)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">Ainda nao ha saidas fechadas para comparar.</td></tr>`;

  document.querySelector("#patternCount").textContent = patterns.length;
  document.querySelector("#patternRows").innerHTML = patterns.length ? patterns.map((pattern) => `<tr>
    <td>${new Date(pattern.observedAt).toLocaleString("pt-BR")}</td><td><b>${safe(pattern.symbol)}</b><small>${safe(pattern.chain)}</small></td>
    <td>${safe(patternName(pattern.pattern))}</td><td class="${pattern.action === "buy" ? "positive" : pattern.action === "sell" ? "negative" : ""}">${pattern.action === "buy" ? "Compra paper" : pattern.action === "sell" ? "Venda paper" : "Observar"}<small>${safe(pattern.reason)}</small></td>
    <td class="num">${Number(pattern.score) || 0}/100</td><td class="num">${pattern.buyers}</td><td class="num">${pattern.sellers}</td>
    <td class="num">${money(pattern.buyVolumeUsd)}</td><td class="num">${money(pattern.sellVolumeUsd)}</td></tr>`).join("")
    : `<tr><td colspan="9" class="empty">Aguardando alertas para classificar.</td></tr>`;

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
  document.querySelector("#trainingStatus").textContent = `Painel ${new Date(data.generatedAt).toLocaleTimeString("pt-BR")} · cotações verificadas ${data.pricesCheckedAt ? new Date(data.pricesCheckedAt).toLocaleTimeString("pt-BR") : "aguardando"}`;
  document.querySelector("#trainingStatus").classList.remove("error");
}

async function refresh() {
  try {
    const response = await fetch("/api/training", { headers: { accept: "application/json" }, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Nao foi possivel carregar o treino.");
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
document.querySelector("#botTabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-bot-id]");
  if (!button || !current) return;
  selectedBotId = button.dataset.botId;
  render(current);
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
  const adminKey = document.querySelector("#capitalKey").value;
  const amountUsd = Number(document.querySelector("#capitalAmount").value);
  button.disabled = true;
  message.textContent = "Registrando aporte no D1…";
  message.className = "capital-message";
  if (!pendingCapitalEventId) pendingCapitalEventId = crypto.randomUUID();
  try {
    const response = await fetch("/api/training", {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json", authorization: `Bearer ${adminKey}` },
      body: JSON.stringify({ botId: document.querySelector("#capitalBot").value, amountUsd, eventId: pendingCapitalEventId }),
      cache: "no-store",
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error ?? "Não foi possível registrar o aporte.");
    pendingCapitalEventId = null;
    document.querySelector("#capitalKey").value = "";
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
