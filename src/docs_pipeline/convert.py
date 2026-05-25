"""Document conversion pipeline for semiconductor SOPs and technical docs.

Priority: Docling (rich structure) > PyMuPDF4LLM (PDF) > raw text.
Markdown files are parsed directly with section-aware splitting.

Output is a list of DocumentElement, each representing a coherent
document fragment with full metadata (source, section, page, content_type).
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


# ── DocumentElement ──────────────────────────────────────

@dataclass
class DocumentElement:
    """A single coherent fragment from a document.

    Attributes:
        text: The text content of this element.
        source: Source filename (e.g. "SOP-ETCH-042.pdf").
        section: Section heading this element belongs to.
        page: Page number (0 for markdown or unknown).
        content_type: Semantic type of this element.
        element_id: Unique hash-based identifier.
    """
    text: str
    source: str
    section: str = ""
    page: int = 0
    content_type: str = "general"
    element_id: str = ""

    def __post_init__(self):
        if not self.element_id:
            self.element_id = _make_element_id(self.source, self.section, self.text)


CONTENT_TYPES = {
    "procedure",
    "parameter_table",
    "warning",
    "bkm",             # best known method
    "glossary",
    "report_template",
    "general",
}


# ── Markdown converter ───────────────────────────────────

def convert_markdown(path: Path) -> List[DocumentElement]:
    """Parse a Markdown file into section-aware DocumentElements.

    Splits on ## and ### headings. Each section becomes one or more elements.
    Content type is inferred from heading text and content patterns.
    """
    raw = path.read_text(encoding="utf-8")
    source = path.name
    elements = []
    sections = _split_by_headings(raw)

    for heading, body in sections:
        if not body.strip():
            continue

        content_type = _infer_content_type(heading, body)

        # Split long sections into paragraph-level elements
        paragraphs = _split_paragraphs(body)
        for para in paragraphs:
            if not para.strip():
                continue
            elements.append(DocumentElement(
                text=para.strip(),
                source=source,
                section=_clean_heading(heading),
                content_type=content_type,
            ))

    logger.info("Markdown %s: %d elements", source, len(elements))
    return elements


# ── PDF converter ────────────────────────────────────────

def convert_pdf(path: Path) -> List[DocumentElement]:
    """Convert a PDF file using Docling, falling back to PyMuPDF4LLM or pypdf.

    The fallback chain:
      1. Docling (best quality: tables, structure, reading order)
      2. PyMuPDF4LLM (good text extraction, LLM-friendly markdown)
      3. pypdf (basic text extraction, always available)
    """
    source = path.name

    # Try Docling first
    elements = _try_docling(path)
    if elements:
        return elements

    # Try PyMuPDF4LLM
    elements = _try_pymupdf4llm(path)
    if elements:
        return elements

    # Fallback to pypdf
    return _fallback_pypdf(path)


# ── Public API ───────────────────────────────────────────

def convert(path: str | Path) -> List[DocumentElement]:
    """Convert a document file to DocumentElements. Auto-detects format."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".md":
        return convert_markdown(path)
    elif suffix == ".pdf":
        return convert_pdf(path)
    elif suffix in (".txt", ".text"):
        return _convert_text(path)
    else:
        logger.warning("Unknown format %s, treating as text", suffix)
        return _convert_text(path)


def convert_directory(directory: str | Path) -> List[DocumentElement]:
    """Convert all supported documents in a directory."""
    directory = Path(directory)
    all_elements = []
    for ext in (".md", ".pdf", ".txt"):
        for filepath in directory.glob(f"*{ext}"):
            try:
                all_elements.extend(convert(filepath))
            except Exception as e:
                logger.error("Failed to convert %s: %s", filepath, e)
    logger.info("Directory %s: %d total elements", directory, len(all_elements))
    return all_elements


# ── Internal helpers ─────────────────────────────────────

def _split_by_headings(text: str) -> List[tuple]:
    """Split markdown text by ## and ### headings. Returns (heading, body) pairs."""
    pattern = r"^(#{2,3})\s+(.+)$"
    parts = re.split(pattern, text, flags=re.MULTILINE)

    result = []
    current_heading = ""
    current_body: list[str] = []

    i = 0
    while i < len(parts):
        chunk = parts[i]
        if re.match(r"^#{2,3}$", chunk):  # heading marker
            if current_body:
                result.append((current_heading, "\n".join(current_body)))
            current_heading = parts[i + 1] if i + 1 < len(parts) else ""
            current_body = []
            i += 2
        else:
            current_body.append(chunk)
            i += 1

    if current_body:
        result.append((current_heading, "\n".join(current_body)))

    # If no headings found, treat entire document as one section
    if not result:
        result.append(("", text))

    return result


def _split_paragraphs(text: str, max_len: int = 1500) -> List[str]:
    """Split body text into paragraph-level chunks.

    Preserves table blocks (lines starting with |) as single units.
    """
    lines = text.strip().split("\n")
    paragraphs = []
    current = []
    current_is_table = False

    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") or stripped.startswith("|-")

        # Transition between table and non-table → flush
        if current and is_table_line != current_is_table:
            paragraphs.append("\n".join(current))
            current = []

        current_is_table = is_table_line
        current.append(line)

        # Flush if too long and not in a table
        if not current_is_table and len("\n".join(current)) > max_len:
            paragraphs.append("\n".join(current))
            current = []

    if current:
        paragraphs.append("\n".join(current))

    return paragraphs


def _infer_content_type(heading: str, body: str) -> str:
    """Infer the semantic content type from heading and body patterns."""
    combined = (heading + " " + body[:500]).lower()

    if any(w in combined for w in ("warning", "caution", "danger", "注意")):
        return "warning"
    if any(w in combined for w in ("template", "report structure", "form")):
        return "report_template"
    if "|" in body and "---" in body:
        return "parameter_table"
    if any(w in combined for w in ("step", "procedure", "investigation")):
        return "procedure"
    if any(w in combined for w in ("bkm", "best known method", "lesson learned")):
        return "bkm"
    if any(w in combined for w in ("glossary", "definition", "terminology")):
        return "glossary"
    return "general"


def _clean_heading(heading: str) -> str:
    """Remove markdown heading markers and extra whitespace."""
    h = re.sub(r"^#+\s*", "", heading)
    return h.strip()


def _make_element_id(source: str, section: str, text: str) -> str:
    """Generate a stable element ID from content hash."""
    key = f"{source}|{section}|{text[:200]}"
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def _convert_text(path: Path) -> List[DocumentElement]:
    """Convert a plain text file, treating each paragraph as an element."""
    source = path.name
    raw = path.read_text(encoding="utf-8")
    paragraphs = _split_paragraphs(raw)
    return [
        DocumentElement(text=p.strip(), source=source, content_type="general")
        for p in paragraphs if p.strip()
    ]


# ── Backend-specific converters ──────────────────────────

def _try_docling(path: Path) -> Optional[List[DocumentElement]]:
    """Attempt Docling conversion. Returns None if unavailable or failed."""
    try:
        from docling.document_converter import DocumentConverter as DoclingConverter
    except ImportError:
        logger.debug("Docling not installed, skipping")
        return None

    try:
        converter = DoclingConverter()
        result = converter.convert(str(path))
        doc = result.document
        elements = []
        for item in doc.iterate_items():
            elements.append(DocumentElement(
                text=item.text if hasattr(item, "text") else str(item),
                source=path.name,
                section=getattr(item, "heading", ""),
                page=getattr(item, "page_no", 0),
                content_type="general",
            ))
        logger.info("Docling: %d elements from %s", len(elements), path.name)
        return elements if elements else None
    except Exception as e:
        logger.warning("Docling failed for %s: %s", path.name, e)
        return None


def _try_pymupdf4llm(path: Path) -> Optional[List[DocumentElement]]:
    """Attempt PyMuPDF4LLM conversion. Returns None if unavailable."""
    try:
        import pymupdf4llm
    except ImportError:
        logger.debug("PyMuPDF4LLM not installed, skipping")
        return None

    try:
        md_text = pymupdf4llm.to_markdown(str(path))
        elements = []
        sections = _split_by_headings(md_text)
        for heading, body in sections:
            if not body.strip():
                continue
            elements.append(DocumentElement(
                text=body.strip(),
                source=path.name,
                section=_clean_heading(heading),
                content_type="general",
            ))
        logger.info("PyMuPDF4LLM: %d elements from %s", len(elements), path.name)
        return elements if elements else None
    except Exception as e:
        logger.warning("PyMuPDF4LLM failed for %s: %s", path.name, e)
        return None


def _fallback_pypdf(path: Path) -> List[DocumentElement]:
    """Basic PDF text extraction using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF fallback. Install with: pip install pypdf"
        )

    reader = PdfReader(str(path))
    elements = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if text and text.strip():
            elements.append(DocumentElement(
                text=text.strip(),
                source=path.name,
                page=i,
                content_type="general",
            ))
    logger.info("pypdf fallback: %d pages from %s", len(elements), path.name)
    return elements
