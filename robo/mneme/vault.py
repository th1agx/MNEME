"""Knowledge Vault: conhecimento em Markdown, versionado em Git, navegável no Obsidian e indexado no RAG.

O Vault fica fora do caminho crítico: o motor não lê nem escreve aqui. Só uma tarefa em lote roda este módulo, e os dados operacionais são abertos em modo de leitura.
Nota não é prova. A natureza diz o que cada documento é, e a LLM nunca aprova nada: ela só cria hipótese ou conhecimento não verificado.

    python -m mneme.vault iniciar
    python -m mneme.vault ciclo
    python -m mneme.vault buscar "liquidity sweep"
    python -m mneme.vault auditar
    python -m mneme.vault verificar-backup
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .biblioteca import Biblioteca, Documento
from .config import PASTA_DADOS

ESTRUTURA = (
    "01-trading-knowledge/price-action", "01-trading-knowledge/market-structure", "01-trading-knowledge/smc-ict", "01-trading-knowledge/wyckoff", "01-trading-knowledge/fibonacci",
    "01-trading-knowledge/elliott-wave", "01-trading-knowledge/harmonic-patterns", "01-trading-knowledge/indicators", "01-trading-knowledge/volume-order-flow",
    "02-quantitative-research/hypotheses", "02-quantitative-research/experiments", "02-quantitative-research/backtests", "02-quantitative-research/models", "02-quantitative-research/validated-strategies",
    "03-market-intelligence/macroeconomics", "03-market-intelligence/geopolitical-events", "03-market-intelligence/news", "03-market-intelligence/social-intelligence",
    "04-markets/forex", "04-markets/bitcoin", "04-markets/ethereum", "04-markets/solana", "04-markets/jupiter", "04-markets/gold", "04-markets/fixed-expiry-trading",
    "05-ai-research/machine-learning", "05-ai-research/deep-learning", "05-ai-research/llm", "05-ai-research/rag", "05-ai-research/multi-agent", "05-ai-research/autonomous-learning",
    "06-trading-journal", "07-learning-evolution", "08-sources-references", "09-system-knowledge",
)
# O que cada natureza vale para quem consulta. Hipótese e nota não verificada entram no RAG, mas nunca como fonte forte.
NATUREZAS = {"referencia-externa": "media", "conhecimento-tecnico": "media", "hipotese": "baixa", "experimento": "media", "resultado-negativo": "alta", "resultado-em-validacao": "media", "estrategia-aprovada": "alta", "nao-verificado": "baixa"}
AUTORES = ("humano", "laboratorio", "sistema", "llm")
PERMITIDAS_LLM = ("hipotese", "nao-verificado")
SEM_APROVAR = "nao-verificado"
MARCA_NOTAS = "## Minhas notas"
INVALIDOS = re.compile(r'[\\/:*?"<>|#^\[\]]')
LINK = re.compile(r"\[\[([^\]|#]+)")
MINIMO_APROVACAO = 1000


class RegraDoVault(ValueError):
    """Uma nota tentou dizer mais do que pode."""


def nome_de_arquivo(titulo: str) -> str:
    return re.sub(r"\s+", " ", INVALIDOS.sub(" ", titulo)).strip()[:120]


def _hoje(agora: datetime) -> str:
    return agora.astimezone(timezone.utc).date().isoformat()


@dataclass
class Nota:
    titulo: str
    pasta: str
    natureza: str
    corpo: str
    autor: str = "sistema"
    tipo: str = "nota"
    mercados: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=list)
    fontes: list[str] = field(default_factory=list)
    relacionadas: list[str] = field(default_factory=list)
    extras: dict = field(default_factory=dict)

    @property
    def caminho(self) -> str:
        return f"{self.pasta}/{nome_de_arquivo(self.titulo)}.md"


def separar(texto: str) -> tuple[dict, str]:
    """Propriedades e corpo. Arquivo editado à mão com YAML quebrado não derruba nada: vira nota sem propriedades, e a auditoria avisa."""
    texto = texto.replace("\r\n", "\n")
    bloco = re.match(r"---\n(.*?)\n---\n?(.*)", texto, re.S)
    if not bloco:
        return {}, texto
    try:
        dados = yaml.safe_load(bloco.group(1))
    except yaml.YAMLError:
        return {}, bloco.group(2)
    return (dados if isinstance(dados, dict) else {}), bloco.group(2)


def _gravar(caminho: Path, texto: str) -> None:
    """Troca atômica: uma queda no meio nunca deixa nota pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=caminho.parent, delete=False, suffix=".tmp") as t:
        t.write(texto)
        temporario = t.name
    os.replace(temporario, caminho)


class Vault:
    def __init__(self, raiz: Path | str, relogio=lambda: datetime.now(timezone.utc)):
        self.raiz = Path(raiz)
        self.trabalho = self.raiz / "mneme-knowledge"
        self.hub = self.raiz / "hub.git"
        self.backups = self.raiz / "backups"
        self.diario_de_log = self.raiz / "vault.log"
        self.estado_arquivo = self.raiz / "estado.json"
        self.relogio = relogio

    # ---------- registro ----------

    def registrar(self, evento: str, **detalhes) -> None:
        self.raiz.mkdir(parents=True, exist_ok=True)
        with self.diario_de_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": self.relogio().isoformat(), "evento": evento, **detalhes}, ensure_ascii=False, default=str) + "\n")

    def estado(self) -> dict:
        return json.loads(self.estado_arquivo.read_text(encoding="utf-8")) if self.estado_arquivo.exists() else {}

    def guardar_estado(self, **campos) -> None:
        _gravar(self.estado_arquivo, json.dumps({**self.estado(), **campos}, ensure_ascii=False, indent=1))

    # ---------- git ----------

    def _git(self, *args: str, cwd: Path | None = None, conferir: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=cwd or self.trabalho, text=True, capture_output=True, check=conferir, timeout=120)

    def iniciar(self) -> None:
        """Pode rodar de novo sem estragar nada: só cria o que falta, e nunca sobrescreve uma nota existente."""
        self.raiz.mkdir(parents=True, exist_ok=True)
        if not self.hub.exists():
            self._git("init", "--bare", "--initial-branch=main", str(self.hub), cwd=self.raiz)
        if not self.trabalho.exists():
            self._git("clone", str(self.hub), str(self.trabalho), cwd=self.raiz)
            self._git("symbolic-ref", "HEAD", "refs/heads/main")
        self._git("config", "user.name", "MNEME")
        self._git("config", "user.email", "mneme@localhost")
        for pasta in ESTRUTURA:
            marca = self.trabalho / pasta / ".gitkeep"
            if not marca.exists():
                _gravar(marca, "")
        ignorar = self.trabalho / ".gitignore"
        if not ignorar.exists():
            _gravar(ignorar, ".obsidian/workspace*\n.obsidian/cache\n.trash/\n*.tmp\n")
        self.salvar("Estrutura do Vault")

    def salvar(self, mensagem: str) -> bool:
        self._git("add", "-A")
        if not self._git("status", "--porcelain").stdout.strip():
            return False
        self._git("commit", "-m", mensagem)
        return True

    def sincronizar(self) -> str:
        """Traz o que veio do computador e envia o que o robô fez. Se o mesmo trecho mudou dos dois lados, vale a edição humana, e o Git guarda as duas versões."""
        self._git("fetch", "origin")
        tem_remoto = self._git("rev-parse", "--verify", "-q", "origin/main", conferir=False).returncode == 0
        if tem_remoto:
            mesclar = self._git("merge", "--no-edit", "-X", "theirs", "origin/main", conferir=False)
            if mesclar.returncode != 0:
                self._git("merge", "--abort", conferir=False)
                self.registrar("conflito", detalhe=(mesclar.stdout + mesclar.stderr)[:300])
                return "conflito"
        enviar = self._git("push", "origin", "HEAD:main", conferir=False)
        if enviar.returncode != 0:
            self.registrar("envio_falhou", detalhe=enviar.stderr[:300])
            return "envio_falhou"
        return "ok"

    # ---------- notas ----------

    def escrever(self, nota: Nota) -> str:
        """Cria ou atualiza. As regras ficam aqui para valerem para qualquer autor, e o que a pessoa escreveu em 'Minhas notas' é preservado."""
        if nota.natureza not in NATUREZAS:
            raise RegraDoVault(f"Natureza desconhecida: {nota.natureza}")
        if nota.autor not in AUTORES:
            raise RegraDoVault(f"Autor desconhecido: {nota.autor}")
        if nota.autor == "llm" and nota.natureza not in PERMITIDAS_LLM:
            raise RegraDoVault("A LLM só cria hipótese ou conhecimento não verificado.")
        if nota.natureza == "estrategia-aprovada" and "aprovacao" not in nota.extras:
            raise RegraDoVault("Estratégia só é aprovada por aprovar_estrategia, com evidência.")
        if nota.pasta not in ESTRUTURA:
            raise RegraDoVault(f"Pasta fora do Vault: {nota.pasta}")
        arquivo = self.trabalho / nota.caminho
        hoje = _hoje(self.relogio())
        ligacoes = "\n".join(f"- [[{nome_de_arquivo(r)}]]" for r in nota.relacionadas)
        principal = nota.corpo.strip() + (f"\n\n## Relacionadas\n\n{ligacoes}" if ligacoes else "")
        criada, minhas = hoje, ""
        if arquivo.exists():
            antes, corpo_antes = separar(arquivo.read_text(encoding="utf-8"))
            criada = str(antes.get("created_at", hoje))
            atual, _, resto = corpo_antes.partition(MARCA_NOTAS)
            minhas = resto.strip()
            # Quem editou o corpo no Obsidian manda nessa nota: o ciclo não reescreve o que a pessoa mudou.
            if antes.get("gerado_sha") != _sha(atual) and _sha(atual) != _sha(principal):
                self.registrar("edicao_preservada", caminho=nota.caminho, autor=nota.autor)
                return nota.caminho
        propriedades = {"title": nota.titulo, "type": nota.tipo, "natureza": nota.natureza, "autor": nota.autor, "markets": nota.mercados, "timeframes": nota.timeframes, "sources": nota.fontes,
                        "related": [f"[[{nome_de_arquivo(r)}]]" for r in nota.relacionadas], "created_at": criada, "updated_at": hoje, "gerado_sha": _sha(principal), **nota.extras}
        cabecalho = yaml.safe_dump(propriedades, allow_unicode=True, sort_keys=False, default_flow_style=False)
        novo = f"---\n{cabecalho}---\n\n{principal}\n\n{MARCA_NOTAS}\n\n{minhas}\n"
        if arquivo.exists() and _sem_data(arquivo.read_text(encoding="utf-8")) == _sem_data(novo):
            return nota.caminho  # nada mudou: sem isso, cada ciclo criaria um commit só com a data
        _gravar(arquivo, novo)
        self.registrar("nota", caminho=nota.caminho, natureza=nota.natureza, autor=nota.autor)
        return nota.caminho

    def propor_da_llm(self, titulo: str, corpo: str, fontes: list[str], relacionadas: list[str] | None = None, natureza: str = "hipotese", pasta: str = "02-quantitative-research/hypotheses", mercados: list[str] | None = None) -> str:
        """O caminho da LLM. Ela propõe pesquisa, mas não aprova, e o texto dela não vira conhecimento comprovado."""
        return self.escrever(Nota(titulo, pasta, natureza, corpo, "llm", "proposta", mercados or [], [], fontes, relacionadas or []))

    def aprovar_estrategia(self, titulo: str, evidencia: dict, aprovado_por: str, corpo: str, relacionadas: list[str] | None = None) -> str:
        """Só aqui uma estratégia vira aprovada. Exige os critérios quantitativos e uma pessoa. Falta de qualquer um é recusa."""
        if not aprovado_por or aprovado_por.lower() in ("llm", "mneme", "sistema", "laboratorio"):
            raise RegraDoVault("A aprovação precisa de uma pessoa.")
        faltas = []
        if evidencia.get("operacoes", 0) < MINIMO_APROVACAO:
            faltas.append(f"menos de {MINIMO_APROVACAO} operações")
        if not evidencia.get("passou_area_selada"):
            faltas.append("sem aprovação na área selada")
        if not evidencia.get("limite_inferior_liquido", -1) > 0:
            faltas.append("limite inferior da expectativa líquida não positivo")
        if not evidencia.get("corrigido_multiplos_testes"):
            faltas.append("sem correção por múltiplos testes")
        if faltas:
            raise RegraDoVault("Não aprovada: " + "; ".join(faltas))
        return self.escrever(Nota(titulo, "02-quantitative-research/validated-strategies", "estrategia-aprovada", corpo, "humano", "estrategia", relacionadas=relacionadas or [], extras={"aprovacao": {"por": aprovado_por, "em": _hoje(self.relogio()), **evidencia}}))

    def arquivos(self) -> list[Path]:
        if not self.trabalho.exists():
            return []
        return sorted(a for a in self.trabalho.rglob("*.md") if ".obsidian" not in a.parts and ".git" not in a.parts)

    def natureza_efetiva(self, propriedades: dict) -> tuple[str, str | None]:
        """Nota editada à mão não ganha crédito sozinha: quem diz mais do que pode é tratado como não verificado, e a auditoria avisa."""
        natureza, autor = propriedades.get("natureza"), propriedades.get("autor")
        if natureza not in NATUREZAS:
            return SEM_APROVAR, "sem natureza válida"
        if autor == "llm" and natureza not in PERMITIDAS_LLM:
            return SEM_APROVAR, "a LLM não pode declarar esta natureza"
        if natureza == "estrategia-aprovada" and not (isinstance(propriedades.get("aprovacao"), dict) and propriedades["aprovacao"].get("por") and propriedades["aprovacao"].get("passou_area_selada")):
            return SEM_APROVAR, "aprovada sem evidência"
        return natureza, None

    def auditar(self) -> dict:
        nomes = {a.stem for a in self.arquivos()}
        problemas, quebrados, por_natureza = [], [], defaultdict(int)
        for a in self.arquivos():
            texto = a.read_text(encoding="utf-8", errors="replace")
            propriedades, corpo = separar(texto)
            efetiva, motivo = self.natureza_efetiva(propriedades)
            por_natureza[efetiva] += 1
            relativo = a.relative_to(self.trabalho).as_posix()
            if motivo:
                problemas.append({"nota": relativo, "motivo": motivo})
            for alvo in LINK.findall(corpo):
                if alvo.strip() not in nomes:
                    quebrados.append({"nota": relativo, "link": alvo.strip()})
        return {"notas": len(nomes), "por_natureza": dict(por_natureza), "problemas": problemas, "links_quebrados": quebrados}

    # ---------- RAG ----------

    def documentos(self) -> list[Documento]:
        docs = []
        for a in self.arquivos():
            propriedades, corpo = separar(a.read_text(encoding="utf-8", errors="replace"))
            texto = corpo.split(MARCA_NOTAS)[0].strip() + ("\n\n" + corpo.split(MARCA_NOTAS, 1)[1].strip() if MARCA_NOTAS in corpo and corpo.split(MARCA_NOTAS, 1)[1].strip() else "")
            if not texto:
                continue
            natureza, _ = self.natureza_efetiva(propriedades)
            titulo = str(propriedades.get("title") or a.stem)
            docs.append(Documento(f"[{natureza}] {titulo}", f"vault:{a.relative_to(self.trabalho).as_posix()}", "vault", f"Natureza: {natureza}.\n\n{texto}", f"vault:{natureza}", NATUREZAS[natureza], str(propriedades.get("autor") or "") or None, str(propriedades.get("updated_at") or "") or None))
        return docs

    def indexar(self, biblioteca: Biblioteca) -> dict:
        """Só o que mudou gera embedding de novo. Nota apagada ou renomeada sai do índice."""
        docs = self.documentos()
        atuais = {d.origem for d in docs}
        indexadas = {l[0] for l in biblioteca.con.execute("SELECT origem FROM documentos WHERE fonte = 'vault'")}
        for origem in indexadas - atuais:
            biblioteca.con.execute("DELETE FROM documentos WHERE id = ?", (hashlib.sha256(origem.encode()).hexdigest()[:20],))
        biblioteca.con.commit()
        return {**biblioteca.ingerir(docs, self.relogio()), "removidas": len(indexadas - atuais)}

    # ---------- backup ----------

    def fazer_backup(self, biblioteca: Path | None = None, manter: int = 14) -> Path:
        self.backups.mkdir(parents=True, exist_ok=True)
        marca = self.relogio().strftime("%Y%m%d-%H%M%S")
        destino = self.backups / f"vault-{marca}.bundle"
        self._git("bundle", "create", str(destino), "--all")
        if biblioteca and Path(biblioteca).exists():
            origem = sqlite3.connect(f"file:{biblioteca}?mode=ro", uri=True, timeout=30)
            copia = sqlite3.connect(self.backups / f"biblioteca-{marca}.db")
            with copia:
                origem.backup(copia)  # cópia consistente, mesmo com o banco em uso
            origem.close()
            copia.close()
        for padrao in ("vault-*.bundle", "biblioteca-*.db"):
            for velho in sorted(self.backups.glob(padrao))[:-manter]:
                velho.unlink()
        self.guardar_estado(ultimo_backup=self.relogio().isoformat())
        self.registrar("backup", destino=destino.name)
        return destino

    def verificar_backup(self) -> dict:
        """Backup só vale se restaurar: clona o pacote mais novo numa pasta temporária e compara com o Vault."""
        pacotes = sorted(self.backups.glob("vault-*.bundle"))
        if not pacotes:
            return {"ok": False, "motivo": "sem backup"}
        with tempfile.TemporaryDirectory() as t:
            destino = Path(t) / "restaurado"
            self._git("clone", "-q", str(pacotes[-1]), str(destino), cwd=Path(t))
            self._git("fsck", "--strict", cwd=destino)
            notas = len(list(destino.rglob("*.md")))
        bancos = sorted(self.backups.glob("biblioteca-*.db"))
        banco_ok = None
        if bancos:
            c = sqlite3.connect(f"file:{bancos[-1]}?mode=ro", uri=True)
            banco_ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            c.close()
        self._git("fsck", "--strict", cwd=self.hub)
        return {"ok": banco_ok is not False, "pacote": pacotes[-1].name, "notas_restauradas": notas, "biblioteca_integra": banco_ok}


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.strip().encode()).hexdigest()[:16]


def _sem_data(texto: str) -> str:
    return re.sub(r"^updated_at: .*$", "", texto, count=1, flags=re.M)


# ---------- importação do que o MNEME já produz ----------

def _pasta_da_tecnica(nome: str) -> str:
    n = nome.lower()
    regras = (("harm", "harmonic-patterns"), ("elliott", "elliott-wave"), ("wyckoff", "wyckoff"), ("fibonacci", "fibonacci"), (r"fvg|fair value|order block|varredura|smart money|\bict\b|liquidez|breaker|imbalance", "smc-ict"),
              (r"estrutura|rompimento|reteste|suporte|\blta\b|\bltb\b|topo|\boco\b|ombro|triângulo|bandeira|canal|tendência|padrões gráficos", "market-structure"), ("vela|candle|martelo|engolfo|falso|price action", "price-action"),
              (r"\bpoc\b|perfil|\bvsa\b|volume|fluxo|delta|order flow|agress|livro|funding|open interest", "volume-order-flow"))
    for padrao, pasta in regras:
        if re.search(padrao, n):
            return f"01-trading-knowledge/{pasta}"
    return "01-trading-knowledge/indicators"


# Nome da técnica no laboratório e nome do conceito na biblioteca nem sempre coincidem.
SINONIMOS = ((r"\bfvg\b", "Fair Value Gap"), (r"order block", "Order Block"), (r"varredura", "Varredura de liquidez"), (r"\blta\b|\bltb\b", "Linhas de tendência"), (r"vela", "Padrões de vela"), (r"rompimento|reteste", "Rompimentos e falsos rompimentos"),
             (r"topo|\boco\b|triângulo", "Padrões gráficos"), (r"\bpoc\b|\bvsa\b|perfil", "Perfil de volume"), (r"suporte", "Suporte e resistência"), (r"estrutura|tendência", "Estrutura de mercado"), (r"divergência", "RSI"))


def _conceitos_de(tecnica: str, conceitos: list[str]) -> list[str]:
    t = tecnica.lower()
    achados = [nome for padrao, nome in SINONIMOS if re.search(padrao, t) and nome in conceitos]
    palavras = set(re.findall(r"\w{3,}", t)) - {"fora", "toque", "extremo", "banda", "nuvem", "zona", "dourada", "cruzamento"}
    return list(dict.fromkeys(achados + [c for c in conceitos if palavras & set(re.findall(r"\w{3,}", c.lower()))]))[:3]


def ler_metodologias(texto: str) -> list[dict]:
    linhas, dentro = [], False
    for l in texto.replace("\r\n", "\n").splitlines():
        partes = [p.strip() for p in l.strip().strip("|").split("|")]
        # As tabelas têm 4 ou 5 colunas: a de Smart Money não traz referências. Outras tabelas do arquivo não são metodologias.
        if l.startswith("|") and partes[0] == "Metodologia":
            dentro = True
        elif not l.startswith("|"):
            dentro = False
        elif dentro and len(partes) in (4, 5) and partes[0] and not set(partes[0]) <= {"-", ":"}:
            linhas.append({"nome": partes[0], "regra": partes[1], "evidencia": partes[2], "limites": partes[3], "referencias": partes[4] if len(partes) == 5 else "Sem referência registrada."})
    return linhas


MERCADOS = (("Forex", "04-markets/forex", "Compra e venda de pares de moedas, com stop, alvo e tamanho de posição. Inclui EUR/USD, GBP/USD e USD/JPY.", ["forex"]),
            ("Ouro", "04-markets/gold", "XAU/USD, com compra e venda, stop, alvo e tamanho de posição.", ["ouro"]),
            ("Bitcoin", "04-markets/bitcoin", "BTC em mercado centralizado, com dados de velas, trades, livro, funding e open interest.", ["cripto"]),
            ("Ethereum", "04-markets/ethereum", "ETH em mercado centralizado, com os mesmos dados do Bitcoin.", ["cripto"]),
            ("Solana", "04-markets/solana", "SOL em mercado centralizado e o ecossistema Solana. Dados on-chain ainda não implementados.", ["cripto"]),
            ("Jupiter", "04-markets/jupiter", "Agregador de DEX em Solana. A estratégia de seguir traders opera nele. Modelos próprios ainda não implementados.", ["cripto"]),
            ("Expiração fixa", "04-markets/fixed-expiry-trading", "CALL ou PUT com expiração definida, estilo Quotex. O empate é 1 / (1 + payout). Primeiro sinais, apurados no simulado.", ["forex", "ouro", "cripto"]))
ATIVO_MERCADO = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana", "EURUSD": "Forex", "GBPUSD": "Forex", "USDJPY": "Forex", "XAUUSD": "Ouro"}


def importar_base(v: Vault, metodologias: Path) -> int:
    n = 0
    for titulo, pasta, corpo, mercados in MERCADOS:
        v.escrever(Nota(titulo, pasta, "conhecimento-tecnico", f"# {titulo}\n\n{corpo}", "sistema", "mercado", mercados))
        n += 1
    if metodologias.exists():
        for m in ler_metodologias(metodologias.read_text(encoding="utf-8")):
            corpo = f"# {m['nome']}\n\n## Como o MNEME usa\n\n{m['regra']}\n\n## Evidência da literatura\n\n{m['evidencia']}\n\n## Limitações\n\n{m['limites']}\n\n## Referências\n\n{m['referencias']}"
            v.escrever(Nota(m["nome"], _pasta_da_tecnica(m["nome"]), "conhecimento-tecnico", corpo, "sistema", "trading-concept", ["cripto", "forex", "ouro"], fontes=[m["referencias"]]))
            n += 1
    return n


def _conceitos(v: Vault) -> list[str]:
    return [a.stem for a in v.arquivos() if a.parts[-3:-2] == ("01-trading-knowledge",) or "01-trading-knowledge" in a.parts]


def importar_tecnicas(v: Vault, pasta_lab: Path) -> int:
    """Cada técnica medida vira um resultado, positivo ou negativo. Passar da correção é só 'em validação': aprovar exige a área selada e uma pessoa."""
    conceitos, n = _conceitos(v), 0
    for arquivo, rotulo, mercados, ligacoes in (("tecnicas.json", "cripto", ["cripto"], ["Bitcoin", "Ethereum", "Solana"]), ("tecnicas_forex.json", "Forex e ouro", ["forex", "ouro"], ["Forex", "Ouro"])):
        caminho = pasta_lab / arquivo
        if not caminho.exists():
            continue
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for r in dados.get("resumo", []):
            melhor = r.get("melhor") or {}
            natureza = "resultado-em-validacao" if r.get("corrigidas", 0) > 0 else "resultado-negativo"
            corpo = (f"# Resultado em {rotulo}: {r['tecnica']}\n\nMedido no laboratório, sem a área selada, contra o empate de {dados['empate']:.2%} (payout hipotético de {dados['payout']:.0%}). Não é aprovação.\n\n"
                     f"| Medida | Valor |\n|---|---:|\n| Medições | {r['medicoes']} |\n| Sinais | {r['sinais']} |\n| Acerto geral | {r['acerto']:.2%} |\n| Medições acima de 50% | {r['acima_de_50']} |\n| Passaram do empate após correção | {r['corrigidas']} |\n"
                     f"| Melhor caso | {melhor.get('par', '')} {melhor.get('tempo', '')} / {melhor.get('horizonte', '')} min: {melhor.get('acerto', 0):.2%} em {melhor.get('sinais', 0)} sinais |\n")
            v.escrever(Nota(f"Resultado em {rotulo} - {r['tecnica']}", "02-quantitative-research/backtests", natureza, corpo, "laboratorio", "backtest", mercados, relacionadas=_conceitos_de(r["tecnica"], conceitos) + ligacoes, extras={"acerto": round(r["acerto"], 4), "corrigidas": r["corrigidas"]}))
            n += 1
    return n


def importar_experimentos(v: Vault, registro: Path) -> int:
    """O registro continua sendo a fonte. Aqui cada família vira uma nota consultável, e cada estratégia do motor, uma nota própria. Nada se perde: resultado negativo também entra."""
    if not registro.exists():
        return 0
    grupos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for linha in registro.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(linha)
        except json.JSONDecodeError:
            continue
        chave = e["parametros"].get("estrategia", e["nome"]) if e["familia"] == "motor" else e["nome"]
        grupos[(e["familia"], chave)].append(e)
    n = 0
    for (familia, nome), lista in grupos.items():
        if familia == "tecnicas":
            continue  # já resumidas por técnica em importar_tecnicas
        ultimo = lista[-1]
        amostra = json.dumps(ultimo["resultado"], ensure_ascii=False, default=str)[:1500]
        parametros = json.dumps(ultimo["parametros"], ensure_ascii=False, default=str)[:500]
        corpo = (f"# Experimento: {familia} - {nome}\n\nRegistrado {len(lista)} vez(es), de {lista[0]['quando'][:10]} a {ultimo['quando'][:10]}.\n\n## Parâmetros da última execução\n\n`{parametros}`\n\n"
                 f"## Dados\n\nImpressão digital: `{ultimo.get('dados', '')}`. Commit: `{ultimo.get('commit', '')}`.\n\n## Último resultado\n\n```json\n{amostra}\n```\n\nFonte completa: `dados/laboratorio/experimentos.jsonl`.")
        natureza, relacionadas, mercados = "experimento", [], []
        if familia == "motor":
            expectativa = ultimo["resultado"].get("expectativa")
            natureza = "resultado-em-validacao" if expectativa is not None and expectativa > 0 else "resultado-negativo"
            ativo = str(nome).split("|")[0]
            if ativo in ATIVO_MERCADO:
                relacionadas.append(ATIVO_MERCADO[ativo])
            if "expiracao_fixa" in str(nome):
                relacionadas.append("Expiração fixa")
            mercados = [ultimo["resultado"].get("mercado", "")] if ultimo["resultado"].get("mercado") else []
        v.escrever(Nota(f"Experimento {familia} - {nome}", "02-quantitative-research/experiments", natureza, corpo, "laboratorio", "experimento", mercados, relacionadas=relacionadas, extras={"execucoes": len(lista)}))
        n += 1
    return n


def importar_hipoteses(v: Vault, fila: Path) -> int:
    """Ciclo de aprendizado (mneme.aprendizado): cada hipótese testada vira uma nota, com o veredito do laboratório."""
    if not fila.exists():
        return 0
    n = 0
    for linha in fila.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(linha)
        except json.JSONDecodeError:
            continue
        h, r = e["hipotese"], e["resultado"]
        candidata = e["veredito"] == "candidata"
        corpo = (f"# Hipótese: {h['setup']} com filtro {h['filtro']}\n\n{h['par']}, aposta de {h['minutos']} min. Proposta por: {h['origem']}. Motivo: {h['motivo'] or 'não informado'}.\n\n"
                 f"## Resultado do laboratório\n\n| Medida | Valor |\n|---|---|\n| Sinais | {r['sinais']} |\n| Acerto com o filtro | {r['acerto']:.2%} |\n"
                 f"| Acerto sem o filtro | {r['acerto_sem_filtro']:.2%} |\n| Com 1 min de atraso | {r['acerto_com_atraso_1min']:.2%} |\n| Placebo | {r['placebo']:.2%} |\n"
                 f"| Empate | {r['empate']:.2%} |\n| p ajustado (Holm, {e['testes_ate_agora']} hipóteses) | {e['p_ajustado']:.3f} |\n\nDados de {r['de'][:10]} a {r['ate'][:10]}. Testada em {e['quando'][:16]}.\n\n"
                 f"## Veredito\n\n{'**Candidata.** Passou em tudo nos dados de desenvolvimento. Ainda precisa da área selada e da aprovação de uma pessoa.' if candidata else '**Rejeitada.** Não passou em pelo menos um critério; o resultado fica registrado para não ser testado de novo.'}")
        mercado = {"BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "SOLUSDT": "Solana"}.get(h["par"])
        v.escrever(Nota(f"Hipótese {h['setup']} com {h['filtro'].replace('_', ' ')} em {h['par']} {h['minutos']} min", "02-quantitative-research/hypotheses",
                        "resultado-em-validacao" if candidata else "resultado-negativo", corpo, "laboratorio", "experimento", ["cripto"], [f"{h['minutos']}min"],
                        relacionadas=[x for x in (mercado, "Ciclo de aprendizado") if x], extras={"veredito": e["veredito"], "origem": h["origem"]}))
        n += 1
    return n


def anexar_conhecimento_ao_motor(dados: Path, biblioteca: Biblioteca, agora: datetime) -> int:
    """E7: o motor recebe, como contexto rastreável, o que a biblioteca sabe de cada estratégia. Ele registra, não obedece."""
    import pandas as pd

    from .motor.conhecimento import anexar_conhecimento
    from .motor.diario import Diario
    from .motor.modalidades import carregar_configuracao
    config = carregar_configuracao(dados / "operacao.json")
    if config is None or not (dados / "operacao" / "diario.db").exists():
        return 0
    return anexar_conhecimento(Diario(dados / "operacao" / "diario.db"), biblioteca, config.estrategias, pd.Timestamp(agora))


def escrever_resumo_do_quadro(v: Vault, banco: Path, agora: datetime) -> int:
    """F1: o que o quadro de evidências registrou nos últimos 7 dias. Só descritivo; lido sem escrever no banco do quadro."""
    if not banco.exists():
        return 0
    from types import SimpleNamespace

    from .quadro.relatorio import resumo
    con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        dias = [resumo(SimpleNamespace(con=con), f"{agora - timedelta(days=i):%Y-%m-%d}") for i in range(7)]
    finally:
        con.close()
    linhas = []
    for d in dias:
        if not d["oportunidades"]:
            continue
        falhas = sum(p["n"] for p in d["pedidos"] if p["situacao"] in ("erro", "tempo_esgotado"))
        total = sum(p["n"] for p in d["pedidos"]) or 1
        linhas.append(f"| {d['dia']} | {d['oportunidades']} | {d['ligadas_ao_motor']} | {d['por_estado'].get('apurada', 0)} | {falhas / total:.2%} | {d['com_conflito']} |")
    fontes = []
    for nome, f in (dias[1] if len(dias) > 1 else dias[0])["fontes"].items():
        fontes.append(f"| {nome} | {f['n']} | {f['acerto']:.1%} | {f['ic95'][0]:.1%} a {f['ic95'][1]:.1%} |")
    corpo = ("# Quadro de evidências: resumo\n\nF1 em sombra: o quadro só registra; não decide nem opera. Plano em [[Plano F1 - quadro de evidências]].\n\n"
             "| Dia (UTC) | Oportunidades | Ligadas ao motor | Apuradas | Falhas de especialista | Com conflito |\n|---|---:|---:|---:|---:|---:|\n" + "\n".join(linhas) +
             "\n\n## Poder de cada fonte sozinha (dia anterior, só descritivo)\n\n| Fonte | Direções apuradas | Acerto | IC 95% |\n|---|---:|---:|---|\n" + "\n".join(fontes) +
             "\n\nAusentes: " + "; ".join(dias[0]["ausentes"]) + ".")
    v.escrever(Nota("Quadro de evidências - resumo", "09-system-knowledge", "experimento", corpo, "laboratorio", "experimento", ["cripto"],
                    relacionadas=["Plano F1 - quadro de evidências"]))
    return 1


def escrever_efeito_do_contexto(v: Vault, diario: Path) -> int:
    """E8: a nota que diz se a notícia ajudou ou atrapalhou as decisões já apuradas."""
    if not diario.exists():
        return 0
    from .motor.conhecimento import efeito_do_contexto
    from .motor.diario import Diario
    d = Diario(diario)
    linhas = []
    for tipo in ("operada", "sombra"):
        for g in efeito_do_contexto(d, tipo):
            acerto = "-" if not g["decisoes"] else f"{g['acerto']:.1%}"
            ic = "-" if not g["decisoes"] else f"{g['ic95'][0]:.1%} a {g['ic95'][1]:.1%}"
            linhas.append(f"| {tipo} | {g['grupo']} | {g['decisoes']} | {acerto} | {ic} |")
    corpo = ("# Efeito das notícias nas decisões do motor\n\nAcerto das decisões já apuradas, separado pela relação entre o sentimento das notícias vigentes e a direção da decisão. "
             "Empates não contam. O contexto só pode passar a pesar na decisão se \"a favor\" ficar acima de \"contra\" com os intervalos separados, numa amostra grande.\n\n"
             "| Decisão | Notícia | Decisões | Acerto | IC 95% |\n|---|---|---:|---:|---|\n" + "\n".join(linhas))
    v.escrever(Nota("Efeito das notícias nas decisões", "09-system-knowledge", "experimento", corpo, "laboratorio", "experimento", ["cripto", "forex"],
                    relacionadas=["Ciclo de aprendizado"]))
    return 1


def escrever_atribuicao_e9(v: Vault, diario: Path, mercado: Path) -> int:
    """E9 v2 (A1): onde o motor acerta e onde erra, por dimensão. Só descritivo: gera perguntas para hipóteses, não aprova nada."""
    if not diario.exists():
        return 0
    import pandas as pd

    from .dados.armazem import ArmazemVelas
    from .e9.atribuicao import atribuir
    from .e9.dossie import montar_dossie
    from .e9.regua import ATUAL, REGUAS, amostra_minima

    x = montar_dossie(diario, ArmazemVelas(mercado))
    if x.empty:
        return 0
    regua = REGUAS[ATUAL]
    minimo = amostra_minima(regua, float(x["payout"].dropna().median()) if x["payout"].notna().any() else 0.85, familia=1)
    nomes = {"estrategia": "Estratégia", "ativo": "Ativo", "horizonte": "Horizonte (min)", "faixa_hora": "Faixa de horário (UTC)",
             "vol_quintil": "Volatilidade da última hora (quintil nos 7 dias anteriores)", "noticia": "Notícia em relação à direção",
             "forca_quintil": "Força do sinal (quintil dentro da estratégia)", "motivo_recusa": "Motivo de ficar em sombra"}
    secoes = []
    for modalidade, base_mod in x.groupby("modalidade"):
        for tipo, base in base_mod.groupby("tipo"):
            secoes.append(f"## {modalidade}, {tipo} ({len(base)} decisões)")
            for dimensao, titulo in nomes.items():
                if dimensao == "motivo_recusa" and tipo != "sombra":
                    continue
                t = atribuir(base, dimensao, regua)
                linhas = [f"| {_sanear(r['valor']).replace('|', ' · ')} | {r['decisoes']} | {r['velas']} | {r['dias']} | "
                          f"{'-' if pd.isna(r['acerto']) else f'{r.acerto:.1%}'} | "
                          f"{'-' if pd.isna(r['ic95_baixo']) else f'{r.ic95_baixo:.1%} a {r.ic95_alto:.1%}'} | {'-' if pd.isna(r['empate']) else f'{r.empate:.1%}'} | "
                          f"{r['expectativa_por_unidade']:+.3f} | {r['leitura']} |" for _, r in t.iterrows()]
                secoes.append(f"### {titulo}\n\n| Valor | Decisões | Velas | Dias | Acerto | IC 95% | Empate | Expectativa/unid. | Leitura |\n"
                              "|---|---:|---:|---:|---:|---|---:|---:|---|\n" + "\n".join(linhas))
    inicio, fim = x["vela"].min(), x["vela"].max()
    corpo = (f"# E9: onde o motor acerta e onde erra\n\nDossiê de {len(x)} decisões encerradas, de {inicio:%d/%m %H:%M} a {fim:%d/%m %H:%M} UTC. "
             f"**Tudo aqui é exploratório:** um recorte que parece bom ou ruim vira pergunta para o E9, nunca conclusão. "
             f"Melhoria só com hipótese registrada antes e teste na régua {regua.versao} ({regua.impressao()}), que pede ao menos "
             f"{minimo} velas independentes para um efeito de {regua.efeito_minimo:.0%} acima do empate.\n\n"
             "A amostra efetiva é o número de **velas** distintas (decisões na mesma vela andam juntas), e o intervalo é o mais largo entre "
             "o de Wilson e o que sorteia dias inteiros. Com poucos dias, o intervalo por dias é instável: só semanas de dado o estreitam. "
             "Volatilidade e notícia usam só o que se sabia no momento da decisão. Plano em [[Plano E9 v2 - aprendizado contínuo]].\n\n"
             + "\n\n".join(secoes))
    v.escrever(Nota("E9 - onde o motor acerta e erra", "09-system-knowledge", "experimento", corpo, "laboratorio", "experimento", ["cripto"],
                    relacionadas=["Plano E9 v2 - aprendizado contínuo", "Efeito das notícias nas decisões"]))
    return 1


def importar_diario(v: Vault, diario: Path) -> int:
    """Lê o diário operacional em modo de leitura, sem nenhuma trava sobre ele. O Markdown só resume: o banco continua sendo a fonte."""
    if not diario.exists():
        return 0
    c = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    try:
        n = 0
        for (dia,) in c.execute("SELECT DISTINCT dia FROM decisoes ORDER BY dia").fetchall():
            linhas = c.execute("SELECT estrategia, tipo, COUNT(*) n, SUM(resultado = 'ganho') g, SUM(resultado = 'perda') p, ROUND(COALESCE(SUM(pnl), 0), 2) r FROM decisoes WHERE dia = ? GROUP BY 1, 2 ORDER BY 2, 1", (dia,)).fetchall()
            tabela = "\n".join(f"| {l['estrategia']} | {l['tipo']} | {l['n']} | {l['g'] or 0} | {l['p'] or 0} | {l['r']} |" for l in linhas)
            corpo = f"# Diário de {dia}\n\nOperações simuladas. Poucas operações não são evidência.\n\n| Estratégia | Tipo | Decisões | Ganhos | Perdas | Resultado |\n|---|---|---:|---:|---:|---:|\n{tabela}\n\nFonte: `dados/operacao/diario.db`."
            v.escrever(Nota(f"Diário {dia}", "06-trading-journal", "experimento", corpo, "laboratorio", "diario"))
            n += 1
        return n
    finally:
        c.close()


def _sanear(texto: str) -> str:
    """Texto de fora não cria link nem bloco de propriedades."""
    return re.sub(r"\s+", " ", str(texto).replace("[[", "(").replace("]]", ")").replace("---", "-")).strip()


def importar_noticias(v: Vault, diario: Path) -> int:
    """A leitura da LLM entra como não verificada, citando a evidência. Ela informa e não prova nada."""
    if not diario.exists():
        return 0
    c = sqlite3.connect(f"file:{diario}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    try:
        por_dia: dict[str, list] = defaultdict(list)
        for l in c.execute("SELECT * FROM contexto WHERE tipo = 'noticia' ORDER BY criado_em"):
            por_dia[l["criado_em"][:10]].append(l)
    finally:
        c.close()
    for dia, linhas in por_dia.items():
        itens = []
        for l in linhas:
            d = json.loads(l["valor"])
            itens.append(f"- **{l['ativo']}**, sentimento {d.get('sentimento')}: {_sanear(d.get('titulo', ''))}\n  - Evidência: \"{_sanear(d.get('evidencia', ''))}\"\n  - Origem: {_sanear(l['origem'])}")
        v.escrever(Nota(f"Leitura de notícias {dia}", "03-market-intelligence/news", "nao-verificado", f"# Leitura de notícias {dia}\n\nLeitura da LLM, conferida só quanto à citação literal. Não é conhecimento comprovado.\n\n" + "\n".join(itens), "llm", "noticias"))
    return len(por_dia)


def importar_fontes(v: Vault, biblioteca: Biblioteca) -> int:
    """Um índice por fonte. Os textos continuam no RAG: copiá-los aqui duplicaria milhares de páginas."""
    n = 0
    for l in biblioteca.con.execute("SELECT fonte, COUNT(*) c, MIN(confiabilidade) f, MAX(coletado_em) u FROM documentos WHERE fonte != 'vault' GROUP BY fonte").fetchall():
        v.escrever(Nota(f"Fonte {l['fonte']}", "08-sources-references", "referencia-externa", f"# Fonte: {l['fonte']}\n\n{l['c']} documentos indexados no RAG. Confiabilidade: {l['f']}. Última coleta: {l['u'][:10]}.\n\nOs textos ficam na biblioteca. Consulte com `python -m mneme.vault buscar`.", "sistema", "fonte"))
        n += 1
    return n


def escrever_auditoria(v: Vault) -> dict:
    r = v.auditar()
    linhas = [f"- {k}: {c}" for k, c in sorted(r["por_natureza"].items())]
    problemas = [f"- `{p['nota']}`: {p['motivo']}" for p in r["problemas"][:50]] or ["Nenhum."]
    quebrados = [f"- `{q['nota']}`: {_sanear(q['link'])}" for q in r["links_quebrados"][:50]] or ["Nenhum."]
    v.escrever(Nota("Auditoria do Vault", "09-system-knowledge", "conhecimento-tecnico", f"# Auditoria do Vault\n\n{r['notas']} notas.\n\n## Por natureza\n\n" + "\n".join(linhas) + "\n\n## Notas que dizem mais do que podem\n\nSão tratadas como não verificadas no RAG.\n\n" + "\n".join(problemas) + "\n\n## Links quebrados\n\n" + "\n".join(quebrados), "sistema", "auditoria"))
    return r


def ciclo(v: Vault, dados: Path, biblioteca: Biblioteca, backup_a_cada: timedelta = timedelta(days=1)) -> dict:
    """Um ciclo completo, com trava para nunca rodar dois ao mesmo tempo. Cada etapa falha sozinha, e nada aqui toca o robô."""
    v.raiz.mkdir(parents=True, exist_ok=True)
    with (v.raiz / "ciclo.trava").open("w") as trava:
        try:
            fcntl.flock(trava, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"situacao": "ja_rodando"}
        v.iniciar()
        resumo: dict = {"sync_inicio": v.sincronizar()}
        metodologias = Path(__file__).resolve().parents[1] / "conhecimento" / "metodologias.md"
        for nome, tarefa in (("base", lambda: importar_base(v, metodologias)), ("tecnicas", lambda: importar_tecnicas(v, dados / "laboratorio")), ("experimentos", lambda: importar_experimentos(v, dados / "laboratorio" / "experimentos.jsonl")),
                             ("diario", lambda: importar_diario(v, dados / "operacao" / "diario.db")), ("noticias", lambda: importar_noticias(v, dados / "operacao" / "diario.db")), ("fontes", lambda: importar_fontes(v, biblioteca)),
                             ("hipoteses", lambda: importar_hipoteses(v, dados / "aprendizado" / "hipoteses.jsonl")),
                             ("efeito_contexto", lambda: escrever_efeito_do_contexto(v, dados / "operacao" / "diario.db")),
                             ("quadro", lambda: escrever_resumo_do_quadro(v, dados / "quadro" / "quadro.db", v.relogio())),
                             ("e9_atribuicao", lambda: escrever_atribuicao_e9(v, dados / "operacao" / "diario.db", dados / "mercado"))):
            try:
                resumo[nome] = tarefa()
            except (OSError, ValueError, KeyError, sqlite3.Error) as erro:
                resumo[nome] = f"falhou: {erro}"
                v.registrar("etapa_falhou", etapa=nome, erro=str(erro))
        auditoria = escrever_auditoria(v)
        resumo["notas"] = auditoria["notas"]
        v.salvar(f"Ciclo do MNEME {v.relogio():%Y-%m-%d %H:%M}")
        resumo["sync_fim"] = v.sincronizar()
        atual = v._git("rev-parse", "HEAD").stdout.strip()
        if atual != v.estado().get("indexado"):
            try:
                resumo["rag"] = v.indexar(biblioteca)
                v.guardar_estado(indexado=atual)  # só marca depois de terminar: se cair no meio, indexa de novo no próximo ciclo
            except (OSError, sqlite3.Error, ValueError) as erro:
                resumo["rag"] = f"falhou: {erro}"
                v.registrar("rag_falhou", erro=str(erro))
        anexado = v.estado().get("conhecimento_motor")
        if not anexado or v.relogio() - datetime.fromisoformat(anexado) >= timedelta(hours=1):
            try:
                resumo["conhecimento_motor"] = anexar_conhecimento_ao_motor(dados, biblioteca, v.relogio())
                v.guardar_estado(conhecimento_motor=v.relogio().isoformat())
            except (OSError, sqlite3.Error, ValueError, KeyError) as erro:
                resumo["conhecimento_motor"] = f"falhou: {erro}"
        ultimo = v.estado().get("ultimo_backup")
        if not ultimo or v.relogio() - datetime.fromisoformat(ultimo) >= backup_a_cada:
            v.fazer_backup(biblioteca.caminho)
            resumo["backup"] = True
        v.registrar("ciclo", **resumo)
        return resumo


def main() -> None:
    parser = argparse.ArgumentParser(prog="mneme.vault")
    parser.add_argument("comando", choices=["iniciar", "ciclo", "buscar", "auditar", "backup", "verificar-backup", "reindexar"])
    parser.add_argument("texto", nargs="?")
    parser.add_argument("--tudo", action="store_true", help="Busca em toda a biblioteca, não só no Vault")
    parser.add_argument("--dados", default=str(Path(os.getenv("MNEME_DADOS_MERCADO", str(PASTA_DADOS / "mercado"))).parent))
    args = parser.parse_args()
    dados = Path(args.dados)
    v = Vault(dados / "vault")
    banco = dados / "conhecimento" / "biblioteca.db"
    if args.comando == "iniciar":
        v.iniciar()
        print(json.dumps(v.auditar(), ensure_ascii=False))
    elif args.comando == "ciclo":
        print(json.dumps(ciclo(v, dados, Biblioteca(banco)), ensure_ascii=False, default=str))
    elif args.comando == "buscar":
        for r in Biblioteca(banco).consultar(args.texto or "", k=5, fonte=None if args.tudo else "vault"):
            print(json.dumps({"titulo": r.titulo, "origem": r.origem, "natureza": r.categoria, "confiabilidade": r.confiabilidade, "suspeito": r.suspeito, "texto": r.texto[:200]}, ensure_ascii=False))
    elif args.comando == "auditar":
        print(json.dumps(v.auditar(), ensure_ascii=False, indent=1))
    elif args.comando == "backup":
        print(v.fazer_backup(banco))
    elif args.comando == "verificar-backup":
        print(json.dumps(v.verificar_backup(), ensure_ascii=False))
    else:
        print(json.dumps(v.indexar(Biblioteca(banco)), ensure_ascii=False))


if __name__ == "__main__":
    main()
