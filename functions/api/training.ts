interface TrainingEnv {
  MNEME_DB: D1Database;
}

interface WalletRow {
  trader_id: string;
  trader_handle: string;
  initial_usd: number;
  cash_usd: number;
  realized_pnl_usd: number;
  fees_usd: number;
  last_rank: number | null;
  updated_at: string;
}

interface PositionRow {
  trader_id: string;
  chain: string;
  token_address: string;
  token_symbol: string;
  quantity: number;
  cost_usd: number;
  entry_price_usd: number;
  mark_price_usd: number | null;
  updated_at: string;
}

interface OrderRow {
  event_id: string;
  trader_id: string;
  trader_handle: string;
  side: "buy" | "sell";
  status: "processing" | "filled" | "skipped";
  chain: string | null;
  token_address: string | null;
  token_symbol: string | null;
  quantity: number | null;
  price_usd: number | null;
  notional_usd: number | null;
  fee_usd: number;
  realized_pnl_usd: number | null;
  reason: string | null;
  signal_at: string;
  executed_at: string;
}

const jsonHeaders = { "cache-control": "no-store", "x-content-type-options": "nosniff" };

export const onRequestGet: PagesFunction<TrainingEnv> = async ({ env, request }) => {
  if (request.method !== "GET") return Response.json({ error: "Método não permitido." }, { status: 405, headers: jsonHeaders });
  try {
    const [walletResult, positionResult, orderResult] = await Promise.all([
      env.MNEME_DB.prepare("SELECT * FROM paper_training_wallets ORDER BY realized_pnl_usd DESC").all<WalletRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_positions ORDER BY updated_at DESC LIMIT 2000").all<PositionRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_orders WHERE status != 'processing' ORDER BY executed_at DESC LIMIT 100").all<OrderRow>(),
    ]);

    const positionsByTrader = new Map<string, PositionRow[]>();
    for (const position of positionResult.results) {
      const current = positionsByTrader.get(position.trader_id) ?? [];
      current.push(position);
      positionsByTrader.set(position.trader_id, current);
    }
    const statsByTrader = new Map(walletResult.results.map((wallet) => [wallet.trader_id, { closedTrades: 0, wins: 0 }]));
    const statsResult = await env.MNEME_DB.prepare(`SELECT trader_id, COUNT(*) AS closed_trades,
      SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) AS wins
      FROM paper_training_orders WHERE side = 'sell' AND status = 'filled' AND realized_pnl_usd IS NOT NULL GROUP BY trader_id`)
      .all<{ trader_id: string; closed_trades: number; wins: number }>();
    for (const row of statsResult.results) statsByTrader.set(row.trader_id, { closedTrades: row.closed_trades, wins: row.wins });

    const wallets = walletResult.results.map((wallet) => {
      const positions = positionsByTrader.get(wallet.trader_id) ?? [];
      const marketValue = positions.reduce((sum, position) => sum + position.quantity * (position.mark_price_usd ?? position.entry_price_usd), 0);
      const unrealized = positions.reduce((sum, position) => sum + position.quantity * (position.mark_price_usd ?? position.entry_price_usd) - position.cost_usd, 0);
      const stats = statsByTrader.get(wallet.trader_id) ?? { closedTrades: 0, wins: 0 };
      return {
        trader: wallet.trader_handle,
        sourceRank: wallet.last_rank,
        initialUsd: wallet.initial_usd,
        cashUsd: wallet.cash_usd,
        marketValueUsd: marketValue,
        realizedPnlUsd: wallet.realized_pnl_usd,
        unrealizedPnlUsd: unrealized,
        totalPnlUsd: wallet.realized_pnl_usd + unrealized,
        returnPct: wallet.initial_usd > 0 ? ((wallet.cash_usd + marketValue - wallet.initial_usd) / wallet.initial_usd) * 100 : 0,
        winRatePct: stats.closedTrades ? (stats.wins / stats.closedTrades) * 100 : null,
        closedTrades: stats.closedTrades,
        openPositions: positions.length,
        updatedAt: wallet.updated_at,
      };
    }).sort((a, b) => b.totalPnlUsd - a.totalPnlUsd);

    return Response.json({
      mode: "paper",
      strategy: "Cópia individual de sinais dos traders acompanhados; sem ordens reais.",
      execution: { feeRate: 0.001, slippageRate: 0.005, buySizing: "2% do valor do sinal, entre US$ 20 e US$ 200", initialWalletUsd: 10_000 },
      generatedAt: new Date().toISOString(),
      wallets,
      positions: positionResult.results.map((position) => ({
        trader: walletResult.results.find((wallet) => wallet.trader_id === position.trader_id)?.trader_handle ?? position.trader_id,
        symbol: position.token_symbol,
        chain: position.chain,
        quantity: position.quantity,
        entryPriceUsd: position.entry_price_usd,
        markPriceUsd: position.mark_price_usd,
        costUsd: position.cost_usd,
        unrealizedPnlUsd: position.quantity * (position.mark_price_usd ?? position.entry_price_usd) - position.cost_usd,
        updatedAt: position.updated_at,
      })),
      orders: orderResult.results.map((order) => ({
        trader: order.trader_handle,
        side: order.side,
        status: order.status,
        chain: order.chain,
        symbol: order.token_symbol,
        quantity: order.quantity,
        priceUsd: order.price_usd,
        notionalUsd: order.notional_usd,
        feeUsd: order.fee_usd,
        realizedPnlUsd: order.realized_pnl_usd,
        reason: order.reason,
        executedAt: order.executed_at,
      })),
    }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "O banco do Treino Bot ainda não está pronto." }, { status: 503, headers: jsonHeaders });
  }
};
