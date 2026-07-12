#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unpack_script="$project_root/scripts/unpack-project.sh"

if [[ $# -eq 0 ]]; then
  printf 'Usage: ./scripts/replace-from-chatgpt.sh [--force] <archive.zip>\n' >&2
  exit 2
fi

if command -v git >/dev/null 2>&1 && git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf '%s\n' '--- Git status before import ---'
  git -C "$project_root" status --short
  printf '\n'
fi

"$unpack_script" "$@"

if command -v git >/dev/null 2>&1 && git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf '\n%s\n' '--- Git status after import ---'
  git -C "$project_root" status --short
  printf '\n%s\n' '--- Change summary ---'
  git -C "$project_root" diff --stat
fi
