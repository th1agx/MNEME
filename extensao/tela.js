// MNEME Sinais: o MNEME desenhando em cima das velas da própria corretora.
// A cada segundo ele olha a imagem do gráfico (só os pixels; nada de clicar ou ler dados da página), acha as velas e
// traça por cima o que lê nelas: suporte, resistência, linhas de tendência, Fibonacci, topos e fundos e o leque de onde a
// vela pode ir. Quando uma vela fecha, a leitura é refeita e traçada de novo na sua frente.
// O leque é o tamanho típico do movimento, não um caminho previsto; não há velas próprias nem fundo.
(function () {
  if (window.__mnemeTela) return;
  window.__mnemeTela = true;
  const V = globalThis.MnemeVisao;
  const COR = { suporte: "#2dd4bf", resistencia: "#f472b6", tendencia: "#60a5fa", fib: "rgba(250,204,21,0.10)", fibLinha: "rgba(250,204,21,0.75)",
    cone95: "rgba(167,139,250,0.08)", cone68: "rgba(167,139,250,0.32)", centro: "#fde047", texto: "#e2e8f0" };
  const TRACO_MS = 2200, OLHAR_MS = 1000, EIXO_CSS = 95; // largura do eixo de preço da corretora, que não deve ser coberto

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

  let ligado = false, timer = null, leitura = null, velas = [], assinatura = "", inicio = 0, ratio = 2;
  const grafico = () => document.querySelector("canvas.layer.plot");

  /** Copia a imagem do gráfico logo depois de a corretora desenhar o quadro (o WebGL apaga a imagem depois disso). */
  function olhar() {
    const c = grafico();
    if (!c || !c.width) { txt.textContent = "MNEME · gráfico não encontrado"; return; }
    requestAnimationFrame(() => queueMicrotask(() => {
      try {
        const W = c.width, H = c.height, copia = new OffscreenCanvas(W, H), g = copia.getContext("2d");
        g.drawImage(c, 0, 0);
        velas = V.detectar(g.getImageData(0, 0, W, H).data, W, H);
        leitura = V.ler(velas);
        const nova = V.assinatura(velas);
        if (nova !== assinatura) { assinatura = nova; inicio = performance.now(); }
        txt.textContent = leitura ? `MNEME · ${velas.length} velas · estrutura de ${leitura.estrutura}` : `MNEME · procurando velas (${velas.length})`;
      } catch (e) { txt.textContent = "MNEME · não consegui ler o gráfico"; }
    }));
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
  function linha(x1, y1, x2, y2, p, cor, larg = 2, tracejado = null) {
    ctx.save(); ctx.strokeStyle = cor; ctx.lineWidth = larg * ratio; if (tracejado) ctx.setLineDash(tracejado.map((n) => n * ratio));
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x1 + (x2 - x1) * p, y1 + (y2 - y1) * p); ctx.stroke(); ctx.restore();
  }
  function rotulo(texto, x, y, cor, p) {
    if (p < 0.98) return;
    ctx.save(); ctx.font = `600 ${10 * ratio}px -apple-system,Segoe UI,Roboto,sans-serif`; ctx.fillStyle = cor; ctx.textAlign = "right";
    ctx.fillText(texto, x, y - 4 * ratio); ctx.restore();
  }

  function desenhar(agora) {
    ctx.clearRect(0, 0, tela.width, tela.height);
    if (!leitura || !velas.length) return;
    const l = leitura.linhas, W = tela.width, xMax = W - EIXO_CSS * ratio, x0 = velas[0].x0;
    const fase = (de, ate) => suave(((agora - inicio) / TRACO_MS - de) / (ate - de)); // cada peça entra numa fatia do tempo

    // 1. Fibonacci da última perna: a zona de 50% a 78,6% e os níveis.
    if (l.fibonacci) {
      const p = fase(0, 0.35), n = l.fibonacci.niveis, xa = l.fibonacci.x;
      ctx.save(); ctx.globalAlpha = p; ctx.fillStyle = COR.fib; ctx.fillRect(xa, Math.min(n[0.5], n[0.786]), xMax - xa, Math.abs(n[0.786] - n[0.5])); ctx.restore();
      for (const [k, y] of Object.entries(n)) { linha(xa, y, xMax, y, p, COR.fibLinha, 1, [4, 4]); rotulo(`${(k * 100).toFixed(1).replace(".0", "")}%`, xMax, y, COR.fibLinha, p); }
    }
    // 2. Suporte e resistência, traçados da esquerda para a direita.
    if (l.resistencia !== null) { const p = fase(0.15, 0.5); linha(x0, l.resistencia, xMax, l.resistencia, p, COR.resistencia, 2); rotulo("resistência", xMax, l.resistencia, COR.resistencia, p); }
    if (l.suporte !== null) { const p = fase(0.2, 0.55); linha(x0, l.suporte, xMax, l.suporte, p, COR.suporte, 2); rotulo("suporte", xMax, l.suporte + 14 * ratio, COR.suporte, p); }
    // 3. Linhas de tendência pelos dois últimos topos ou fundos.
    for (const [t, nome] of [[l.lta, "LTA"], [l.ltb, "LTB"]]) {
      if (!t) continue;
      const p = fase(0.4, 0.75), x2 = Math.min(t.x2, xMax), y2 = t.y1 + (t.y2 - t.y1) * (x2 - t.x1) / (t.x2 - t.x1);
      linha(t.x1, t.y1, x2, y2, p, COR.tendencia, 2.5); rotulo(nome, x2, y2, COR.tendencia, p);
    }
    // 4. Topos e fundos que o MNEME marcou.
    const pm = fase(0.1, 0.4);
    ctx.save(); ctx.globalAlpha = pm; ctx.font = `${11 * ratio}px sans-serif`; ctx.textAlign = "center";
    for (const t of leitura.topos) { ctx.fillStyle = COR.resistencia; ctx.fillText("▼", t.x, t.y - 6 * ratio); }
    for (const f of leitura.fundos) { ctx.fillStyle = COR.suporte; ctx.fillText("▲", f.x, f.y + 16 * ratio); }
    ctx.restore();
    // 5. O leque de onde a vela pode ir, abrindo a partir do fechamento da vela atual.
    const lq = leitura.leque.filter((c) => c.x <= xMax), ult = velas[velas.length - 1], pl = fase(0.6, 1);
    if (lq.length) {
      const k = (c, campo) => ult.fe + (c[campo] - ult.fe) * pl;
      for (const [cima, baixo, cor] of [["hi95", "lo95", COR.cone95], ["hi68", "lo68", COR.cone68]]) {
        ctx.beginPath(); ctx.moveTo(ult.x, ult.fe);
        lq.forEach((c) => ctx.lineTo(c.x, k(c, cima)));
        [...lq].reverse().forEach((c) => ctx.lineTo(c.x, k(c, baixo)));
        ctx.closePath(); ctx.fillStyle = cor; ctx.fill();
      }
      linha(ult.x, ult.fe, lq[lq.length - 1].x, ult.fe, pl, COR.centro, 1, [3, 4]);
    }
    // 6. O ponto vivo no preço atual.
    const pulso = 0.5 + 0.5 * Math.sin(agora / 250);
    ctx.save(); ctx.fillStyle = COR.centro; ctx.globalAlpha = 0.4 + 0.6 * pulso;
    ctx.beginPath(); ctx.arc(ult.x, ult.fe, (3 + 2 * pulso) * ratio, 0, Math.PI * 2); ctx.fill(); ctx.restore();
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
    inicio = performance.now(); olhar(); timer = setInterval(olhar, OLHAR_MS); requestAnimationFrame(quadro);
  }

  try { chrome.storage.local.get(["tela_ligada"]).then((c) => { if (c.tela_ligada) alternar(true); }); } catch (e) { /* extensão recarregada */ }
  globalThis.MnemeTela = { alternar, temGrafico: () => !!grafico() };
})();
