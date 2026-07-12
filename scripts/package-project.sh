#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_name="$(basename "$project_root")"
output="${1:-"$(dirname "$project_root")/${project_name}.zip"}"

rm -f "$output"
cd "$(dirname "$project_root")"

COPYFILE_DISABLE=1 zip -r "$output" "$project_name" \
  -x "*/.venv/*" \
     "*/.git/*" \
     "*/.pytest_cache/*" \
     "*/.ruff_cache/*" \
     "*/.mypy_cache/*" \
     "*/.coverage" \
     "*/htmlcov/*" \
     "*/__pycache__/*" \
     "*.pyc" \
     "*/.DS_Store" \
     "*/._*" \
     "*/__MACOSX/*"

printf 'Created %s\n' "$output"
