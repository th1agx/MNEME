import { MARKET_SYMBOLS } from "./chart-data.js";

export const MARKET_INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"];
const PUBLIC_MARKET_URL = "https://data-api.binance.vision/api/v3/klines";

function validCandles(candles) {
  return Array.isArray(candles) && candles.length > 0 && candles.length <= 180 && candles.every((c, i) =>
    c && [c.time, c.closeTime, c.open, c.high, c.low, c.close, c.volume, c.quoteVolume].every(Number.isFinite)
    && Number.isSafeInteger(c.time) && Number.isSafeInteger(c.closeTime) && c.time >= 0 && c.closeTime > c.time && c.closeTime <= 8.64e15
    && Math.min(c.open, c.high, c.low, c.close) > 0 && c.low <= Math.min(c.open, c.close) && c.high >= Math.max(c.open, c.close)
    && c.volume >= 0 && c.quoteVolume >= 0 && (i === 0 || c.time > candles[i - 1].time));
}

export function parsePublicCandles(rows, symbol, interval, at = Date.now()) {
  if (!Array.isArray(rows)) throw new Error("Histórico de mercado inválido.");
  const candles = rows.map((row) => {
    if (!Array.isArray(row) || row.length < 8) throw new Error("Histórico de mercado incompleto.");
    const values = row.slice(0, 8).map((v) => typeof v === "number" || (typeof v === "string" && v.trim() !== "") ? Number(v) : NaN);
    const [time, open, high, low, close, volume, closeTime, quoteVolume] = values;
    return { time, closeTime, open, high, low, close, volume, quoteVolume, complete: closeTime < at };
  });
  if (!validCandles(candles)) throw new Error("Histórico de mercado inválido.");
  return { symbol, interval, source: "Binance Spot", quote: "USDT", fetchedAt: new Date(at).toISOString(), candles };
}

/** Se o servidor não alcança o mercado público, consulta a mesma fonte pelo navegador.
 * Não usa proxies, chaves de API, cookies ou dados privados do bot nessa consulta.
 */
export function createMarketClient(fetchImpl = fetch, now = Date.now) {
  let retryServerAfter = 0;
  return async (symbol, interval, signal) => {
    if (!MARKET_SYMBOLS.includes(symbol) || !MARKET_INTERVALS.includes(interval)) throw new Error("Moeda ou intervalo não suportado.");
    signal?.throwIfAborted();
    if (now() >= retryServerAfter) {
      let response;
      try {
        response = await fetchImpl(`/api/market/candles?${new URLSearchParams({ symbol, interval })}`, { signal });
      } catch (error) {
        if (signal?.aborted || error.name === "AbortError") throw error;
      }
      // Falhas de autenticação, validação e limite não devem ser contornadas.
      if (response && !response.ok && response.status < 500) {
        throw new Error(response.status === 401 || response.status === 403 ? "Acesso ao mercado não autorizado." : `Consulta de mercado recusada (HTTP ${response.status}).`);
      }
      if (response?.ok) {
        try {
          const data = await response.json();
          if (data.symbol === symbol && data.interval === interval && data.source === "Binance Spot" && data.quote === "USDT"
            && Number.isFinite(Date.parse(data.fetchedAt)) && validCandles(data.candles)) return data;
        } catch (error) {
          if (signal?.aborted || error.name === "AbortError") throw error;
        }
      }
      retryServerAfter = now() + 60_000;
    }
    signal?.throwIfAborted();
    const url = new URL(PUBLIC_MARKET_URL);
    url.search = new URLSearchParams({ symbol, interval, limit: "180" }).toString();
    const response = await fetchImpl(url, { signal, credentials: "omit" });
    if (!response.ok) throw new Error(`A Binance não disponibilizou as velas (HTTP ${response.status}).`);
    return parsePublicCandles(await response.json(), symbol, interval, now());
  };
}
