import json
from datetime import datetime, timezone

import httpx
import numpy as np
import pandas as pd
import pytest

from mneme.core.pesquisa import agenda
from mneme.core.pesquisa.arquivo import Arquivo, impressao_do_codigo
from mneme.core.pesquisa.ciclo import ciclo
from mneme.core.pesquisa.gerador import ler_resposta
from mneme.core.pesquisa.llm import Resposta, Roteador
from mneme.core.pesquisa.sandbox import SandboxLocal
from mneme.core.pesquisa.seguranca import CodigoRecusado, validar

AGORA = datetime(2026, 11, 11, 18, tzinfo=timezone.utc)

MOMENTO = """import numpy as np
import pandas as pd

def sinal(v):
    r = v["fechamento"].pct_change(5)
    s = pd.Series(0, index=v.index)
    s[r > r.rolling(240).std() * 2] = -1
    s[r < -r.rolling(240).std() * 2] = 1
    return s
"""

FUTURO = """import pandas as pd

def sinal(v):
    media_do_periodo_inteiro = v["fechamento"].mean()  # usa velas que ainda não aconteceram
    return pd.Series((v["fechamento"] > media_do_periodo_inteiro).astype(int) * 2 - 1, index=v.index)
"""


def velas(inicio="2026-01-20", n=12000, semente=2):
    rng = np.random.default_rng(semente)
    f = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    a = np.r_[f[0], f[:-1]]
    return pd.DataFrame({"abertura": a, "maxima": np.maximum(a, f) * 1.0003, "minima": np.minimum(a, f) * 0.9997, "fechamento": f,
                         "volume": rng.uniform(1, 10, n)}, index=pd.date_range(inicio, periods=n, freq="1min", tz="UTC"))


class LLMFixa:
    def __init__(self, codigo, ideia="reversão depois de esticar"):
        self.resposta = f"IDEIA: {ideia}\nMECANISMO: excesso de curto prazo volta\n```python\n{codigo}```"

    def texto(self, *_):
        return Resposta(self.resposta, "teste:fixa")


@pytest.mark.parametrize("ruim", [
    "import os\ndef sinal(v):\n    return v",
    "def sinal(v):\n    open('x')\n    return v",
    "def sinal(v):\n    return v['fechamento'].shift(-1)",
    "def sinal(v):\n    return v.__class__",
    "import pandas as pd\ndef sinal(v):\n    return pd.read_csv('x')",
    "def outra(v):\n    return v",
    "def sinal(v)\n    return v",
])
def test_seguranca_recusa_o_que_sai_do_contrato(ruim):
    with pytest.raises(CodigoRecusado):
        validar(ruim)


def test_seguranca_aceita_o_contrato():
    validar(MOMENTO)


def test_sandbox_roda_e_pega_quem_olha_o_futuro():
    v = velas(n=3000)
    ok = SandboxLocal().executar(MOMENTO, v)
    assert ok.erro is None and len(ok.sinal) == len(v) and set(ok.sinal.unique()) <= {-1, 0, 1}
    futuro = SandboxLocal().executar(FUTURO, v)
    assert futuro.olha_o_futuro and futuro.sinal is None
    quebrado = SandboxLocal().executar("def sinal(v):\n    return 1 / 0", v)
    assert quebrado.erro.startswith("ZeroDivisionError")


def test_sandbox_bloqueia_import_fora_da_lista_mesmo_se_escapar_da_checagem():
    r = SandboxLocal().executar("def sinal(v):\n    m = __import__('os')\n    return v['fechamento'] * 0", velas(n=500))
    assert r.erro and "não permitido" in r.erro


def test_le_a_resposta_da_llm():
    p = ler_resposta("IDEIA: teste\nMECANISMO: porque sim\n```python\ndef sinal(v):\n    return v\n```", "api:x")
    assert (p.ideia, p.mecanismo, p.fonte) == ("teste", "porque sim", "api:x") and p.codigo.startswith("def sinal")
    with pytest.raises(ValueError):
        ler_resposta("sem código", "api:x")


def test_roteador_cai_no_modelo_local_quando_a_api_falha_ou_nao_existe():
    def rota(pedido: httpx.Request):
        if "chat/completions" in str(pedido.url):
            return httpx.Response(500)
        return httpx.Response(200, json={"message": {"content": "local ok"}})

    cliente = httpx.Client(transport=httpx.MockTransport(rota))
    com_api = Roteador(cliente, {"MNEME_LLM_API_URL": "https://api.exemplo/v1", "MNEME_LLM_API_KEY": "k", "MNEME_LLM_API_MODELO": "m"})
    assert com_api.tem_api and com_api.texto("s", "u").fonte.startswith("local:")
    assert not Roteador(cliente, {}).tem_api


def test_agenda_passa_por_todos_os_bracos_antes_de_preferir():
    rng = np.random.default_rng(0)
    est = {}
    vistos = []
    for _ in range(len(agenda.BRACOS) * agenda.MINIMO_POR_BRACO):
        b = agenda.escolher(est, rng)
        vistos.append(b)
        est.setdefault(b, {"tentativas": 0, "promissoras": 0})["tentativas"] += 1
    assert set(vistos) == set(agenda.BRACOS) and all(est[b]["tentativas"] == agenda.MINIMO_POR_BRACO for b in agenda.BRACOS)


def test_ciclo_gera_mede_registra_e_nao_repete(tmp_path):
    arquivo = Arquivo(tmp_path / "geradas.jsonl", commit="abc1234")
    v = velas()
    primeira = ciclo(arquivo, lambda par: v, LLMFixa(MOMENTO), SandboxLocal(), np.random.default_rng(0), AGORA)
    assert primeira["fase"] == "exploracao" and primeira["etapa_falha"] is None and primeira["commit"] == "abc1234"
    assert primeira["resultado"]["sinais"] > 0 and primeira["veredito"] in ("promissora", "rejeitada")
    assert primeira["resultado"]["ate"] < "2026-02-01"
    segunda = ciclo(arquivo, lambda par: v, LLMFixa(MOMENTO), SandboxLocal(), np.random.default_rng(1), AGORA)
    assert segunda["etapa_falha"] == "repetida"
    terceira = ciclo(arquivo, lambda par: v, LLMFixa(FUTURO, "topo"), SandboxLocal(), np.random.default_rng(2), AGORA)
    assert terceira["etapa_falha"] == "olha_o_futuro"
    quarta = ciclo(arquivo, lambda par: v, LLMFixa("import os\ndef sinal(v):\n    return v"), SandboxLocal(), np.random.default_rng(3), AGORA)
    assert quarta["etapa_falha"] == "seguranca"
    resumo = arquivo.resumo_para_pesquisador()
    assert resumo["tentativas"] == 4 and len(resumo["falhas_recentes"]) == 3


def test_promissora_vai_para_a_confirmacao_em_dados_que_a_exploracao_nao_viu(tmp_path):
    arquivo = Arquivo(tmp_path / "geradas.jsonl", commit="abc1234")
    falsa = {"id": impressao_do_codigo(MOMENTO), "quando": AGORA.isoformat(), "fase": "exploracao", "braco": {"par": "ETHUSDT", "minutos": 15},
             "fonte": "teste", "ideia": "x", "mecanismo": "", "codigo": MOMENTO, "etapa_falha": None, "motivo_falha": None,
             "resultado": {"p_valor": 0.01}, "veredito": "promissora", "commit": "abc1234"}
    arquivo.caminho.write_text(json.dumps(falsa) + "\n", encoding="utf-8")
    v = velas(inicio="2026-03-01")
    linha = ciclo(arquivo, lambda par: v, LLMFixa("nunca usado"), SandboxLocal(), np.random.default_rng(0), AGORA)
    assert linha["fase"] == "confirmacao" and linha["veredito"] in ("candidata", "rejeitada") and linha["testes_ate_agora"] == 1
    assert linha["resultado"]["de"] >= "2026-03-01" and arquivo.pendentes_de_confirmacao() == []


def test_vault_resume_o_arquivo(tmp_path):
    from mneme.vault import Vault, importar_geradas
    arquivo = Arquivo(tmp_path / "geradas.jsonl", commit="abc1234")
    ciclo(arquivo, lambda par: velas(), LLMFixa(MOMENTO), SandboxLocal(), np.random.default_rng(0), AGORA)
    ciclo(arquivo, lambda par: velas(), LLMFixa("import os\ndef sinal(v):\n    return v"), SandboxLocal(), np.random.default_rng(1), AGORA)
    v = Vault(tmp_path / "vault", relogio=lambda: AGORA)
    v.iniciar()
    assert importar_geradas(v, arquivo.caminho) >= 1
    nota = (v.trabalho / "02-quantitative-research" / "hypotheses" / "E9 generativo - arquivo.md").read_text(encoding="utf-8")
    assert "2 tentativas" in nota and "seguranca 1" in nota


def test_sandbox_aceita_os_nomes_de_coluna_em_ingles_com_o_mesmo_resultado():
    """O modelo pequeno insiste em close/high; os apelidos são os mesmos dados e dão o mesmo sinal."""
    v = velas(n=800)
    pt = SandboxLocal().executar("def sinal(v):\n    r = v['fechamento'] - v['abertura']\n    return (r > 0).astype(int) - (r < 0).astype(int)", v)
    en = SandboxLocal().executar("def sinal(v):\n    r = v['close'] - v['open']\n    return (r > 0).astype(int) - (r < 0).astype(int)", v)
    assert pt.erro is None and en.erro is None and pt.sinal.equals(en.sinal)
    faixa = SandboxLocal().executar("def sinal(v):\n    return ((v['high'] - v['low']) > (v['maxima'] - v['minima']).rolling(5).mean()).astype(int)", v)
    assert faixa.erro is None


def test_sandbox_avisa_as_colunas_que_existem_quando_a_ideia_pede_outra():
    r = SandboxLocal().executar("def sinal(v):\n    return v['vwap'] * 0", velas(n=300))
    assert r.erro and "colunas disponíveis" in r.erro and "fechamento" in r.erro
