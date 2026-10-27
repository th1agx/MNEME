# Acesso ao código do MNEME

O código é cifrado. Para abrir, você usa a senha que eu te mandei.

**1. Instale o Git (uma vez)**
- Windows: [Git for Windows](https://git-scm.com) (instalação padrão; ele traz o Git Bash).
- Mac: o Git vem com o Xcode (o Mac oferece instalar na primeira vez que você roda `git`) e o script usa o [Homebrew](https://brew.sh).
- Linux: `sudo apt install git`

**2. No Git Bash (ou terminal), rode:**
```bash
mkdir -p /c/dev && cd /c/dev
git clone https://github.com/th1agx/MNEME.git && cd MNEME
bash colaborar/acesso.sh
```
No Mac/Linux, troque `/c/dev` por `~/dev`.

**3. Digite seu nome e a sua senha** quando o script pedir. Pronto.

O script instala o git-crypt sozinho se faltar. Para rodar o projeto depois, você também vai precisar do [Node](https://nodejs.org) 22.9 ou mais novo; o script avisa se faltar.

A senha é só sua: não repasse e não cole em chat, e-mail ou assistente de código.
