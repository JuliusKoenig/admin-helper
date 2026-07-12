#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./scripts/unpack-project.sh [--force] <archive.zip>

Extract an archive into this project and overwrite matching files.
Local .git and .venv directories are always preserved.

Options:
  -f, --force  Continue without prompting when the Git working tree is dirty.
  -h, --help   Show this help.
USAGE
}

force=false
archive_argument=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--force)
      force=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -* )
      printf 'Unknown option: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "$archive_argument" ]]; then
        printf 'Only one ZIP archive may be supplied.\n\n' >&2
        usage >&2
        exit 2
      fi
      archive_argument="$1"
      ;;
  esac
  shift
done

if [[ -z "$archive_argument" ]]; then
  usage >&2
  exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$project_root/pyproject.toml" ]]; then
  printf 'Refusing to continue: %s does not look like the project root.\n' "$project_root" >&2
  exit 1
fi

archive_directory="$(cd "$(dirname "$archive_argument")" 2>/dev/null && pwd)" || {
  printf 'Archive directory does not exist: %s\n' "$(dirname "$archive_argument")" >&2
  exit 1
}
archive="$archive_directory/$(basename "$archive_argument")"

if [[ ! -f "$archive" ]]; then
  printf 'Archive not found: %s\n' "$archive" >&2
  exit 1
fi

case "$archive" in
  *.zip|*.ZIP) ;;
  *)
    printf 'Expected a .zip archive: %s\n' "$archive" >&2
    exit 1
    ;;
esac

if command -v git >/dev/null 2>&1 && git -C "$project_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git -C "$project_root" status --porcelain)" && "$force" != true ]]; then
    printf 'The Git working tree contains uncommitted changes:\n\n'
    git -C "$project_root" status --short
    printf '\nContinue and overwrite matching files? [y/N] '
    read -r answer
    case "$answer" in
      y|Y|yes|YES|Yes) ;;
      *)
        printf 'Aborted.\n'
        exit 1
        ;;
    esac
  fi
fi

if ! unzip -tq "$archive" >/dev/null; then
  printf 'Archive validation failed: %s\n' "$archive" >&2
  exit 1
fi

temporary_directory="$(mktemp -d "${TMPDIR:-/tmp}/admin-helper-unpack.XXXXXX")"
cleanup() {
  rm -rf "$temporary_directory"
}
trap cleanup EXIT INT TERM

unzip -q "$archive" -d "$temporary_directory"

# Ignore metadata entries when deciding whether the archive has one wrapper directory.
top_level_count="$(find "$temporary_directory" -mindepth 1 -maxdepth 1 \
  ! -name '__MACOSX' ! -name '.DS_Store' ! -name '._*' -print | wc -l | tr -d ' ')"
source_root="$temporary_directory"

if [[ "$top_level_count" -eq 1 ]]; then
  only_entry="$(find "$temporary_directory" -mindepth 1 -maxdepth 1 \
    ! -name '__MACOSX' ! -name '.DS_Store' ! -name '._*' -print -quit)"
  if [[ -d "$only_entry" ]]; then
    source_root="$only_entry"
  fi
fi

if [[ ! -f "$source_root/pyproject.toml" ]]; then
  printf 'Refusing to import: the archive does not contain pyproject.toml at its project root.\n' >&2
  exit 1
fi

# Reject symbolic links so an archive cannot make rsync write outside the project.
if find "$source_root" -type l -print -quit | grep -q .; then
  printf 'Refusing to import: the archive contains symbolic links.\n' >&2
  exit 1
fi

rsync -a \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='.DS_Store' \
  --exclude='._*' \
  --exclude='__MACOSX/' \
  "$source_root/" "$project_root/"

printf 'Project updated from %s\n' "$archive"
