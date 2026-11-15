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

  globalThis.MnemeLogica = { fase, escolher, contagem, payout, corretora };
})();
