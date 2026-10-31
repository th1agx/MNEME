// Tipos mínimos do D1 usados aqui, para o arquivo também passar no typecheck dos testes.
interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
}
interface TrainingSettingsEnv {
  MNEME_DB: { prepare(sql: string): D1Statement; batch(statements: D1Statement[]): Promise<unknown> };
}
interface Context { env: TrainingSettingsEnv; request: Request }

interface SettingsRow {
  daily_profit_target_pct: number | null;
  daily_loss_limit_pct: number | null;
}

const headers = { "cache-control": "no-store", "x-content-type-options": "nosniff" };

const view = (row: SettingsRow | null) => ({
  dailyProfitTargetPct: row?.daily_profit_target_pct ?? null,
  dailyLossLimitPct: row?.daily_loss_limit_pct ?? null,
});

/** null desliga; senão de 0,01% a `max`%, com até duas casas. */
function parsePct(value: unknown, max: number): number | null | undefined {
  if (value === null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0 || n > max || Math.round(n * 100) !== n * 100) return undefined;
  return n;
}

export const onRequestGet = async ({ env }: Context): Promise<Response> => {
  try {
    const row = await env.MNEME_DB.prepare("SELECT daily_profit_target_pct, daily_loss_limit_pct FROM paper_training_settings WHERE id = 1")
      .first<SettingsRow>();
    return Response.json(view(row), { headers });
  } catch {
    return Response.json({ error: "O banco do Treino Bot ainda não está pronto." }, { status: 503, headers });
  }
};

export const onRequestPut = async ({ env, request }: Context): Promise<Response> => {
  if (request.headers.get("x-mneme") !== "1") return Response.json({ error: "Requisição sem o cabeçalho do painel." }, { status: 403, headers });
  let body: { dailyProfitTargetPct?: unknown; dailyLossLimitPct?: unknown };
  try { body = await request.json() as typeof body; } catch {
    return Response.json({ error: "Envie as configurações em JSON." }, { status: 400, headers });
  }
  const target = parsePct(body.dailyProfitTargetPct ?? null, 1000);
  const loss = parsePct(body.dailyLossLimitPct ?? null, 100);
  const errors = [
    ...(target === undefined ? [{ path: "cloud.dailyProfitTargetPct", message: "Use um percentual maior que 0 e até 1000, com até duas casas, ou deixe em branco." }] : []),
    ...(loss === undefined ? [{ path: "cloud.dailyLossLimitPct", message: "Use um percentual maior que 0 e até 100, com até duas casas, ou deixe em branco." }] : []),
  ];
  if (errors.length) return Response.json({ errors }, { status: 400, headers });

  try {
    const now = new Date().toISOString();
    await env.MNEME_DB.batch([
      env.MNEME_DB.prepare(`INSERT INTO paper_training_settings (id, daily_profit_target_pct, daily_loss_limit_pct) VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET daily_profit_target_pct = excluded.daily_profit_target_pct, daily_loss_limit_pct = excluded.daily_loss_limit_pct`)
        .bind(target, loss),
      // Meta nova vale já hoje: a marca de "atingida" é recalculada com o resultado atual.
      env.MNEME_DB.prepare(`UPDATE paper_training_daily_metrics SET target_reached = CASE WHEN ? IS NOT NULL AND return_pct >= ? THEN 1 ELSE 0 END,
        updated_at = ? WHERE day_utc = ?`).bind(target, target, now, now.slice(0, 10)),
    ]);
    return Response.json({ settings: view({ daily_profit_target_pct: target ?? null, daily_loss_limit_pct: loss ?? null }) }, { headers });
  } catch {
    return Response.json({ error: "Não foi possível salvar no D1." }, { status: 503, headers });
  }
};
