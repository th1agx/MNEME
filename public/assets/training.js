const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value) || 0);
const unitPrice = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 8 }).format(Number(value) || 0);
const pct = (value) => value == null ? "-" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const safe = (value) => String(value ?? "-").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
const patternName = (value) => ({
  large_buy: "Compra de alto valor", crowd_buy: "Compra em grupo", large_and_crowd_buy: "Alto valor + grupo",
  large_sell: "Venda de alto valor", crowd_sell: "Venda em grupo", sell_batch: "Venda em lote",
  mixed_flow: "Fluxo conflitante", unconfirmed: "Sem confirmacao",
}[value] ?? value ?? "-");
let current = null;

function render(data) {
  current = data;
  const wallets = data.wallets ?? [];
  const wallet = wallets[0];
  const positions = data.positions ?? [];
  const summary = [
    ["Capital inicial (simulado)", money(wallet?.initialUsd ?? data.paperCapital?.totalAllocatedUsd)],
    ["Saldo disponível para compras", money(wallet?.cashUsd)],
    ["Valor atual das posições", money(wallet?.marketValueUsd)],
    ["Patrimônio total (saldo + posições)", money(wallet?.equityUsd)],
    ["Ganho/perda ainda em aberto", money(wallet?.unrealizedPnlUsd)],
    ["Lucro/prejuízo já realizado", money(wallet?.realizedPnlUsd)],
  ];
  document.querySelector("#trainingSummary").innerHTML = summary.map(([label, value]) => `<div class="training-kpi"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");
  const positionLines = positions.map((position) => `${safe(position.symbol)}: custo de ${money(position.costUsd)}; valor agora de ${money(position.costUsd + position.unrealizedPnlUsd)}; variação aberta de ${money(position.unrealizedPnlUsd)}.`).join(" ");
  document.querySelector("#trainingExplanation").innerHTML = `<b>Como ler:</b> o lucro em aberto é uma estimativa: valor atual das posições menos o custo de compra, incluindo taxas. Ele ainda pode subir ou cair e só é realizado quando há venda. O patrimônio soma o saldo disponível ao valor atual das posições. ${positionLines || "Ainda não há posições abertas."}<span>Resultado de hoje: <b>${money(wallet?.dailyPnlUsd)}</b> (${pct(wallet?.dailyReturnPct)}). A meta de 30% é só uma referência, não uma previsão.</span>`;

  const headerLabels = {
    "#": "#", "Conta": "Conta", "Resultado total": "Lucro/prejuízo total", "Realizado": "Já realizado (vendas)", "Em aberto": "Ainda em aberto",
    "Retorno": "Retorno sobre capital", "Hoje": "Resultado de hoje", "Meta diária 30%": "Meta diária (referência)", "Estado": "Estado",
    "Acerto": "Vendas com lucro", "Fechadas": "Vendas fechadas", "Abertas": "Posições abertas",
  };
  document.querySelectorAll("#walletRows").forEach((body) => body.closest("table").querySelectorAll("thead th").forEach((th) => { if (headerLabels[th.textContent.trim()]) th.textContent = headerLabels[th.textContent.trim()]; }));
  const setHeaders = (bodyId, labels) => document.querySelector(`#${bodyId}`).closest("table").querySelectorAll("thead th").forEach((th, index) => { if (labels[index]) th.textContent = labels[index]; });
  setHeaders("positionRows", ["Conta", "Ativo", "Rede", "Preço médio de compra", "Preço usado agora", "Custo total (inclui taxa)", "Ganho/perda em aberto"]);
  setHeaders("orderRows", ["Executada", "Conta", "Lado", "Ativo", "Rede", "Preço por unidade", "Valor da ordem", "Taxa", "Padrão detectado", "Lucro/prejuízo desta venda", "Situação"]);

  const query = document.querySelector("#walletSearch").value.trim().toLowerCase();
  const visible = wallets.filter((item) => item.trader.toLowerCase().includes(query));
  document.querySelector("#walletRows").innerHTML = visible.length ? visible.map((item) => `<tr>
    <td>1</td><td>${safe(item.trader)}</td><td class="num ${tone(item.totalPnlUsd)}">${money(item.totalPnlUsd)}</td>
    <td class="num ${tone(item.realizedPnlUsd)}">${money(item.realizedPnlUsd)}</td><td class="num ${tone(item.unrealizedPnlUsd)}">${money(item.unrealizedPnlUsd)}</td>
    <td class="num ${tone(item.returnPct)}">${pct(item.returnPct)}</td><td class="num ${tone(item.dailyPnlUsd)}">${money(item.dailyPnlUsd)}<small>${pct(item.dailyReturnPct)}</small></td>
    <td><div class="goal-meter"><span style="width:${Math.max(0, Math.min(100, Number(item.dailyTargetProgressPct) || 0))}%"></span></div><small>${item.dailyTargetReached ? "Atingida hoje" : `${pct(item.dailyReturnPct)} de 30%`}</small></td>
    <td>${item.haltedAt ? `<span class="halted" title="${safe(item.haltReason)}">Pausada</span>` : "Ativa"}</td>
    <td class="num">${pct(item.winRatePct)}</td><td class="num">${item.closedTrades}</td><td class="num">${item.openPositions}</td></tr>`).join("") : `<tr><td colspan="12" class="empty">${wallets.length ? "Nenhum resultado para este filtro." : "A carteira aparece quando o Worker iniciar."}</td></tr>`;

  const performance = data.patternPerformance ?? [];
  document.querySelector("#patternPerformanceRows").innerHTML = performance.length ? performance.map((row) => `<tr>
    <td>${safe(patternName(row.pattern))}</td><td class="num">${row.closedTrades}</td><td class="num">${pct(row.winRatePct)}</td>
    <td class="num ${tone(row.realizedPnlUsd)}">${money(row.realizedPnlUsd)}</td><td class="num ${tone(row.averagePnlUsd)}">${money(row.averagePnlUsd)}</td></tr>`).join("")
    : `<tr><td colspan="5" class="empty">Ainda nao ha saidas fechadas para comparar.</td></tr>`;

  const patterns = data.patterns ?? [];
  document.querySelector("#patternCount").textContent = patterns.length;
  document.querySelector("#patternRows").innerHTML = patterns.length ? patterns.map((pattern) => `<tr>
    <td>${new Date(pattern.observedAt).toLocaleString("pt-BR")}</td><td><b>${safe(pattern.symbol)}</b><small>${safe(pattern.chain)}</small></td>
    <td>${safe(patternName(pattern.pattern))}</td><td class="${pattern.action === "buy" ? "positive" : pattern.action === "sell" ? "negative" : ""}">${pattern.action === "buy" ? "Compra paper" : pattern.action === "sell" ? "Venda paper" : "Observar"}<small>${safe(pattern.reason)}</small></td>
    <td class="num">${Number(pattern.score) || 0}/100</td><td class="num">${pattern.buyers}</td><td class="num">${pattern.sellers}</td>
    <td class="num">${money(pattern.buyVolumeUsd)}</td><td class="num">${money(pattern.sellVolumeUsd)}</td></tr>`).join("")
    : `<tr><td colspan="9" class="empty">Aguardando alertas para classificar.</td></tr>`;

  const incidents = data.incidents ?? [];
  document.querySelector("#incidentCount").textContent = incidents.length;
  document.querySelector("#incidentRows").innerHTML = incidents.length ? incidents.map((incident) => {
    const details = incident.diagnostics ?? {};
    const recent = details.last24h ?? {};
    const summary = `Patrimonio ${money(details.equityUsd)}; saldo ${money(details.cashUsd)}; posicoes abertas ${Number(details.openPositions) || 0}; trades 24h ${Number(recent.trades) || 0}; ganhos/perdas ${Number(recent.wins) || 0}/${Number(recent.losses) || 0}; taxas ${money(recent.feesUsd)}; resultado realizado 24h ${money(recent.realizedPnlUsd)}.`;
    return `<tr><td>${new Date(incident.occurredAt).toLocaleString("pt-BR")}</td><td>${safe(incident.trader)}</td><td>${safe(incident.summary)}</td><td>${safe(summary)}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="empty">Nenhuma carteira zerada.</td></tr>`;

  document.querySelector("#positionCount").textContent = positions.length;
  document.querySelector("#positionRows").innerHTML = positions.length ? positions.map((position) => `<tr>
    <td>${safe(position.trader)}</td><td><b>${safe(position.symbol)}</b></td><td>${safe(position.chain)}</td>
    <td class="num">${unitPrice(position.entryPriceUsd)}</td><td class="num">${unitPrice(position.markPriceUsd)}</td><td class="num">${money(position.costUsd)}</td>
    <td class="num ${tone(position.unrealizedPnlUsd)}">${money(position.unrealizedPnlUsd)}</td></tr>`).join("") : `<tr><td colspan="7" class="empty">Nenhuma posicao aberta.</td></tr>`;

  const orders = data.orders ?? [];
  document.querySelector("#orderCount").textContent = `${orders.length} recentes`;
  document.querySelector("#orderRows").innerHTML = orders.length ? orders.map((order) => `<tr>
    <td>${new Date(order.executedAt).toLocaleString("pt-BR")}</td><td>${safe(order.trader)}</td>
    <td class="${order.side === "buy" ? "positive" : "negative"}">${order.side === "buy" ? "Compra" : "Venda"}</td>
    <td><b>${safe(order.symbol)}</b></td><td>${safe(order.chain)}</td><td class="num">${unitPrice(order.priceUsd)}</td>
    <td class="num">${money(order.notionalUsd)}</td><td class="num">${money(order.feeUsd)}</td>
    <td>${safe(patternName(order.patternType))}<small>forca ${Number(order.patternScore) || 0}/100</small></td>
    <td class="${tone(order.realizedPnlUsd)}">${order.realizedPnlUsd == null ? "-" : money(order.realizedPnlUsd)}</td>
    <td>${order.status === "filled" ? "Executada" : safe(order.reason ?? "Ignorada")}</td></tr>`).join("") : `<tr><td colspan="11" class="empty">Nenhuma movimentacao registrada.</td></tr>`;
  document.querySelector("#trainingStatus").textContent = `Atualizado ${new Date(data.generatedAt).toLocaleTimeString("pt-BR")} · atualiza a cada 15 segundos`;
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

document.querySelector("#walletSearch").addEventListener("input", () => { if (current) render(current); });
void refresh();
setInterval(refresh, 15_000);
