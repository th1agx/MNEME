// Editor de parâmetros do Treino Bot: lê e grava em /api/training/params e /api/training/presets.
const paramsDialog = document.querySelector("#paramsDialog");
const paramsGroupNames = { entry: "Entrada", exit: "Saída", risk: "Risco" };
const paramsUnitSuffix = { usd: "US$", pct: "%", min: "min", count: "" };
const paramsKeyStorage = "mneme-training-admin-key";
let paramsState = null;
let paramsBotId = null;
let paramsDraft = {};
let paramsPresetId = "";
let paramsDeleteArmed = false;

const paramsEl = (id) => document.querySelector(`#${id}`);
const paramsFormat = (value, unit) => {
  if (unit === "bool") return value ? "Ligado" : "Desligado";
  if (unit === "usd") return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
  if (unit === "pct") return `${Number(value).toLocaleString("pt-BR")}%`;
  if (unit === "min") return value > 0 ? `${value} min` : "Desligado";
  return Number(value).toLocaleString("pt-BR");
};
const paramsTime = (value) => value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";

function readKey() {
  try { return sessionStorage.getItem(paramsKeyStorage) ?? ""; } catch { return ""; }
}
function storeKey(value) {
  try { value ? sessionStorage.setItem(paramsKeyStorage, value) : sessionStorage.removeItem(paramsKeyStorage); } catch { /* sessão sem storage */ }
}

function setParamsMessage(text, kind = "") {
  const message = paramsEl("paramsMessage");
  message.textContent = text;
  message.className = `capital-message ${kind}`;
}

async function paramsRequest(method, path, body) {
  const key = paramsEl("paramsKey").value.trim();
  const response = await fetch(path, {
    method,
    headers: { accept: "application/json", ...(body ? { "content-type": "application/json" } : {}), ...(key ? { authorization: `Bearer ${key}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error ?? "Não foi possível concluir a operação.");
  if (key) storeKey(key);
  return result;
}

const currentBot = () => paramsState?.bots.find((bot) => bot.id === paramsBotId);

function applyStatus(bot) {
  if (!bot.version) return "Usando o padrão do robô";
  const saved = `Versão ${bot.version} salva em ${paramsTime(bot.updatedAt)}`;
  if (bot.appliedVersion === bot.version) return `${saved} · aplicada pelo robô em ${paramsTime(bot.appliedAt)}`;
  return `${saved} · aguardando o robô aplicar`;
}

function renderParamsSummary() {
  const note = paramsEl("paramsVersionNote");
  if (!paramsState) return;
  note.textContent = paramsState.bots.map((bot) => `${bot.name.replace("MNEME ", "")}: ${bot.version ? `v${bot.version}${bot.appliedVersion === bot.version ? "" : " (pendente)"}` : "padrão"}`).join(" · ");
}

function renderParamsEditor() {
  const bot = currentBot();
  if (!bot) return;
  paramsEl("paramsBotTabs").innerHTML = paramsState.bots.map((item) => `<button type="button" data-bot-id="${safe(item.id)}" aria-pressed="${item.id === paramsBotId}">${safe(item.name)}</button>`).join("");
  paramsEl("paramsStatus").textContent = applyStatus(bot);
  paramsEl("paramsFields").innerHTML = Object.entries(paramsGroupNames).map(([group, title]) => `<fieldset class="params-group"><legend>${title}</legend>${
    paramsState.fields.filter((field) => field.group === group).map((field) => {
      const value = paramsDraft[field.key];
      const changed = value !== bot.params[field.key];
      const custom = value !== bot.defaults[field.key];
      const input = field.unit === "bool"
        ? `<label class="params-toggle"><input type="checkbox" data-key="${field.key}" ${value ? "checked" : ""}><span>${value ? "Ligado" : "Desligado"}</span></label>`
        : `<div class="params-input">${field.unit === "usd" ? "<span>US$</span>" : ""}<input type="number" inputmode="decimal" data-key="${field.key}" value="${value}" min="${field.min}" max="${field.max}" step="${field.step}" required>${field.unit !== "usd" && paramsUnitSuffix[field.unit] ? `<span>${paramsUnitSuffix[field.unit]}</span>` : ""}</div>`;
      return `<div class="params-field ${changed ? "changed" : ""}"><span class="params-label">${safe(field.label)}${custom ? '<em>personalizado</em>' : ""}</span>${input}<small>Padrão ${safe(paramsFormat(bot.defaults[field.key], field.unit))}${field.unit !== "bool" ? ` · ${safe(paramsFormat(field.min, field.unit))} a ${safe(paramsFormat(field.max, field.unit))}` : ""}</small></div>`;
    }).join("")
  }</fieldset>`).join("");
  renderParamsDiff();
  const presets = paramsState.presets ?? [];
  paramsEl("presetSelect").innerHTML = `<option value="">Presets salvos (${presets.length})</option>${presets.map((preset) => `<option value="${safe(preset.id)}" ${preset.id === paramsPresetId ? "selected" : ""}>${safe(preset.name)}</option>`).join("")}`;
  ["presetLoad", "presetUpdate", "presetDelete"].forEach((id) => { paramsEl(id).disabled = !paramsPresetId; });
  paramsEl("presetDelete").textContent = paramsDeleteArmed ? "Confirmar exclusão" : "Excluir";
  const history = (paramsState.history ?? []).filter((item) => item.botId === paramsBotId);
  paramsEl("paramsHistory").innerHTML = history.length ? history.map((item) => `<li><b>v${item.version}</b> · ${paramsTime(item.createdAt)}${item.action === "reset" ? " · padrão restaurado" : ""}${item.note && item.action !== "reset" ? ` · ${safe(item.note)}` : ""}<span>${(item.changes ?? []).map((change) => {
    const field = paramsState.fields.find((entry) => entry.key === change.key);
    return `${safe(change.label)}: ${safe(paramsFormat(change.from, field?.unit))} → ${safe(paramsFormat(change.to, field?.unit))}`;
  }).join(" · ")}</span></li>`).join("") : "<li>Nenhuma alteração registrada.</li>";
  paramsEl("paramsSave").disabled = !paramsState.editable;
  paramsEl("paramsReset").disabled = !paramsState.editable || !bot.version;
  if (!paramsState.editable) setParamsMessage("Edição desativada: configure o Secret TRAINING_ADMIN_KEY (32+ caracteres) no projeto Pages.", "error");
}

function renderParamsDiff() {
  const bot = currentBot();
  const changes = paramsState.fields.filter((field) => paramsDraft[field.key] !== bot.params[field.key]);
  paramsEl("paramsDiff").innerHTML = changes.length
    ? `<b>${changes.length} ${changes.length === 1 ? "alteração" : "alterações"}:</b> ${changes.map((field) => `${safe(field.label)} ${safe(paramsFormat(bot.params[field.key], field.unit))} → <b>${safe(paramsFormat(paramsDraft[field.key], field.unit))}</b>`).join(" · ")}`
    : "Nenhuma alteração pendente.";
  paramsEl("paramsSave").textContent = changes.length ? `Salvar v${bot.version + 1}` : "Salvar";
}

async function loadParams(keepDraft = false) {
  const response = await fetch("/api/training/params", { headers: { accept: "application/json" }, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? "Não foi possível carregar os parâmetros.");
  paramsState = data;
  if (!paramsBotId || !data.bots.some((bot) => bot.id === paramsBotId)) paramsBotId = data.bots[0]?.id;
  if (!keepDraft) paramsDraft = { ...currentBot().params };
  if (paramsPresetId && !data.presets.some((preset) => preset.id === paramsPresetId)) paramsPresetId = "";
  renderParamsSummary();
}

async function openParams() {
  paramsBotId = typeof selectedBotId === "string" ? selectedBotId : paramsBotId;
  paramsEl("paramsKey").value = readKey();
  setParamsMessage("");
  paramsDeleteArmed = false;
  try {
    await loadParams();
    renderParamsEditor();
    paramsDialog.showModal();
  } catch (error) {
    paramsEl("paramsVersionNote").textContent = error.message;
  }
}

const presetById = () => paramsState?.presets.find((preset) => preset.id === paramsPresetId);
const presetName = () => paramsEl("presetName").value.trim();

async function runParamsAction(action, success) {
  setParamsMessage("Salvando…");
  try {
    const result = await action();
    await loadParams();
    renderParamsEditor();
    setParamsMessage(typeof success === "function" ? success(result) : success, "success");
    if (typeof refresh === "function") void refresh();
  } catch (error) {
    setParamsMessage(error instanceof Error ? error.message : "Não foi possível concluir a operação.", "error");
  }
}

paramsEl("openParams").addEventListener("click", () => void openParams());
paramsEl("closeParams").addEventListener("click", () => paramsDialog.close());
paramsEl("paramsCancel").addEventListener("click", () => paramsDialog.close());
paramsEl("paramsBotTabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-bot-id]");
  if (!button) return;
  paramsBotId = button.dataset.botId;
  paramsDraft = { ...currentBot().params };
  setParamsMessage("");
  renderParamsEditor();
});
paramsEl("paramsFields").addEventListener("input", (event) => {
  const input = event.target.closest("[data-key]");
  if (!input) return;
  paramsDraft[input.dataset.key] = input.type === "checkbox" ? input.checked : input.value === "" ? NaN : Number(input.value);
  const field = input.closest(".params-field");
  field.classList.toggle("changed", paramsDraft[input.dataset.key] !== currentBot().params[input.dataset.key]);
  if (input.type === "checkbox") input.nextElementSibling.textContent = input.checked ? "Ligado" : "Desligado";
  renderParamsDiff();
});
paramsEl("paramsForm").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!paramsEl("paramsForm").reportValidity()) return;
  const bot = currentBot();
  void runParamsAction(
    () => paramsRequest("PUT", "/api/training/params", { botId: bot.id, params: paramsDraft, baseVersion: bot.version, note: paramsEl("paramsNote").value }),
    (result) => result.unchanged ? "Nada mudou; a versão atual foi mantida." : `Versão ${result.version} salva. Fica pendente até o robô confirmar que aplicou.`,
  ).then(() => { paramsEl("paramsNote").value = ""; });
});
paramsEl("paramsReset").addEventListener("click", () => {
  const bot = currentBot();
  void runParamsAction(() => paramsRequest("DELETE", `/api/training/params?botId=${encodeURIComponent(bot.id)}&baseVersion=${bot.version}`), "Padrão restaurado como nova versão.");
});
paramsEl("presetSelect").addEventListener("change", (event) => {
  paramsPresetId = event.target.value;
  paramsDeleteArmed = false;
  paramsEl("presetName").value = presetById()?.name ?? "";
  renderParamsEditor();
});
paramsEl("presetLoad").addEventListener("click", () => {
  const preset = presetById();
  if (!preset) return;
  paramsDraft = { ...currentBot().params, ...preset.params };
  renderParamsEditor();
  setParamsMessage(`Preset "${preset.name}" carregado no formulário. Revise e salve para aplicar.`);
});
paramsEl("presetSave").addEventListener("click", () => {
  if (presetName().length < 2) return setParamsMessage("Digite um nome para o preset.", "error");
  void runParamsAction(async () => {
    const result = await paramsRequest("POST", "/api/training/presets", { name: presetName(), params: paramsDraft });
    paramsPresetId = result.preset.id;
    return result;
  }, (result) => `Preset "${result.preset.name}" criado.`).then(() => { paramsDraft = { ...paramsDraft }; });
});
paramsEl("presetUpdate").addEventListener("click", () => {
  const preset = presetById();
  if (!preset) return;
  void runParamsAction(() => paramsRequest("PUT", "/api/training/presets", { id: preset.id, name: presetName() || preset.name, params: paramsDraft }), "Preset atualizado com os valores do formulário.");
});
paramsEl("presetDelete").addEventListener("click", () => {
  const preset = presetById();
  if (!preset) return;
  if (!paramsDeleteArmed) {
    paramsDeleteArmed = true;
    paramsEl("presetDelete").textContent = "Confirmar exclusão";
    return;
  }
  paramsDeleteArmed = false;
  void runParamsAction(async () => {
    await paramsRequest("DELETE", `/api/training/presets?id=${encodeURIComponent(preset.id)}`);
    paramsPresetId = "";
    paramsEl("presetName").value = "";
  }, `Preset "${preset.name}" excluído.`);
});
loadParams().catch(() => { paramsEl("paramsVersionNote").textContent = ""; });
