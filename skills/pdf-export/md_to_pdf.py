#!/usr/bin/env python3
"""
Zero-dependency Markdown/plain-text -> PDF converter.

Uses ONLY the Python standard library — no pip install, no pandoc, no
wkhtmltopdf, no reportlab. Works in any minimal sandbox that has python3.

It builds a real PDF (PDF 1.4) by hand using the built-in Helvetica /
Helvetica-Bold fonts (the 14 standard fonts every PDF viewer ships, so no
font embedding is needed). Good enough for text reports: headings, bullets,
wrapped paragraphs, multiple pages.

Usage:
    python3 md_to_pdf.py input.md output.pdf
    python3 md_to_pdf.py input.md output.pdf "Optional Document Title"

Supported Markdown subset:
    # H1   ## H2   ### H3
    - bullet   * bullet
    1. numbered
    blank line  -> paragraph spacing
    **bold** / *italic* markers are stripped (rendered as plain text)
    `code` backticks are stripped
    --- horizontal rule -> spacer
Everything else is treated as a normal paragraph and word-wrapped.
"""
import re
import sys

# ── Page geometry (US Letter, 72 pt = 1 inch) ──────────────────────────────
PAGE_W, PAGE_H = 612.0, 792.0
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 54.0, 54.0, 54.0
TEXT_W = PAGE_W - 2 * MARGIN_X

# Approx character width for Helvetica at size 1 (avg), used for wrapping.
# Helvetica avg advance ~0.5 em; 0.52 is a safe slightly-conservative value.
AVG_CHAR_W = 0.52


def char_width(size: float) -> float:
    return size * AVG_CHAR_W


def wrap(text: str, size: float, width: float) -> list:
    """Greedy word-wrap to fit `width` points at the given font size."""
    if not text:
        return [""]
    max_chars = max(1, int(width / char_width(size)))
    words = text.split()
    lines, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            # Hard-break a single word longer than the line.
            while len(w) > max_chars:
                lines.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def strip_inline(s: str) -> str:
    """Drop markdown emphasis / code markers; we render plain glyphs."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1 (\2)", s)  # links -> text (url)
    return s


# Characters outside cp1252 that we transliterate to ASCII so they don't
# turn into "?" (cp1252 / WinAnsiEncoding covers em/en dashes, smart quotes,
# bullets and ellipsis natively, so those are left alone).
_TRANSLIT = {
    "→": "->", "←": "<-", "↔": "<->",
    "✓": "[x]", "✗": "[ ]", "•": "•",  # bullet kept (cp1252 0x95)
    " ": " ", "​": "", "﻿": "",
}


def pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def to_winansi(s: str) -> bytes:
    """Encode to cp1252 (== PDF WinAnsiEncoding). Transliterate the few
    common Unicode glyphs that cp1252 lacks; anything still unmappable
    becomes '?' rather than crashing."""
    for k, v in _TRANSLIT.items():
        s = s.replace(k, v)
    return s.encode("cp1252", "replace")


class Block:
    __slots__ = ("text", "size", "bold", "space_before", "leading", "bullet")

    def __init__(self, text, size=11.0, bold=False, space_before=0.0,
                 leading=None, bullet=False):
        self.text = text
        self.size = size
        self.bold = bold
        self.space_before = space_before
        self.leading = leading if leading is not None else size * 1.35
        self.bullet = bullet


def parse_markdown(md: str, title: str = "") -> list:
    """Turn markdown text into a flat list of layout Blocks."""
    blocks = []
    if title:
        blocks.append(Block(title, size=20.0, bold=True, space_before=0,
                            leading=26.0))
        blocks.append(Block("", size=6.0))  # spacer

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            blocks.append(Block("", size=6.0))  # blank -> spacer
            continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            blocks.append(Block("", size=8.0))  # hr -> spacer
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            txt = strip_inline(m.group(2))
            size = {1: 18.0, 2: 15.0, 3: 13.0}.get(level, 12.0)
            blocks.append(Block(txt, size=size, bold=True,
                                space_before=10.0 if blocks else 0.0,
                                leading=size * 1.3))
            continue

        m = re.match(r"^\s*([-*])\s+(.*)$", line)
        if m:
            blocks.append(Block(strip_inline(m.group(2)), size=11.0,
                                bullet=True, space_before=2.0))
            continue

        m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
        if m:
            blocks.append(Block(f"{m.group(1)}. " + strip_inline(m.group(2)),
                                size=11.0, space_before=2.0))
            continue

        blocks.append(Block(strip_inline(line), size=11.0, space_before=2.0))
    return blocks


def layout_pages(blocks: list) -> list:
    """Flow blocks into pages. Each page is a list of (x, y, size, bold, text)."""
    pages, cur = [], []
    y = PAGE_H - MARGIN_TOP

    def new_page():
        nonlocal cur, y
        if cur:
            pages.append(cur)
        cur = []
        y = PAGE_H - MARGIN_TOP

    for b in blocks:
        y -= b.space_before
        indent = 16.0 if b.bullet else 0.0
        prefix = "•  " if b.bullet else ""
        avail = TEXT_W - indent
        lines = wrap(prefix + b.text, b.size, avail) if b.text else [""]
        for i, ln in enumerate(lines):
            if y - b.leading < MARGIN_BOTTOM:
                new_page()
            y -= b.leading
            x = MARGIN_X + indent
            # Continuation lines of a bullet align under the text, not the dot.
            if b.bullet and i > 0:
                x += char_width(b.size) * len("•  ")
                ln = ln  # already wrapped without prefix on continuation? keep simple
            if ln.strip():
                cur.append((x, y, b.size, b.bold, ln))
    if cur:
        pages.append(cur)
    return pages or [[]]


def build_pdf(pages: list) -> bytes:
    """Assemble the PDF byte stream with an xref table."""
    objs = []  # each entry: raw bytes of the object body (without "N 0 obj")

    # Object numbering plan:
    #  1: Catalog
    #  2: Pages
    #  3: Font Helvetica
    #  4: Font Helvetica-Bold
    #  5..(5+P-1): Page objects
    #  then one content stream per page
    n_pages = len(pages)
    first_page_obj = 5
    first_content_obj = first_page_obj + n_pages

    kids = " ".join(f"{first_page_obj + i} 0 R" for i in range(n_pages))

    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")                       # 1
    objs.append(f"<< /Type /Pages /Count {n_pages} /Kids [{kids}] >>"
                .encode())                                                   # 2
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                b"/Encoding /WinAnsiEncoding >>")                            # 3
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                b"/Encoding /WinAnsiEncoding >>")                            # 4

    # Page objects
    for i in range(n_pages):
        content_obj = first_content_obj + i
        page = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_obj} 0 R >>"
        ).encode()
        objs.append(page)

    # Content streams
    for page in pages:
        parts = ["BT"]
        prev_font = None
        for (x, y, size, bold, text) in page:
            font = "F2" if bold else "F1"
            if font != prev_font:
                parts.append(f"/{font} {size:.1f} Tf")
                prev_font = font
            else:
                parts.append(f"/{font} {size:.1f} Tf")
            parts.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
            # Escape parens/backslash, then encode each piece as WinAnsi.
            esc_bytes = b"(" + to_winansi(pdf_escape(text)) + b") Tj"
            parts.append(esc_bytes)
        parts.append(b"ET")
        # parts is a mix of str (operators) and bytes (text-bearing Tj lines).
        stream = b"\n".join(
            p if isinstance(p, (bytes, bytearray)) else p.encode("ascii")
            for p in parts
        )
        obj = (b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
               + stream + b"\nendstream")
        objs.append(obj)

    # Serialize with xref
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (len(objs) + 1)
    for idx, body in enumerate(objs, start=1):
        offsets[idx] = len(out)
        out += f"{idx} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_pos = len(out)
    n = len(objs) + 1
    out += f"xref\n0 {n}\n".encode()
    out += b"0000000000 65535 f \n"
    for idx in range(1, n):
        out += f"{offsets[idx]:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {n} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


def main(argv):
    if len(argv) < 3:
        print("usage: md_to_pdf.py input.md output.pdf [\"Title\"]",
              file=sys.stderr)
        return 2
    in_path, out_path = argv[1], argv[2]
    title = argv[3] if len(argv) > 3 else ""
    with open(in_path, "r", encoding="utf-8", errors="replace") as f:
        md = f.read()
    blocks = parse_markdown(md, title)
    pages = layout_pages(blocks)
    pdf = build_pdf(pages)
    with open(out_path, "wb") as f:
        f.write(pdf)
    print(f"wrote {out_path}: {len(pdf)} bytes, {len(pages)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
