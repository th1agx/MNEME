const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value) || 0);
const pct = (value) => value == null ? "-" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const safe = (value) => String(value ?? "-").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
let current = null;

function render(data) {
  current = data;
  const wallets = data.wallets ?? [];
  const wallet = wallets[0];
  const summary = [
    ["Carteira paper", wallets.length],
    ["Capital simulado", money(data.paperCapital?.totalAllocatedUsd)],
    ["Patrimonio atual", money(wallet?.equityUsd)],
    ["Resultado hoje", money(wallet?.dailyPnlUsd)],
    ["Meta diaria", "30% (referencia)"],
  ];
  document.querySelector("#trainingSummary").innerHTML = summary.map(([label, value]) => `<div class="training-kpi"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");

  const query = document.querySelector("#walletSearch").value.trim().toLowerCase();
  const visible = wallets.filter((item) => item.trader.toLowerCase().includes(query));
  document.querySelector("#walletRows").innerHTML = visible.length ? visible.map((item) => `<tr>
    <td>1</td><td>${safe(item.trader)}</td><td class="num ${tone(item.totalPnlUsd)}">${money(item.totalPnlUsd)}</td>
    <td class="num ${tone(item.realizedPnlUsd)}">${money(item.realizedPnlUsd)}</td><td class="num ${tone(item.unrealizedPnlUsd)}">${money(item.unrealizedPnlUsd)}</td>
    <td class="num ${tone(item.returnPct)}">${pct(item.returnPct)}</td><td class="num ${tone(item.dailyPnlUsd)}">${money(item.dailyPnlUsd)}<small>${pct(item.dailyReturnPct)}</small></td>
    <td><div class="goal-meter"><span style="width:${Math.max(0, Math.min(100, Number(item.dailyTargetProgressPct) || 0))}%"></span></div><small>${item.dailyTargetReached ? "Atingida hoje" : `${pct(item.dailyReturnPct)} de 30%`}</small></td>
    <td>${item.haltedAt ? `<span class="halted" title="${safe(item.haltReason)}">Pausada</span>` : "Ativa"}</td>
    <td class="num">${pct(item.winRatePct)}</td><td class="num">${item.closedTrades}</td><td class="num">${item.openPositions}</td></tr>`).join("") : `<tr><td colspan="12" class="empty">${wallets.length ? "Nenhum resultado para este filtro." : "A carteira aparece quando o Worker iniciar."}</td></tr>`;

  const incidents = data.incidents ?? [];
  document.querySelector("#incidentCount").textContent = incidents.length;
  document.querySelector("#incidentRows").innerHTML = incidents.length ? incidents.map((incident) => {
    const details = incident.diagnostics ?? {};
    const recent = details.last24h ?? {};
    const summary = `Patrimonio ${money(details.equityUsd)}; saldo ${money(details.cashUsd)}; posicoes abertas ${Number(details.openPositions) || 0}; trades 24h ${Number(recent.trades) || 0}; ganhos/perdas ${Number(recent.wins) || 0}/${Number(recent.losses) || 0}; taxas ${money(recent.feesUsd)}; resultado realizado 24h ${money(recent.realizedPnlUsd)}.`;
    return `<tr><td>${new Date(incident.occurredAt).toLocaleString("pt-BR")}</td><td>${safe(incident.trader)}</td><td>${safe(incident.summary)}</td><td>${safe(summary)}</td></tr>`;
  }).join("") : `<tr><td colspan="4" class="empty">Nenhuma carteira zerada.</td></tr>`;

  const positions = data.positions ?? [];
  document.querySelector("#positionCount").textContent = positions.length;
  document.querySelector("#positionRows").innerHTML = positions.length ? positions.map((position) => `<tr>
    <td>${safe(position.trader)}</td><td><b>${safe(position.symbol)}</b></td><td>${safe(position.chain)}</td>
    <td class="num">${money(position.entryPriceUsd)}</td><td class="num">${money(position.markPriceUsd)}</td><td class="num">${money(position.costUsd)}</td>
    <td class="num ${tone(position.unrealizedPnlUsd)}">${money(position.unrealizedPnlUsd)}</td></tr>`).join("") : `<tr><td colspan="7" class="empty">Nenhuma posicao aberta.</td></tr>`;

  const orders = data.orders ?? [];
  document.querySelector("#orderCount").textContent = `${orders.length} recentes`;
  document.querySelector("#orderRows").innerHTML = orders.length ? orders.map((order) => `<tr>
    <td>${new Date(order.executedAt).toLocaleString("pt-BR")}</td><td>${safe(order.trader)}</td>
    <td class="${order.side === "buy" ? "positive" : "negative"}">${order.side === "buy" ? "Compra" : "Venda"}</td>
    <td><b>${safe(order.symbol)}</b></td><td>${safe(order.chain)}</td><td class="num">${money(order.priceUsd)}</td>
    <td class="num">${money(order.notionalUsd)}</td><td class="num">${money(order.feeUsd)}</td>
    <td class="${tone(order.realizedPnlUsd)}">${order.realizedPnlUsd == null ? "-" : money(order.realizedPnlUsd)}</td>
    <td>${order.status === "filled" ? "Executada" : safe(order.reason ?? "Ignorada")}</td></tr>`).join("") : `<tr><td colspan="10" class="empty">Nenhuma movimentacao registrada.</td></tr>`;
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
