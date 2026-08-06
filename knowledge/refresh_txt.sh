#!/usr/bin/env bash
#
# Regenerate knowledge/*.txt from knowledge/*.pdf
#
# Why this exists: `grep` cannot see text inside a PDF — the content lives in
# compressed FlateDecode streams, so `grep -il "night shift" knowledge/*.pdf`
# returns nothing even when the policy is right there on page 19. The agent
# greps the generated .txt files instead, the same way it greps lyzr-docs/*.mdx.
#
# The .pdf is the source of truth (and the file to attach in Slack).
# The .txt is generated, searchable, and committed.
#
# Run this on a machine with poppler's `pdftotext` installed (brew install
# poppler) — it is the highest-quality tier of read_document.py's fallback
# chain. The agent sandbox usually has neither pdftotext nor network access for
# `pip install pypdf`, which is exactly why we pre-extract here and commit.
#
# Usage:
#   bash knowledge/refresh_txt.sh            # regenerate all .txt
#   bash knowledge/refresh_txt.sh --check    # exit 1 if any .txt is missing/stale
#
set -euo pipefail

cd "$(dirname "$0")/.."
READER="skills/read-document/read_document.py"
MAX_CHARS=2000000   # well above any current doc, so nothing gets truncated

if [ ! -f "$READER" ]; then
  echo "ERROR: $READER not found (run from the repo, not elsewhere)" >&2
  exit 1
fi

# Stable, grep-friendly names for the known documents. Anything new gets a
# slugified version of its filename.
slug_for() {
  case "$1" in
    "Lyzr - Employee Handbook (1) (2).pdf")        echo "employee-handbook-india" ;;
    "Lyzr Inc- US Employee Handbook-2026 (1).pdf") echo "employee-handbook-us-2026" ;;
    "Lyzr - Agentic AI for Supply Chain.pdf")      echo "agentic-ai-supply-chain" ;;
    "Volkswagen-India-Safety-Manual.pdf")          echo "volkswagen-india-safety-manual" ;;
    *)
      printf '%s' "${1%.pdf}" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
      ;;
  esac
}

CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

stale=0
found_any=0

for pdf in knowledge/*.pdf; do
  [ -e "$pdf" ] || continue
  found_any=1
  base="$(basename "$pdf")"
  txt="knowledge/$(slug_for "$base").txt"

  if [ "$CHECK_ONLY" = 1 ]; then
    if [ ! -f "$txt" ]; then
      echo "MISSING: $txt (for $base)"
      stale=1
    elif [ "$pdf" -nt "$txt" ]; then
      echo "STALE:   $txt is older than $base"
      stale=1
    fi
    continue
  fi

  {
    echo "# GENERATED FILE - do not edit by hand."
    echo "# Source PDF: $pdf"
    echo "# Regenerate:  bash knowledge/refresh_txt.sh"
    echo
  } > "$txt"

  if ! python3 "$READER" "$pdf" "$MAX_CHARS" >> "$txt" 2>/dev/null; then
    echo "ERROR: extraction failed for $pdf" >&2
    rm -f "$txt"
    exit 1
  fi

  printf '  %-34s -> %-40s %8s chars\n' "$base" "$(basename "$txt")" "$(wc -c < "$txt" | tr -d ' ')"
done

if [ "$found_any" = 0 ]; then
  echo "No PDFs found in knowledge/ — nothing to do."
  exit 0
fi

if [ "$CHECK_ONLY" = 1 ]; then
  if [ "$stale" = 1 ]; then
    echo
    echo "Run: bash knowledge/refresh_txt.sh   (then commit the .txt files)"
    exit 1
  fi
  echo "All knowledge/*.txt are present and up to date."
fi
