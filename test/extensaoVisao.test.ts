import { beforeAll, describe, expect, it } from "vitest";

type Vela = { x: number; lado: number; ab: number; fe: number; max: number; min: number };
let V: {
  detectar(d: Uint8ClampedArray, W: number, H: number): Vela[];
  pivos(v: Vela[], l?: number): { topos: { i: number; y: number }[]; fundos: { i: number; y: number }[] };
  ler(v: Vela[], frente?: number): any;
  assinatura(v: Vela[]): string;
};

beforeAll(async () => {
  await import("../extensao/visao.js");
  V = (globalThis as unknown as { MnemeVisao: typeof V }).MnemeVisao;
});

/** Pinta velas numa imagem escura, como a corretora: corpo de 20 px e pavio de 2 px no meio. */
function imagem(velas: { lado: number; ct: number; cb: number; max: number; min: number }[], W = 400, H = 300) {
  const d = new Uint8ClampedArray(W * H * 4);
  for (let i = 0; i < d.length; i += 4) d.set([20, 23, 30, 255], i);
  const pinta = (x: number, y: number, lado: number) => d.set(lado > 0 ? [70, 166, 85, 255] : [222, 95, 80, 255], (y * W + x) * 4);
  velas.forEach((v, k) => {
    const x0 = 10 + k * 30;
    for (let x = x0; x < x0 + 20; x++) for (let y = v.ct; y <= v.cb; y++) pinta(x, y, v.lado);
    for (let x = x0 + 9; x < x0 + 11; x++) for (let y = v.max; y <= v.min; y++) pinta(x, y, v.lado);
  });
  return d;
}

describe("visão da tela", () => {
  it("acha cada vela com corpo, pavio e cor", () => {
    const d = imagem([{ lado: 1, ct: 100, cb: 150, max: 90, min: 160 }, { lado: -1, ct: 110, cb: 130, max: 80, min: 140 }]);
    const v = V.detectar(d, 400, 300);
    expect(v).toHaveLength(2);
    expect(v[0]).toMatchObject({ lado: 1, ab: 150, fe: 100, max: 90, min: 160 });
    expect(v[1]).toMatchObject({ lado: -1, ab: 110, fe: 130, max: 80, min: 140 });
    expect(v[1].x - v[0].x).toBe(30);
  });

  it("ignora cor solta que não é vela", () => {
    const d = imagem([{ lado: 1, ct: 100, cb: 150, max: 90, min: 160 }]);
    d.set([70, 166, 85, 255], (5 * 400 + 300) * 4); // um ponto verde isolado
    expect(V.detectar(d, 400, 300)).toHaveLength(1);
  });

  // Zigue-zague: fundo em 2, topo em 5, fundo mais alto em 8 (em pixels, y menor é preço maior).
  const serie: Vela[] = [200, 190, 220, 180, 150, 120, 150, 170, 175, 160, 140, 130, 135].map((y, i) => ({ x: i * 10, lado: 1, ab: y + 5, fe: y, max: y - 5, min: y + 5 }));

  it("só confirma pivô com velas fechadas depois", () => {
    const { topos, fundos } = V.pivos(serie);
    expect(fundos.map((p) => p.i)).toContain(2);
    expect(topos.map((p) => p.i)).toContain(5);
    // A última vela (em formação) nunca vira pivô.
    expect([...topos, ...fundos].every((p) => p.i < serie.length - 1)).toBe(true);
  });

  it("lê linhas, estrutura e um leque que abre com o tempo", () => {
    const r = V.ler(serie, 5);
    expect(r.passo).toBe(10);
    expect(r.linhas.suporte).not.toBeNull();
    expect(r.linhas.resistencia).not.toBeNull();
    const l = r.leque;
    expect(l).toHaveLength(5);
    expect(l[4].lo68 - l[4].hi68).toBeGreaterThan(l[0].lo68 - l[0].hi68);
    expect(l.every((c: any) => c.hi95 <= c.hi68 && c.lo68 <= c.lo95)).toBe(true);
    expect(["alta", "baixa", "lateral"]).toContain(r.estrutura);
  });

  it("não lê com poucas velas e muda a assinatura só quando uma vela fecha", () => {
    expect(V.ler(serie.slice(0, 5))).toBeNull();
    const vivo = serie.map((v, i) => (i === serie.length - 1 ? { ...v, max: v.max - 7 } : v));
    expect(V.assinatura(vivo)).toBe(V.assinatura(serie));
    expect(V.assinatura(serie.slice(0, -1))).not.toBe(V.assinatura(serie));
    // A corretora reescalou o gráfico (tudo 1,3 vez maior e deslocado): a leitura não recomeça.
    const reescalada = serie.map((v) => ({ ...v, max: v.max * 1.3 + 40, min: v.min * 1.3 + 40, ab: v.ab * 1.3 + 40, fe: v.fe * 1.3 + 40 }));
    expect(V.assinatura(reescalada)).toBe(V.assinatura(serie));
  });

  it("monta a estrutura alternando topo e fundo até o preço atual", () => {
    const z = V.ler(serie).zigue as { tipo: string; y: number }[];
    expect(z.length).toBeGreaterThanOrEqual(3);
    expect(z[z.length - 1].tipo).toBe("agora");
    for (let i = 1; i < z.length - 1; i++) expect(z[i].tipo).not.toBe(z[i - 1].tipo);
  });
});
