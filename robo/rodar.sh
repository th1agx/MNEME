#!/usr/bin/env bash
# Só para desenvolvimento: roda o robô de traders uma vez no Mac, num banco separado.
# O robô de verdade roda na Oracle (serviço `traders` do compose.yaml) e não depende deste computador.
set -euo pipefail
cd "$(dirname "$0")"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
export MNEME_BANCO="${MNEME_BANCO:-$PWD/dados/desenvolvimento.db}"
echo "Desenvolvimento: banco $MNEME_BANCO. A operação real está na Oracle."
exec "$UV" run python -m mneme
