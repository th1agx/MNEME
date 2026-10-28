// Rota pública de mercado do Pages: independente da origem privada do bot na VPS.
export const SYMBOLS = ["SOLUSDT", "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "SUIUSDT"];
export const INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"];

export function createMarketHandler(fetchImpl: typeof fetch = fetch, now: () => number = Date.now) {
  const cached = new Map<string, { at: number; body: unknown }>();
  const pending = new Map<string, Promise<unknown>>();

  async function load(symbol: string, interval: string) {
    const url = new URL("https://data-api.binance.vision/api/v3/klines");
    url.search = new URLSearchParams({ symbol, interval, limit: "180" }).toString();
    const upstream = await fetchImpl(url, { signal: AbortSignal.timeout(8_000) });
    if (!upstream.ok) throw new Error("Mercado indisponível.");
    const rows: unknown = await upstream.json();
    if (!Array.isArray(rows) || !rows.length || rows.length > 180) throw new Error("Histórico inválido.");
    const at = now();
    const candles = rows.map((row: unknown) => {
      if (!Array.isArray(row) || row.length < 8) throw new Error("Vela incompleta.");
      const values = row.slice(0, 8).map((v: unknown) => typeof v === "number" || (typeof v === "string" && v.trim() !== "") ? Number(v) : NaN);
      const [time, open, high, low, close, volume, closeTime, quoteVolume] = values as [number, number, number, number, number, number, number, number];
      if (!values.every(Number.isFinite) || !Number.isSafeInteger(time) || !Number.isSafeInteger(closeTime)
        || time < 0 || closeTime <= time || closeTime > 8.64e15 || Math.min(open, high, low, close) <= 0
        || low > Math.min(open, close) || high < Math.max(open, close) || volume < 0 || quoteVolume < 0) throw new Error("Vela inválida.");
      return { time, closeTime, open, high, low, close, volume, quoteVolume, complete: closeTime < at };
    });
    if (candles.some((c, i) => i > 0 && c.time <= candles[i - 1]!.time)) throw new Error("Velas fora de ordem.");
    return { symbol, interval, source: "Binance Spot", quote: "USDT", fetchedAt: new Date(at).toISOString(), candles };
  }

  return async ({ request }: { request: Request }): Promise<Response> => {
    const params = new URL(request.url).searchParams;
    const symbol = params.get("symbol") ?? "SOLUSDT", interval = params.get("interval") ?? "1m";
    if (!SYMBOLS.includes(symbol) || !INTERVALS.includes(interval)) {
      return Response.json({ error: "Moeda ou intervalo não suportado." }, { status: 400, headers: { "cache-control": "no-store" } });
    }
    const key = `${symbol}:${interval}`;
    try {
      let result = cached.get(key);
      if (!result || now() - result.at >= 10_000) {
        let job = pending.get(key);
        if (!job) {
          job = load(symbol, interval).then((body) => {
            cached.set(key, { at: now(), body });
            return body;
          }).finally(() => pending.delete(key));
          pending.set(key, job);
        }
        result = { at: now(), body: await job };
      }
      return Response.json(result.body, { headers: { "cache-control": "no-store" } });
    } catch {
      return Response.json({ error: "Não foi possível atualizar as velas da Binance. Nova tentativa em 10 segundos." }, { status: 502, headers: { "cache-control": "no-store" } });
    }
  };
}

export const onRequestGet = createMarketHandler();
