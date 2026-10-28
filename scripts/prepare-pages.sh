#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -d "$1/assets" ]]; then
  echo "Uso: bash scripts/prepare-pages.sh <pasta-public-staging>" >&2
  exit 2
fi

public_dir="$(cd "$1" && pwd)"
shopt -s nullglob
files=("$public_dir"/assets/*.js)

for file in "${files[@]}"; do
  minified="$(mktemp --suffix=.js)"
  trap 'rm -f "$minified"' EXIT
  esbuild "$file" --minify --outfile="$minified" >/dev/null
  javascript-obfuscator "$minified" \
    --output "$file" \
    --compact true \
    --string-array true \
    --rename-globals false >/dev/null
  rm -f "$minified"
  trap - EXIT
done

echo "Preparados ${#files[@]} arquivos JavaScript ofuscados em $public_dir/assets."
