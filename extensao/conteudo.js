// MNEME Sinais: desenha o card no canto da corretora. Tudo fica dentro de um shadow DOM próprio:
// a extensão não lê, não clica e não altera nada da página da corretora. Quem opera é sempre a pessoa.
(function () {
  if (window.__mnemeSinais) return;
  window.__mnemeSinais = true;
  const L = globalThis.MnemeLogica;
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CORRETORA = L.corretora(location.hostname);

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;right:16px;bottom:16px;z-index:2147483647;";
  document.documentElement.appendChild(host);
  const raiz = host.attachShadow({ mode: "closed" });
  raiz.innerHTML = `
    <style>
      .card{font:600 14px/1.3 -apple-system,Segoe UI,Roboto,sans-serif;color:#fff;background:#1b1f27;border-radius:14px;
        box-shadow:0 8px 28px rgba(0,0,0,.45);width:250px;overflow:hidden;user-select:none}
      .topo{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#11141a;cursor:move;font-size:12px;color:#9aa4b2}
      .topo button{background:none;border:0;color:#9aa4b2;font-size:14px;cursor:pointer}
      .corpo{padding:12px}
      .grande{font-size:30px;font-weight:800;letter-spacing:.5px;text-align:center;padding:10px;border-radius:10px;margin:6px 0}
      .call{background:#13a85b}.put{background:#e0384b}.neutro{background:#3a4150}
      .linha{display:flex;justify-content:space-between;font-size:13px;color:#cfd6e0;margin-top:4px}
      .tempo{font-size:22px;text-align:center;margin-top:6px}
      .acoes{display:flex;gap:6px;margin-top:10px}
      .acoes input{width:70px;padding:6px;border-radius:8px;border:0;background:#2a303b;color:#fff;font:inherit}
      .acoes button{flex:1;padding:7px;border:0;border-radius:8px;font:inherit;cursor:pointer;background:#2f6fed;color:#fff}
      .acoes button.nao{background:#3a4150}
      .msg{font-size:12px;color:#9aa4b2;text-align:center;margin-top:8px}
      .min .corpo{display:none}
    </style>
    <div class="card"><div class="topo"><span>MNEME · sinais</span><span><button class="graf" title="leitura no gráfico">📈</button><button class="min" title="minimizar">–</button></span></div><div class="corpo"></div></div>`;
  const card = raiz.querySelector(".card"), corpo = raiz.querySelector(".corpo");
  raiz.querySelector(".topo .min").onclick = () => card.classList.toggle("min");
  raiz.querySelector(".topo .graf").onclick = () => {
    // Com o gráfico da corretora na tela, o MNEME desenha em cima das velas dela; sem ele, abre a camada própria.
    const T = globalThis.MnemeTela, G = globalThis.MnemeGrafico;
    if (T && T.temGrafico()) T.alternar(); else if (G) G.alternar();
  };

  // Arrastar pelo topo.
  let arrasto = null;
  raiz.querySelector(".topo").addEventListener("mousedown", (e) => { arrasto = { x: e.clientX, y: e.clientY, r: parseInt(host.style.right), b: parseInt(host.style.bottom) }; });
  window.addEventListener("mousemove", (e) => { if (!arrasto) return; host.style.right = `${arrasto.r - (e.clientX - arrasto.x)}px`; host.style.bottom = `${arrasto.b - (e.clientY - arrasto.y)}px`; });
  window.addEventListener("mouseup", () => { arrasto = null; });

  // Depois de recarregar a extensão, a cópia antiga deste script perde a ligação: ela se desliga sozinha, sem erro.
  const timers = [];
  function enviar(msg, cb) {
    try {
      if (!chrome.runtime || !chrome.runtime.id) throw new Error("sem contexto");
      chrome.runtime.sendMessage(msg, cb);
    } catch (e) {
      timers.forEach(clearInterval);
      host.remove();
    }
  }

  function bip(alto) {
    try {
      const ctx = new AudioContext(), o = ctx.createOscillator(), g = ctx.createGain();
      o.frequency.value = alto ? 880 : 520; o.connect(g); g.connect(ctx.destination); g.gain.value = 0.08;
      o.start(); o.stop(ctx.currentTime + 0.18);
    } catch (e) { /* sem som, segue */ }
  }

  let sinais = [], erro = "", desvio = 0, ultimoAvisado = "", ultimaFase = "", respondidos = new Set();

  function buscar() {
    enviar({ tipo: "sinais" }, (r) => {
      if (chrome.runtime.lastError || !r) { erro = "extensão sem resposta"; return; }
      if (r.erro) { erro = r.erro; return; }
      erro = ""; sinais = r.sinais || [];
      if (r.agora) desvio = Date.parse(r.agora) - Date.now(); // usa o relógio do servidor
    });
  }

  function registrar(sinal, entrou) {
    const campo = raiz.querySelector("input");
    const p = entrou ? L.payout(campo ? campo.value : "") : null;
    if (entrou && p === null) { campo && (campo.style.outline = "2px solid #e0384b"); return; }
    enviar({ tipo: "entrada", entrada: { sinal_id: sinal.id, entrou, payout: p, corretora: CORRETORA } }, () => {});
    respondidos.add(sinal.id);
    desenhar();
  }

  function desenhar() {
    const agora = Date.now() + desvio;
    const atual = L.escolher(sinais, agora);
    if (!atual) {
      corpo.innerHTML = `<div class="grande neutro">aguardando</div><div class="msg">${esc(erro || "sem sinal no cenário escolhido agora")}</div>`;
      return;
    }
    const { sinal, fase } = atual;
    const chave = `${sinal.id}|${fase}`;
    if (chave !== ultimaFase) {
      ultimaFase = chave;
      if (fase === "preparar" && ultimoAvisado !== sinal.id) { ultimoAvisado = sinal.id; bip(false); }
      if (fase === "entrar") bip(true);
    }
    const lado = sinal.direcao === "CALL" ? "call" : "put";
    const seta = sinal.direcao === "CALL" ? "▲ CALL" : "▼ PUT";
    const titulo = { preparar: "prepare", entrar: "ENTRE AGORA", andamento: "em andamento", apurando: "apurando", resultado: "resultado" }[fase];
    let meio = `<div class="grande ${lado}">${seta}</div>`;
    if (fase === "resultado") {
      const cor = sinal.resultado === "ganho" ? "call" : sinal.resultado === "perda" ? "put" : "neutro";
      meio = `<div class="grande ${cor}">${esc(String(sinal.resultado).toUpperCase())}</div>`;
    }
    const tempo = fase === "preparar" || fase === "andamento" ? `<div class="tempo">${L.contagem(sinal, fase, agora)}</div>` : "";
    const pedir = (fase === "entrar" || fase === "andamento") && !respondidos.has(sinal.id)
      ? `<div class="acoes"><input placeholder="payout %" inputmode="decimal"><button class="sim">entrei</button><button class="nao">não</button></div>` : "";
    corpo.innerHTML = `<div class="linha"><span>${esc(sinal.ativo)}</span><span>${titulo}</span></div>${meio}
      <div class="linha"><span>expiração ${esc(sinal.expiracao_min)} min</span><span>entrada ${new Date(sinal.entrada_em).toLocaleTimeString().slice(0, 5)}</span></div>
      ${tempo}${pedir}<div class="msg">${esc(sinal.cenario)}</div>`;
    const sim = raiz.querySelector(".sim"), nao = raiz.querySelector(".nao");
    if (sim) sim.onclick = () => registrar(sinal, true);
    if (nao) nao.onclick = () => registrar(sinal, false);
  }

  buscar();
  timers.push(setInterval(buscar, 2000));
  // Não redesenha enquanto a pessoa digita o payout.
  timers.push(setInterval(() => { if (raiz.activeElement && raiz.activeElement.tagName === "INPUT") return; desenhar(); }, 500));
})();
