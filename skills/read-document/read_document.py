#!/usr/bin/env python3
"""
Extract text from a document so the agent can read it.

Handles PDF, DOCX, XLSX, PPTX, CSV, and plain text. Tries the most reliable
method available, degrading gracefully:

  PDF  -> pdftotext (poppler) > pypdf (pip --user) > stdlib FlateDecode parse
  DOCX -> stdlib (unzip word/document.xml, strip tags)
  XLSX -> stdlib (unzip sharedStrings + sheet1)
  PPTX -> stdlib (unzip ppt/slides/*.xml, strip tags)
  CSV / TXT / MD / JSON / code -> read directly

Usage:
    python3 read_document.py <file> [max_chars]

Prints extracted text to stdout. On total failure, prints an explanation to
stderr and exits non-zero so the agent knows to tell the user.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile


def from_pdf(path: str) -> str:
    # 1) poppler's pdftotext, if present — best quality.
    exe = shutil.which("pdftotext")
    if exe:
        try:
            out = subprocess.run([exe, "-layout", path, "-"],
                                 capture_output=True, timeout=120)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.decode("utf-8", "replace")
        except Exception:
            pass
    # 2) pypdf via pip --user (bwrap has network).
    text = _pypdf(path)
    if text:
        return text
    # 3) stdlib FlateDecode fallback — works for many simple PDFs.
    return _pdf_stdlib(path)


def _pypdf(path: str) -> str:
    try:
        import pypdf  # noqa
    except ImportError:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--user",
                            "--quiet", "pypdf"], timeout=180, check=True)
            import importlib, site
            importlib.reload(site)
            import pypdf  # noqa
        except Exception:
            return ""
    try:
        import pypdf
        reader = pypdf.PdfReader(path)
        return "\n\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        return ""


def _pdf_stdlib(path: str) -> str:
    """Last-resort PDF text extraction using only stdlib zlib.
    Decompresses FlateDecode streams and pulls text from (…)Tj / […]TJ ops.
    Not perfect for complex PDFs, but recovers readable text from most."""
    import zlib
    data = open(path, "rb").read()
    chunks = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except Exception:
            pass
        # (text) Tj   and   [(a) (b)] TJ
        for t in re.findall(rb"\((?:[^()\\]|\\.)*\)", raw):
            s = t[1:-1]
            s = s.replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
            try:
                chunks.append(s.decode("latin-1"))
            except Exception:
                pass
    text = " ".join(chunks)
    return re.sub(r"\s{2,}", " ", text).strip()


def _strip_xml(xml_bytes: bytes, tag_suffixes=("}t", "}p")) -> str:
    """Pull text out of OOXML by collecting text nodes; insert breaks on
    paragraph boundaries."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        # Fallback: brute-force strip tags.
        return html.unescape(re.sub(rb"<[^>]+>", b" ", xml_bytes).decode("utf-8", "replace"))
    out = []
    for el in root.iter():
        tag = el.tag
        if tag.endswith("}t") and el.text:      # w:t / a:t text run
            out.append(el.text)
        elif tag.endswith("}p"):                 # paragraph boundary
            out.append("\n")
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


def from_docx(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        return _strip_xml(z.read("word/document.xml"))


def from_pptx(path: str) -> str:
    parts = []
    with zipfile.ZipFile(path) as z:
        slides = sorted(n for n in z.namelist()
                        if re.match(r"ppt/slides/slide\d+\.xml$", n))
        for n in slides:
            parts.append(_strip_xml(z.read(n)))
    return "\n\n---\n\n".join(p for p in parts if p)


def from_xlsx(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root:
                shared.append("".join(t.text or "" for t in si.iter()
                                      if t.tag.endswith("}t")))
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        lines = []
        for n in sheets:
            root = ET.fromstring(z.read(n))
            for row in root.iter():
                if not row.tag.endswith("}row"):
                    continue
                cells = []
                for c in row:
                    if not c.tag.endswith("}c"):
                        continue
                    is_shared = c.get("t") == "s"
                    v = next((ch.text for ch in c if ch.tag.endswith("}v")), None)
                    if v is None:
                        cells.append("")
                    elif is_shared:
                        try:
                            cells.append(shared[int(v)])
                        except Exception:
                            cells.append(v)
                    else:
                        cells.append(v)
                if any(cells):
                    lines.append("\t".join(cells))
        return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print("usage: read_document.py <file> [max_chars]", file=sys.stderr)
        return 2
    path = argv[1]
    max_chars = int(argv[2]) if len(argv) > 2 else 200_000
    if not os.path.exists(path):
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    try:
        if ext == "pdf":
            text = from_pdf(path)
        elif ext == "docx":
            text = from_docx(path)
        elif ext == "pptx":
            text = from_pptx(path)
        elif ext == "xlsx":
            text = from_xlsx(path)
        else:
            # csv / txt / md / json / code / unknown -> read as text
            text = open(path, "r", encoding="utf-8", errors="replace").read()
    except Exception as e:
        print(f"ERROR extracting {ext or 'file'}: {e}", file=sys.stderr)
        return 1

    if not text or not text.strip():
        print(f"ERROR: no extractable text found in {path} "
              f"(it may be a scanned/image PDF needing OCR).", file=sys.stderr)
        return 1

    out = text[:max_chars]
    if len(text) > max_chars:
        out += f"\n\n[... truncated, {len(text) - max_chars} more chars ...]"
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
