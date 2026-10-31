import { ensureTables, jsonHeaders, requireAdmin, validateParams, type ParamsEnv } from "./params";

interface PresetBody {
  id?: unknown;
  name?: unknown;
  params?: unknown;
}

async function readBody(request: Request): Promise<PresetBody | null> {
  try { return await request.json() as PresetBody; } catch { return null; }
}

function cleanName(value: unknown): string | null {
  const name = typeof value === "string" ? value.trim().replace(/\s+/g, " ") : "";
  return name.length >= 2 && name.length <= 40 ? name : null;
}

const conflict = (error: unknown) => error instanceof Error && /UNIQUE/i.test(error.message)
  ? Response.json({ error: "Já existe um preset com esse nome." }, { status: 409, headers: jsonHeaders })
  : null;

export const onRequestGet: PagesFunction<ParamsEnv> = async ({ env }) => {
  try {
    await ensureTables(env.MNEME_DB);
    const rows = await env.MNEME_DB.prepare("SELECT id, name, params_json, created_at, updated_at FROM paper_training_param_presets ORDER BY name")
      .all<{ id: string; name: string; params_json: string; created_at: string; updated_at: string }>();
    return Response.json({ presets: rows.results.map((row) => ({ id: row.id, name: row.name, params: JSON.parse(row.params_json), createdAt: row.created_at, updatedAt: row.updated_at })) }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "Não foi possível carregar os presets." }, { status: 503, headers: jsonHeaders });
  }
};

export const onRequestPost: PagesFunction<ParamsEnv> = async ({ env, request }) => {
  const denied = requireAdmin(env, request);
  if (denied) return denied;
  const body = await readBody(request);
  const name = cleanName(body?.name);
  if (!name) return Response.json({ error: "Dê um nome de 2 a 40 caracteres ao preset." }, { status: 400, headers: jsonHeaders });
  const { params, error } = validateParams(body?.params);
  if (!params) return Response.json({ error }, { status: 400, headers: jsonHeaders });
  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  try {
    await ensureTables(env.MNEME_DB);
    await env.MNEME_DB.prepare("INSERT INTO paper_training_param_presets (id, name, params_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)")
      .bind(id, name, JSON.stringify(params), now, now).run();
    return Response.json({ ok: true, preset: { id, name, params, createdAt: now, updatedAt: now } }, { status: 201, headers: jsonHeaders });
  } catch (cause) {
    return conflict(cause) ?? Response.json({ error: "Não foi possível criar o preset agora." }, { status: 503, headers: jsonHeaders });
  }
};

export const onRequestPut: PagesFunction<ParamsEnv> = async ({ env, request }) => {
  const denied = requireAdmin(env, request);
  if (denied) return denied;
  const body = await readBody(request);
  const id = typeof body?.id === "string" ? body.id : "";
  const name = cleanName(body?.name);
  if (!id || !name) return Response.json({ error: "Informe o preset e um nome de 2 a 40 caracteres." }, { status: 400, headers: jsonHeaders });
  const { params, error } = validateParams(body?.params);
  if (!params) return Response.json({ error }, { status: 400, headers: jsonHeaders });
  try {
    await ensureTables(env.MNEME_DB);
    const result = await env.MNEME_DB.prepare("UPDATE paper_training_param_presets SET name = ?, params_json = ?, updated_at = ? WHERE id = ?")
      .bind(name, JSON.stringify(params), new Date().toISOString(), id).run();
    if (!result.meta.changes) return Response.json({ error: "Preset não encontrado." }, { status: 404, headers: jsonHeaders });
    return Response.json({ ok: true }, { headers: jsonHeaders });
  } catch (cause) {
    return conflict(cause) ?? Response.json({ error: "Não foi possível atualizar o preset agora." }, { status: 503, headers: jsonHeaders });
  }
};

export const onRequestDelete: PagesFunction<ParamsEnv> = async ({ env, request }) => {
  const denied = requireAdmin(env, request);
  if (denied) return denied;
  const id = new URL(request.url).searchParams.get("id") ?? "";
  if (!id) return Response.json({ error: "Informe o preset." }, { status: 400, headers: jsonHeaders });
  try {
    await ensureTables(env.MNEME_DB);
    const result = await env.MNEME_DB.prepare("DELETE FROM paper_training_param_presets WHERE id = ?").bind(id).run();
    if (!result.meta.changes) return Response.json({ error: "Preset não encontrado." }, { status: 404, headers: jsonHeaders });
    return Response.json({ ok: true }, { headers: jsonHeaders });
  } catch {
    return Response.json({ error: "Não foi possível excluir o preset agora." }, { status: 503, headers: jsonHeaders });
  }
};
