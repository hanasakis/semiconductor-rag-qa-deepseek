"""Semantic chunker for semiconductor SOP documents.

Splits DocumentElements from convert.py into retrieval-ready chunks.
Preserves table blocks, checklists, and section hierarchy.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List

from src.docs_pipeline.convert import DocumentElement


@dataclass
class DocChunk:
    """A retrieval-ready chunk with full provenance metadata."""

    text: str
    source: str
    section_path: str  # e.g. "Yield Triage SOP > 4. Triage Procedure > Step 2"
    page: int = 0
    content_type: str = "general"
    element_ids: List[str] = field(default_factory=list)
    chunk_id: str = ""

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = _make_chunk_id(self.text)


def chunk_document(
    elements: List[DocumentElement],
    source_name: str,
    max_chunk_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[DocChunk]:
    """Convert DocumentElements into retrieval-ready DocChunks.

    Rules:
      - Tables (content_type=parameter_table) are never split.
      - Checklists (lines starting with '- [ ]' or '- [x]') stay intact.
      - Overlap preserves context across chunk boundaries.
      - section_path tracks full heading hierarchy.

    Args:
        elements: Output from convert_markdown() or convert_pdf().
        source_name: Source filename for provenance.
        max_chunk_chars: Soft max characters per chunk (may exceed for tables).
        overlap_chars: Characters of overlap between consecutive chunks.

    Returns:
        List of DocChunk ready for indexing and retrieval.
    """
    chunks: List[DocChunk] = []
    section_stack: List[str] = []

    for el in elements:
        if not el.text.strip():
            continue

        # Track section hierarchy
        _update_section_stack(section_stack, el.section)

        section_path = " > ".join(section_stack) if section_stack else el.section

        # Never split tables, checklists, or warnings — they stand alone
        if el.content_type in ("parameter_table", "warning") or _is_checklist(el.text):
            chunk = DocChunk(
                text=el.text.strip(),
                source=source_name,
                section_path=section_path,
                page=el.page,
                content_type=el.content_type,
                element_ids=[el.element_id],
            )
            chunks.append(chunk)
            continue

        # For normal text: accumulate until max_chunk_chars
        if chunks and chunks[-1].content_type not in ("parameter_table", "warning") and (
            len(chunks[-1].text) + len(el.text) < max_chunk_chars
        ):
            _extend_chunk(chunks[-1], el, section_path, overlap_chars)
        else:
            chunks.append(_new_chunk(el, source_name, section_path))

    return chunks


def chunk_documents(
    elements_by_source: dict[str, List[DocumentElement]],
    max_chunk_chars: int = 1200,
    overlap_chars: int = 150,
) -> List[DocChunk]:
    """Convenience: chunk multiple documents."""
    all_chunks = []
    for source, elements in elements_by_source.items():
        all_chunks.extend(
            chunk_document(elements, source, max_chunk_chars, overlap_chars)
        )
    return all_chunks


# ── internal helpers ─────────────────────────────────────

def _update_section_stack(stack: List[str], section: str):
    """Maintain a breadcrumb trail of section headings.

    If the new section is more specific (e.g. "Step 1" after "4. Procedure"),
    we push. If it appears to be at the same or higher level, we pop and push.
    """
    if not section:
        return

    # Heuristic: deeper sections often start with digits or "Step"
    is_deep = bool(re.match(r"^[\d.]+\s|^Step\s", section))

    if is_deep and stack and section not in stack:
        if section.startswith("Step") and stack[-1].startswith("Step"):
            stack.pop()  # Replace previous step
        stack.append(section)
    else:
        # Same-level or parent section: pop until we find the right level
        while stack and stack[-1] != section:
            if not is_deep:
                stack.pop()
            else:
                break
        if section not in stack:
            stack.append(section)


def _is_checklist(text: str) -> bool:
    """Check if text is primarily a checklist."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 2:
        return False
    checklist_lines = sum(
        1 for l in lines if l.startswith("- [ ]") or l.startswith("- [x]")
    )
    return checklist_lines >= len(lines) * 0.5


def _new_chunk(el: DocumentElement, source: str, section_path: str) -> DocChunk:
    return DocChunk(
        text=el.text.strip(),
        source=source,
        section_path=section_path,
        page=el.page,
        content_type=el.content_type,
        element_ids=[el.element_id],
    )


def _extend_chunk(
    chunk: DocChunk, el: DocumentElement, section_path: str, overlap: int
):
    """Append an element's text to an existing chunk with overlap handling."""
    if chunk.text:
        # Minimal overlap: include the new section_path as context
        if section_path and section_path not in chunk.text:
            chunk.text += f"\n[{section_path}]\n{el.text.strip()}"
        else:
            chunk.text += f"\n\n{el.text.strip()}"
    else:
        chunk.text = el.text.strip()

    chunk.section_path = section_path  # Update to the most specific section
    chunk.element_ids.append(el.element_id)


def _make_chunk_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]
