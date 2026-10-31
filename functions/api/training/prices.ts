interface TrainingPriceEnv {
  MNEME_DB: D1Database;
}

interface OpenTrainingPosition {
  trader_id: string;
  chain: string;
  token_address: string;
  quantity: number;
  cost_usd: number;
  entry_price_usd: number;
  mark_price_usd: number | null;
}

interface DexPair {
  baseToken?: { address?: string };
  priceUsd?: string | null;
  liquidity?: { usd?: number | null } | null;
}

const botIds = ["mneme-paper"];
const headers = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
const MAX_ADDRESSES_PER_REQUEST = 30;

export const onRequestGet: PagesFunction<TrainingPriceEnv> = async ({ env, request }) => {
  if (request.method !== "GET") return Response.json({ error: "Método não permitido." }, { status: 405, headers });
  try {
    const result = await env.MNEME_DB.prepare(`SELECT trader_id, chain, token_address, quantity, cost_usd, entry_price_usd, mark_price_usd
      FROM paper_training_positions WHERE trader_id = ?`).bind(...botIds).all<OpenTrainingPosition>();
    const groups = new Map<string, Set<string>>();
    for (const position of result.results) {
      const chain = position.chain.toLowerCase();
      const addresses = groups.get(chain) ?? new Set<string>();
      addresses.add(position.token_address);
      groups.set(chain, addresses);
    }

    const prices = new Map<string, number>();
    const liquidities = new Map<string, number>();
    await Promise.all([...groups].flatMap(([chain, addressSet]) => {
      const addresses = [...addressSet];
      const batches: string[][] = [];
      for (let offset = 0; offset < addresses.length; offset += MAX_ADDRESSES_PER_REQUEST) {
        batches.push(addresses.slice(offset, offset + MAX_ADDRESSES_PER_REQUEST));
      }
      return batches.map(async (batch) => {
        const url = `https://api.dexscreener.com/tokens/v1/${encodeURIComponent(chain)}/${batch.map(encodeURIComponent).join(",")}`;
        const cacheKey = new Request(url);
        let response = await caches.default.match(cacheKey);
        if (!response) {
          response = await fetch(url, { headers: { accept: "application/json" } });
          if (!response.ok) return;
          const cacheCopy = new Response(response.clone().body, {
            status: response.status,
            headers: { "content-type": "application/json", "cache-control": "public, max-age=5" },
          });
          await caches.default.put(cacheKey, cacheCopy);
        }
        const pairs = await response.json() as DexPair[];
        const wanted = new Set(batch.map((address) => address.toLowerCase()));
        for (const pair of pairs) {
          const address = pair.baseToken?.address?.toLowerCase();
          const price = Number(pair.priceUsd);
          if (!address || !wanted.has(address) || !Number.isFinite(price) || price <= 0) continue;
          const key = `${chain}:${address}`;
          const previous = prices.get(key);
          // For tokens with several pools, prefer the price from the deepest pool.
          const chosenLiquidity = pair.liquidity?.usd ?? 0;
          const oldLiquidity = liquidities.get(key) ?? -1;
          if (previous == null || chosenLiquidity > oldLiquidity) {
            prices.set(key, price);
            liquidities.set(key, chosenLiquidity);
          }
        }
      });
    }));

    const checkedAt = new Date().toISOString();
    return Response.json({
      checkedAt,
      positions: result.results.map((position) => {
        const priceUsd = prices.get(`${position.chain.toLowerCase()}:${position.token_address.toLowerCase()}`) ?? position.mark_price_usd ?? position.entry_price_usd;
        return {
          botId: position.trader_id,
          chain: position.chain,
          address: position.token_address,
          priceUsd,
          unrealizedPnlUsd: position.quantity * priceUsd - position.cost_usd,
          marketValueUsd: position.quantity * priceUsd,
        };
      }),
    }, { headers });
  } catch {
    return Response.json({ error: "Não foi possível atualizar as cotações agora." }, { status: 503, headers });
  }
};
