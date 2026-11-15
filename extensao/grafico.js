// MNEME Sinais: a leitura do MNEME projetada na tela da corretora, ao vivo.
// - a vela que está se formando anda a cada 2 s (preço real da Binance) e deixa um rastro dentro do cone de previsão;
// - a cada nova leitura, as linhas são traçadas, o cone se abre e os cenários se desenham, como se o MNEME estivesse
//   pensando na sua frente;
// - modo projetado (padrão): fundo transparente, o gráfico da corretora continua visível por baixo.
// Não lê nem mexe na página da corretora.
(function () {
  if (window.__mnemeGrafico) return;
  window.__mnemeGrafico = true;
  const L = globalThis.MnemeLogica;
  const COR = { grade: "rgba(255,255,255,0.06)", texto: "#cbd5e1", alta: "#22c55e", baixa: "#ef4444", suporte: "#2dd4bf", resistencia: "#f472b6",
    tendencia: "#60a5fa", fib: "rgba(250,204,21,0.10)", fibLinha: "rgba(250,204,21,0.7)", vwap: "#a78bfa", poc: "rgba(255,255,255,0.4)",
    cone95: "rgba(124,58,237,0.18)", cone68: "rgba(124,58,237,0.36)", centro: "#34d399", cenario: "rgba(96,165,250,0.9)", vivo: "#fde047" };
  const ANIMACAO_MS = 3200;

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483646;display:none;pointer-events:none;";
  document.documentElement.appendChild(host);
  const raiz = host.attachShadow({ mode: "closed" });
  raiz.innerHTML = `
    <style>
      .barra{position:absolute;top:0;left:0;height:24px;display:flex;gap:8px;align-items:center;padding:0 10px;border-radius:8px;
        font:600 11px -apple-system,Segoe UI,Roboto,sans-serif;color:#cbd5e1;background:rgba(17,20,26,.75);cursor:move;pointer-events:auto}
      .barra button{background:none;border:0;color:#cbd5e1;font-size:12px;cursor:pointer;padding:0 2px}
      .ponto{width:7px;height:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;animation:p 1.2s infinite}
      @keyframes p{50%{opacity:.25}}
      canvas{position:absolute;top:28px;left:0}
      .canto{position:absolute;right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;pointer-events:auto;
        background:linear-gradient(135deg,transparent 50%,rgba(255,255,255,.35) 50%)}
    </style>
    <div class="barra"><span class="ponto"></span><span>MNEME · ao vivo</span><button class="fundo" title="fundo sólido ou projetado">◐</button><button class="fechar" title="fechar">✕</button></div>
    <canvas></canvas><div class="canto"></div>`;
  const canvas = raiz.querySelector("canvas"), ctx = canvas.getContext("2d");
  raiz.querySelector(".fechar").onclick = () => alternar(false);

  let caixa = { x: 0.10, y: 0.22, w: 0.72, h: 0.68 }, solido = false;
  raiz.querySelector(".fundo").onclick = () => { solido = !solido; chrome.storage.local.set({ grafico_solido: solido }); };
  chrome.storage.local.get(["grafico_caixa", "grafico_ligado", "grafico_solido"]).then((c) => {
    if (c.grafico_caixa) caixa = c.grafico_caixa;
    solido = !!c.grafico_solido;
    posicionar();
    if (c.grafico_ligado) alternar(true);
  });
  function posicionar() {
    host.style.left = `${caixa.x * innerWidth}px`; host.style.top = `${caixa.y * innerHeight}px`;
    host.style.width = `${caixa.w * innerWidth}px`; host.style.height = `${caixa.h * innerHeight}px`;
    const dpr = devicePixelRatio || 1, w = caixa.w * innerWidth, h = caixa.h * innerHeight - 28;
    canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  addEventListener("resize", posicionar);
  let arrasto = null;
  const comecar = (tipo) => (e) => { arrasto = { tipo, x: e.clientX, y: e.clientY, c: { ...caixa } }; e.preventDefault(); };
  raiz.querySelector(".barra").addEventListener("mousedown", comecar("mover"));
  raiz.querySelector(".canto").addEventListener("mousedown", comecar("tamanho"));
  addEventListener("mousemove", (e) => {
    if (!arrasto) return;
    const dx = (e.clientX - arrasto.x) / innerWidth, dy = (e.clientY - arrasto.y) / innerHeight;
    if (arrasto.tipo === "mover") caixa = { ...arrasto.c, x: arrasto.c.x + dx, y: arrasto.c.y + dy };
    else caixa = { ...arrasto.c, w: Math.max(0.25, arrasto.c.w + dx), h: Math.max(0.25, arrasto.c.h + dy) };
    posicionar();
  });
  addEventListener("mouseup", () => { if (arrasto) chrome.storage.local.set({ grafico_caixa: caixa }); arrasto = null; });

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

  // ---------- dados ----------
  let ligado = false, leitura = null, sinais = [], erro = "", vivo = null, rastro = [], inicioAnimacao = 0, chaveLeitura = "";
  function alternar(estado) {
    ligado = estado === undefined ? !ligado : estado;
    host.style.display = ligado ? "block" : "none";
    chrome.storage.local.set({ grafico_ligado: ligado });
    if (ligado) { posicionar(); chaveLeitura = ""; buscar(); requestAnimationFrame(quadro); }
  }
  globalThis.MnemeGrafico = { alternar };

  function buscar() {
    if (!ligado) return;
    enviar({ tipo: "leitura" }, (r) => {
      if (chrome.runtime.lastError || !r) { erro = "extensão sem resposta"; return; }
      if (r.erro) { erro = r.erro; return; }
      erro = "";
      const chave = r.previsao ? `${r.previsao.vela}|${r.previsao.preco}` : r.agora;
      if (chave !== chaveLeitura) { chaveLeitura = chave; inicioAnimacao = performance.now(); rastro = []; }  // nova leitura: desenha de novo
      leitura = r;
    });
    enviar({ tipo: "sinais" }, (r) => { if (r && r.sinais) sinais = r.sinais; });
  }
  function buscarAoVivo() {
    if (!ligado || !leitura) return;
    enviar({ tipo: "ao_vivo", ativo: leitura.ativo, candle: leitura.candle }, (r) => {
      if (!r || r.erro) return;
      vivo = r;
      rastro.push({ t: r.agora, p: r.fe });
      if (rastro.length > 400) rastro.shift();
    });
  }
  timers.push(setInterval(buscar, 15_000), setInterval(buscarAoVivo, 2_000));

  // ---------- desenho ----------
  const facil = (x) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
  function fase(inicio, fim, agora) { return facil((agora - inicio) / (fim - inicio)); }
  function parcial(pontos, frac) {
    if (frac >= 1 || pontos.length < 2) return pontos;
    const n = (pontos.length - 1) * frac, i = Math.floor(n), r = n - i;
    const fora = pontos.slice(0, i + 1);
    if (i + 1 < pontos.length) fora.push([pontos[i][0] + (pontos[i + 1][0] - pontos[i][0]) * r, pontos[i][1] + (pontos[i + 1][1] - pontos[i][1]) * r]);
    return fora;
  }
  function linha(pontos, cor, largura = 1.5, tracejado = null, brilho = 0) {
    if (pontos.length < 2) return;
    ctx.save(); ctx.strokeStyle = cor; ctx.lineWidth = largura; if (tracejado) ctx.setLineDash(tracejado);
    if (brilho) { ctx.shadowColor = cor; ctx.shadowBlur = brilho; }
    ctx.beginPath(); pontos.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke(); ctx.restore();
  }
  function faixa(cima, baixo, cor) {
    ctx.save(); ctx.fillStyle = cor; ctx.beginPath();
    cima.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    [...baixo].reverse().forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.closePath(); ctx.fill(); ctx.restore();
  }
  function texto(t, x, y, cor = COR.texto, fonte = "11px -apple-system,Segoe UI,sans-serif", alinhar = "left") {
    ctx.save(); ctx.fillStyle = cor; ctx.font = fonte; ctx.textAlign = alinhar; ctx.shadowColor = "rgba(0,0,0,0.8)"; ctx.shadowBlur = 3; ctx.fillText(t, x, y); ctx.restore();
  }

  function quadro(agoraMs) {
    if (!ligado) return;
    desenhar(agoraMs);
    requestAnimationFrame(quadro);
  }

  function desenhar(agoraMs) {
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (!W || !H) return;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = solido ? "rgba(11,14,19,0.95)" : "rgba(11,14,19,0)";
    ctx.fillRect(0, 0, W, H);
    if (!leitura || !leitura.velas || !leitura.velas.length) {
      texto(erro || "o MNEME está lendo o mercado…", W / 2, H / 2, COR.texto, "14px -apple-system,sans-serif", "center");
      return;
    }
    const decorrido = agoraMs - inicioAnimacao;
    const a = (i, f) => fase(ANIMACAO_MS * i, ANIMACAO_MS * f, decorrido); // progresso de cada etapa da animação
    const area = { x: 12, y: 14, w: W - 84, h: H - 42 };
    const velas = [...leitura.velas];
    if (vivo && Date.parse(vivo.t) > Date.parse(velas[velas.length - 1].t)) velas.push({ ...vivo, aoVivo: true });
    const base = { ...leitura, velas: velas.filter((v) => !v.aoVivo) };
    const lim = L.limites(base);
    if (vivo) { lim.pmin = Math.min(lim.pmin, vivo.min); lim.pmax = Math.max(lim.pmax, vivo.max); }
    const e = L.escala(lim, area);
    const meia = Math.max(1.5, (e.x(lim.t0 + leitura.candle * 60_000) - e.x(lim.t0)) * 0.32);

    for (let i = 0; i <= 5; i++) {
      const p = lim.pmin + (lim.pmax - lim.pmin) * i / 5, y = e.y(p);
      linha([[area.x, y], [area.x + area.w, y]], COR.grade, 1);
      texto(p.toFixed(p > 100 ? 2 : 5), area.x + area.w + 6, y + 4, "rgba(203,213,225,0.7)");
    }
    linha([[e.corte, area.y], [e.corte, area.y + area.h]], "rgba(255,255,255,0.18)", 1, [4, 4]);
    texto("agora", e.corte - 4, area.y + 10, COR.texto, "10px -apple-system,sans-serif", "right");
    texto(`previsão · ${leitura.expiracao} min`, e.corte + 6, area.y + 10, "#c4b5fd", "bold 10px -apple-system,sans-serif");

    // Velas (a última, ao vivo, pisca levemente).
    for (const v of velas) {
      const x = v.aoVivo ? e.corte - meia - 2 : e.x(v.t) + meia, sobe = v.fe >= v.ab, cor = sobe ? COR.alta : COR.baixa;
      ctx.save(); if (v.aoVivo) ctx.globalAlpha = 0.65 + 0.35 * Math.abs(Math.sin(agoraMs / 500));
      linha([[x, e.y(v.max)], [x, e.y(v.min)]], cor, 1);
      const y1 = e.y(Math.max(v.ab, v.fe)), y2 = e.y(Math.min(v.ab, v.fe));
      ctx.fillStyle = cor; ctx.fillRect(x - meia, y1, meia * 2, Math.max(1, y2 - y1)); ctx.restore();
    }

    const ln = leitura.linhas || {};
    // 1) As linhas são traçadas da esquerda para a direita.
    const tLinhas = a(0, 0.45);
    if (ln.fibonacci && ln.fibonacci.zona_dourada && tLinhas > 0) {
      const [ya, yb] = ln.fibonacci.zona_dourada.map(e.y);
      ctx.fillStyle = COR.fib; ctx.fillRect(area.x, Math.min(ya, yb), area.w * tLinhas, Math.abs(ya - yb));
      if (tLinhas > 0.9) texto(`Fibonacci (${ln.fibonacci.sentido})`, area.x + 4, Math.min(ya, yb) - 3, COR.fibLinha);
    }
    if (ln.poc && tLinhas > 0) { linha([[area.x, e.y(ln.poc)], [area.x + area.w * tLinhas, e.y(ln.poc)]], COR.poc, 1, [2, 4]); if (tLinhas > 0.9) texto("POC", area.x + 4, e.y(ln.poc) - 3, COR.poc); }
    for (const [campo, cor, nome] of [["suporte", COR.suporte, "suporte"], ["resistencia", COR.resistencia, "resistência"]]) {
      const pts = [];
      (ln.degraus || []).forEach((d, i, todos) => {
        if (d[campo] == null) return;
        const x0 = e.x(d.t), x1 = i + 1 < todos.length ? e.x(todos[i + 1].t) : e.corte;
        pts.push([x0, e.y(d[campo])], [x1, e.y(d[campo])]);
      });
      const vis = parcial(pts, tLinhas);
      linha(vis, cor, 2, null, 10);
      if (tLinhas >= 1 && pts.length) texto(nome, pts[pts.length - 1][0] - 4, pts[pts.length - 1][1] - 5, cor, "bold 10px -apple-system,sans-serif", "right");
    }
    const tTend = a(0.3, 0.6);
    for (const [lt, nome] of [[ln.lta, "tendência de alta"], [ln.ltb, "tendência de baixa"]]) {
      if (!lt || tTend <= 0) continue;
      const pts = parcial([[e.x(lt.t1), e.y(lt.y1)], [e.x(lt.t2), e.y(lt.y2)]], tTend);
      linha(pts, COR.tendencia, 1.6, [6, 4], 6);
      if (tTend >= 1) texto(nome, pts[1][0] - 4, pts[1][1] - 5, COR.tendencia, "10px -apple-system,sans-serif", "right");
    }
    if (ln.vwap) linha(parcial(ln.vwap.map((p) => [e.x(p.t) + meia, e.y(p.v)]), a(0.15, 0.55)), COR.vwap, 1.2);

    // 2) O cone se abre a partir do "agora" e 3) os cenários se desenham um a um.
    const p = leitura.previsao;
    if (p && p.cone && p.cone.length) {
      const abre = a(0.5, 0.75);
      const inicio = [e.corte, e.y(p.preco)];
      const pts = (k) => [inicio, ...p.cone.map((c) => [e.x(c.t), e.y(p.preco + (c[k] - p.preco) * abre)])];
      if (abre > 0) { faixa(pts("hi95"), pts("lo95"), COR.cone95); faixa(pts("hi68"), pts("lo68"), COR.cone68); }
      (p.cenarios || []).forEach((c, i) => {
        const t = a(0.7 + i * 0.05, 0.85 + i * 0.05);
        if (t > 0) linha(parcial([inicio, ...c.map((y, j) => [e.x(p.cone[j].t), e.y(y)])], t), COR.cenario, 1.2, [3, 4]);
      });
      if (abre > 0) linha(parcial([inicio, [e.x(p.cone[p.cone.length - 1].t), e.y(p.preco)]], abre), COR.centro, 2.5, null, 8);
      // 4) O preço real andando dentro do cone (rastro desde a leitura).
      const caminho = rastro.filter((r) => r.t >= Date.parse(p.cone[0].t) - 60_000).map((r) => [e.x(Math.min(r.t, lim.t1)), e.y(r.p)]);
      if (caminho.length) {
        linha([inicio, ...caminho], COR.vivo, 2, null, 10);
        const [x, y] = caminho[caminho.length - 1];
        ctx.save(); ctx.fillStyle = COR.vivo; ctx.shadowColor = COR.vivo; ctx.shadowBlur = 14;
        ctx.beginPath(); ctx.arc(x, y, 3.5 + 1.5 * Math.abs(Math.sin(agoraMs / 300)), 0, Math.PI * 2); ctx.fill(); ctx.restore();
      }
    }
    if (vivo) {
      const y = e.y(vivo.fe);
      linha([[area.x, y], [area.x + area.w, y]], "rgba(253,224,71,0.35)", 1, [2, 3]);
      ctx.save(); ctx.fillStyle = COR.vivo; ctx.fillRect(area.x + area.w + 2, y - 8, 70, 16); ctx.restore();
      texto(vivo.fe.toFixed(vivo.fe > 100 ? 2 : 5), area.x + area.w + 6, y + 4, "#111", "bold 11px -apple-system,sans-serif");
    }

    // 5) Marcadores dos sinais do motor.
    if (a(0.85, 1) > 0) {
      for (const s of sinais) {
        const t = Date.parse(s.entrada_em);
        if (t < lim.t0 || t > lim.t1) continue;
        const vela = leitura.velas.reduce((m, v) => (Date.parse(v.t) <= t ? v : m), leitura.velas[0]);
        const x = e.x(t), call = s.direcao === "CALL", y = call ? e.y(vela.min) + 16 : e.y(vela.max) - 16;
        ctx.save(); ctx.globalAlpha = a(0.85, 1);
        ctx.fillStyle = s.resultado === "ganho" ? COR.alta : s.resultado === "perda" ? COR.baixa : (call ? COR.alta : COR.baixa);
        ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 10; ctx.beginPath();
        if (call) { ctx.moveTo(x, y - 9); ctx.lineTo(x - 8, y + 5); ctx.lineTo(x + 8, y + 5); } else { ctx.moveTo(x, y + 9); ctx.lineTo(x - 8, y - 5); ctx.lineTo(x + 8, y - 5); }
        ctx.fill(); ctx.restore();
        texto(s.direcao, x, call ? y + 17 : y - 11, call ? COR.alta : COR.baixa, "bold 10px -apple-system,sans-serif", "center");
      }
    }

    // Painel de leitura (aparece no fim da animação) e o que o MNEME está fazendo agora.
    const linhas = L.resumo(leitura), pw = 252, ph = 28 + linhas.length * 20, px = area.x + area.w - pw - 6, py = area.y + area.h - ph - 4;
    ctx.save(); ctx.globalAlpha = Math.max(0.15, a(0.8, 1)); ctx.fillStyle = "rgba(17,20,26,0.88)"; ctx.strokeStyle = "rgba(255,255,255,0.14)";
    ctx.beginPath(); ctx.roundRect(px, py, pw, ph, 10); ctx.fill(); ctx.stroke(); ctx.restore();
    texto("MNEME · " + (leitura.ativo || ""), px + 12, py + 18, "#f1f5f9", "bold 12px -apple-system,sans-serif");
    linhas.forEach(([k, v], i) => {
      const y = py + 40 + i * 20;
      texto(k, px + 12, y);
      const cor = /▲|alta|✓/.test(v) ? COR.alta : /▼|baixa|✗/.test(v) ? COR.baixa : "#f1f5f9";
      texto(v, px + pw - 12, y, cor, "bold 11px -apple-system,sans-serif", "right");
    });
    const etapa = decorrido < ANIMACAO_MS * 0.45 ? "traçando suporte, resistência e tendência…" : decorrido < ANIMACAO_MS * 0.75 ? "projetando os próximos minutos…"
      : decorrido < ANIMACAO_MS ? "sorteando cenários pela volatilidade…" : "acompanhando o preço dentro da previsão";
    texto(`MNEME: ${etapa}`, area.x + 4, H - 10, "#c4b5fd", "bold 11px -apple-system,sans-serif");
  }
})();
