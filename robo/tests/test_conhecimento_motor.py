from dataclasses import dataclass

import pandas as pd

from mneme.motor.conhecimento import anexar_conhecimento, chave_da_estrategia, efeito_do_contexto
from mneme.motor.diario import Diario
from mneme.motor.modalidades import Estrategia, ExpiracaoFixa

AGORA = pd.Timestamp("2026-11-07T18:00:00Z")
ESTRATEGIA = Estrategia("cripto", "ETHUSDT", 5, 5, ExpiracaoFixa(0.85))


@dataclass
class Achado:
    titulo: str
    origem: str
    confiabilidade: str
    suspeito: bool
    texto: str


class BibliotecaFalsa:
    def __init__(self, falha=False):
        self.falha, self.perguntas = falha, []

    def consultar(self, pergunta, k=3):
        if self.falha:
            raise OSError("biblioteca indisponível")
        self.perguntas.append(pergunta)
        return [Achado(f"Nota {i}", f"vault:nota-{i}.md", "media", False, "texto " * 80) for i in range(k)]


def test_conhecimento_chega_ao_motor_com_origem_e_validade(tmp_path):
    d = Diario(tmp_path / "diario.db")
    assert anexar_conhecimento(d, BibliotecaFalsa(), (ESTRATEGIA,), AGORA) == 3
    vigente = d.contexto_vigente((chave_da_estrategia(ESTRATEGIA),), AGORA + pd.Timedelta(hours=1))
    assert len(vigente) == 3 and {c["origem"] for c in vigente} == {"rag:biblioteca"}
    assert vigente[0]["valor"]["origem"].startswith("vault:") and len(vigente[0]["valor"]["trecho"]) <= 240
    assert d.contexto_vigente((chave_da_estrategia(ESTRATEGIA),), AGORA + pd.Timedelta(hours=25)) == ()
    assert d.contexto_vigente((chave_da_estrategia(ESTRATEGIA),), AGORA - pd.Timedelta(minutes=1)) == ()  # nada do futuro


def test_biblioteca_fora_do_ar_nao_quebra(tmp_path):
    d = Diario(tmp_path / "diario.db")
    assert anexar_conhecimento(d, BibliotecaFalsa(falha=True), (ESTRATEGIA,), AGORA) == 0


def _decidir(d, chave, direcao, sentimento, resultado):
    contexto = () if sentimento is None else ({"tipo": "noticia", "valor": {"sentimento": sentimento}},)
    d.registrar(chave=chave, estrategia=ESTRATEGIA.nome, mercado="cripto", ativo="ETHUSDT", modalidade="expiracao_fixa", vela=AGORA,
                decidido_em=AGORA, latencia_s=0.1, direcao=direcao, forca=0.1, expectativa=0.01, evidencia={}, motivo="", motivos_recusa=(),
                contexto=contexto, sinal={}, tipo="operada", tamanho=1.0)
    d.encerrar(chave, {"resultado": resultado, "pnl": 0.85 if resultado == "ganho" else -1.0, "preco_entrada": 1.0, "preco_saida": 1.0, "encerrado_por": "expiracao"}, AGORA)


def test_efeito_do_contexto_separa_a_favor_contra_e_sem_noticia(tmp_path):
    d = Diario(tmp_path / "diario.db")
    _decidir(d, "a", 1, 1, "ganho")
    _decidir(d, "b", -1, -1, "ganho")
    _decidir(d, "c", 1, -1, "perda")
    _decidir(d, "d", 1, None, "perda")
    _decidir(d, "e", 1, 0, "ganho")
    grupos = {g["grupo"]: g for g in efeito_do_contexto(d, "operada")}
    assert (grupos["a favor"]["decisoes"], grupos["a favor"]["acerto"]) == (2, 1.0)
    assert (grupos["contra"]["decisoes"], grupos["contra"]["acerto"]) == (1, 0.0)
    assert grupos["sem notícia"]["decisoes"] == 1 and grupos["neutra"]["decisoes"] == 1
