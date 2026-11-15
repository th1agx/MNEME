// MNEME Sinais: a camada de gráfico por cima da tela da corretora. Desenha o que o MNEME lê e prevê, com o preço de
// referência real (Binance, Yahoo). Não lê nem mexe no gráfico da corretora: cobre a área com o próprio gráfico.
(function () {
  if (window.__mnemeGrafico) return;
  window.__mnemeGrafico = true;
  const L = globalThis.MnemeLogica;
  const COR = { fundo: "rgba(11,14,19,0.94)", grade: "rgba(255,255,255,0.05)", texto: "#9aa4b2", alta: "#22c55e", baixa: "#ef4444",
    suporte: "#2dd4bf", resistencia: "#f472b6", tendencia: "#60a5fa", fib: "rgba(250,204,21,0.10)", fibLinha: "rgba(250,204,21,0.55)",
    vwap: "#a78bfa", poc: "rgba(255,255,255,0.35)", cone95: "rgba(124,58,237,0.16)", cone68: "rgba(124,58,237,0.32)", centro: "#34d399",
    cenario: "rgba(96,165,250,0.85)" };

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483646;display:none;";
  document.documentElement.appendChild(host);
  const raiz = host.attachShadow({ mode: "closed" });
  raiz.innerHTML = `
    <style>
      .moldura{position:absolute;inset:0;border-radius:12px;overflow:hidden;box-shadow:0 10px 40px rgba(0,0,0,.5);border:1px solid rgba(255,255,255,.08)}
      .barra{position:absolute;top:0;left:0;right:0;height:26px;display:flex;align-items:center;justify-content:space-between;padding:0 10px;
        font:600 12px -apple-system,Segoe UI,Roboto,sans-serif;color:#9aa4b2;background:rgba(17,20,26,.9);cursor:move;z-index:2}
      .barra button{background:none;border:0;color:#9aa4b2;font-size:14px;cursor:pointer}
      canvas{position:absolute;top:26px;left:0}
      .canto{position:absolute;right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;z-index:2;
        background:linear-gradient(135deg,transparent 50%,rgba(255,255,255,.25) 50%)}
    </style>
    <div class="moldura"><div class="barra"><span>MNEME · leitura ao vivo</span><button title="fechar">✕</button></div><canvas></canvas><div class="canto"></div></div>`;
  const canvas = raiz.querySelector("canvas"), ctx = canvas.getContext("2d");
  raiz.querySelector(".barra button").onclick = () => alternar(false);

  // Posição e tamanho: guardados neste navegador; o padrão cobre a área central do gráfico da corretora.
  let caixa = { x: 0.10, y: 0.22, w: 0.72, h: 0.68 };
  chrome.storage.local.get(["grafico_caixa", "grafico_ligado"]).then((c) => {
    if (c.grafico_caixa) caixa = c.grafico_caixa;
    posicionar();
    if (c.grafico_ligado) alternar(true);
  });
  function posicionar() {
    host.style.left = `${caixa.x * innerWidth}px`; host.style.top = `${caixa.y * innerHeight}px`;
    host.style.width = `${caixa.w * innerWidth}px`; host.style.height = `${caixa.h * innerHeight}px`;
    const dpr = devicePixelRatio || 1, w = caixa.w * innerWidth, h = caixa.h * innerHeight - 26;
    canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    desenhar();
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

  let ligado = false, leitura = null, sinais = [], erro = "";
  function alternar(estado) {
    ligado = estado === undefined ? !ligado : estado;
    host.style.display = ligado ? "block" : "none";
    chrome.storage.local.set({ grafico_ligado: ligado });
    if (ligado) { buscar(); posicionar(); }
  }
  globalThis.MnemeGrafico = { alternar };

  function buscar() {
    if (!ligado) return;
    chrome.runtime.sendMessage({ tipo: "leitura" }, (r) => {
      if (chrome.runtime.lastError || !r) { erro = "extensão sem resposta"; return; }
      if (r.erro) { erro = r.erro; return; }
      erro = ""; leitura = r; desenhar();
    });
    chrome.runtime.sendMessage({ tipo: "sinais" }, (r) => { if (r && r.sinais) sinais = r.sinais; });
  }
  setInterval(buscar, 15_000);

  function linha(pontos, cor, largura = 1.5, tracejado = null) {
    if (pontos.length < 2) return;
    ctx.save(); ctx.strokeStyle = cor; ctx.lineWidth = largura; if (tracejado) ctx.setLineDash(tracejado);
    ctx.beginPath(); pontos.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke(); ctx.restore();
  }
  function faixa(cima, baixo, cor) {
    ctx.save(); ctx.fillStyle = cor; ctx.beginPath();
    cima.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    [...baixo].reverse().forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.closePath(); ctx.fill(); ctx.restore();
  }
  function texto(t, x, y, cor = COR.texto, fonte = "11px -apple-system,Segoe UI,sans-serif", alinhar = "left") {
    ctx.save(); ctx.fillStyle = cor; ctx.font = fonte; ctx.textAlign = alinhar; ctx.fillText(t, x, y); ctx.restore();
  }

  function desenhar() {
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (!W || !H) return;
    ctx.fillStyle = COR.fundo; ctx.fillRect(0, 0, W, H);
    if (!leitura || !leitura.velas || !leitura.velas.length) {
      texto(erro || "carregando a leitura do MNEME…", W / 2, H / 2, COR.texto, "14px -apple-system,sans-serif", "center");
      return;
    }
    const area = { x: 12, y: 12, w: W - 84, h: H - 40 };
    const lim = L.limites(leitura), e = L.escala(lim, area);
    const meia = Math.max(1.5, (e.x(lim.t0 + leitura.candle * 60_000) - e.x(lim.t0)) * 0.32);

    // Grade e escala de preço.
    for (let i = 0; i <= 5; i++) {
      const p = lim.pmin + (lim.pmax - lim.pmin) * i / 5, y = e.y(p);
      linha([[area.x, y], [area.x + area.w, y]], COR.grade, 1);
      texto(p.toFixed(p > 100 ? 2 : 5), area.x + area.w + 6, y + 4);
    }
    const ln = leitura.linhas || {};

    // Zona de Fibonacci (0,5 a 0,786 da última perna) e POC.
    if (ln.fibonacci && ln.fibonacci.zona_dourada) {
      const [a, b] = ln.fibonacci.zona_dourada.map(e.y);
      ctx.fillStyle = COR.fib; ctx.fillRect(area.x, Math.min(a, b), area.w, Math.abs(a - b));
      texto(`Fibonacci ${ln.fibonacci.sentido}`, area.x + 4, Math.min(a, b) - 3, COR.fibLinha);
    }
    if (ln.poc) { linha([[area.x, e.y(ln.poc)], [area.x + area.w, e.y(ln.poc)]], COR.poc, 1, [2, 4]); texto("POC", area.x + 4, e.y(ln.poc) - 3, COR.poc); }

    // Suporte e resistência em degraus (mudam a cada pivô confirmado).
    for (const [campo, cor] of [["suporte", COR.suporte], ["resistencia", COR.resistencia]]) {
      const pts = [];
      (ln.degraus || []).forEach((d, i, todos) => {
        if (d[campo] == null) return;
        const x0 = e.x(d.t), x1 = i + 1 < todos.length ? e.x(todos[i + 1].t) : e.x(lim.t1);
        pts.push([x0, e.y(d[campo])], [x1, e.y(d[campo])]);
      });
      ctx.save(); ctx.shadowColor = cor; ctx.shadowBlur = 8; linha(pts, cor, 2); ctx.restore();
    }
    // Linhas de tendência e VWAP.
    for (const [lt, nome] of [[ln.lta, "LTA"], [ln.ltb, "LTB"]]) {
      if (!lt) continue;
      linha([[e.x(lt.t1), e.y(lt.y1)], [e.x(lt.t2), e.y(lt.y2)]], COR.tendencia, 1.5, [6, 4]);
      texto(nome, e.x(lt.t2) - 24, e.y(lt.y2) - 4, COR.tendencia);
    }
    if (ln.vwap) linha(ln.vwap.map((p) => [e.x(p.t) + meia, e.y(p.v)]), COR.vwap, 1.2);

    // Velas.
    for (const v of leitura.velas) {
      const x = e.x(v.t) + meia, sobe = v.fe >= v.ab, cor = sobe ? COR.alta : COR.baixa;
      linha([[x, e.y(v.max)], [x, e.y(v.min)]], cor, 1);
      const y1 = e.y(Math.max(v.ab, v.fe)), y2 = e.y(Math.min(v.ab, v.fe));
      ctx.fillStyle = cor; ctx.fillRect(x - meia, y1, meia * 2, Math.max(1, y2 - y1));
    }

    // Previsão anterior: o cone da vela passada e onde o preço de fato terminou.
    const ant = leitura.anterior;
    if (ant && ant.cone && ant.cone.length) {
      const fim = ant.cone[ant.cone.length - 1];
      linha([[e.x(fim.t), e.y(fim.lo68)], [e.x(fim.t), e.y(fim.hi68)]], "rgba(124,58,237,0.6)", 3);
      if (ant.realizado != null) {
        ctx.fillStyle = ant.dentro_68 ? COR.alta : COR.baixa;
        ctx.beginPath(); ctx.arc(e.x(fim.t), e.y(ant.realizado), 4, 0, Math.PI * 2); ctx.fill();
      }
    }

    // Previsão: cone de 95% e 68%, linha central e cenários sorteados da volatilidade.
    const p = leitura.previsao;
    if (p && p.cone && p.cone.length) {
      const inicio = [e.x(leitura.velas[leitura.velas.length - 1].t) + meia * 2, e.y(p.preco)];
      const pts = (k) => [inicio, ...p.cone.map((c) => [e.x(c.t), e.y(c[k])])];
      faixa(pts("hi95"), pts("lo95"), COR.cone95);
      faixa(pts("hi68"), pts("lo68"), COR.cone68);
      (p.cenarios || []).forEach((c) => linha([inicio, ...c.map((y, i) => [e.x(p.cone[i].t), e.y(y)])], COR.cenario, 1.2, [3, 4]));
      linha([inicio, [e.x(p.cone[p.cone.length - 1].t), e.y(p.preco)]], COR.centro, 2.5);
    }

    // Marcadores dos sinais do motor: ▲ CALL embaixo da vela, ▼ PUT em cima, com a cor do resultado.
    for (const s of sinais) {
      const t = Date.parse(s.entrada_em);
      if (t < lim.t0 || t > lim.t1) continue;
      const vela = leitura.velas.reduce((m, v) => (Date.parse(v.t) <= t ? v : m), leitura.velas[0]);
      const x = e.x(t), call = s.direcao === "CALL";
      const y = call ? e.y(vela.min) + 16 : e.y(vela.max) - 16;
      ctx.fillStyle = s.resultado === "ganho" ? COR.alta : s.resultado === "perda" ? COR.baixa : (call ? COR.alta : COR.baixa);
      ctx.beginPath();
      if (call) { ctx.moveTo(x, y - 8); ctx.lineTo(x - 7, y + 4); ctx.lineTo(x + 7, y + 4); }
      else { ctx.moveTo(x, y + 8); ctx.lineTo(x - 7, y - 4); ctx.lineTo(x + 7, y - 4); }
      ctx.fill();
      texto(s.direcao, x, call ? y + 16 : y - 10, ctx.fillStyle, "bold 10px -apple-system,sans-serif", "center");
    }

    // Painel de leitura, no canto como no exemplo.
    const linhas = L.resumo(leitura), pw = 250, ph = 26 + linhas.length * 20, px = area.x + area.w - pw - 6, py = area.y + area.h - ph - 4;
    ctx.save(); ctx.fillStyle = "rgba(17,20,26,0.92)"; ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.beginPath(); ctx.roundRect(px, py, pw, ph, 10); ctx.fill(); ctx.stroke(); ctx.restore();
    texto("MNEME · " + (leitura.ativo || ""), px + 12, py + 18, "#e5e7eb", "bold 12px -apple-system,sans-serif");
    linhas.forEach(([k, v], i) => {
      const y = py + 40 + i * 20;
      texto(k, px + 12, y);
      const cor = /▲|alta|✓/.test(v) ? COR.alta : /▼|baixa|✗/.test(v) ? COR.baixa : "#e5e7eb";
      texto(v, px + pw - 12, y, cor, "bold 11px -apple-system,sans-serif", "right");
    });
    texto("cone: onde o preço pode estar (68% e 95%) · pontilhado: cenários sorteados, não previsão do caminho",
          area.x + 4, H - 8, "rgba(154,164,178,0.8)", "10px -apple-system,sans-serif");
  }
  setInterval(() => { if (ligado) desenhar(); }, 1_000);
})();
