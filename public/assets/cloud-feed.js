// Acompanhamento independente do servidor de execução.
function startCloudFeed() {
  const events = new Map();
  const source = new EventSource("/api/feed");
  let active = false;
  const status = (text) => { $("status").textContent = text; };
  source.addEventListener("status", message => {
    const connection = JSON.parse(message.data);
    if (!active) {
      active = true;
      document.querySelector('.page-heading h1').textContent = "Mercado e operações";
      document.querySelector('.page-heading p').textContent = "Acompanhe preços e operações recebidas do feed.";
      document.querySelectorAll('.section-nav a').forEach(link => { link.hidden = link.hash !== "#mercado"; });
      const feedLink = document.createElement("a");
      feedLink.href = "#feed-operations"; feedLink.textContent = "Operações do feed";
      document.querySelector(".section-nav").append(feedLink);
      document.querySelector("#feed-operations p").textContent = "Compras e vendas recebidas dos traders disponíveis no feed. Histórico reenviado é identificado. Atualização automática enquanto a página está aberta.";
      $("modeBadge").textContent = "Acompanhamento";
      $("kill").hidden = true;
      $("alertsBtn").hidden = true;
      for (const selector of [".desk", "#ordens", "#historico"]) document.querySelector(selector).hidden = true;
      $("trades").closest("section").hidden = true;
      $("notices").textContent = "Acompanhamento na nuvem. Carteira, sugestões e execução precisam do bot conectado.";
      document.querySelector(".connection-bar .muted").textContent = "Operações do feed";
      document.querySelector(".tape").setAttribute("aria-label", "Últimas operações do feed");
      draw();
    }
    status(connection.status === "conectado"
      ? (connection.realtime === false ? `Feed conectado · atraso informado de ${connection.delaySeconds ?? "?"} s` : "Feed conectado · acompanhamento na nuvem")
      : "Conectando o acompanhamento na nuvem…");
  });
  function draw() {
    const list = [...events.values()];
    renderFeedOperations({ feedEvents: list, top: { traders: [] } });
    renderTape({ events: list });
    const traders = new Set(list.map(e => e.userId ?? e.traderHandle).filter(Boolean));
    $("overview").innerHTML = `<div><span class="muted">Operações recentes</span><h2>${list.length}</h2></div><div><span class="muted">Traders no feed recente</span><h2>${traders.size}</h2></div><div><span class="muted">Última recepção</span><h2>${list.length ? hms(list.at(-1).receivedAt) : "—"}</h2></div>`;
  }
  source.addEventListener("operation", message => {
    const event = JSON.parse(message.data);
    if (events.has(event.eventId)) return;
    events.set(event.eventId, event);
    if (events.size > 200) events.delete(events.keys().next().value);
    draw();
  });
  source.onerror = () => status(active ? "Feed desconectado · tentando reconectar…" : "Acompanhamento na nuvem aguardando configuração ou conexão.");
  window.addEventListener("pagehide", () => source.close(), { once: true });
}
