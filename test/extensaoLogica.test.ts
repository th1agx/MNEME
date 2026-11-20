import { beforeAll, describe, expect, it } from "vitest";

type Sinal = { entrada_em: string; expiracao_min: number; resultado: string | null; id: string };
let L: {
  fase(s: Sinal, agora: number): string; escolher(s: Sinal[], agora: number): { sinal: Sinal; fase: string } | null;
  contagem(s: Sinal, f: string, agora: number): string; payout(t: string): number | null; corretora(h: string): string; somLigado(valor: unknown): boolean; chaveEstrutura(leitura: unknown): string; paresDoMenu(pares: unknown[]): { ativo: string; tempo_grafico: string }[];
};

beforeAll(async () => {
  await import("../extensao/logica.js");
  L = (globalThis as unknown as { MnemeLogica: typeof L }).MnemeLogica;
});

const s = (entrada: string, resultado: string | null = null, id = "a"): Sinal => ({ id, entrada_em: entrada, expiracao_min: 5, resultado });
const t = (iso: string) => Date.parse(iso);

describe("card da extensão", () => {
  it("passa por preparar, entrar, andamento, apurando e resultado", () => {
    const x = s("2026-11-16T14:01:00Z");
    expect(L.fase(x, t("2026-11-16T13:59:30Z"))).toBe("aguardando");
    expect(L.fase(x, t("2026-11-16T14:00:20Z"))).toBe("preparar");
    expect(L.fase(x, t("2026-11-16T14:01:05Z"))).toBe("entrar");
    expect(L.fase(x, t("2026-11-16T14:03:00Z"))).toBe("andamento");
    expect(L.fase(x, t("2026-11-16T14:06:10Z"))).toBe("apurando");
    expect(L.fase(s("2026-11-16T14:01:00Z", "ganho"), t("2026-11-16T14:06:30Z"))).toBe("resultado");
  });

  it("mostra o sinal que importa e esconde resultado velho", () => {
    const velho = s("2026-11-16T13:40:00Z", "perda", "velho");
    const atual = s("2026-11-16T14:01:00Z", null, "atual");
    expect(L.escolher([velho, atual], t("2026-11-16T14:00:30Z"))?.sinal.id).toBe("atual");
    expect(L.escolher([velho], t("2026-11-16T14:00:30Z"))).toBeNull();
  });

  it("conta o tempo até a entrada e até o fim", () => {
    const x = s("2026-11-16T14:01:00Z");
    expect(L.contagem(x, "preparar", t("2026-11-16T14:00:18Z"))).toBe("0:42");
    expect(L.contagem(x, "andamento", t("2026-11-16T14:02:00Z"))).toBe("4:00");
  });

  it("mostra o último sinal e o placar enquanto espera", () => {
    const E = (globalThis as unknown as { MnemeLogica: { espera(u: unknown, d: unknown, a: number): string[] } }).MnemeLogica.espera;
    const ultimo = { direcao: "PUT", entrada_em: "2026-11-16T22:11:00+00:00", resultado: "perda" };
    expect(E(ultimo, { aprovadas: { sinais: 20, ganhos: 11, perdas: 9, abertos: 0 }, testes: { sinais: 3, ganhos: 2, perdas: 1, abertos: 0 } }, t("2026-11-16T22:43:00Z")))
      .toEqual(["Último: ▼ PUT às 19:11 · perda ✗ · há 32 min", "Hoje · aprovadas: 20 sinais · 11 ✓ · 9 ✗", "Hoje · testes demo: 3 sinais · 2 ✓ · 1 ✗"]);
    expect(E(ultimo, null, t("2026-11-17T00:20:00Z"))[0]).toContain("há 2 h 09");
    expect(E(null, { aprovadas: { sinais: 0, ganhos: 0, perdas: 0, abertos: 0 }, testes: { sinais: 0, ganhos: 0, perdas: 0, abertos: 0 } }, 0)).toEqual(["Hoje: nenhuma indicação aprovada", "Hoje · testes demo: nenhum"]);
  });

  it("lê o payout em porcentagem e reconhece a corretora", () => {
    expect(L.payout("87")).toBe(0.87);
    expect(L.payout("87,5%")).toBe(0.875);
    expect(L.payout("0")).toBeNull();
    expect(L.payout("abc")).toBeNull();
    expect(L.corretora("qxbroker.com")).toBe("quotex");
    expect(L.corretora("iqoption.com")).toBe("iqoption");
  });

  it("mantém o som ligado por padrão e respeita quando a pessoa o desliga", () => {
    expect(L.somLigado(undefined)).toBe(true);
    expect(L.somLigado(false)).toBe(false);
  });

  it("mantém o mesmo traçado enquanto a vela atual apenas muda de preço", () => {
    expect(L.chaveEstrutura({ previsao: { vela: "2026-11-18T12:00:00Z", preco: 91_000 } })).toBe("2026-11-18T12:00:00Z");
    expect(L.chaveEstrutura({ previsao: { vela: "2026-11-18T12:00:00Z", preco: 91_250 } })).toBe("2026-11-18T12:00:00Z");
    expect(L.chaveEstrutura({ previsao: { vela: "2026-11-18T12:15:00Z", preco: 91_250 } })).toBe("2026-11-18T12:15:00Z");
  });

  it("oferece Todas e cada par configurado no menu do HUD", () => {
    expect(L.paresDoMenu([{ ativo: "EURUSD", tempo_grafico: "5m" }, { ativo: "EURJPY", tempo_grafico: "5m" }, { ativo: "EURUSD", tempo_grafico: "5m" }]))
      .toEqual([{ ativo: "", tempo_grafico: "" }, { ativo: "EURUSD", tempo_grafico: "5m" }, { ativo: "EURJPY", tempo_grafico: "5m" }]);
  });
});

describe("camada de gráfico", () => {
  const l = {
    candle: 5, expiracao: 5,
    velas: [{ t: "2026-11-16T14:00:00Z", max: 101, min: 99 }, { t: "2026-11-16T14:05:00Z", max: 102, min: 100 }],
    previsao: { prob_sobe: 0.58, direcao: "CALL", sigma_1min: 0.0005, tecnicas: { alta: 13, baixa: 4, total: 23 },
      cone: [{ t: "2026-11-16T14:11:00Z", lo95: 98, hi95: 104, lo68: 99, hi68: 103 }] },
    anterior: { prob_sobe: 0.6, subiu: true, dentro_68: true, realizado: 101 },
  };
  type Lim = { pmin: number; pmax: number; t0: number; t1: number };
  type Esc = { x(t: string | number): number; y(p: number): number };
  const G = () => (globalThis as unknown as { MnemeLogica: { limites(l: unknown): Lim; escala(l: Lim, a: unknown): Esc; resumo(l: unknown): string[][] } }).MnemeLogica;

  it("cabe velas e cone e converte para pixel", () => {
    const lim = G().limites(l);
    expect(lim.pmin).toBeLessThan(98);
    expect(lim.pmax).toBeGreaterThan(104);
    const e = G().escala(lim, { x: 0, y: 0, w: 1000, h: 500 });
    expect(e.x(lim.t0)).toBe(0);
    expect(e.y(lim.pmax)).toBe(0);
    expect(e.y(lim.pmin)).toBe(500);
    expect(e.x("2026-11-16T14:05:00Z")).toBeLessThan(e.x("2026-11-16T14:11:00Z"));
  });

  it("monta o painel de leitura", () => {
    const r = Object.fromEntries(G().resumo(l));
    expect(r["Técnicas"]).toBe("alta 13/23");
    expect(r["Subir em 5 min"]).toBe("58%");
    expect(r["Sinal"]).toBe("▲ CALL");
    expect(r["Vela anterior"]).toContain("direção ✓");
  });
});
