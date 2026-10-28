// Transformações de apresentação, sem regras de negociação ou preços inventados.
export const MARKET_SYMBOLS = ["SOLUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT"];
export const baseSymbol = (symbol) => symbol.replace(/USDT$/, "");

export function orderMarket(order) {
  const token = String(order.tokenSymbol ?? "").toUpperCase();
  // Só o mint canônico identifica SOL/WSOL; um token que apenas se chama SOL não é Solana.
  if (order.chain === "solana" && order.tokenAddress === "So11111111111111111111111111111111111111112") return "SOLUSDT";
  if (token === "SOL" || token === "WSOL") return null;
  const symbol = `${token}USDT`;
  return MARKET_SYMBOLS.includes(symbol) ? symbol : null;
}

export function chartOrders(orders, symbol) {
  return orders.filter((order) => orderMarket(order) === symbol);
}

export function orderMarkers(candles, orders, symbol) {
  const groups = new Map();
  for (const order of chartOrders(orders, symbol)) {
    if (order.status !== "filled" || !Number.isFinite(order.priceUsd) || order.priceUsd <= 0) continue;
    const at = Date.parse(order.createdAt);
    const index = candles.findIndex((c) => at >= c.time && at <= c.closeTime);
    if (index < 0) continue;
    const key = `${index}:${order.side}`;
    const marker = groups.get(key) ?? { index, side: order.side, orders: [], volumeUsd: 0 };
    marker.orders.push(order);
    if (Number.isFinite(order.filledUsd) && order.filledUsd > 0) marker.volumeUsd += order.filledUsd;
    groups.set(key, marker);
  }
  return [...groups.values()].sort((a, b) => a.index - b.index);
}

export function filterOrders(orders, filter, symbol = null) {
  return orders.filter((order) => (!symbol || orderMarket(order) === symbol)
    && (filter === "all" || (filter === "failed" ? order.status === "failed" : order.side === filter)))
    .slice().sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
}
