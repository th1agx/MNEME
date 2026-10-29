#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -d "$1/assets" ]]; then
  echo "Uso: bash scripts/prepare-pages.sh <pasta-public-staging>" >&2
  exit 2
fi

public_dir="$(cd "$1" && pwd)"
asset_version="${GITHUB_SHA:-local-$(date -u +%Y%m%d%H%M%S)}"

# Cada publicação usa URLs novas para que o navegador não reutilize gráficos antigos.
PAGES_PUBLIC_DIR="$public_dir" PAGES_ASSET_VERSION="$asset_version" node <<'NODE'
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";

const root = process.env.PAGES_PUBLIC_DIR;
const version = process.env.PAGES_ASSET_VERSION;

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await visit(path);
      continue;
    }

    if (!entry.isFile() || !/\.(?:html|js)$/i.test(entry.name)) continue;
    let source = await readFile(path, "utf8");
    if (entry.name.endsWith(".html")) {
      source = source.replace(/((?:src|href)\s*=\s*["'])(\/assets\/[^"'?#]+)(?:\?[^"']*)?(["'])/g, `$1$2?v=${version}$3`);
    } else {
      source = source.replace(/(\bfrom\s*["'])(\.{1,2}\/[^"']+?\.js)(?:\?[^"']*)?(["'])/g, `$1$2?v=${version}$3`);
      source = source.replace(/(\bimport\s*\(\s*["'])(\.{1,2}\/[^"']+?\.js)(?:\?[^"']*)?(["'])/g, `$1$2?v=${version}$3`);
    }
    await writeFile(path, source, "utf8");
  }
}

await visit(root);
console.log(`Versão dos assets: ${version}`);
NODE

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
