// Tela de configuração: formulário gerado a partir de uma descrição dos campos.
// A validação de verdade acontece no servidor (mesmo schema do domínio); aqui só exibimos os erros.

const SECTIONS = [
  {
    title: "Modo de execução",
    text: "O que o bot faz quando um sinal passa em todas as regras.",
    fields: [
      { path: "execution.mode", label: "Modo", type: "segmented", full: true, options: [["suggest", "Só sugestões"], ["paper", "Simulado"], ["live", "Dinheiro real"]],
        hint: "Só sugestões: mostra e alerta. Simulado: opera numa carteira de mentira para medir a estratégia. Dinheiro real: compra e vende sozinho na sua carteira Solana dedicada." },
      { path: "execution.paperStartingBalanceUsd", label: "Saldo inicial da carteira simulada", type: "number", suffix: "US$", min: 0 },
    ],
  },
  {
    title: "Quem acompanhar",
    text: "Ranking usado para escolher os traders copiados.",
    fields: [
      { path: "leaderboard.window", label: "Período do ranking", type: "select", options: [["24h", "24 horas"], ["7d", "7 dias"], ["30d", "30 dias"], ["all", "Desde sempre"]] },
      { path: "leaderboard.topN", label: "Quantos traders do topo", type: "number", min: 1, max: 50 },
      { path: "leaderboard.refreshMinutes", label: "Atualizar o ranking a cada", type: "number", suffix: "min", min: 1,
        hint: "Cada consulta ao ranking gasta créditos do provedor de sinais." },
    ],
  },
  {
    title: "Quando entrar",
    text: "O sinal só vira compra se passar em todas estas regras.",
    fields: [
      { path: "entry.minScore", label: "Score mínimo", type: "number", suffix: "/100", min: 0, max: 100, calibration: true,
        hint: "Score de confiança (0 a 100) somando ranking, histórico do trader, consenso, velocidade, liquidez e se o preço já disparou. Não é probabilidade: a taxa de acerto real aparece abaixo conforme o bot opera." },
      { path: "entry.requireConsensus", label: "Só entrar com consenso", type: "check", full: true,
        hint: "Exige que outros traders do Top tenham comprado o mesmo token na janela abaixo." },
      { path: "entry.consensusMinTraders", label: "Traders para consenso", type: "number", min: 2 },
      { path: "entry.consensusWindowMinutes", label: "Janela do consenso", type: "number", suffix: "min", min: 1 },
      { path: "entry.maxLatencySeconds", label: "Atraso máximo do sinal", type: "number", suffix: "s", min: 1,
        hint: "Conta desde a operação do trader na blockchain. Sinais que chegam depois disso são ignorados." },
      { path: "entry.signalTtlSeconds", label: "Validade da sugestão", type: "number", suffix: "s", min: 5,
        hint: "No modo sugestões, quanto tempo o sinal fica ativo na tela." },
      { path: "entry.minLiquidityUsd", label: "Liquidez mínima do token", type: "number", suffix: "US$", min: 0,
        hint: "Evita tokens onde a própria compra mexe muito no preço. 0 desliga." },
      { path: "entry.maxPriceChange5mPct", label: "Não entrar se já subiu mais de", type: "number", suffix: "% 5min", min: 0 },
      { path: "entry.allowedChains", label: "Redes permitidas", type: "list", full: true,
        hint: "Separe por vírgula. A execução real hoje só opera em solana." },
    ],
  },
  {
    title: "Quanto apostar",
    text: "Tamanho de cada compra, antes dos limites de risco.",
    fields: [
      { path: "sizing.mode", label: "Como calcular", type: "segmented", full: true,
        options: [["fixed", "Valor fixo"], ["percentOfBalance", "% do saldo"], ["proportionalToTrader", "% da operação do trader"]] },
      { path: "sizing.fixedUsd", label: "Valor fixo por compra", type: "number", suffix: "US$", min: 0, showIf: (s) => s.sizing.mode === "fixed" },
      { path: "sizing.percentOfBalance", label: "Percentual do saldo livre", type: "number", suffix: "%", min: 0, max: 100, showIf: (s) => s.sizing.mode === "percentOfBalance" },
      { path: "sizing.proportionalPct", label: "Percentual da operação do trader", type: "number", suffix: "%", min: 0, max: 100, showIf: (s) => s.sizing.mode === "proportionalToTrader",
        hint: "Ex.: 1% de uma compra de US$ 5.000 do trader = US$ 50." },
      { path: "sizing.minOrderUsd", label: "Mínimo por ordem", type: "number", suffix: "US$", min: 0, hint: "Abaixo disso a compra não é feita." },
      { path: "sizing.maxOrderUsd", label: "Máximo por ordem", type: "number", suffix: "US$", min: 0 },
    ],
  },
  {
    title: "Limites de risco",
    text: "Travas que valem para qualquer sinal, inclusive com consenso.",
    fields: [
      { path: "limits.maxOpenPositions", label: "Posições abertas ao mesmo tempo", type: "number", min: 1 },
      { path: "limits.maxExposureUsd", label: "Exposição total máxima", type: "number", suffix: "US$", min: 0 },
      { path: "limits.maxPerTokenUsd", label: "Máximo em um mesmo token", type: "number", suffix: "US$", min: 0 },
      { path: "limits.dailyLossLimitUsd", label: "Parar de comprar se perder no dia", type: "number", suffix: "US$", min: 0 },
      { path: "limits.dailyProfitTargetUsd", label: "Parar de comprar ao ganhar no dia", type: "number", suffix: "US$", min: 0, nullable: true,
        hint: "Meta do dia: ao atingir, o bot não abre novas posições até amanhã. As vendas e os stops continuam. Em branco desliga." },
      { path: "limits.slippageBps", label: "Slippage máximo", type: "number", suffix: "bps", min: 1,
        hint: "Vale para compras. 100 bps = 1%. No modo real, a compra é recusada antes de assinar se a cotação vier pior que isso." },
      { path: "limits.exitSlippageBps", label: "Slippage máximo nas vendas", type: "number", suffix: "bps", min: 1,
        hint: "Maior que o de compra de propósito: um stop precisa executar mesmo com o preço caindo rápido. 1000 bps = 10%." },
      { path: "limits.maxConsecutiveFailures", label: "Pausar entradas após falhas seguidas", type: "number", min: 1,
        hint: "Disjuntor: depois de tantas ordens com erro em sequência, o bot para de comprar e avisa." },
      { path: "limits.paperFeeUsd", label: "Taxa por ordem (simulado)", type: "number", suffix: "US$", min: 0, step: "0.01" },
    ],
  },
  {
    title: "Quando sair",
    text: "O bot vende quando a primeira destas condições acontecer. Deixe em branco para desligar.",
    fields: [
      { path: "exit.followTraderExit", label: "Vender quando o trader copiado vender", type: "check", full: true },
      { path: "exit.followTraderMode", label: "Quanto vender junto", type: "segmented", full: true, options: [["proportional", "Mesma fração do trader"], ["all", "Tudo"]],
        showIf: (s) => s.exit.followTraderExit,
        hint: "Mesma fração: se o trader vender 25% da posição dele, o bot vende 25% da sua. Quando o feed não informa a fração, vende tudo." },
      { path: "exit.takeProfitPct", label: "Alvo de lucro", type: "number", suffix: "%", min: 0, nullable: true },
      { path: "exit.stopLossPct", label: "Stop de perda", type: "number", suffix: "%", min: 0, nullable: true },
      { path: "exit.trailingStopPct", label: "Stop móvel", type: "number", suffix: "%", min: 0, nullable: true,
        hint: "Vende se cair esse percentual a partir da máxima desde a compra." },
      { path: "exit.maxHoldMinutes", label: "Tempo máximo na posição", type: "number", suffix: "min", min: 1, nullable: true },
      { path: "monitor.priceRefreshSeconds", label: "Checar preços a cada", type: "number", suffix: "s", min: 5 },
    ],
  },
];

let current = null, defaults = null, liveAvailable = false, calibration = null;

const get = (obj, path) => path.split(".").reduce((o, k) => o?.[k], obj);
function set(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => o[k], obj)[last] = value;
}
const fieldId = (path) => "f-" + path.replace(/\./g, "-");

function control(f, value) {
  const id = fieldId(f.path);
  if (f.type === "check") {
    return `<label class="check"><input type="checkbox" id="${id}" data-path="${f.path}" ${value ? "checked" : ""}><span><b>${esc(f.label)}</b>${f.hint ? `<br><span class="hint">${esc(f.hint)}</span>` : ""}</span></label>`;
  }
  if (f.type === "segmented") {
    return `<div class="segmented" role="radiogroup" aria-labelledby="${id}-l">${f.options.map(([v, l]) => {
      const disabled = f.path === "execution.mode" && v === "live" && !liveAvailable;
      return `<label title="${disabled ? "Defina LIVE_TRADING=on e SOLANA_PRIVATE_KEY no .env e reinicie" : ""}" style="${disabled ? "opacity:.45;cursor:not-allowed" : ""}">
        <input type="radio" name="${id}" value="${v}" data-path="${f.path}" ${value === v ? "checked" : ""} ${disabled ? "disabled" : ""}><span>${esc(l)}</span></label>`;
    }).join("")}</div>`;
  }
  if (f.type === "select") {
    return `<select id="${id}" data-path="${f.path}">${f.options.map(([v, l]) => `<option value="${v}" ${value === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  }
  if (f.type === "list") {
    return `<input type="text" id="${id}" data-path="${f.path}" data-list value="${esc((value ?? []).join(", "))}">`;
  }
  const input = `<input type="number" inputmode="decimal" id="${id}" data-path="${f.path}" ${f.nullable ? "data-nullable" : ""}
    value="${value ?? ""}" ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""} step="${f.step ?? "any"}" ${f.nullable ? `placeholder="desligado"` : ""}>`;
  return f.suffix ? `<div class="suffix">${input}<span>${esc(f.suffix)}</span></div>` : input;
}

function calibrationHint() {
  if (!calibration) return "";
  const at = calibration.atMinScore;
  const min = current.entry.minScore;
  return at.trades
    ? `<span class="hint">Na sua história, sinais com score ${min} ou mais acertaram <b class="${at.winRate >= 0.5 ? "up" : "down"}">${Math.round(at.winRate * 100)}%</b> em ${at.trades} operações encerradas.</span>`
    : `<span class="hint">Ainda não há operações encerradas com score ${min} ou mais para medir o acerto. Rode no simulado para calibrar antes de usar dinheiro real.</span>`;
}

function render() {
  $("sections").innerHTML = SECTIONS.map((sec) => `
    <section class="pane form-section">
      <header><h2>${esc(sec.title)}</h2><p>${esc(sec.text)}</p></header>
      <div class="fields">
        ${sec.fields.filter((f) => !f.showIf || f.showIf(current)).map((f) => `
          <div class="field ${f.full ? "full" : ""}" data-field="${f.path}">
            ${f.type === "check" ? "" : `<label id="${fieldId(f.path)}-l" for="${fieldId(f.path)}">${esc(f.label)}</label>`}
            ${control(f, get(current, f.path))}
            ${f.type !== "check" && f.hint ? `<span class="hint">${esc(f.hint)}</span>` : ""}
            ${f.calibration ? `<span data-calib>${calibrationHint()}</span>` : ""}
            <span class="err" data-err></span>
          </div>`).join("")}
        ${sec.title === "Modo de execução" ? liveCallout() : ""}
      </div>
    </section>`).join("");
  $("modeBadge").innerHTML = modeBadge(current.execution.mode);
}

function liveCallout() {
  if (!liveAvailable) {
    return `<div class="field full"><div class="callout">Dinheiro real está bloqueado. Para liberar: crie uma carteira Solana nova só para o bot, coloque pouco saldo, defina <b>SOLANA_PRIVATE_KEY</b> e <b>LIVE_TRADING=on</b> no <b>.env</b> e reinicie o MNEME.</div></div>`;
  }
  if (current.execution.mode !== "live") return "";
  return `<div class="field full"><div class="callout live">Proteção do modo real: cada compra fica limitada a 10% do capital de referência. Ao atingir perda acumulada de 10%, novas compras param e a trava fica salva mesmo após reiniciar; vendas continuam liberadas. Use uma carteira Solana dedicada ao bot.</div>
    <label class="check" style="margin-top:8px"><input type="checkbox" id="liveAck"><span>Entendo que operações reais podem dar prejuízo e quero ativar o modo dinheiro real.</span></label></div>`;
}

/** Lê o formulário para o objeto atual (sem enviar). */
function readForm() {
  const next = structuredClone(current);
  for (const el of $("form").querySelectorAll("[data-path]")) {
    const path = el.dataset.path;
    if (el.type === "radio") { if (el.checked) set(next, path, el.value); continue; }
    if (el.type === "checkbox") { set(next, path, el.checked); continue; }
    if (el.dataset.list !== undefined) { set(next, path, el.value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean)); continue; }
    if (el.tagName === "SELECT") { set(next, path, el.value); continue; }
    const raw = el.value.trim().replace(",", ".");
    set(next, path, raw === "" ? (el.dataset.nullable !== undefined ? null : NaN) : Number(raw));
  }
  return next;
}

$("form").addEventListener("change", (ev) => {
  // Campos que mudam o que aparece (modo, forma de calcular) redesenham a página.
  current = readForm();
  if (ev.target.type === "radio" || ev.target.type === "checkbox" || ev.target.dataset.path === "entry.minScore") {
    const focus = ev.target.dataset.path;
    render();
    document.querySelector(`[data-path="${focus}"]:checked, #${fieldId(focus)}`)?.focus();
  }
  $("msg").textContent = "Alterações não salvas.";
  $("msg").className = "msg";
});

$("defaults").addEventListener("click", () => {
  const mode = current.execution.mode;
  current = structuredClone(defaults);
  current.execution.mode = mode === "live" ? "paper" : mode;
  render();
  $("msg").textContent = "Padrões carregados. Clique em Salvar para aplicar.";
  $("msg").className = "msg";
});

$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  current = readForm();
  for (const el of document.querySelectorAll("[data-err]")) el.textContent = "";
  for (const el of document.querySelectorAll(".field.invalid")) el.classList.remove("invalid");
  if (current.execution.mode === "live" && !$("liveAck")?.checked) {
    $("msg").textContent = "Confirme a caixa do modo dinheiro real para salvar.";
    $("msg").className = "msg bad";
    return;
  }
  $("save").disabled = true;
  const r = await api("PUT", "/api/settings", current).finally(() => ($("save").disabled = false));
  if (r.ok) {
    current = r.data.settings;
    render();
    $("msg").textContent = `Salvo às ${hms(new Date().toISOString())}.`;
    $("msg").className = "msg ok";
    return;
  }
  const errors = r.data?.errors ?? [{ path: "", message: "Erro ao salvar." }];
  let first = null;
  for (const e of errors) {
    const field = document.querySelector(`[data-field="${e.path}"]`) ?? document.querySelector(`[data-field^="${e.path.split(".").slice(0, 2).join(".")}"]`);
    if (field) {
      field.classList.add("invalid");
      field.querySelector("[data-err]").textContent = e.message;
      first ??= field;
    }
  }
  first?.scrollIntoView({ behavior: "smooth", block: "center" });
  $("msg").textContent = `${errors.length === 1 ? "1 campo precisa" : `${errors.length} campos precisam`} de ajuste.${first ? "" : " " + errors.map((e) => e.message).join(" ")}`;
  $("msg").className = "msg bad";
});

(async () => {
  const [s, st] = await Promise.all([api("GET", "/api/settings"), api("GET", "/api/state")]);
  current = s.data.settings;
  defaults = s.data.defaults;
  liveAvailable = s.data.liveAvailable;
  calibration = st.data?.calibration ?? null;
  render();
})();
