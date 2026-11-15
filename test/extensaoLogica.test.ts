import { beforeAll, describe, expect, it } from "vitest";

type Sinal = { entrada_em: string; expiracao_min: number; resultado: string | null; id: string };
let L: {
  fase(s: Sinal, agora: number): string; escolher(s: Sinal[], agora: number): { sinal: Sinal; fase: string } | null;
  contagem(s: Sinal, f: string, agora: number): string; payout(t: string): number | null; corretora(h: string): string;
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

  it("lê o payout em porcentagem e reconhece a corretora", () => {
    expect(L.payout("87")).toBe(0.87);
    expect(L.payout("87,5%")).toBe(0.875);
    expect(L.payout("0")).toBeNull();
    expect(L.payout("abc")).toBeNull();
    expect(L.corretora("qxbroker.com")).toBe("quotex");
    expect(L.corretora("iqoption.com")).toBe("iqoption");
  });
});
