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
  halted_at: string | null;
  halt_reason: string | null;
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
  entry_pattern: string | null;
  entry_score: number | null;
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
  pattern_type: string | null;
  pattern_score: number | null;
  signal_count: number | null;
  signal_volume_usd: number | null;
  entry_pattern: string | null;
}

interface PatternObservationRow {
  chain: string; token_symbol: string; pattern_type: string; score: number; action: "buy" | "sell" | "watch";
  reason: string; signal_count: number; distinct_buyers: number; distinct_sellers: number;
  buy_volume_usd: number; sell_volume_usd: number; observed_at: string;
}

const jsonHeaders = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
const trainingWalletId = "mneme-paper-bot";

export const onRequestGet: PagesFunction<TrainingEnv> = async ({ env, request }) => {
  if (request.method !== "GET") return Response.json({ error: "Método não permitido." }, { status: 405, headers: jsonHeaders });
  try {
    const [walletResult, positionResult, orderResult] = await Promise.all([
      env.MNEME_DB.prepare("SELECT * FROM paper_training_wallets WHERE trader_id = ?").bind(trainingWalletId).all<WalletRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_positions WHERE trader_id = ? ORDER BY updated_at DESC LIMIT 2000").bind(trainingWalletId).all<PositionRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_orders WHERE trader_id = ? AND status != 'processing' ORDER BY executed_at DESC LIMIT 100").bind(trainingWalletId).all<OrderRow>(),
    ]);
    const [dailyResult, incidentResult, patternResult, patternPerformanceResult] = await Promise.all([
      env.MNEME_DB.prepare(`SELECT * FROM paper_training_daily_metrics
        WHERE trader_id = ? AND day_utc = ?`).bind(trainingWalletId, new Date().toISOString().slice(0, 10)).all<{
          trader_id: string; day_utc: string; opening_equity_usd: number; current_equity_usd: number;
          pnl_usd: number; return_pct: number; target_reached: number; updated_at: string;
        }>(),
      env.MNEME_DB.prepare(`SELECT trader_handle, incident_type, summary, diagnostics_json, occurred_at
        FROM paper_training_incidents WHERE trader_id = ? ORDER BY occurred_at DESC LIMIT 50`).bind(trainingWalletId).all<{
          trader_handle: string; incident_type: string; summary: string; diagnostics_json: string; occurred_at: string;
        }>(),
      env.MNEME_DB.prepare(`SELECT chain, token_symbol, pattern_type, score, action, reason, signal_count,
        distinct_buyers, distinct_sellers, buy_volume_usd, sell_volume_usd, observed_at
        FROM paper_training_pattern_observations ORDER BY observed_at DESC LIMIT 50`).all<PatternObservationRow>(),
      env.MNEME_DB.prepare(`SELECT entry_pattern AS pattern, COUNT(*) AS closed_trades,
        SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) AS wins,
        COALESCE(SUM(realized_pnl_usd), 0) AS realized_pnl_usd,
        COALESCE(AVG(realized_pnl_usd), 0) AS average_pnl_usd
        FROM paper_training_orders WHERE trader_id = ? AND side = 'sell' AND status = 'filled'
          AND realized_pnl_usd IS NOT NULL AND entry_pattern IS NOT NULL GROUP BY entry_pattern`)
        .bind(trainingWalletId).all<{ pattern: string; closed_trades: number; wins: number; realized_pnl_usd: number; average_pnl_usd: number }>(),
    ]);
    const dailyByTrader = new Map(dailyResult.results.map((row) => [row.trader_id, row]));

    const positionsByTrader = new Map<string, PositionRow[]>();
    for (const position of positionResult.results) {
      const current = positionsByTrader.get(position.trader_id) ?? [];
      current.push(position);
      positionsByTrader.set(position.trader_id, current);
    }
    const statsByTrader = new Map(walletResult.results.map((wallet) => [wallet.trader_id, { closedTrades: 0, wins: 0 }]));
    const statsResult = await env.MNEME_DB.prepare(`SELECT trader_id, COUNT(*) AS closed_trades,
      SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) AS wins
      FROM paper_training_orders WHERE trader_id = ? AND side = 'sell' AND status = 'filled' AND realized_pnl_usd IS NOT NULL GROUP BY trader_id`)
      .bind(trainingWalletId)
      .all<{ trader_id: string; closed_trades: number; wins: number }>();
    for (const row of statsResult.results) statsByTrader.set(row.trader_id, { closedTrades: row.closed_trades, wins: row.wins });

    const wallets = walletResult.results.map((wallet) => {
      const positions = positionsByTrader.get(wallet.trader_id) ?? [];
      const marketValue = positions.reduce((sum, position) => sum + position.quantity * (position.mark_price_usd ?? position.entry_price_usd), 0);
      const unrealized = positions.reduce((sum, position) => sum + position.quantity * (position.mark_price_usd ?? position.entry_price_usd) - position.cost_usd, 0);
      const stats = statsByTrader.get(wallet.trader_id) ?? { closedTrades: 0, wins: 0 };
      const daily = dailyByTrader.get(wallet.trader_id);
      const equity = wallet.cash_usd + marketValue;
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
        equityUsd: equity,
        dailyPnlUsd: daily?.pnl_usd ?? 0,
        dailyReturnPct: daily?.return_pct ?? 0,
        dailyTargetReached: daily?.target_reached === 1,
        dailyTargetProgressPct: daily ? Math.max(0, Math.min(100, daily.return_pct / 30 * 100)) : 0,
        haltedAt: wallet.halted_at,
        haltReason: wallet.halt_reason,
        winRatePct: stats.closedTrades ? (stats.wins / stats.closedTrades) * 100 : null,
        closedTrades: stats.closedTrades,
        openPositions: positions.length,
        updatedAt: wallet.updated_at,
      };
    }).sort((a, b) => b.totalPnlUsd - a.totalPnlUsd);

    return Response.json({
      mode: "paper",
      strategy: "Uma carteira paper agrega sinais recentes, confirma padroes de fluxo e opera so acima dos limites definidos; sem ordens reais.",
      execution: { feeRate: 0.001, slippageRate: 0.005, initialWalletUsd: 200_000, dailyTargetPct: 30, dailyTargetIsGoalOnly: true,
        patternWindowMinutes: 5, largeSignalUsd: 5_000, crowdMinimumTraders: 3, crowdMinimumVolumeUsd: 2_500,
        minimumLiquidityUsd: 10_000, buyCooldownMinutes: 15, maxAssetExposurePct: 2, maxPortfolioExposurePct: 25,
        buySizingByScore: "0.5% entre 70-74; 1% entre 75-84; 1.5% a partir de 85",
        scoreMeaning: "forca heuristica das regras, nao probabilidade de lucro" },
      paperCapital: { walletCount: walletResult.results.length, totalAllocatedUsd: walletResult.results.reduce((sum, wallet) => sum + wallet.initial_usd, 0) },
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
        entryPattern: position.entry_pattern,
        entryScore: position.entry_score,
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
        patternType: order.pattern_type,
        patternScore: order.pattern_score,
        signalCount: order.signal_count,
        signalVolumeUsd: order.signal_volume_usd,
        entryPattern: order.entry_pattern,
        reason: order.reason,
        executedAt: order.executed_at,
      })),
      incidents: incidentResult.results.map((incident) => {
        let diagnostics: unknown = null;
        try { diagnostics = JSON.parse(incident.diagnostics_json); } catch { diagnostics = null; }
        return { trader: incident.trader_handle, type: incident.incident_type, summary: incident.summary, diagnostics, occurredAt: incident.occurred_at };
      }),
      patterns: patternResult.results.map((row) => ({
        chain: row.chain, symbol: row.token_symbol, pattern: row.pattern_type, score: row.score,
        action: row.action, reason: row.reason, signalCount: row.signal_count,
        buyers: row.distinct_buyers, sellers: row.distinct_sellers,
        buyVolumeUsd: row.buy_volume_usd, sellVolumeUsd: row.sell_volume_usd, observedAt: row.observed_at,
      })),
      patternPerformance: patternPerformanceResult.results.map((row) => ({
        pattern: row.pattern, closedTrades: row.closed_trades, wins: row.wins,
        winRatePct: row.closed_trades ? row.wins / row.closed_trades * 100 : null,
        realizedPnlUsd: row.realized_pnl_usd, averagePnlUsd: row.average_pnl_usd,
      })),
    }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "O banco do Treino Bot ainda não está pronto." }, { status: 503, headers: jsonHeaders });
  }
};
