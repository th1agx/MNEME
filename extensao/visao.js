// MNEME Sinais: a visão da tela. Encontra as velas da corretora na imagem do gráfico e lê nelas o que o MNEME lê
// (pivôs, suporte e resistência, linhas de tendência, Fibonacci da última perna e o tamanho provável do movimento).
// Tudo em pixels da tela: y menor é preço maior. Funções puras, testadas no vitest; não toca na página.
(function () {
  const LADOS = 2; // um pivô precisa de 2 velas de cada lado
  const FIB = [0.382, 0.5, 0.618, 0.786];

  /** 1 = verde (alta), -1 = vermelho (baixa), 0 = outra cor. */
  function corDoPixel(R, G, B) {
    if (G > 130 && R < 120 && B < 130 && G - R > 50) return 1;
    if (R > 180 && G < 130 && B < 120 && R - G > 70) return -1;
    return 0;
  }

  const mediana = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[s.length >> 1] : NaN; };

  /** As velas na imagem RGBA `d` (largura W, altura H), da esquerda para a direita. A última pode estar se formando. */
  function detectar(d, W, H) {
    const cols = [];
    for (let x = 0; x < W; x++) {
      let v = 0, m = 0, topo = H, fundo = -1;
      for (let y = 0; y < H; y++) {
        const i = (y * W + x) * 4, k = corDoPixel(d[i], d[i + 1], d[i + 2]);
        if (!k) continue;
        k > 0 ? v++ : m++;
        if (y < topo) topo = y;
        if (y > fundo) fundo = y;
      }
      cols.push({ v, m, topo, fundo });
    }
    const grupos = [];
    let atual = null;
    for (let x = 0; x < W; x++) {
      const s = cols[x], lado = s.v + s.m < 2 ? 0 : s.v >= s.m ? 1 : -1;
      if (lado && atual && atual.lado === lado && x === atual.x1 + 1) { atual.x1 = x; atual.cols.push(s); }
      else if (lado) { atual = { lado, x0: x, x1: x, cols: [s] }; grupos.push(atual); }
      else atual = null;
    }
    // A vela cortada pela borda esquerda some e volta conforme o gráfico anda: fica de fora para não mudar a leitura.
    const largos = grupos.filter((g) => g.x1 - g.x0 >= 3 && g.x0 > 0);
    const larg = mediana(largos.map((g) => g.x1 - g.x0 + 1));
    return largos.filter((g) => g.x1 - g.x0 + 1 >= larg * 0.5).map((g) => {
      // Corpo: a mediana das colunas (o pavio é uma coluna só e não muda a mediana). Pavio: o extremo de todas.
      const ct = mediana(g.cols.map((s) => s.topo)), cb = mediana(g.cols.map((s) => s.fundo));
      const max = Math.min(...g.cols.map((s) => s.topo)), min = Math.max(...g.cols.map((s) => s.fundo));
      return { x: (g.x0 + g.x1) / 2, x0: g.x0, x1: g.x1, lado: g.lado, ab: g.lado > 0 ? cb : ct, fe: g.lado > 0 ? ct : cb, max, min };
    });
  }

  /** Topos e fundos confirmados: só valem com LADOS velas fechadas depois (a última vela, em formação, não confirma nada). */
  function pivos(velas, lados = LADOS) {
    const fechadas = velas.slice(0, -1), topos = [], fundos = [];
    for (let i = lados; i < fechadas.length - lados; i++) {
      const viz = fechadas.slice(i - lados, i + lados + 1);
      if (viz.every((v) => v.max >= fechadas[i].max)) topos.push({ i, x: fechadas[i].x, y: fechadas[i].max });
      if (viz.every((v) => v.min <= fechadas[i].min)) fundos.push({ i, x: fechadas[i].x, y: fechadas[i].min });
    }
    return { topos, fundos };
  }

  /** Reta por dois pivôs, levada até `xFim`. A de alta só vale subindo (y caindo), a de baixa só descendo. */
  function tendencia(p, alta, xFim) {
    if (p.length < 2) return null;
    const [a, b] = p.slice(-2), passo = (b.y - a.y) / (b.x - a.x);
    if ((alta && passo >= 0) || (!alta && passo <= 0)) return null;
    return { x1: a.x, y1: a.y, x2: xFim, y2: b.y + passo * (xFim - b.x) };
  }

  /** Tudo o que o MNEME lê nas velas da tela, mais o leque de onde a vela pode ir nas próximas `frente` velas. */
  function ler(velas, frente = 5) {
    if (velas.length < 2 * LADOS + 3) return null;
    const passo = mediana(velas.slice(1).map((v, i) => v.x - velas[i].x));
    const ultima = velas[velas.length - 1], xFim = ultima.x + passo * frente;
    const { topos, fundos } = pivos(velas);
    const linhas = {
      suporte: fundos.length ? fundos[fundos.length - 1].y : null,
      resistencia: topos.length ? topos[topos.length - 1].y : null,
      lta: tendencia(fundos, true, xFim), ltb: tendencia(topos, false, xFim), fibonacci: null,
    };
    if (topos.length && fundos.length) {
      const t = topos[topos.length - 1], f = fundos[fundos.length - 1], sobe = f.i < t.i, perna = f.y - t.y;
      linhas.fibonacci = { sentido: sobe ? "alta" : "baixa", x: Math.min(t.x, f.x),
        niveis: Object.fromEntries(FIB.map((k) => [k, sobe ? t.y + k * perna : f.y - k * perna])) };
    }
    // Leque: o tamanho típico do movimento de uma vela para a outra (em pixels), aberto pela raiz do tempo.
    const mov = velas.slice(1).map((v, i) => v.fe - velas[i].fe);
    const media = mov.reduce((a, b) => a + b, 0) / mov.length;
    const sigma = Math.sqrt(mov.reduce((a, b) => a + (b - media) ** 2, 0) / Math.max(1, mov.length - 1));
    const leque = Array.from({ length: frente }, (_, k) => {
      const s = sigma * Math.sqrt(k + 1);
      return { x: ultima.x + passo * (k + 1), y: ultima.fe, lo68: ultima.fe + s, hi68: ultima.fe - s, lo95: ultima.fe + 1.96 * s, hi95: ultima.fe - 1.96 * s };
    });
    const estrutura = estruturaDe(topos, fundos);
    return { passo, linhas, topos, fundos, leque, estrutura, zigue: zigue(topos, fundos, ultima), velas: velas.length };
  }

  /** A estrutura do mercado: topos e fundos alternados, da esquerda para a direita, terminando no preço atual.
   *  Dois topos seguidos ficam só com o mais alto; dois fundos seguidos, só com o mais baixo. */
  function zigue(topos, fundos, ultima) {
    const pts = [...topos.map((p) => ({ ...p, tipo: "topo" })), ...fundos.map((p) => ({ ...p, tipo: "fundo" }))].sort((a, b) => a.i - b.i);
    const z = [];
    for (const p of pts) {
      const u = z[z.length - 1];
      if (u && u.tipo === p.tipo) { if ((p.tipo === "topo" && p.y < u.y) || (p.tipo === "fundo" && p.y > u.y)) z[z.length - 1] = p; }
      else z.push(p);
    }
    if (z.length) z.push({ x: ultima.x, y: ultima.fe, tipo: "agora" });
    return z.map(({ x, y, tipo }) => ({ x, y, tipo }));
  }

  /** Topos e fundos subindo é alta; descendo é baixa; o resto é lateral. */
  function estruturaDe(topos, fundos) {
    if (topos.length < 2 || fundos.length < 2) return "lateral";
    const t = topos.slice(-2), f = fundos.slice(-2);
    if (t[1].y < t[0].y && f[1].y < f[0].y) return "alta";
    if (t[1].y > t[0].y && f[1].y > f[0].y) return "baixa";
    return "lateral";
  }

  /** Uma assinatura das velas fechadas que só muda quando uma vela fecha. Usa a cor e o tamanho relativo de cada vela,
   *  e não pixels: a corretora reescala o gráfico enquanto a vela atual se mexe, e isso não pode refazer o traçado. */
  function assinatura(velas) {
    const fechadas = velas.slice(0, -1);
    const alt = Math.max(1, ...fechadas.map((v) => v.min - v.max));
    return fechadas.map((v) => `${v.lado}${Math.round(((v.min - v.max) / alt) * 4)}`).join("");
  }

  globalThis.MnemeVisao = { corDoPixel, detectar, pivos, tendencia, ler, estruturaDe, zigue, assinatura };
})();
