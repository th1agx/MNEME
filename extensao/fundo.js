// MNEME Sinais: o processo de fundo. É o único que fala com o MNEME (pelo túnel SSH); a página da corretora nunca recebe a chave.
const SITE_PADRAO = "http://127.0.0.1:8787"; // o túnel SSH até a VPS (colaborar/tunel-sinais.sh)

async function config() {
  const c = await chrome.storage.local.get(["site", "chave"]);
  return { site: (c.site || SITE_PADRAO).replace(/\/$/, ""), chave: c.chave || "" };
}

chrome.runtime.onMessage.addListener((pedido, _remetente, responder) => {
  (async () => {
    const { site, chave } = await config();
    if (!chave) return responder({ erro: "Configure a chave nas opções da extensão." });
    try {
      if (pedido.tipo === "sinais") {
        const r = await fetch(`${site}/api/sinais`, { headers: { "x-mneme-chave": chave }, cache: "no-store" });
        return responder(r.ok ? await r.json() : { erro: `MNEME respondeu ${r.status}` });
      }
      if (pedido.tipo === "entrada") {
        const r = await fetch(`${site}/api/sinais/entrada`, { method: "POST", headers: { "x-mneme-chave": chave, "content-type": "application/json" },
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
