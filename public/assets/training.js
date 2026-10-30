const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD" }).format(Number(value) || 0);
const pct = (value) => value == null ? "—" : `${Number(value).toFixed(2).replace(".", ",")}%`;
const safe = (value) => String(value ?? "—").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const tone = (value) => Number(value) > 0 ? "positive" : Number(value) < 0 ? "negative" : "";
let current = null;

function render(data) {
  current = data;
  const wallets = data.wallets ?? [];
  const totalPnl = wallets.reduce((sum, wallet) => sum + wallet.totalPnlUsd, 0);
  const openCount = wallets.reduce((sum, wallet) => sum + wallet.openPositions, 0);
  const summary = [
    ["Carteiras fictícias", wallets.length],
    ["Resultado combinado", money(totalPnl)],
    ["Traders no ranking", wallets.length],
    ["Posições abertas", openCount],
  ];
  document.querySelector("#trainingSummary").innerHTML = summary.map(([label, value]) => `<div class="training-kpi"><span>${safe(label)}</span><b>${safe(value)}</b></div>`).join("");

  const query = document.querySelector("#walletSearch").value.trim().toLowerCase();
  const ranked = wallets.filter((wallet) => wallet.trader.toLowerCase().includes(query));
  document.querySelector("#walletRows").innerHTML = ranked.length ? ranked.map((wallet, index) => `<tr>
    <td>${index + 1}</td><td>${safe(wallet.trader)}${wallet.sourceRank ? `<small class="muted"> · Top ${wallet.sourceRank}</small>` : ""}</td>
    <td class="num ${tone(wallet.totalPnlUsd)}">${money(wallet.totalPnlUsd)}</td><td class="num ${tone(wallet.realizedPnlUsd)}">${money(wallet.realizedPnlUsd)}</td>
    <td class="num ${tone(wallet.unrealizedPnlUsd)}">${money(wallet.unrealizedPnlUsd)}</td><td class="num ${tone(wallet.returnPct)}">${pct(wallet.returnPct)}</td>
    <td class="num">${pct(wallet.winRatePct)}</td><td class="num">${wallet.closedTrades}</td><td class="num">${wallet.openPositions}</td></tr>`).join("") : `<tr><td colspan="9" class="empty">${wallets.length ? "Nenhum trader corresponde ao filtro." : "O ranking aparece quando chegarem sinais válidos."}</td></tr>`;

  const positions = data.positions ?? [];
  document.querySelector("#positionCount").textContent = positions.length;
  document.querySelector("#positionRows").innerHTML = positions.length ? positions.map((position) => `<tr>
    <td>${safe(position.trader)}</td><td><b>${safe(position.symbol)}</b></td><td>${safe(position.chain)}</td>
    <td class="num">${money(position.entryPriceUsd)}</td><td class="num">${money(position.markPriceUsd)}</td><td class="num">${money(position.costUsd)}</td>
    <td class="num ${tone(position.unrealizedPnlUsd)}">${money(position.unrealizedPnlUsd)}</td></tr>`).join("") : `<tr><td colspan="7" class="empty">Nenhuma posição aberta.</td></tr>`;

  const orders = data.orders ?? [];
  document.querySelector("#orderCount").textContent = `${orders.length} recentes`;
  document.querySelector("#orderRows").innerHTML = orders.length ? orders.map((order) => `<tr>
    <td>${new Date(order.executedAt).toLocaleString("pt-BR")}</td><td>${safe(order.trader)}</td>
    <td class="${order.side === "buy" ? "positive" : "negative"}">${order.side === "buy" ? "Compra" : "Venda"}</td>
    <td><b>${safe(order.symbol)}</b></td><td>${safe(order.chain)}</td><td class="num">${money(order.priceUsd)}</td>
    <td class="num">${money(order.notionalUsd)}</td><td class="num">${money(order.feeUsd)}</td>
    <td class="${tone(order.realizedPnlUsd)}">${order.realizedPnlUsd == null ? "—" : money(order.realizedPnlUsd)}</td>
    <td>${order.status === "filled" ? "Executada" : safe(order.reason ?? "Ignorada")}</td></tr>`).join("") : `<tr><td colspan="10" class="empty">Nenhuma movimentação registrada.</td></tr>`;
  document.querySelector("#trainingStatus").textContent = `Atualizado ${new Date(data.generatedAt).toLocaleTimeString("pt-BR")} · atualiza a cada 15 segundos`;
  document.querySelector("#trainingStatus").classList.remove("error");
}

async function refresh() {
  try {
    const response = await fetch("/api/training", { headers: { accept: "application/json" }, cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error ?? "Não foi possível carregar o treino.");
    render(data);
  } catch (error) {
    const status = document.querySelector("#trainingStatus");
    status.textContent = error instanceof Error ? error.message : "Não foi possível carregar o treino.";
    status.classList.add("error");
  }
}

document.querySelector("#walletSearch").addEventListener("input", () => { if (current) render(current); });
void refresh();
setInterval(refresh, 15_000);
