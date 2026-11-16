// MNEME Sinais: o MNEME desenhando em cima das velas da própria corretora.
// A cada segundo ele olha a imagem do gráfico (só os pixels; nada de clicar ou ler dados da página), acha as velas e
// lê nelas a estrutura (topos e fundos), suporte, resistência, Fibonacci, linhas de tendência e o leque de onde a vela
// pode ir. Quando uma vela fecha, ele traça tudo de novo na sua frente, com uma caneta, peça por peça. Entre um
// fechamento e outro, as linhas só deslizam para acompanhar a escala da corretora; nada é refeito.
// O leque é o tamanho típico do movimento, não um caminho previsto; não há velas próprias nem fundo.
(function () {
  if (window.__mnemeTela) return;
  window.__mnemeTela = true;
  const V = globalThis.MnemeVisao;
  const COR = { suporte: "#2dd4bf", resistencia: "#f472b6", tendencia: "#60a5fa", estrutura: "#fde047", fib: "rgba(250,204,21,0.09)",
    fibLinha: "rgba(250,204,21,0.7)", cone95: "rgba(167,139,250,0.08)", cone68: "rgba(167,139,250,0.30)", caneta: "#fef9c3" };
  const TRACO_MS = 4500, OLHAR_MS = 1000, EIXO_CSS = 95, SUAVE = 0.18;
  // Em que fatia do traçado entra cada peça, e o que a barra diz enquanto isso.
  const ETAPAS = { estrutura: [0, 0.38], resistencia: [0.3, 0.52], suporte: [0.36, 0.58], fib: [0.5, 0.7], tendencia: [0.6, 0.8], leque: [0.76, 1] };
  const FALAS = [[0.3, "traçando a estrutura…"], [0.5, "marcando suporte e resistência…"], [0.6, "medindo o Fibonacci…"], [0.76, "puxando as tendências…"], [1, "projetando o leque…"]];

  const host = document.createElement("div");
  host.style.cssText = "position:fixed;z-index:2147483646;display:none;pointer-events:none;";
  document.documentElement.appendChild(host);
  const raiz = host.attachShadow({ mode: "closed" });
  raiz.innerHTML = `
    <style>
      canvas{position:absolute;top:0;left:0;width:100%;height:100%}
      .barra{position:absolute;bottom:34px;left:8px;display:flex;gap:8px;align-items:center;padding:3px 10px;border-radius:8px;pointer-events:auto;
        font:600 11px -apple-system,Segoe UI,Roboto,sans-serif;color:#e2e8f0;background:rgba(17,20,26,.8)}
      .barra button{background:none;border:0;color:#cbd5e1;font-size:12px;cursor:pointer;padding:0 2px}
      .ponto{width:7px;height:7px;border-radius:50%;background:#22c55e;box-shadow:0 0 8px #22c55e;animation:p 1.2s infinite}
      @keyframes p{50%{opacity:.25}}
    </style>
    <canvas></canvas>
    <div class="barra"><span class="ponto"></span><span class="txt">MNEME · olhando a tela</span><button class="fechar" title="desligar">✕</button></div>`;
  const tela = raiz.querySelector("canvas"), ctx = tela.getContext("2d"), txt = raiz.querySelector(".txt");
  raiz.querySelector(".fechar").onclick = () => alternar(false);

  let ligado = false, timer = null, alvo = null, mostra = null, assinatura = "", inicio = 0, ratio = 2, info = "";
  const grafico = () => document.querySelector("canvas.layer.plot");

  /** Copia a imagem do gráfico logo depois de a corretora desenhar o quadro (o WebGL apaga a imagem depois disso). */
  function olhar() {
    const c = grafico();
    if (!c || !c.width) { info = "gráfico não encontrado"; return; }
    requestAnimationFrame(() => queueMicrotask(() => {
      try {
        const W = c.width, H = c.height, copia = new OffscreenCanvas(W, H), g = copia.getContext("2d");
        g.drawImage(c, 0, 0);
        const velas = V.detectar(g.getImageData(0, 0, W, H).data, W, H), l = V.ler(velas);
        if (!l) { info = `procurando velas (${velas.length})`; return; }
        const ult = velas[velas.length - 1];
        alvo = { ...l, atual: { x: ult.x, y: ult.fe }, x0: velas[0].x0 };
        const nova = V.assinatura(velas);
        if (nova !== assinatura || !mostra) { assinatura = nova; inicio = performance.now(); mostra = null; } // uma vela fechou: traça de novo
        info = `${velas.length} velas · estrutura de ${l.estrutura}`;
      } catch (e) { info = "não consegui ler o gráfico"; }
    }));
  }

  /** Aproxima o que está na tela do que foi lido, um pouco por quadro: a escala da corretora muda e as linhas deslizam. */
  function aproximar(a, b) {
    if (typeof b === "number") return typeof a === "number" ? a + (b - a) * SUAVE : b;
    if (Array.isArray(b)) return Array.isArray(a) && a.length === b.length ? b.map((x, i) => aproximar(a[i], x)) : b;
    if (b && typeof b === "object") { const r = {}; for (const k of Object.keys(b)) r[k] = aproximar(a && a[k], b[k]); return r; }
    return b;
  }

  function posicionar() {
    const c = grafico();
    if (!c) return false;
    const r = c.getBoundingClientRect();
    host.style.left = `${r.left}px`; host.style.top = `${r.top}px`; host.style.width = `${r.width}px`; host.style.height = `${r.height}px`;
    if (tela.width !== c.width || tela.height !== c.height) { tela.width = c.width; tela.height = c.height; }
    ratio = c.width / Math.max(1, r.width);
    return true;
  }

  // ---------- desenho (em pixels do gráfico da corretora) ----------
  const suave = (t) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);
  let canetas = [];
  /** Traça um caminho até a fração `p` do comprimento; a ponta, enquanto não termina, ganha a caneta. */
  function caminho(pts, p, cor, larg = 2, tracejado = null) {
    if (pts.length < 2 || p <= 0) return;
    const seg = pts.slice(1).map((q, i) => Math.hypot(q.x - pts[i].x, q.y - pts[i].y)), total = seg.reduce((a, b) => a + b, 0);
    let resta = total * p, ponta = pts[0];
    ctx.save(); ctx.strokeStyle = cor; ctx.lineWidth = larg * ratio; ctx.lineJoin = "round";
    if (tracejado) ctx.setLineDash(tracejado.map((n) => n * ratio));
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 0; i < seg.length && resta > 0; i++) {
      const f = Math.min(1, resta / (seg[i] || 1));
      ponta = { x: pts[i].x + (pts[i + 1].x - pts[i].x) * f, y: pts[i].y + (pts[i + 1].y - pts[i].y) * f };
      ctx.lineTo(ponta.x, ponta.y); resta -= seg[i];
    }
    ctx.stroke(); ctx.restore();
    if (p < 1) canetas.push(ponta);
  }
  function rotulo(texto, x, y, cor, p) {
    if (p < 0.98) return;
    ctx.save(); ctx.font = `600 ${10 * ratio}px -apple-system,Segoe UI,Roboto,sans-serif`; ctx.fillStyle = cor; ctx.textAlign = "right";
    ctx.fillText(texto, x, y - 4 * ratio); ctx.restore();
  }
  function caneta(q, agora) {
    const r = (4 + 1.5 * Math.sin(agora / 90)) * ratio;
    ctx.save(); ctx.fillStyle = COR.caneta; ctx.shadowColor = COR.caneta; ctx.shadowBlur = 18 * ratio;
    ctx.beginPath(); ctx.arc(q.x, q.y, r, 0, Math.PI * 2); ctx.fill(); ctx.restore();
  }

  function desenhar(agora) {
    ctx.clearRect(0, 0, tela.width, tela.height);
    if (!alvo) { txt.textContent = `MNEME · ${info || "olhando a tela"}`; return; }
    mostra = mostra ? aproximar(mostra, alvo) : alvo;
    const m = mostra, l = m.linhas, xMax = tela.width - EIXO_CSS * ratio, t = (agora - inicio) / TRACO_MS;
    const fase = (nome) => { const [de, ate] = ETAPAS[nome]; return suave((t - de) / (ate - de)); };
    canetas = [];

    // 1. A estrutura: o zigue-zague de topos e fundos, da esquerda para a direita, terminando no preço atual.
    const pe = fase("estrutura"), z = m.zigue.map((q, i) => (i === m.zigue.length - 1 ? { ...q, x: m.atual.x, y: m.atual.y } : q));
    caminho(z, pe, COR.estrutura, 1.6);
    ctx.save(); ctx.font = `${11 * ratio}px sans-serif`; ctx.textAlign = "center";
    z.forEach((q, i) => {
      if (q.tipo === "agora" || pe < (i + 0.5) / z.length) return; // cada marca aparece quando a caneta passa por ela
      ctx.fillStyle = q.tipo === "topo" ? COR.resistencia : COR.suporte;
      ctx.fillText(q.tipo === "topo" ? "▼" : "▲", q.x, q.tipo === "topo" ? q.y - 6 * ratio : q.y + 16 * ratio);
    });
    ctx.restore();
    // 2. Resistência e suporte.
    if (l.resistencia !== null) { const p = fase("resistencia"); caminho([{ x: m.x0, y: l.resistencia }, { x: xMax, y: l.resistencia }], p, COR.resistencia, 2); rotulo("resistência", xMax, l.resistencia, COR.resistencia, p); }
    if (l.suporte !== null) { const p = fase("suporte"); caminho([{ x: m.x0, y: l.suporte }, { x: xMax, y: l.suporte }], p, COR.suporte, 2); rotulo("suporte", xMax, l.suporte + 14 * ratio, COR.suporte, p); }
    // 3. Fibonacci da última perna.
    if (l.fibonacci) {
      const p = fase("fib"), n = l.fibonacci.niveis, xa = l.fibonacci.x;
      ctx.save(); ctx.globalAlpha = p; ctx.fillStyle = COR.fib; ctx.fillRect(xa, Math.min(n[0.5], n[0.786]), xMax - xa, Math.abs(n[0.786] - n[0.5])); ctx.restore();
      for (const [k, y] of Object.entries(n)) { caminho([{ x: xa, y }, { x: xMax, y }], p, COR.fibLinha, 1, [4, 4]); rotulo(`${(k * 100).toFixed(1).replace(".0", "")}%`, xMax, y, COR.fibLinha, p); }
    }
    // 4. Linhas de tendência pelos dois últimos topos ou fundos, levadas para a frente.
    for (const [r, nome] of [[l.lta, "LTA"], [l.ltb, "LTB"]]) {
      if (!r) continue;
      const p = fase("tendencia"), x2 = Math.min(r.x2, xMax), y2 = r.y1 + (r.y2 - r.y1) * (x2 - r.x1) / (r.x2 - r.x1);
      caminho([{ x: r.x1, y: r.y1 }, { x: x2, y: y2 }], p, COR.tendencia, 2.5); rotulo(nome, x2, y2, COR.tendencia, p);
    }
    // 5. O leque de onde a vela pode ir, abrindo a partir do preço atual e seguindo a vela que se forma.
    const pl = fase("leque"), a = m.atual, lq = m.leque.filter((c) => c.x <= xMax);
    if (lq.length && pl > 0) {
      const desloca = a.y - m.leque[0].y;
      for (const [cima, baixo, cor] of [["hi95", "lo95", COR.cone95], ["hi68", "lo68", COR.cone68]]) {
        const k = (c, campo) => a.y + (c[campo] + desloca - a.y) * pl;
        ctx.beginPath(); ctx.moveTo(a.x, a.y);
        lq.forEach((c) => ctx.lineTo(c.x, k(c, cima)));
        [...lq].reverse().forEach((c) => ctx.lineTo(c.x, k(c, baixo)));
        ctx.closePath(); ctx.fillStyle = cor; ctx.fill();
      }
    }
    // 6. A caneta na ponta do que está sendo traçado e o ponto vivo no preço atual.
    canetas.forEach((q) => caneta(q, agora));
    const pulso = 0.5 + 0.5 * Math.sin(agora / 250);
    ctx.save(); ctx.fillStyle = COR.estrutura; ctx.globalAlpha = 0.4 + 0.6 * pulso;
    ctx.beginPath(); ctx.arc(a.x, a.y, (3 + 2 * pulso) * ratio, 0, Math.PI * 2); ctx.fill(); ctx.restore();

    const fala = FALAS.find(([ate]) => t < ate);
    txt.textContent = `MNEME · ${fala ? fala[1] : info}`;
  }

  function quadro(agora) {
    if (!ligado) return;
    if (posicionar()) desenhar(agora);
    requestAnimationFrame(quadro);
  }

  function alternar(forcar) {
    ligado = typeof forcar === "boolean" ? forcar : !ligado;
    host.style.display = ligado ? "block" : "none";
    clearInterval(timer);
    try { chrome.storage.local.set({ tela_ligada: ligado }); } catch (e) { ligado = false; }
    if (!ligado) return;
    if (globalThis.MnemeGrafico) globalThis.MnemeGrafico.alternar(false); // as duas camadas não aparecem juntas
    alvo = null; mostra = null; assinatura = ""; olhar(); timer = setInterval(olhar, OLHAR_MS); requestAnimationFrame(quadro);
  }

  try { chrome.storage.local.get(["tela_ligada"]).then((c) => { if (c.tela_ligada) alternar(true); }); } catch (e) { /* extensão recarregada */ }
  globalThis.MnemeTela = { alternar, temGrafico: () => !!grafico() };
})();
