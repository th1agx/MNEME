// Tipos mínimos do D1 usados aqui, para o arquivo também passar no typecheck dos testes.
interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
}
interface TrainingSettingsEnv {
  MNEME_DB: { prepare(sql: string): D1Statement; batch(statements: D1Statement[]): Promise<unknown> };
}
interface Context { env: TrainingSettingsEnv; request: Request }

/** O dia de operação vira à meia-noite de Brasília (UTC-3), igual ao Worker. */
const brasiliaDay = (date: Date) => new Date(date.getTime() - 3 * 60 * 60_000).toISOString().slice(0, 10);

const headers = { "cache-control": "no-store", "x-content-type-options": "nosniff" };

/**
 * Campos que o robô da nuvem lê de Configurações. Em branco = null: meta e limite ficam desligados,
 * e sem os campos da regra o robô não compra.
 */
const FIELDS = [
  { key: "dailyProfitTargetPct", column: "daily_profit_target_pct", min: 0, max: 1000, integer: false,
    message: "Use um percentual maior que 0 e até 1000, com até duas casas, ou deixe em branco." },
  { key: "dailyLossLimitPct", column: "daily_loss_limit_pct", min: 0, max: 100, integer: false,
    message: "Use um percentual maior que 0 e até 100, com até duas casas, ou deixe em branco." },
  { key: "minWinRatePct", column: "consensus_min_win_rate_pct", min: 0, max: 100, integer: false,
    message: "Use um percentual maior que 0 e até 100, com até duas casas." },
  { key: "minClosedTrades", column: "consensus_min_closed_trades", min: 0, max: 1000, integer: true,
    message: "Use um número inteiro de 1 a 1000." },
  { key: "minTraders", column: "consensus_min_traders", min: 0, max: 50, integer: true,
    message: "Use um número inteiro de 1 a 50." },
  { key: "windowMinutes", column: "consensus_window_minutes", min: 0, max: 1440, integer: true,
    message: "Use minutos inteiros de 1 a 1440." },
  { key: "orderSizePct", column: "order_size_pct", min: 0, max: 100, integer: false,
    message: "Use um percentual maior que 0 e até 100, com até duas casas." },
  { key: "minLiquidityUsd", column: "min_liquidity_usd", min: 0, max: 1_000_000_000, integer: false,
    message: "Use um valor em dólares maior que 0, ou deixe em branco para não filtrar." },
] as const;

type Row = Record<(typeof FIELDS)[number]["column"], number | null>;
const COLUMNS = FIELDS.map((field) => field.column).join(", ");

const view = (row: Partial<Row> | null) => Object.fromEntries(FIELDS.map((field) => [field.key, row?.[field.column] ?? null]));

/** null = em branco; undefined = inválido. Valores aceitos são maiores que `min`, até `max`, com até duas casas. */
function parse(value: unknown, field: (typeof FIELDS)[number]): number | null | undefined {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= field.min || n > field.max) return undefined;
  if (field.integer ? !Number.isInteger(n) : Math.round(n * 100) !== n * 100) return undefined;
  return n;
}

export const onRequestGet = async ({ env }: Context): Promise<Response> => {
  try {
    const row = await env.MNEME_DB.prepare(`SELECT ${COLUMNS} FROM paper_training_settings WHERE id = 1`).first<Row>();
    return Response.json(view(row), { headers });
  } catch {
    return Response.json({ error: "O banco do Treino Bot ainda não está pronto." }, { status: 503, headers });
  }
};

export const onRequestPut = async ({ env, request }: Context): Promise<Response> => {
  if (request.headers.get("x-mneme") !== "1") return Response.json({ error: "Requisição sem o cabeçalho do painel." }, { status: 403, headers });
  let body: Record<string, unknown>;
  try { body = await request.json() as Record<string, unknown>; } catch {
    return Response.json({ error: "Envie as configurações em JSON." }, { status: 400, headers });
  }
  const values = FIELDS.map((field) => parse(body?.[field.key], field));
  const errors = FIELDS.flatMap((field, index) => values[index] === undefined ? [{ path: `cloud.${field.key}`, message: field.message }] : []);
  if (errors.length) return Response.json({ errors }, { status: 400, headers });
  const saved = Object.fromEntries(FIELDS.map((field, index) => [field.column, values[index] ?? null])) as Row;
  const target = saved.daily_profit_target_pct;

  try {
    const now = new Date().toISOString();
    await env.MNEME_DB.batch([
      env.MNEME_DB.prepare(`INSERT INTO paper_training_settings (id, ${COLUMNS}) VALUES (1, ${FIELDS.map(() => "?").join(", ")})
        ON CONFLICT(id) DO UPDATE SET ${FIELDS.map((field) => `${field.column} = excluded.${field.column}`).join(", ")}`)
        .bind(...FIELDS.map((field) => saved[field.column])),
      // Meta nova vale já hoje: a marca de "atingida" é recalculada com o resultado atual.
      env.MNEME_DB.prepare(`UPDATE paper_training_daily_metrics SET target_reached = CASE WHEN ? IS NOT NULL AND return_pct >= ? THEN 1 ELSE 0 END,
        updated_at = ? WHERE day_utc = ?`).bind(target, target, now, brasiliaDay(new Date(now))),
    ]);
    return Response.json({ settings: view(saved) }, { headers });
  } catch {
    return Response.json({ error: "Não foi possível salvar no D1." }, { status: 503, headers });
  }
};
