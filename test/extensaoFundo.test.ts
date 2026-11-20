import { beforeEach, describe, expect, it, vi } from "vitest";

type Armazenamento = Record<string, unknown>;
let dados: Armazenamento;
let Fundo: { config(): Promise<{ ativo: string }> };

beforeEach(async () => {
  vi.resetModules();
  dados = { ativo: "GBPUSD", filtro_versao: 1 };
  (globalThis as typeof globalThis & { chrome: unknown }).chrome = {
    storage: { local: {
      get: async () => ({ ...dados }),
      set: async (mudanca: Armazenamento) => { Object.assign(dados, mudanca); },
    } },
    runtime: { onMessage: { addListener: () => {} } },
  };
  await import("../extensao/fundo.js");
  Fundo = (globalThis as typeof globalThis & { MnemeFundo: typeof Fundo }).MnemeFundo;
});

describe("preferência de par da extensão", () => {
  it("volta para Todas uma vez ao migrar um filtro antigo", async () => {
    await expect(Fundo.config()).resolves.toMatchObject({ ativo: "" });
    expect(dados).toMatchObject({ ativo: "", filtro_versao: 2 });
  });
});
