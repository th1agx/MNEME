// MNEME Sinais: o processo de fundo. É o único que fala com o MNEME (pelo túnel SSH); a página da corretora nunca recebe a chave.
const SITE_PADRAO = "http://127.0.0.1:8787"; // o túnel SSH até a VPS (colaborar/tunel-sinais.sh)

async function config() {
  const c = await chrome.storage.local.get(["site", "chave", "ativo"]);
  return { site: (c.site || SITE_PADRAO).replace(/\/$/, ""), chave: c.chave || "", ativo: String(c.ativo || "").trim() };
}

// Uma URL salva nas opções pode ficar velha (por exemplo, depois de trocar de
// computador). Nesse caso a extensão tenta uma vez o túnel local padrão. Não
// faz fallback para respostas HTTP: 401/500 precisam aparecer para a pessoa,
// pois indicam chave inválida ou problema no MNEME, não um endereço antigo.
async function requisicao(site, caminho, opcoes) {
  const destinos = site === SITE_PADRAO ? [SITE_PADRAO] : [site, SITE_PADRAO];
  let ultimoErro;
  for (const destino of destinos) {
    try {
      return await fetch(`${destino}${caminho}`, opcoes);
    } catch (erro) {
      ultimoErro = erro;
    }
  }
  throw ultimoErro || new Error("sem conexão com o MNEME");
}

// Preço ao vivo da vela que está se formando, da API pública da Binance (sem chave). Só cripto por enquanto.
async function velaAoVivo(ativo, candle) {
  if (!/USDT$/.test(ativo)) return { erro: "sem preço ao vivo para este ativo" };
  const r = await fetch(`https://api.binance.com/api/v3/klines?symbol=${ativo}&interval=${candle}m&limit=1`, { cache: "no-store" });
  if (!r.ok) return { erro: `Binance respondeu ${r.status}` };
  const [k] = await r.json();
  return { t: new Date(k[0]).toISOString(), ab: +k[1], max: +k[2], min: +k[3], fe: +k[4], agora: Date.now() };
}

chrome.runtime.onMessage.addListener((pedido, _remetente, responder) => {
  if (pedido.tipo === "ao_vivo") {
    velaAoVivo(String(pedido.ativo || ""), Number(pedido.candle) || 5).then(responder).catch(() => responder({ erro: "sem conexão com a Binance" }));
    return true;
  }
  (async () => {
    const { site, chave, ativo } = await config();
    if (pedido.tipo === "configuracao") return responder({ ativo });
    if (pedido.tipo === "selecionar_ativo") {
      await chrome.storage.local.set({ ativo: String(pedido.ativo || "").trim() });
      return responder({ ok: true });
    }
    if (!chave) return responder({ erro: "Configure a chave nas opções da extensão." });
    try {
      if (pedido.tipo === "sinais") {
        const paridade = ativo ? `?ativo=${encodeURIComponent(ativo)}` : "";
        const r = await requisicao(site, `/api/sinais${paridade}`, { headers: { "x-mneme-chave": chave }, cache: "no-store" });
        return responder(r.ok ? await r.json() : { erro: `MNEME respondeu ${r.status}` });
      }
      if (pedido.tipo === "pares") {
        const r = await requisicao(site, "/api/pares", { headers: { "x-mneme-chave": chave }, cache: "no-store" });
        return responder(r.ok ? await r.json() : { erro: `MNEME respondeu ${r.status}` });
      }
      if (pedido.tipo === "leitura") {
        const paridade = ativo ? `?ativo=${encodeURIComponent(ativo)}` : "";
        const r = await requisicao(site, `/api/leitura${paridade}`, { headers: { "x-mneme-chave": chave }, cache: "no-store" });
        return responder(r.ok ? await r.json() : { erro: `MNEME respondeu ${r.status}` });
      }
      if (pedido.tipo === "entrada") {
        const r = await requisicao(site, "/api/sinais/entrada", { method: "POST", headers: { "x-mneme-chave": chave, "content-type": "application/json" },
          body: JSON.stringify(pedido.entrada) });
        return responder(r.ok ? { ok: true } : { erro: `MNEME respondeu ${r.status}` });
      }
      responder({ erro: "pedido desconhecido" });
    } catch (e) {
      responder({ erro: "sem conexão: o túnel SSH está ligado?" });
    }
  })();
  return true; // resposta assíncrona
});
