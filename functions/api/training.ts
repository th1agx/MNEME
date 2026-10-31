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
  trader_id: string; chain: string; token_symbol: string; pattern_type: string; score: number; action: "buy" | "sell" | "watch";
  reason: string; signal_count: number; distinct_buyers: number; distinct_sellers: number;
  buy_volume_usd: number; sell_volume_usd: number; observed_at: string;
}

const jsonHeaders = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
const trainingBotIds = ["mneme-paper-conservative", "mneme-paper-risky"] as const;

export const onRequestGet: PagesFunction<TrainingEnv> = async ({ env, request }) => {
  if (request.method !== "GET") return Response.json({ error: "Método não permitido." }, { status: 405, headers: jsonHeaders });
  try {
    const [walletResult, positionResult, orderResult, top50FlowResult] = await Promise.all([
      env.MNEME_DB.prepare("SELECT * FROM paper_training_wallets WHERE trader_id IN (?, ?)").bind(...trainingBotIds).all<WalletRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_positions WHERE trader_id IN (?, ?) ORDER BY updated_at DESC LIMIT 4000").bind(...trainingBotIds).all<PositionRow>(),
      env.MNEME_DB.prepare("SELECT * FROM paper_training_orders WHERE trader_id IN (?, ?) AND status != 'processing' ORDER BY executed_at DESC LIMIT 200").bind(...trainingBotIds).all<OrderRow>(),
      env.MNEME_DB.prepare(`SELECT COUNT(*) AS signal_count, COUNT(DISTINCT source_trader_id) AS active_traders,
        COUNT(DISTINCT CASE WHEN side = 'buy' THEN source_trader_id END) AS buyers,
        COUNT(DISTINCT CASE WHEN side = 'sell' THEN source_trader_id END) AS sellers,
        COALESCE(SUM(CASE WHEN side = 'buy' THEN amount_usd ELSE 0 END), 0) AS buy_volume_usd,
        COALESCE(SUM(CASE WHEN side = 'sell' THEN amount_usd ELSE 0 END), 0) AS sell_volume_usd
        FROM paper_training_signal_events WHERE signal_at >= ? AND source_rank BETWEEN 1 AND 50`)
        .bind(new Date(Date.now() - 5 * 60_000).toISOString()).first<{
          signal_count: number; active_traders: number; buyers: number; sellers: number; buy_volume_usd: number; sell_volume_usd: number;
        }>(),
    ]);
    const [dailyResult, incidentResult, patternResult, patternPerformanceResult, dailyHistoryResult, capitalEventResult, capitalTotalResult] = await Promise.all([
      env.MNEME_DB.prepare(`SELECT * FROM paper_training_daily_metrics
        WHERE trader_id IN (?, ?) AND day_utc = ?`).bind(...trainingBotIds, new Date().toISOString().slice(0, 10)).all<{
          trader_id: string; day_utc: string; opening_equity_usd: number; current_equity_usd: number;
          pnl_usd: number; return_pct: number; target_reached: number; updated_at: string;
        }>(),
      env.MNEME_DB.prepare(`SELECT trader_id, trader_handle, incident_type, summary, diagnostics_json, occurred_at
        FROM paper_training_incidents WHERE trader_id IN (?, ?) ORDER BY occurred_at DESC LIMIT 100`).bind(...trainingBotIds).all<{
          trader_id: string; trader_handle: string; incident_type: string; summary: string; diagnostics_json: string; occurred_at: string;
        }>(),
      env.MNEME_DB.prepare(`SELECT trader_id, chain, token_symbol, pattern_type, score, action, reason, signal_count,
        distinct_buyers, distinct_sellers, buy_volume_usd, sell_volume_usd, observed_at
        FROM paper_training_pattern_observations WHERE trader_id IN (?, ?) ORDER BY observed_at DESC LIMIT 100`).bind(...trainingBotIds).all<PatternObservationRow>(),
      env.MNEME_DB.prepare(`SELECT trader_id, entry_pattern AS pattern, COUNT(*) AS closed_trades,
        SUM(CASE WHEN realized_pnl_usd > 0 THEN 1 ELSE 0 END) AS wins,
        COALESCE(SUM(realized_pnl_usd), 0) AS realized_pnl_usd,
        COALESCE(AVG(realized_pnl_usd), 0) AS average_pnl_usd
        FROM paper_training_orders WHERE trader_id IN (?, ?) AND side = 'sell' AND status = 'filled'
          AND realized_pnl_usd IS NOT NULL AND entry_pattern IS NOT NULL GROUP BY trader_id, entry_pattern`)
        .bind(...trainingBotIds).all<{ trader_id: string; pattern: string; closed_trades: number; wins: number; realized_pnl_usd: number; average_pnl_usd: number }>(),
      env.MNEME_DB.prepare(`SELECT trader_id, day_utc, current_equity_usd, pnl_usd, return_pct, updated_at
        FROM paper_training_daily_metrics WHERE trader_id IN (?, ?) ORDER BY day_utc DESC LIMIT 60`)
        .bind(...trainingBotIds).all<{ trader_id: string; day_utc: string; current_equity_usd: number; pnl_usd: number; return_pct: number; updated_at: string }>(),
      env.MNEME_DB.prepare(`SELECT event_id, trader_id, amount_usd, created_at
        FROM paper_training_capital_events WHERE applied_at IS NOT NULL ORDER BY created_at DESC LIMIT 30`)
        .all<{ event_id: string; trader_id: string; amount_usd: number; created_at: string }>(),
      env.MNEME_DB.prepare(`SELECT trader_id, COALESCE(SUM(amount_usd), 0) AS capital_added_usd
        FROM paper_training_capital_events WHERE applied_at IS NOT NULL GROUP BY trader_id`)
        .all<{ trader_id: string; capital_added_usd: number }>(),
    ]);
    const capitalAddedByTrader = new Map(capitalTotalResult.results.map((row) => [row.trader_id, row.capital_added_usd]));
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
      FROM paper_training_orders WHERE trader_id IN (?, ?) AND side = 'sell' AND status = 'filled' AND realized_pnl_usd IS NOT NULL GROUP BY trader_id`)
      .bind(...trainingBotIds)
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
        botId: wallet.trader_id,
        trader: wallet.trader_handle,
        sourceRank: wallet.last_rank,
        initialUsd: wallet.initial_usd,
        capitalAddedUsd: capitalAddedByTrader.get(wallet.trader_id) ?? 0,
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
      strategy: "Os bots analisam o fluxo recente dos 50 traders do Top em cada ativo. Compram somente depois de confirmar volume e pressao compradora; vendas exigem confirmacao do fluxo vendedor. Historico paper positivo reforca a pontuacao quando ha amostra suficiente. Tudo em simulacao.",
      top50Flow: {
        windowMinutes: 5,
        activeTraders: top50FlowResult?.active_traders ?? 0,
        signalCount: top50FlowResult?.signal_count ?? 0,
        buyers: top50FlowResult?.buyers ?? 0,
        sellers: top50FlowResult?.sellers ?? 0,
        buyVolumeUsd: top50FlowResult?.buy_volume_usd ?? 0,
        sellVolumeUsd: top50FlowResult?.sell_volume_usd ?? 0,
      },
      execution: { feeRate: 0.001, slippageRate: 0.005, initialWalletUsd: 200_000, dailyTargetPct: 30, dailyTargetIsGoalOnly: true,
        scoreMeaning: "etiqueta de execucao, nao probabilidade de lucro" },
      paperCapital: { walletCount: walletResult.results.length, totalAllocatedUsd: walletResult.results.reduce((sum, wallet) => sum + wallet.initial_usd, 0) },
      bots: [
        { id: trainingBotIds[0], name: "MNEME Conservador", minBuyers: 3, minSellers: 3, minimumBuyVolumeUsd: 2_500, minimumSellVolumeUsd: 2_500, minimumPressurePct: 65, buySizePct: 2, minimumLiquidityUsd: 25_000, maxAssetExposurePct: 10, maxPortfolioExposurePct: 100, buyCooldownMinutes: 5 },
        { id: trainingBotIds[1], name: "MNEME Arriscado", minBuyers: 2, minSellers: 2, minimumBuyVolumeUsd: 1_000, minimumSellVolumeUsd: 1_000, minimumPressurePct: 55, buySizePct: 4, minimumLiquidityUsd: 10_000, maxAssetExposurePct: 15, maxPortfolioExposurePct: 100, buyCooldownMinutes: 0 },
      ],
      generatedAt: new Date().toISOString(),
      capitalControlReady: true,
      wallets,
      positions: positionResult.results.map((position) => ({
        botId: position.trader_id,
        trader: walletResult.results.find((wallet) => wallet.trader_id === position.trader_id)?.trader_handle ?? position.trader_id,
        symbol: position.token_symbol,
        chain: position.chain,
        address: position.token_address,
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
        botId: order.trader_id,
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
        return { botId: incident.trader_id, trader: incident.trader_handle, type: incident.incident_type, summary: incident.summary, diagnostics, occurredAt: incident.occurred_at };
      }),
      patterns: patternResult.results.map((row) => ({
        botId: row.trader_id,
        chain: row.chain, symbol: row.token_symbol, pattern: row.pattern_type, score: row.score,
        action: row.action, reason: row.reason, signalCount: row.signal_count,
        buyers: row.distinct_buyers, sellers: row.distinct_sellers,
        buyVolumeUsd: row.buy_volume_usd, sellVolumeUsd: row.sell_volume_usd, observedAt: row.observed_at,
      })),
      patternPerformance: patternPerformanceResult.results.map((row) => ({
        botId: row.trader_id,
        pattern: row.pattern, closedTrades: row.closed_trades, wins: row.wins,
        winRatePct: row.closed_trades ? row.wins / row.closed_trades * 100 : null,
        realizedPnlUsd: row.realized_pnl_usd, averagePnlUsd: row.average_pnl_usd,
      })),
      dailyHistory: dailyHistoryResult.results.map((row) => ({ botId: row.trader_id, day: row.day_utc, equityUsd: row.current_equity_usd, pnlUsd: row.pnl_usd, returnPct: row.return_pct, updatedAt: row.updated_at })),
      capitalEvents: capitalEventResult.results.map((event) => ({
        eventId: event.event_id, botId: event.trader_id, amountUsd: event.amount_usd, createdAt: event.created_at,
      })),
    }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "O banco do Treino Bot ainda não está pronto." }, { status: 503, headers: jsonHeaders });
  }
};

export const onRequestPost: PagesFunction<TrainingEnv> = async ({ env, request }) => {
  let body: { botId?: unknown; amountUsd?: unknown; eventId?: unknown };
  try { body = await request.json() as typeof body; } catch {
    return Response.json({ error: "Envie os dados do aporte em JSON." }, { status: 400, headers: jsonHeaders });
  }
  const botId = typeof body.botId === "string" ? body.botId : "";
  const amountUsd = typeof body.amountUsd === "number" ? body.amountUsd : Number(body.amountUsd);
  const eventId = typeof body.eventId === "string" ? body.eventId : "";
  if (!trainingBotIds.includes(botId as typeof trainingBotIds[number])) return Response.json({ error: "Bot inválido." }, { status: 400, headers: jsonHeaders });
  if (!Number.isFinite(amountUsd) || amountUsd < 10 || amountUsd > 1_000_000 || Math.round(amountUsd * 100) !== amountUsd * 100) {
    return Response.json({ error: "O aporte deve ser de US$ 10 a US$ 1.000.000, com até duas casas decimais." }, { status: 400, headers: jsonHeaders });
  }
  if (!/^[a-zA-Z0-9-]{20,80}$/.test(eventId)) return Response.json({ error: "Identificador do aporte inválido." }, { status: 400, headers: jsonHeaders });

  try {
    const wallet = await env.MNEME_DB.prepare("SELECT trader_id FROM paper_training_wallets WHERE trader_id = ?")
      .bind(botId).first<{ trader_id: string }>();
    if (!wallet) return Response.json({ error: "A carteira ainda não foi criada pelo Worker." }, { status: 409, headers: jsonHeaders });
    const now = new Date().toISOString();
    const results = await env.MNEME_DB.batch([
      env.MNEME_DB.prepare(`INSERT OR IGNORE INTO paper_training_capital_events (event_id, trader_id, amount_usd, created_at)
        VALUES (?, ?, ?, ?)`).bind(eventId, botId, amountUsd, now),
      env.MNEME_DB.prepare(`UPDATE paper_training_wallets SET initial_usd = initial_usd + ?, cash_usd = cash_usd + ?, updated_at = ?
        WHERE trader_id = ? AND changes() = 1`).bind(amountUsd, amountUsd, now, botId),
      env.MNEME_DB.prepare(`UPDATE paper_training_capital_events SET applied_at = ?
        WHERE event_id = ? AND applied_at IS NULL AND changes() = 1`).bind(now, eventId),
      env.MNEME_DB.prepare(`UPDATE paper_training_daily_metrics SET opening_equity_usd = opening_equity_usd + ?,
        current_equity_usd = current_equity_usd + ?, return_pct = CASE WHEN opening_equity_usd + ? > 0
          THEN pnl_usd / (opening_equity_usd + ?) * 100 ELSE 0 END, updated_at = ?
        WHERE trader_id = ? AND day_utc = ? AND changes() = 1`).bind(amountUsd, amountUsd, amountUsd, amountUsd, now, botId, now.slice(0, 10)),
    ]);
    if ((results[0]?.meta?.changes ?? 0) === 0) {
      return Response.json({ ok: true, duplicate: true, message: "Este aporte já tinha sido registrado." }, { headers: jsonHeaders });
    }
    if ((results[1]?.meta?.changes ?? 0) !== 1 || (results[2]?.meta?.changes ?? 0) !== 1) {
      return Response.json({ error: "Não foi possível aplicar o aporte à carteira." }, { status: 409, headers: jsonHeaders });
    }
    return Response.json({ ok: true, duplicate: false, botId, amountUsd, message: "Capital paper adicionado. O aporte não conta como lucro." }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "Não foi possível registrar o aporte no D1." }, { status: 503, headers: jsonHeaders });
  }
};
