interface FeedEnv {
  SIGNALS_WS_URL?: string;
  SIGNALS_API_KEY?: string;
}

/** Seleciona somente os campos públicos necessários ao acompanhamento. */
export function feedOperation(value: unknown, receivedAt: number) {
  if (!value || typeof value !== "object") return null;
  const a = value as Record<string, unknown>;
  const text = (v: unknown) => typeof v === "string" ? v.slice(0, 200) : null;
  const number = (v: unknown) => typeof v === "number" && Number.isFinite(v) ? v : null;
  const time = number(a.execTs) ?? number(a.ts);
  if (a.type !== "alert" || !text(a.eventId) || (a.alertType !== "buy" && a.alertType !== "sell")
    || time === null || time < 0 || time > 8.64e15) return null;
  return {
    eventId: text(a.eventId), eventType: a.alertType, userId: text(a.userId),
    traderHandle: text(a.trader), tokenSymbol: text(a.token), chain: text(a.chain),
    amountUsd: number(a.tradeUsd) ?? number(a.usdValue), replay: a.replay === true,
    eventTime: new Date(time).toISOString(), receivedAt: new Date(receivedAt).toISOString(),
  };
}

export function createFeedHandler(connect: (url: string) => WebSocket = url => new WebSocket(url)) {
  return ({ request, env }: { request: Request; env: FeedEnv }): Response => {
    const headers = { "cache-control": "no-store" };
    if (request.method !== "GET") return Response.json({ error: "Método não permitido." }, { status: 405, headers });
    if (!env.SIGNALS_API_KEY || !env.SIGNALS_WS_URL) {
      return Response.json({ error: "Acompanhamento na nuvem ainda não configurado." }, { status: 503, headers });
    }
    let url: URL;
    try {
      url = new URL(env.SIGNALS_WS_URL);
      if (url.protocol !== "wss:") throw new Error();
      url.searchParams.set("key", env.SIGNALS_API_KEY);
    } catch {
      return Response.json({ error: "Configuração do acompanhamento inválida." }, { status: 503, headers });
    }
    let socket: WebSocket;
    try { socket = connect(url.toString()); } catch {
      return Response.json({ error: "Não foi possível conectar o feed." }, { status: 502, headers });
    }
    const encoder = new TextEncoder();
    let closed = false;
    let heartbeat: ReturnType<typeof setInterval> | undefined;
    const stop = () => {
      closed = true;
      clearInterval(heartbeat);
      try { socket.close(1000, "viewer closed"); } catch { /* conexão ainda abrindo */ }
    };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        const send = (event: string, data: unknown) => {
          if (closed) return;
          if ((controller.desiredSize ?? 0) < -200) { end(); return; }
          controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        };
        const end = () => { if (!closed) { stop(); controller.close(); } };
        send("status", { status: "conectando" });
        socket.addEventListener("open", () => {
          if (closed) { try { socket.close(); } catch {} return; }
          send("status", { status: "conectado" });
        });
        socket.addEventListener("message", message => {
          if (typeof message.data !== "string" || message.data.length > 50_000) return;
          try {
            const data = JSON.parse(message.data);
            if (data?.type === "welcome") {
              send("status", { status: "conectado", realtime: typeof data.realtime === "boolean" ? data.realtime : null,
                delaySeconds: typeof data.delaySeconds === "number" && Number.isFinite(data.delaySeconds) ? data.delaySeconds : null });
            }
            const operation = feedOperation(data, Date.now());
            if (operation) send("operation", operation);
          } catch { /* mensagens que não pertencem ao feed são ignoradas */ }
        });
        socket.addEventListener("error", end);
        socket.addEventListener("close", end);
        heartbeat = setInterval(() => { if (!closed) controller.enqueue(encoder.encode(": heartbeat\n\n")); }, 15_000);
      },
      cancel: stop,
    });
    return new Response(stream, { headers: { ...headers, "content-type": "text/event-stream", "x-content-type-options": "nosniff" } });
  };
}

export const onRequest = createFeedHandler();
