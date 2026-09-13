"""Document loading into page-anchored chunks.

Two parsers, chosen by availability:

* ``pypdf`` - always installed, PDF text layer only. The baseline.
* ``docling`` - optional extra, handles DOCX/PPTX/images/tables and OCR.

Page anchoring is the hard requirement: every chunk must know which page it came
from, because a citation without a page number cannot be verified.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import config
from .errors import DocumentLoadError, NoParserAvailableError
from .models import Chunk, Document

_PDF_SUFFIX = ".pdf"
_TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown"})
# Handled by docling when it is installed.
_RICH_SUFFIXES = frozenset({".docx", ".pptx", ".xlsx", ".html", ".htm", ".png", ".jpg", ".jpeg"})

_PAGE_BREAK = re.compile(r"\n\s*---\s*page\s+break\s*---\s*\n", re.IGNORECASE)


def _doc_id(path: Path, payload: bytes) -> str:
    """Content-addressed id, so re-parsing the same bytes yields the same id."""
    digest = hashlib.sha256(payload).hexdigest()[:16]
    return f"{path.stem}-{digest}"


def _split_page(page_text: str, page_number: int, doc_prefix: str) -> list[Chunk]:
    """Slice one page into overlapping chunks, all tagged with that page."""
    cleaned = page_text.strip()
    if not cleaned:
        return []

    step = config.CHUNK_CHARS - config.CHUNK_OVERLAP
    if step <= 0:  # defensive: a bad config must not spin forever
        raise ValueError("CHUNK_CHARS must exceed CHUNK_OVERLAP")

    chunks: list[Chunk] = []
    for index, start in enumerate(range(0, len(cleaned), step)):
        window = cleaned[start : start + config.CHUNK_CHARS]
        if not window.strip():
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{doc_prefix}-p{page_number}-c{index}",
                page=page_number,
                text=window,
            )
        )
        if start + config.CHUNK_CHARS >= len(cleaned):
            break
    return chunks


def _build(path: Path, payload: bytes, pages: list[str], parser: str) -> Document:
    """Assemble a Document, failing loudly when extraction produced nothing."""
    if not any(page.strip() for page in pages):
        raise DocumentLoadError(
            f"{path.name}: no extractable text. It is likely a scanned document - "
            "install the docling extra for OCR: uv pip install -e '.[docling]'"
        )

    doc_id = _doc_id(path, payload)
    chunks: list[Chunk] = []
    for page_number, page_text in enumerate(pages, start=1):
        chunks.extend(_split_page(page_text, page_number, doc_id))

    return Document(
        doc_id=doc_id,
        source_path=str(path),
        parser=parser,
        pages=tuple(pages),
        chunks=tuple(chunks),
    )


def _load_pdf_pypdf(path: Path, payload: bytes) -> Document:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except (PdfReadError, OSError, ValueError) as exc:
        raise DocumentLoadError(f"{path.name}: could not read PDF ({exc})") from exc

    return _build(path, payload, pages, parser="pypdf")


def _load_plaintext(path: Path, payload: bytes) -> Document:
    try:
        raw = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DocumentLoadError(
            f"{path.name}: text is not valid UTF-8"
        ) from exc

    # Let fixtures and pasted notices declare page boundaries explicitly.
    pages = _PAGE_BREAK.split(raw) if _PAGE_BREAK.search(raw) else [raw]
    return _build(path, payload, pages, parser="plaintext")


def _load_with_docling(path: Path, payload: bytes) -> Document:
    """Parse via docling. Only called when the extra is installed."""
    from docling.document_converter import DocumentConverter

    try:
        result = DocumentConverter().convert(str(path))
    except Exception as exc:  # docling wraps many backend-specific failures
        raise DocumentLoadError(f"{path.name}: docling failed ({exc})") from exc

    doc = result.document
    # Group exported text by page so citations keep a page anchor. Docling's
    # page numbering lives on each item's provenance.
    by_page: dict[int, list[str]] = {}
    for item, _level in doc.iterate_items():
        text = getattr(item, "text", None)
        if not text or not text.strip():
            continue
        provenance = getattr(item, "prov", None) or []
        page_no = getattr(provenance[0], "page_no", 1) if provenance else 1
        by_page.setdefault(int(page_no), []).append(text)

    if not by_page:
        markdown = doc.export_to_markdown()
        return _build(path, payload, [markdown], parser="docling")

    pages = [
        "\n".join(by_page.get(number, []))
        for number in range(1, max(by_page) + 1)
    ]
    return _build(path, payload, pages, parser="docling")


def docling_available() -> bool:
    """Whether the optional docling extra can be imported."""
    from importlib.util import find_spec

    try:
        return find_spec("docling") is not None
    except (ImportError, ValueError):
        return False


def load_document(source: str | Path, *, prefer_docling: bool = True) -> Document:
    """Parse a file into a page-anchored Document.

    Raises DocumentLoadError when the file is missing, unreadable, or yields no
    text, and NoParserAvailableError when the type needs an uninstalled extra.
    """
    path = Path(source).expanduser()
    if not path.is_file():
        raise DocumentLoadError(f"not a file: {path}")

    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise DocumentLoadError(f"{path.name}: cannot read ({exc})") from exc

    if not payload:
        raise DocumentLoadError(f"{path.name}: file is empty")

    suffix = path.suffix.casefold()
    has_docling = docling_available()

    if suffix == _PDF_SUFFIX:
        # Prefer docling for PDFs (tables, OCR); fall back to pypdf when the
        # richer parser is absent or chokes on this particular file.
        if prefer_docling and has_docling:
            try:
                return _load_with_docling(path, payload)
            except DocumentLoadError:
                return _load_pdf_pypdf(path, payload)
        return _load_pdf_pypdf(path, payload)

    if suffix in _TEXT_SUFFIXES:
        return _load_plaintext(path, payload)

    if suffix in _RICH_SUFFIXES:
        if not has_docling:
            raise NoParserAvailableError(
                f"{path.name}: {suffix} needs the docling extra. "
                "Install it with: uv pip install -e '.[docling]'"
            )
        return _load_with_docling(path, payload)

    raise NoParserAvailableError(f"{path.name}: unsupported file type {suffix!r}")
