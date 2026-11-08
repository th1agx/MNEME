#!/usr/bin/env bash
# Liga ou desliga o quadro de evidências (F1, sombra) na A1 e registra a troca para o teste de liga e desliga.
# Só mexe no serviço `quadro` (--no-deps); confere que o contêiner do motor é o mesmo antes e depois.
# Uso: bash sombra.sh ligar|desligar   (agendado no crontab da A1; cronograma no plano F1 do Vault)
set -u
ACAO="${1:?ligar ou desligar}"
REGISTRO="${MNEME_SOMBRA_REGISTRO:-$HOME/lab/linha_de_base/eventos.csv}"
cd "$HOME/mneme/robo" || exit 1
mkdir -p "$(dirname "$REGISTRO")"
exec 9> "$HOME/lab/sombra.trava"
flock -w 120 9 || { echo "$(date -u +%FT%TZ),$ACAO,trava,,sem_execucao" >> "$REGISTRO"; exit 1; }

motor() { docker inspect -f '{{.Id}} {{.State.StartedAt}}' "$(docker compose ps -q motor)" 2>/dev/null; }
antes=$(motor)
case "$ACAO" in
  ligar) docker compose --profile sombra up -d --no-deps quadro >/dev/null 2>&1 ;;
  desligar) docker compose --profile sombra stop quadro >/dev/null 2>&1 ;;
  *) echo "acao invalida: $ACAO" >&2; exit 2 ;;
esac
saida=$?
sleep 10
depois=$(motor)
id_quadro=$(docker compose --profile sombra ps -aq quadro 2>/dev/null)
estado=$([ -n "$id_quadro" ] && docker inspect -f '{{.State.Status}}' "$id_quadro" 2>/dev/null || echo ausente)
[ -n "$antes" ] && [ "$antes" = "$depois" ] && motor_ok=motor_intacto || motor_ok=ALERTA_motor_mudou
echo "$(date -u +%FT%TZ),$ACAO,$saida,$estado,$motor_ok" >> "$REGISTRO"
