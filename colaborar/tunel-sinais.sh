#!/usr/bin/env bash
# Túnel SSH até o servidor de sinais da VPS, para o card da extensão do Chrome (extensao/LEIA-ME.md).
# A VPS não abre porta nenhuma: o serviço `sinais` escuta só em 127.0.0.1:8787 dela, e este túnel liga o
# 127.0.0.1:8787 deste computador a ele, pelo mesmo acesso SSH do `configurar.sh` (alias mneme-a1).
#
# Uso, na raiz do repositório:
#   bash colaborar/tunel-sinais.sh instalar   # macOS: fica ligado sozinho (launchd) e volta se cair
#   bash colaborar/tunel-sinais.sh remover
#   bash colaborar/tunel-sinais.sh testar      # confere se o servidor responde pelo túnel
# Em Linux ou no Git Bash do Windows, sem launchd: `bash colaborar/tunel-sinais.sh ligar` numa janela que fique aberta.
set -euo pipefail
ROTULO="com.mneme.tunel-sinais"
PLIST="$HOME/Library/LaunchAgents/$ROTULO.plist"
PORTA=8787
SSH=(ssh -N -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L "127.0.0.1:$PORTA:127.0.0.1:$PORTA" mneme-a1)

case "${1:-}" in
  instalar)
    [ "$(uname -s)" = "Darwin" ] || { echo "Sem launchd aqui: use 'bash colaborar/tunel-sinais.sh ligar'."; exit 1; }
    mkdir -p "$(dirname "$PLIST")" "$HOME/.mneme"
    {
      echo '<?xml version="1.0" encoding="UTF-8"?>'
      echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
      echo '<plist version="1.0"><dict>'
      echo "  <key>Label</key><string>$ROTULO</string>"
      echo '  <key>ProgramArguments</key><array>'
      for a in "${SSH[@]}"; do echo "    <string>$a</string>"; done
      echo '  </array>'
      echo '  <key>RunAtLoad</key><true/>'
      echo '  <key>KeepAlive</key><true/>'
      echo '  <key>ThrottleInterval</key><integer>15</integer>'
      echo "  <key>StandardErrorPath</key><string>$HOME/.mneme/tunel-sinais.log</string>"
      echo '</dict></plist>'
    } > "$PLIST"
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Túnel instalado ($ROTULO): fica ligado sozinho e volta se cair. Log: ~/.mneme/tunel-sinais.log"
    ;;
  remover)
    launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Túnel removido."
    ;;
  ligar)
    exec "${SSH[@]}"
    ;;
  testar)
    codigo=$(curl -s -m 5 -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORTA/api/sinais" || true)
    case "$codigo" in
      401) echo "ok: o servidor de sinais responde pelo túnel (pede a chave, como deve)." ;;
      200) echo "ok: o servidor responde." ;;
      *) echo "sem resposta (código $codigo): o túnel está ligado e o serviço sinais está de pé na VPS?"; exit 1 ;;
    esac
    ;;
  *)
    sed -n '2,11p' "$0"
    exit 1
    ;;
esac
