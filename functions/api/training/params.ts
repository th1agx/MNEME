export interface ParamsEnv {
  MNEME_DB: D1Database;
  TRAINING_ADMIN_KEY?: string;
}

export type BotParams = Record<string, number | boolean>;

interface ParamField {
  key: string;
  group: "entry" | "exit" | "risk";
  label: string;
  unit: "usd" | "pct" | "count" | "min" | "bool";
  min?: number;
  max?: number;
  step?: number;
}

export const jsonHeaders = { "cache-control": "no-store", "x-content-type-options": "nosniff" };
export const trainingBotIds = ["mneme-paper-conservative", "mneme-paper-risky"] as const;
const botNames: Record<string, string> = { "mneme-paper-conservative": "MNEME Conservador", "mneme-paper-risky": "MNEME Arriscado" };

export const paramFields: ParamField[] = [
  { key: "minBuyers", group: "entry", label: "Compradores mínimos", unit: "count", min: 1, max: 50, step: 1 },
  { key: "minimumBuyVolumeUsd", group: "entry", label: "Volume comprador mínimo", unit: "usd", min: 0, max: 10_000_000, step: 100 },
  { key: "minimumPressurePct", group: "entry", label: "Pressão mínima do fluxo", unit: "pct", min: 50, max: 100, step: 1 },
  { key: "minimumSingleBuyUsd", group: "entry", label: "Ordem individual de compra", unit: "usd", min: 0, max: 10_000_000, step: 500 },
  { key: "minimumSinglePressurePct", group: "entry", label: "Pressão na ordem individual", unit: "pct", min: 50, max: 100, step: 1 },
  { key: "minimumRepeatBuys", group: "entry", label: "Recompras do mesmo trader", unit: "count", min: 1, max: 20, step: 1 },
  { key: "minimumAccurateBuyers", group: "entry", label: "Traders validados exigidos", unit: "count", min: 0, max: 50, step: 1 },
  { key: "minimumAccuracySample", group: "entry", label: "Amostra mínima do trader", unit: "count", min: 1, max: 500, step: 1 },
  { key: "minimumTraderWinRatePct", group: "entry", label: "Win rate mínimo do trader", unit: "pct", min: 0, max: 100, step: 1 },
  { key: "minSellers", group: "exit", label: "Vendedores mínimos", unit: "count", min: 1, max: 50, step: 1 },
  { key: "minimumSellVolumeUsd", group: "exit", label: "Volume vendedor mínimo", unit: "usd", min: 0, max: 10_000_000, step: 100 },
  { key: "minimumSingleSellUsd", group: "exit", label: "Ordem individual de venda", unit: "usd", min: 0, max: 10_000_000, step: 500 },
  { key: "allowBatchSell", group: "exit", label: "Venda em lote", unit: "bool" },
  { key: "minimumBatchSellAssets", group: "exit", label: "Ativos na venda em lote", unit: "count", min: 2, max: 50, step: 1 },
  { key: "buySizePct", group: "risk", label: "Tamanho por entrada", unit: "pct", min: 0.1, max: 100, step: 0.1 },
  { key: "minimumLiquidityUsd", group: "risk", label: "Liquidez mínima do ativo", unit: "usd", min: 0, max: 100_000_000, step: 1_000 },
  { key: "maxAssetExposurePct", group: "risk", label: "Exposição máxima por ativo", unit: "pct", min: 1, max: 100, step: 1 },
  { key: "maxPortfolioExposurePct", group: "risk", label: "Exposição máxima total", unit: "pct", min: 1, max: 100, step: 1 },
  { key: "buyCooldownMinutes", group: "risk", label: "Cooldown por ativo", unit: "min", min: 0, max: 1_440, step: 1 },
];

// Same values the Worker uses today; they stay in effect until a saved version exists.
export const defaultParams: Record<string, BotParams> = {
  "mneme-paper-conservative": { minBuyers: 3, minSellers: 3, minimumBuyVolumeUsd: 2_500, minimumSellVolumeUsd: 2_500, minimumPressurePct: 65, minimumSingleBuyUsd: 20_000, minimumSingleSellUsd: 20_000, minimumSinglePressurePct: 75, minimumRepeatBuys: 3, minimumBatchSellAssets: 3, allowBatchSell: false, minimumAccurateBuyers: 1, minimumAccuracySample: 8, minimumTraderWinRatePct: 60, buySizePct: 2, minimumLiquidityUsd: 25_000, maxAssetExposurePct: 10, maxPortfolioExposurePct: 100, buyCooldownMinutes: 5 },
  "mneme-paper-risky": { minBuyers: 2, minSellers: 2, minimumBuyVolumeUsd: 1_000, minimumSellVolumeUsd: 1_000, minimumPressurePct: 55, minimumSingleBuyUsd: 5_000, minimumSingleSellUsd: 5_000, minimumSinglePressurePct: 55, minimumRepeatBuys: 2, minimumBatchSellAssets: 3, allowBatchSell: true, minimumAccurateBuyers: 0, minimumAccuracySample: 5, minimumTraderWinRatePct: 50, buySizePct: 4, minimumLiquidityUsd: 10_000, maxAssetExposurePct: 15, maxPortfolioExposurePct: 100, buyCooldownMinutes: 0 },
};

interface StoredParamsRow {
  bot_id: string;
  params_json: string;
  version: number;
  updated_at: string;
  applied_version: number | null;
  applied_at: string | null;
}

// The Worker reads paper_training_bot_params on each cycle and writes applied_version/applied_at once a version is in use.
export async function ensureTables(db: D1Database): Promise<void> {
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS paper_training_bot_params (
      bot_id TEXT PRIMARY KEY, params_json TEXT NOT NULL, version INTEGER NOT NULL,
      updated_at TEXT NOT NULL, applied_version INTEGER, applied_at TEXT)`),
    db.prepare(`CREATE TABLE IF NOT EXISTS paper_training_param_changes (
      id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT NOT NULL, version INTEGER NOT NULL,
      action TEXT NOT NULL, changes_json TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL)`),
    db.prepare(`CREATE TABLE IF NOT EXISTS paper_training_param_presets (
      id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, params_json TEXT NOT NULL,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL)`),
  ]);
}

export async function loadBotParams(db: D1Database) {
  const rows = (await db.prepare("SELECT * FROM paper_training_bot_params").all<StoredParamsRow>()).results;
  return trainingBotIds.map((id) => {
    const row = rows.find((item) => item.bot_id === id);
    let stored: BotParams = {};
    try { stored = row ? JSON.parse(row.params_json) as BotParams : {}; } catch { stored = {}; }
    return {
      id,
      name: botNames[id],
      params: { ...defaultParams[id], ...stored },
      defaults: defaultParams[id],
      version: row?.version ?? 0,
      updatedAt: row?.updated_at ?? null,
      appliedVersion: row?.applied_version ?? null,
      appliedAt: row?.applied_at ?? null,
    };
  });
}

export function validateParams(input: unknown): { params?: BotParams; error?: string } {
  if (!input || typeof input !== "object") return { error: "Envie os parâmetros como objeto." };
  const values = input as Record<string, unknown>;
  const params: BotParams = {};
  for (const field of paramFields) {
    const value = values[field.key];
    if (field.unit === "bool") {
      if (typeof value !== "boolean") return { error: `${field.label}: use ligado ou desligado.` };
      params[field.key] = value;
      continue;
    }
    if (typeof value !== "number" || !Number.isFinite(value)) return { error: `${field.label}: informe um número.` };
    if (value < (field.min ?? -Infinity) || value > (field.max ?? Infinity)) return { error: `${field.label}: use um valor entre ${field.min} e ${field.max}.` };
    if ((field.step ?? 1) >= 1 && !Number.isInteger(value)) return { error: `${field.label}: use um número inteiro.` };
    params[field.key] = Math.round(value * 10) / 10;
  }
  if ((params.maxAssetExposurePct as number) > (params.maxPortfolioExposurePct as number)) return { error: "A exposição por ativo não pode passar da exposição total." };
  if ((params.buySizePct as number) > (params.maxAssetExposurePct as number)) return { error: "O tamanho por entrada não pode passar da exposição máxima por ativo." };
  return { params };
}

function constantTimeEqual(left: string, right: string): boolean {
  const encoder = new TextEncoder();
  const a = encoder.encode(left);
  const b = encoder.encode(right);
  if (a.length !== b.length) return false;
  let difference = 0;
  for (let index = 0; index < a.length; index += 1) difference |= a[index] ^ b[index];
  return difference === 0;
}

/** Returns an error response when the request is not allowed to change parameters. */
export function requireAdmin(env: ParamsEnv, request: Request): Response | null {
  const adminKey = env.TRAINING_ADMIN_KEY?.trim();
  if (!adminKey || adminKey.length < 32) return Response.json({ error: "Edição desativada: configure o Secret TRAINING_ADMIN_KEY (32+ caracteres) no projeto Pages." }, { status: 503, headers: jsonHeaders });
  const authorization = request.headers.get("authorization") ?? "";
  if (!constantTimeEqual(authorization.startsWith("Bearer ") ? authorization.slice(7) : "", adminKey)) {
    return Response.json({ error: "Chave administrativa inválida." }, { status: 401, headers: jsonHeaders });
  }
  return null;
}

async function saveVersion(env: ParamsEnv, botId: string, params: BotParams, action: "update" | "reset", note: string, baseVersion: unknown) {
  const current = (await loadBotParams(env.MNEME_DB)).find((bot) => bot.id === botId)!;
  if (typeof baseVersion === "number" && baseVersion !== current.version) {
    return Response.json({ error: "Os parâmetros foram alterados em outra sessão. Recarregue antes de salvar." }, { status: 409, headers: jsonHeaders });
  }
  const changes = paramFields
    .filter((field) => current.params[field.key] !== params[field.key])
    .map((field) => ({ key: field.key, label: field.label, from: current.params[field.key], to: params[field.key] }));
  if (!changes.length) return Response.json({ ok: true, unchanged: true, version: current.version }, { headers: jsonHeaders });
  const version = current.version + 1;
  const now = new Date().toISOString();
  await env.MNEME_DB.batch([
    env.MNEME_DB.prepare(`INSERT INTO paper_training_bot_params (bot_id, params_json, version, updated_at) VALUES (?, ?, ?, ?)
      ON CONFLICT(bot_id) DO UPDATE SET params_json = excluded.params_json, version = excluded.version, updated_at = excluded.updated_at`)
      .bind(botId, JSON.stringify(params), version, now),
    env.MNEME_DB.prepare("INSERT INTO paper_training_param_changes (bot_id, version, action, changes_json, note, created_at) VALUES (?, ?, ?, ?, ?, ?)")
      .bind(botId, version, action, JSON.stringify(changes), note || null, now),
  ]);
  return Response.json({ ok: true, version, changes }, { headers: jsonHeaders });
}

const isBotId = (value: string) => trainingBotIds.includes(value as typeof trainingBotIds[number]);

export const onRequestGet: PagesFunction<ParamsEnv> = async ({ env }) => {
  try {
    await ensureTables(env.MNEME_DB);
    const [bots, history, presets] = await Promise.all([
      loadBotParams(env.MNEME_DB),
      env.MNEME_DB.prepare("SELECT bot_id, version, action, changes_json, note, created_at FROM paper_training_param_changes ORDER BY id DESC LIMIT 30")
        .all<{ bot_id: string; version: number; action: string; changes_json: string; note: string | null; created_at: string }>(),
      env.MNEME_DB.prepare("SELECT id, name, params_json, created_at, updated_at FROM paper_training_param_presets ORDER BY name")
        .all<{ id: string; name: string; params_json: string; created_at: string; updated_at: string }>(),
    ]);
    const parse = (value: string, fallback: unknown) => { try { return JSON.parse(value); } catch { return fallback; } };
    return Response.json({
      fields: paramFields,
      bots,
      editable: (env.TRAINING_ADMIN_KEY?.trim().length ?? 0) >= 32,
      presets: presets.results.map((row) => ({ id: row.id, name: row.name, params: parse(row.params_json, {}), createdAt: row.created_at, updatedAt: row.updated_at })),
      history: history.results.map((row) => ({ botId: row.bot_id, version: row.version, action: row.action, changes: parse(row.changes_json, []), note: row.note, createdAt: row.created_at })),
    }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "Não foi possível carregar os parâmetros." }, { status: 503, headers: jsonHeaders });
  }
};

export const onRequestPut: PagesFunction<ParamsEnv> = async ({ env, request }) => {
  const denied = requireAdmin(env, request);
  if (denied) return denied;
  let body: { botId?: unknown; params?: unknown; note?: unknown; baseVersion?: unknown };
  try { body = await request.json() as typeof body; } catch {
    return Response.json({ error: "Envie os parâmetros em JSON." }, { status: 400, headers: jsonHeaders });
  }
  const botId = String(body.botId ?? "");
  if (!isBotId(botId)) return Response.json({ error: "Bot inválido." }, { status: 400, headers: jsonHeaders });
  const { params, error } = validateParams(body.params);
  if (!params) return Response.json({ error }, { status: 400, headers: jsonHeaders });
  try {
    await ensureTables(env.MNEME_DB);
    return await saveVersion(env, botId, params, "update", typeof body.note === "string" ? body.note.trim().slice(0, 200) : "", body.baseVersion);
  } catch {
    return Response.json({ error: "Não foi possível salvar os parâmetros agora." }, { status: 503, headers: jsonHeaders });
  }
};

/** Restores the defaults as a new version, keeping the audit trail. */
export const onRequestDelete: PagesFunction<ParamsEnv> = async ({ env, request }) => {
  const denied = requireAdmin(env, request);
  if (denied) return denied;
  const url = new URL(request.url);
  const botId = url.searchParams.get("botId") ?? "";
  if (!isBotId(botId)) return Response.json({ error: "Bot inválido." }, { status: 400, headers: jsonHeaders });
  const baseVersion = url.searchParams.has("baseVersion") ? Number(url.searchParams.get("baseVersion")) : undefined;
  try {
    await ensureTables(env.MNEME_DB);
    return await saveVersion(env, botId, defaultParams[botId], "reset", "Padrão restaurado", baseVersion);
  } catch {
    return Response.json({ error: "Não foi possível restaurar o padrão agora." }, { status: 503, headers: jsonHeaders });
  }
};
