"""Additional parser tests to fill coverage gaps (parsers.py 59% → target 90%+).

Coverage gaps targeted:
- _split_page edge cases (line 39, 43, 49)
- _load_pdf_pypdf (lines 85-94)
- _load_plaintext with replace fallback (lines 100-101)
- _load_with_docling (lines 110-137) — mocked
- docling_available import error (lines 146-147)
- load_document error paths (lines 162-163, 174-179, 190)

T06 alignment: scanned docs, empty files, corrupted/unsupported formats.
"""
from __future__ import annotations

import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proofpath.errors import DocumentLoadError, NoParserAvailableError
from proofpath.parsers import _split_page, _build, _doc_id, load_document


# ---------------------------------------------------------------------------
#  _split_page edge cases
# ---------------------------------------------------------------------------

class TestSplitPage:
    def test_empty_page_returns_no_chunks(self) -> None:
        """A blank page should produce no chunks."""
        assert _split_page("", 1, "test") == []

    def test_whitespace_only_page_returns_no_chunks(self) -> None:
        assert _split_page("   \n\t  ", 1, "test") == []

    def test_single_short_page(self) -> None:
        chunks = _split_page("短文本", 1, "d")
        assert len(chunks) == 1
        assert chunks[0].page == 1
        assert chunks[0].text == "短文本"

    def test_long_page_produces_overlapping_chunks(self) -> None:
        """Text longer than CHUNK_CHARS should produce multiple chunks."""
        text = "甲" * 2000
        chunks = _split_page(text, 3, "doc")
        assert len(chunks) > 1
        # All chunks belong to the same page
        assert all(c.page == 3 for c in chunks)
        # Chunk IDs contain page number
        assert all("p3" in c.chunk_id for c in chunks)

    def test_bad_config_raises(self) -> None:
        """CHUNK_OVERLAP >= CHUNK_CHARS should raise, not loop."""
        from proofpath import config
        old_chars, old_overlap = config.CHUNK_CHARS, config.CHUNK_OVERLAP
        try:
            config.CHUNK_CHARS = 10
            config.CHUNK_OVERLAP = 10  # step = 0
            with pytest.raises(ValueError, match="CHUNK_CHARS must exceed"):
                _split_page("a" * 20, 1, "x")
        finally:
            config.CHUNK_CHARS = old_chars
            config.CHUNK_OVERLAP = old_overlap


# ---------------------------------------------------------------------------
#  _build and _doc_id
# ---------------------------------------------------------------------------

class TestBuild:
    def test_content_addressed_id(self) -> None:
        """Same content, different paths → same hash suffix."""
        a = _doc_id(Path("a.txt"), b"hello")
        b = _doc_id(Path("b.txt"), b"hello")
        assert a.split("-")[-1] == b.split("-")[-1]

    def test_no_text_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.txt"
        with pytest.raises(DocumentLoadError, match="no extractable text"):
            _build(path, b"x", ["", "  \n  "], "test")


# ---------------------------------------------------------------------------
#  Plaintext parser: non-UTF-8 fallback (lines 100-101)
# ---------------------------------------------------------------------------

class TestPlaintextFallback:
    def test_latin1_bytes_load_with_replacement(self, tmp_path: Path) -> None:
        """Non-UTF-8 bytes should be handled with replacement, not crash.

        NOTE (2026-09-13): Disabled after the P05 parser tightening. The new
        behavior rejects non-UTF-8 plaintext with DocumentLoadError instead of
        decoding with replacement characters. That is consistent with T06's
        "明确失败原因" requirement and avoids silently corrupting extracted
        text fed into the verifier. Re-enable only if the project revisits that
        decision and decides to restore the latin-1 fallback.
        """
        pytest.skip(
            "P05 tightened plaintext decoding to strict UTF-8; latin-1 fallback removed."
        )
        path = tmp_path / "latin1.txt"
        # Write bytes that are valid Latin-1 but not valid UTF-8
        path.write_bytes(b"Pr\xfcfung bestanden \xe4\xf6\xfc")
        doc = load_document(path)
        assert doc.parser == "plaintext"
        assert len(doc.pages) >= 1


# ---------------------------------------------------------------------------
#  PDF parser (lines 85-94, needs pypdf)
# ---------------------------------------------------------------------------

class TestPdfParser:
    def test_valid_pdf_loads(self, tmp_path: Path) -> None:
        """A minimal valid PDF should parse successfully."""
        pypdf = pytest.importorskip("pypdf")
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        # Add text via annotation-like approach: use a simple text PDF
        path = tmp_path / "test.pdf"
        # Create a minimal PDF with text
        pdf_bytes = (
            b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
            b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R"
            b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Hello World) Tj ET\n"
            b"endstream\nendobj\n"
            b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n"
            b"0000000058 00000 n \n0000000115 00000 n \n"
            b"0000000266 00000 n \n0000000360 00000 n \n"
            b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n430\n%%EOF"
        )
        path.write_bytes(pdf_bytes)
        doc = load_document(path)
        assert doc.parser == "pypdf"

    def test_corrupted_pdf_raises(self, tmp_path: Path) -> None:
        """A file with .pdf extension but garbage content → DocumentLoadError."""
        path = tmp_path / "bad.pdf"
        path.write_bytes(b"this is not a PDF at all")
        with pytest.raises(DocumentLoadError, match="could not read PDF"):
            load_document(path)

    def test_pdf_with_no_text_layer(self, tmp_path: Path) -> None:
        """A PDF with blank pages (no text) → DocumentLoadError about no text."""
        pypdf = pytest.importorskip("pypdf")
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        path = tmp_path / "blank.pdf"
        with open(path, "wb") as f:
            writer.write(f)
        with pytest.raises(DocumentLoadError, match="no extractable text"):
            load_document(path)


# ---------------------------------------------------------------------------
#  Docling mocked paths (lines 110-137)
# ---------------------------------------------------------------------------

class TestDoclingIntegration:
    """Test the docling parser path with mocks (docling is not installed)."""

    def test_docling_fallback_to_pypdf_on_failure(self, tmp_path: Path) -> None:
        """When docling chokes on a PDF, fall back to pypdf."""
        pypdf = pytest.importorskip("pypdf")
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(200, 200)
        path = tmp_path / "fallback.pdf"
        with open(path, "wb") as f:
            writer.write(f)

        with patch("proofpath.parsers.docling_available", return_value=True), \
             patch("proofpath.parsers._load_with_docling", side_effect=DocumentLoadError("boom")):
            # Should fall back to pypdf, which will also fail (blank page)
            with pytest.raises(DocumentLoadError, match="no extractable text"):
                load_document(path, prefer_docling=True)

    def test_docling_available_import_error(self) -> None:
        """If find_spec raises, docling_available returns False."""
        with patch("importlib.util.find_spec", side_effect=ImportError("no")):
            from proofpath.parsers import docling_available
            assert docling_available() is False

    def test_rich_type_with_docling_installed(self, tmp_path: Path) -> None:
        """When docling is available, rich types go through _load_with_docling."""
        path = tmp_path / "doc.docx"
        path.write_bytes(b"PK\x03\x04fakecontent")

        mock_doc = MagicMock()
        mock_doc.iterate_items.return_value = [
            (MagicMock(text="第一页内容测试文本足够长度"), None),
        ]
        mock_doc.export_to_markdown.return_value = "markdown"

        mock_result = MagicMock()
        mock_result.document = mock_doc

        # Fake prov attribute
        item = mock_doc.iterate_items.return_value[0][0]
        prov_entry = MagicMock()
        prov_entry.page_no = 1
        item.prov = [prov_entry]

        with patch("proofpath.parsers.docling_available", return_value=True), \
             patch("proofpath.parsers._load_with_docling") as mock_load:
            mock_load.return_value = MagicMock(
                doc_id="test-id", source_path=str(path), parser="docling",
                pages=("第一页内容测试文本足够长度",), chunks=()
            )
            doc = load_document(path)
            assert mock_load.called


# ---------------------------------------------------------------------------
#  load_document OS error path (lines 162-163)
# ---------------------------------------------------------------------------

class TestLoadDocumentOsError:
    def test_unreadable_file(self, tmp_path: Path) -> None:
        """A file that exists but can't be read → DocumentLoadError."""
        path = tmp_path / "locked.txt"
        path.write_text("test", encoding="utf-8")
        with patch.object(Path, "read_bytes", side_effect=OSError("permission denied")):
            with pytest.raises(DocumentLoadError, match="cannot read"):
                load_document(path)
