// Função pura, sem rota: usada por /api/training e pelos testes.
export interface TraderResultSummaryRow {
  source_trader_id: string; handle: string; closed_trades: number; wins: number; timed_trades: number; average_hold_minutes: number | null;
}

/** Quantos traders já têm acerto medido, quantos passam na regra de Configurações e quanto tempo eles ficam nas operações. */
export function summarizeTraderAccuracy(rows: TraderResultSummaryRow[], minWinRatePct: number | null, minClosedTrades: number | null) {
  const traders = rows.map((row) => ({
    trader: row.handle,
    closedTrades: row.closed_trades,
    winRatePct: row.closed_trades ? (row.wins ?? 0) / row.closed_trades * 100 : 0,
    timedTrades: row.timed_trades ?? 0,
    averageHoldMinutes: row.average_hold_minutes,
  }));
  const ruleSet = minWinRatePct != null && minClosedTrades != null;
  const sampled = traders.filter((trader) => minClosedTrades == null || trader.closedTrades >= minClosedTrades);
  const qualified = ruleSet ? sampled.filter((trader) => trader.winRatePct >= minWinRatePct) : [];
  const holdOf = (list: typeof traders) => {
    const timed = list.filter((trader) => trader.timedTrades > 0 && trader.averageHoldMinutes != null);
    const count = timed.reduce((sum, trader) => sum + trader.timedTrades, 0);
    return count ? timed.reduce((sum, trader) => sum + trader.averageHoldMinutes! * trader.timedTrades, 0) / count : null;
  };
  return {
    windowDays: 30,
    measuredTraders: traders.length,
    closedTrades: traders.reduce((sum, trader) => sum + trader.closedTrades, 0),
    withSampleTraders: sampled.length,
    qualifiedTraders: qualified.length,
    averageHoldMinutes: holdOf(traders),
    qualifiedAverageHoldMinutes: holdOf(qualified),
    top: [...sampled].sort((a, b) => b.winRatePct - a.winRatePct || b.closedTrades - a.closedTrades).slice(0, 10)
      .map((trader) => ({ ...trader, qualified: qualified.includes(trader) })),
  };
}
