---
name: read-document
description: "Extract readable text from binary documents — PDF, DOCX, PPTX, XLSX — so their contents can actually be answered from. Zero dependencies (Python stdlib, with pdftotext/pypdf used when present). Triggers whenever the user attaches or references a PDF/Word/PowerPoint/Excel file, asks what a document says, asks to summarize or pull details out of a document, or asks a question whose answer lives in a PDF in knowledge/ (handbooks, policies, manuals, decks)."
allowed-tools: "Bash, Read, Write"
---

# Reading documents (PDF / DOCX / PPTX / XLSX)

Binary documents cannot be read with the `read` tool and **cannot be searched with
`grep`** — PDF text lives inside compressed streams, so `grep -il "night shift"
handbook.pdf` returns nothing even when the policy is on page 19. Use this skill
to turn the document into text first.

The script is `skills/read-document/read_document.py`. Locate it if unsure:

```bash
DOC="$(find . -name read_document.py 2>/dev/null | head -1)"
```

## Usage

```bash
python3 "$DOC" <file> [max_chars]     # prints extracted text to stdout
```

`max_chars` defaults to 200,000 and appends a `[... truncated ...]` note when it
clips. Pass a larger number for long documents.

Extraction chain, degrading gracefully:

| Format | Method |
|---|---|
| PDF | `pdftotext -layout` (poppler) → `pypdf` (`pip --user`) → stdlib FlateDecode parse |
| DOCX / PPTX / XLSX | stdlib (unzip the XML parts, strip tags) |
| CSV / TXT / MD / JSON / code | read directly — you don't need this skill |

Exit code is non-zero with an explanation on stderr if nothing is extractable
(e.g. a scanned image-only PDF needing OCR). If that happens, say so plainly
rather than guessing at the contents.

## Do not dump a whole document into context

A handbook is 100k–140k characters. Reading all of it to answer one question is
wasteful and usually unnecessary. Extract to a temp file once, then grep it:

```bash
python3 "$DOC" "some-report.pdf" 2000000 > /tmp/doc.txt
grep -n -i -A 30 "notice period" /tmp/doc.txt | head -60
```

Read the surrounding lines, then answer. Only read the full text when the task
genuinely needs the whole document (e.g. "summarize this end to end").

## Some PDFs in `knowledge/` are already extracted — grep those instead

Most PDFs in `knowledge/` have a committed `.txt` sibling. **When a `.txt`
exists, skip this skill and grep it directly** — it's faster, the text is
higher-quality, and it doesn't depend on `pdftotext` existing in the sandbox:

```bash
ls knowledge/*.txt
grep -n -i -A 30 "night shift" knowledge/employee-handbook-india.txt
```

## PDFs with no `.txt` — this skill is the only way to see them

A PDF without a `.txt` sibling will **never** appear in a grep, so an empty
search result says nothing about it. Find the gap by comparing what's present
against what's already extracted:

```bash
ls knowledge/*.pdf                          # all PDFs
grep -h "^# Source PDF:" knowledge/*.txt    # already searchable
```

Each `.txt` records its origin in that header. Extract anything missing from the
second list before concluding the answer isn't available:

```bash
DOC="$(find . -name read_document.py 2>/dev/null | head -1)"
python3 "$DOC" "knowledge/<file>.pdf" 2000000 > /tmp/doc.txt
grep -n -i -B 3 -A 30 "<topic>" /tmp/doc.txt | head -60
```

If a document turns out to be consulted often, extract it once and commit the
`.txt` alongside the PDF, copying the three-line header format the existing ones
use (the `# Regenerate:` line in each is the exact command that produced it).

Use this skill the same way for files the user uploads mid-conversation, or PDFs
you download.

## Files the user uploads in Slack

When the user attaches a file, the bot saves it into the working directory and
the message names it. Extract and actually read it before answering — never tell
the user you can't see a file they clearly attached.

```bash
DOC="$(find . -name read_document.py 2>/dev/null | head -1)"
python3 "$DOC" "Ally_Requirements_Questionnaire_v0.2.pdf" > /tmp/doc.txt
```

## Rules

- Never answer questions about a document you haven't actually extracted.
- Never claim a PDF is unreadable before running this script.
- `grep` on a `.pdf` proving empty means nothing — extract, then grep.
- If extraction genuinely fails, report the stderr reason; don't invent contents.
