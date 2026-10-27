# Acesso ao código do MNEME

O código é cifrado. Para abrir, você cria uma chave sua e eu libero.

**1. Instale (uma vez)**
- Windows: [Git for Windows](https://git-scm.com) e o [git-crypt](https://github.com/AGWA/git-crypt/releases) (`git-crypt-0.7.0-x86_64.exe`, renomeie para `git-crypt.exe` e coloque em `C:\Program Files\Git\usr\bin`).
- Mac: `brew install gnupg git-crypt` · Linux: `sudo apt install gnupg git-crypt`

**2. No Git Bash (ou terminal), rode:**
```bash
mkdir -p /c/dev && cd /c/dev
git clone https://github.com/th1agx/MNEME.git && cd MNEME
bash colaborar/acesso.sh
```
No Mac/Linux, troque `/c/dev` por `~/dev`.

**3. Siga o que aparecer**
- Crie a senha da sua chave na janela que abrir. Guarde bem: só você a conhece.
- Publique sua chave no GitHub pelo link que o script mostrar.
- Me mande pelo WhatsApp: seu usuário do GitHub e a impressão digital que aparecer.

**4. Quando eu avisar que liberei**, rode `bash colaborar/acesso.sh` de novo e digite sua senha. Pronto.
