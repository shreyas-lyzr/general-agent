---
name: pdf-export
description: "Generate a real PDF file from Markdown or plain text with ZERO dependencies — no pandoc, no wkhtmltopdf, no reportlab, no pip install. Uses a bundled pure-stdlib Python script. Triggers whenever the user asks for a PDF: 'make a pdf', 'send me a pdf', 'pdf report', 'export to pdf', 'give me a pdf about'."
allowed-tools: "Bash, Read, Write"
---

# Guaranteed PDF export (zero dependencies)

When the user asks for a **PDF**, use this skill. It ships a self-contained Python
script — `md_to_pdf.py` — that builds a real PDF using only the Python standard
library. It does **not** need pandoc, wkhtmltopdf, weasyprint, reportlab, LaTeX,
or any `pip install`. It works in the minimal bwrap sandbox where those tools are
absent.

This is the reason you should never tell the user "the sandbox lacks PDF tools, print the HTML yourself." You always have this script.

## The script

It lives in this skill directory at `skills/pdf-export/md_to_pdf.py`, relative to
the cloned agent repo root. From the workdir, the repo is the current working
directory, so the path is `skills/pdf-export/md_to_pdf.py`.

If you're unsure where it is, find it:

```bash
find . -name md_to_pdf.py 2>/dev/null | head -1
```

## Workflow

### 1. Write your content as Markdown

Write the report to a `.md` file in the workdir. The converter understands:

- `# H1`, `## H2`, `### H3` headings (rendered bold, larger)
- `- ` / `* ` bullet lists
- `1. ` numbered lists
- blank lines → paragraph spacing
- `---` → horizontal spacer
- `**bold**`, `*italic*`, `` `code` `` markers are stripped to plain text
- `[label](url)` links → rendered as `label (url)`
- everything else → word-wrapped paragraph

Smart punctuation (em/en dashes, curly quotes, bullets, ellipsis) renders
correctly — the script uses WinAnsi encoding.

### 2. Run the converter

```bash
PDF_SCRIPT="$(find . -name md_to_pdf.py 2>/dev/null | head -1)"
python3 "$PDF_SCRIPT" report.md report.pdf "Optional Document Title"
```

- Arg 1: input Markdown/text file
- Arg 2: output PDF path
- Arg 3 (optional): a title rendered large at the top of page 1

It prints `wrote report.pdf: N bytes, P page(s)` on success. Multi-page flow
and page breaks are automatic.

### 3. Verify it exists, then attach it

```bash
/bin/ls -lh report.pdf
```

Then emit the attachment marker in your final reply so the bot uploads it to Slack:

```
Here's the PDF report on <topic>.

[[ATTACH:report.pdf]]
```

## When you want richer formatting

The bundled script is intentionally simple (text reports: headings, bullets,
paragraphs, multi-page). If the user explicitly needs **images, tables, colors,
or complex layout**, and richer tools happen to be available, prefer them:

1. `pandoc input.md -o output.pdf --pdf-engine=weasyprint`
2. `pip install --user weasyprint && weasyprint input.html output.pdf`
3. `wkhtmltopdf input.html output.pdf`
4. `chromium --headless --no-sandbox --print-to-pdf=output.pdf file://$PWD/input.html`

Try those first **only if** rich formatting is required. For a normal text
report, go straight to `md_to_pdf.py` — it always works, so there's no failure
path to apologize for.

## Rules

- Never claim PDF generation is impossible. This script is always present.
- Write the `.md` to the workdir, run the script, verify with `/bin/ls`, then attach.
- If `python3` isn't found, try `/usr/bin/python3` or `python`.
- Don't attach a `.md` or `.html` and call it a PDF. Produce the actual `.pdf`.
- Keep the output filename short and descriptive: `report.pdf`, `shreyas_kapale.pdf`.
