#!/usr/bin/env bash
# Amostrador da linha de base do motor (F1), só de leitura: a cada 60 s grava CPU e memória dos contêineres e a carga da máquina.
# Uso na A1: nohup bash linha_de_base.sh ~/lab/linha_de_base > /dev/null 2>&1 &   (para com kill)
set -u
DESTINO="${1:-$HOME/lab/linha_de_base}"
mkdir -p "$DESTINO"
while true; do
  quando=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  carga=$(cut -d' ' -f1-3 /proc/loadavg)
  docker stats --no-stream --format '{{.Name}},{{.CPUPerc}},{{.MemUsage}}' | sed "s|^|$quando,$carga,|" >> "$DESTINO/docker_stats.csv"
  sleep $((60 - $(date +%s) % 60))
done
