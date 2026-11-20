// MNEME Sinais: a lógica do card, sem tocar na página. Carregada antes do conteudo.js e testada no vitest.
(function () {
  const PREPARAR_MS = 60_000; // o card aparece até 1 minuto antes da entrada
  const ENTRAR_MS = 15_000; // "entre agora" dura 15 segundos a partir do minuto de entrada

  /** Em que fase está um sinal no instante `agora` (ms). */
  function fase(sinal, agora) {
    const entrada = Date.parse(sinal.entrada_em);
    const fim = entrada + sinal.expiracao_min * 60_000;
    if (sinal.resultado) return "resultado";
    if (agora < entrada - PREPARAR_MS) return "aguardando";
    if (agora < entrada) return "preparar";
    if (agora < entrada + ENTRAR_MS) return "entrar";
    if (agora < fim) return "andamento";
    return "apurando";
  }

  /** O sinal que o card mostra: o mais recente que ainda importa, ou o resultado mais recente por 2 minutos. */
  function escolher(sinais, agora) {
    const ordenados = [...sinais].sort((a, b) => Date.parse(b.entrada_em) - Date.parse(a.entrada_em));
    for (const s of ordenados) {
      const f = fase(s, agora);
      const fim = Date.parse(s.entrada_em) + s.expiracao_min * 60_000;
      if (f === "aguardando") continue;
      if (f === "resultado" && agora - fim > 120_000) continue;
      return { sinal: s, fase: f };
    }
    return null;
  }

  /** "0:42" até a entrada, ou até o fim da expiração. */
  function contagem(sinal, f, agora) {
    const entrada = Date.parse(sinal.entrada_em);
    const alvo = f === "preparar" ? entrada : entrada + sinal.expiracao_min * 60_000;
    const s = Math.max(0, Math.round((alvo - agora) / 1000));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  /** O payout digitado em % (87 ou 87,5) vira fração (0,87). Fora de 1 a 100, não vale. */
  function payout(texto) {
    const n = Number(String(texto).replace(",", ".").replace("%", "").trim());
    return Number.isFinite(n) && n > 0 && n <= 100 ? Math.round(n * 10) / 1000 : null;
  }

  function corretora(host) {
    if (/quotex|qxbroker/.test(host)) return "quotex";
    if (/iqoption/.test(host)) return "iqoption";
    return "outra";
  }

  /** O aviso sonoro é ligado por padrão; só fica mudo quando a pessoa o desliga. */
  function somLigado(valor) {
    return valor !== false;
  }

  /** A estrutura só muda com uma vela nova, não a cada variação do preço dentro dela. */
  function chaveEstrutura(leitura) {
    return leitura && leitura.previsao ? String(leitura.previsao.vela || "") : "";
  }

  /** A primeira opção mostra tudo; cada par configurado aparece uma só vez no menu. */
  function paresDoMenu(pares) {
    const vistos = new Set();
    const validos = (pares || []).filter((par) => {
      const ativo = String(par && par.ativo || "");
      if (!ativo || vistos.has(ativo)) return false;
      vistos.add(ativo);
      return true;
    }).map((par) => ({ ativo: String(par.ativo), tempo_grafico: String(par.tempo_grafico || "") }));
    return [{ ativo: "", tempo_grafico: "" }, ...validos];
  }

  /** Limites de preço e de tempo que cabem tudo: velas, linhas visíveis e o cone. */
  function limites(l) {
    const precos = [];
    for (const v of l.velas || []) precos.push(v.max, v.min);
    for (const c of (l.previsao && l.previsao.cone) || []) precos.push(c.lo95, c.hi95);
    const lo = Math.min(...precos), hi = Math.max(...precos), folga = (hi - lo) * 0.08 || hi * 0.001;
    const passo = l.candle ? l.candle * 60_000 : 300_000;
    const tempos = (l.velas || []).map((v) => Date.parse(v.t));
    const t0 = Math.min(...tempos), tAgora = Math.max(...tempos) + passo;
    const cone = (l.previsao && l.previsao.cone) || [];
    const tFim = cone.length ? Math.max(tAgora + 60_000, Date.parse(cone[cone.length - 1].t)) : tAgora + passo;
    return { pmin: lo - folga, pmax: hi + folga, t0, t1: tFim, tAgora };
  }

  const FUTURO = 0.22; // fração da largura reservada para a previsão, com escala própria

  /** Converte preço e tempo em pixel. O passado ocupa 78% da largura e o futuro (o cone) os outros 22%. */
  function escala(lim, area) {
    const corte = area.x + area.w * (1 - FUTURO);
    return {
      corte,
      x: (t) => {
        const ms = typeof t === "string" ? Date.parse(t) : t;
        if (ms <= lim.tAgora) return area.x + (ms - lim.t0) / (lim.tAgora - lim.t0) * (corte - area.x);
        return corte + (ms - lim.tAgora) / (lim.t1 - lim.tAgora) * (area.x + area.w - corte);
      },
      y: (p) => area.y + (lim.pmax - p) / (lim.pmax - lim.pmin) * area.h,
    };
  }

  /** As linhas do painel de leitura, em português. */
  function resumo(l) {
    const p = l.previsao;
    if (!p) return [["Leitura", "sem dados"]];
    const tec = p.tecnicas || { alta: 0, baixa: 0, total: 0 };
    const leitura = tec.alta > tec.baixa ? `alta ${tec.alta}/${tec.total}` : tec.baixa > tec.alta ? `baixa ${tec.baixa}/${tec.total}` : `neutra ${tec.alta}/${tec.baixa}`;
    const faixa = p.sigma_1min ? `±${(p.sigma_1min * Math.sqrt(l.expiracao || 5) * 100).toFixed(2)}%` : "-";
    const linhas = [["Técnicas", leitura], [`Subir em ${l.expiracao} min`, `${Math.round(p.prob_sobe * 100)}%`], ["Faixa provável (68%)", faixa],
                    ["Sinal", p.direcao ? (p.direcao === "CALL" ? "▲ CALL" : "▼ PUT") : "sem sinal (abaixo do corte)"]];
    const a = l.anterior;
    if (a && a.realizado !== null && a.realizado !== undefined) {
      const acertou = (a.prob_sobe >= 0.5) === a.subiu;
      linhas.push(["Vela anterior", `${acertou ? "direção ✓" : "direção ✗"} · ${a.dentro_68 ? "dentro da faixa" : "fora da faixa"}`]);
    }
    return linhas;
  }

  /** O que o card mostra enquanto não há sinal: só o placar, sem confundir histórico com indicação atual. */
  function espera(ultimo, dia, agora) {
    const linhas = [];
    if (dia) {
      const aprovado = dia.aprovadas || dia; // compatível com o servidor anterior enquanto ele atualiza
      const teste = dia.testes;
      linhas.push(aprovado.sinais ? `Hoje · aprovadas: ${aprovado.sinais} sinais · ${aprovado.ganhos} ✓ · ${aprovado.perdas} ✗${aprovado.abertos ? ` · ${aprovado.abertos} em andamento` : ""}` : "Hoje: nenhuma indicação aprovada");
      if (teste) linhas.push(teste.sinais ? `Hoje · testes demo: ${teste.sinais} sinais · ${teste.ganhos} ✓ · ${teste.perdas} ✗${teste.abertos ? ` · ${teste.abertos} em andamento` : ""}` : "Hoje · testes demo: nenhum");
    }
    return linhas;
  }

  globalThis.MnemeLogica = { fase, escolher, contagem, payout, corretora, somLigado, chaveEstrutura, paresDoMenu, limites, escala, resumo, espera };
})();
