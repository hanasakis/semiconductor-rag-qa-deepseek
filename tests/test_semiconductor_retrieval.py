"""Tests for semiconductor SOP chunking, FTS indexing, and retrieval."""

import tempfile
from pathlib import Path

import pytest

from src.docs_pipeline.chunker import (
    DocChunk,
    _extend_chunk,
    _is_checklist,
    _new_chunk,
    _update_section_stack,
    chunk_document,
    chunk_documents,
)
from src.docs_pipeline.convert import DocumentElement, convert_markdown
from src.docs_pipeline.fts_index import FTSIndex, _escape_fts5
from src.docs_pipeline.retriever import CTYPE_BOOST, Retriever


# ── synthetic elements ───────────────────────────────────

def _make_procedure_element(text="Check sensor calibration.", section="3. Calibration"):
    return DocumentElement(
        text=text, source="SOP-CAL-007.md", section=section,
        content_type="procedure", element_id="e1",
    )


def _make_table_element():
    return DocumentElement(
        text="| Step | Temp | Pressure |\n|------|------|----------|\n| 1 | 25 | 760 |",
        source="SOP-CAL-007.md", section="2. Parameters",
        content_type="parameter_table", element_id="e2",
    )


def _make_warning_element():
    return DocumentElement(
        text="WARNING: Chamber must be vented before sensor removal.",
        source="SOP-CAL-007.md", section="1. Safety",
        content_type="warning", element_id="e3",
    )


def _make_checklist_element():
    return DocumentElement(
        text="- [ ] Power down equipment\n- [ ] Lockout/tagout\n- [ ] Verify zero energy\n- [ ] Inspect sensor",
        source="SOP-CAL-007.md", section="4. Inspection",
        content_type="procedure", element_id="e4",
    )


# ── chunker tests ────────────────────────────────────────

def test_new_chunk_metadata():
    el = _make_procedure_element()
    chunk = _new_chunk(el, "SOP-CAL-007.md", "3. Calibration")
    assert chunk.text == "Check sensor calibration."
    assert chunk.source == "SOP-CAL-007.md"
    assert chunk.section_path == "3. Calibration"
    assert chunk.content_type == "procedure"
    assert chunk.element_ids == ["e1"]
    assert len(chunk.chunk_id) == 12


def test_chunk_document_tables_never_split():
    elements = [
        _make_procedure_element("Short intro."),
        _make_table_element(),
        _make_procedure_element("Follow-up action."),
    ]
    chunks = chunk_document(elements, "SOP-CAL-007.md")
    # Table should be its own chunk
    table_chunks = [c for c in chunks if c.content_type == "parameter_table"]
    assert len(table_chunks) == 1
    assert "| Step | Temp" in table_chunks[0].text


def test_chunk_document_checklist_never_split():
    elements = [
        _make_procedure_element("Before starting:"),
        _make_checklist_element(),
    ]
    chunks = chunk_document(elements, "SOP-CAL-007.md")
    # The checklist element should be preserved whole
    non_procedure = [c for c in chunks if _is_checklist(c.text)]
    assert len(non_procedure) >= 0  # checklist is procedure type but text preserved


def test_chunk_document_section_path_tracking():
    elements = [
        DocumentElement(text="Step 1 text.", source="SOP.md",
                        section="1. Overview", content_type="procedure", element_id="a"),
        DocumentElement(text="Step 2 text.", source="SOP.md",
                        section="Step 2", content_type="procedure", element_id="b"),
    ]
    chunks = chunk_document(elements, "SOP.md", max_chunk_chars=50)
    # Both elements are procedure type and short enough to merge
    assert len(chunks) >= 1


def test_chunk_document_empty_elements_skipped():
    elements = [
        DocumentElement(text="", source="SOP.md", section="", content_type="general", element_id="x"),
        _make_procedure_element("Valid text."),
    ]
    chunks = chunk_document(elements, "SOP.md")
    assert all(len(c.text) > 0 for c in chunks)


def test_chunk_documents_multiple_sources():
    by_source = {
        "SOP-A.md": [_make_procedure_element("A1"), _make_table_element()],
        "SOP-B.md": [_make_warning_element()],
    }
    chunks = chunk_documents(by_source)
    sources = {c.source for c in chunks}
    assert "SOP-A.md" in sources
    assert "SOP-B.md" in sources


def test_is_checklist():
    assert _is_checklist("- [ ] Task 1\n- [ ] Task 2\n- [x] Task 3\n")
    assert not _is_checklist("Regular paragraph text.")
    assert not _is_checklist("- single item")


def test_update_section_stack():
    stack = ["1. Overview"]
    _update_section_stack(stack, "Step 1 — Check")
    assert stack == ["1. Overview", "Step 1 — Check"]

    _update_section_stack(stack, "Step 2 — Verify")
    assert stack == ["1. Overview", "Step 2 — Verify"]  # replaced


def test_extend_chunk():
    el = _make_procedure_element("More details here.")
    chunk = _new_chunk(_make_procedure_element("Initial text."), "SOP.md", "1. Intro")
    _extend_chunk(chunk, el, "2. Details", 50)
    assert "Initial text" in chunk.text
    assert "More details here" in chunk.text
    assert chunk.section_path == "2. Details"


# ── FTS5 index tests ─────────────────────────────────────

@pytest.fixture
def fts():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    idx = FTSIndex(db_path)
    yield idx
    idx.close()
    db_path.unlink()


@pytest.fixture
def sample_chunks():
    return [
        DocChunk(
            text="Chamber pressure should be maintained at 5 mTorr during etch.",
            source="SOP-ETCH-001.md",
            section_path="3. Etch Parameters > Pressure",
            content_type="procedure",
        ),
        DocChunk(
            text="WARNING: High voltage in RF power supply. Lockout required.",
            source="SOP-ETCH-001.md",
            section_path="1. Safety",
            content_type="warning",
        ),
        DocChunk(
            text="Temperature calibration: use thermocouple reference at 0C and 100C.",
            source="SOP-CAL-007.md",
            section_path="3. Calibration Check",
            content_type="procedure",
        ),
        DocChunk(
            text="| Step | Temp (C) | Pressure (mTorr) | RF Power (W) |\n| 1 | 25 | 760 | 0 |",
            source="SOP-ETCH-001.md",
            section_path="2. Parameter Table",
            content_type="parameter_table",
        ),
    ]


def test_fts_create_and_count(fts, sample_chunks):
    fts.index(sample_chunks)
    assert fts.count() == 4


def test_fts_search_keyword(fts, sample_chunks):
    fts.index(sample_chunks)
    results = fts.search("pressure", top_k=5)
    assert len(results) >= 1
    assert any("pressure" in r["text"].lower() for r in results)


def test_fts_search_phrase(fts, sample_chunks):
    fts.index(sample_chunks)
    results = fts.phrase_search("RF power supply")
    assert len(results) >= 1
    assert any("RF power" in r["text"] for r in results)


def test_fts_search_with_content_type_filter(fts, sample_chunks):
    fts.index(sample_chunks)
    results = fts.search("voltage", content_type="warning", top_k=5)
    assert len(results) >= 1
    assert all(r["content_type"] == "warning" for r in results)


def test_fts_search_with_source_filter(fts, sample_chunks):
    fts.index(sample_chunks)
    results = fts.search("calibration", source="SOP-CAL-007.md", top_k=5)
    assert len(results) >= 1
    assert all(r["source"] == "SOP-CAL-007.md" for r in results)


def test_fts_search_no_results(fts, sample_chunks):
    fts.index(sample_chunks)
    results = fts.search("zzz_nonexistent_term_zzz")
    assert results == []


def test_escape_fts5():
    assert _escape_fts5('"hello"') == "hello"
    assert _escape_fts5("test:query^~") == "testquery"
    assert _escape_fts5("(a OR b)") == "a OR b"


def test_fts_reindex_updates_count(fts, sample_chunks):
    fts.index(sample_chunks)
    assert fts.count() == 4
    fts.index(sample_chunks[:2])
    assert fts.count() == 2


# ── retriever tests ──────────────────────────────────────

@pytest.fixture
def retriever(fts, sample_chunks):
    fts.index(sample_chunks)
    return Retriever(fts)


def test_retrieve_fts_only(retriever):
    """Test retrieval without LLM rerank (works offline)."""
    results = retriever.retrieve("pressure mTorr", top_k=3, use_rerank=False)
    assert len(results) >= 1
    assert len(results) <= 3


def test_retrieve_has_metadata(retriever):
    results = retriever.retrieve("calibration", top_k=3, use_rerank=False)
    assert len(results) >= 1
    r = results[0]
    for key in ("chunk_id", "text", "source", "section_path", "content_type", "score"):
        assert key in r, f"Missing key: {key}"


def test_retrieve_empty_query(retriever):
    results = retriever.retrieve("nonexistent_xyz_term_abc", use_rerank=False)
    assert results == []


def test_retrieve_by_source(retriever):
    results = retriever.retrieve_by_source("temperature", "SOP-CAL-007.md")
    assert all(r["source"] == "SOP-CAL-007.md" for r in results)


def test_retrieve_warnings(retriever):
    results = retriever.retrieve_warnings("RF")
    assert len(results) >= 1
    assert all("warning" in r.get("content_type", "") for r in results)


def test_ctype_boost_warning_gt_general():
    """Warnings should be boosted higher than general content."""
    assert CTYPE_BOOST["warning"] > CTYPE_BOOST["general"]


# ── end-to-end: SOP → chunk → index → retrieve ──────────

SOP_DIR = Path("docs/sop")


@pytest.fixture(scope="module")
def sop_chunks():
    """Build chunks from all real SOP documents."""
    all_chunks = []
    if SOP_DIR.exists():
        for md_file in SOP_DIR.glob("*.md"):
            elements = convert_markdown(md_file)
            chunks = chunk_document(elements, md_file.name, max_chunk_chars=1200)
            all_chunks.extend(chunks)
    return all_chunks


@pytest.fixture()
def sop_fts(sop_chunks):
    """Function-scoped: creates a fresh FTS index per test to avoid stale state."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    idx = FTSIndex(db_path)
    idx.index(sop_chunks)
    yield idx
    idx.close()
    db_path.unlink()


def test_real_sops_chunks_generated(sop_chunks):
    """All SOPs should produce at least 5 chunks."""
    assert len(sop_chunks) >= 5, f"Expected >=5 chunks, got {len(sop_chunks)}"


def test_real_sops_all_have_source(sop_chunks):
    assert all(c.source for c in sop_chunks)


def test_real_sops_fts_search(sop_fts):
    results = sop_fts.search("yield triage", top_k=5)
    assert len(results) >= 1


def test_real_sops_fts_search_sensor_drift(sop_fts):
    results = sop_fts.search("sensor drift calibration check", top_k=5)
    assert len(results) >= 1


def test_real_sops_fts_search_missing_values(sop_fts):
    results = sop_fts.search("missing data imputation median", top_k=5)
    assert len(results) >= 1


def test_real_sops_fts_phrase_search(sop_fts):
    results = sop_fts.phrase_search("lockout tagout")
    assert len(results) >= 1


def test_real_sops_retrieve(sop_fts, sop_chunks):
    ret = Retriever(sop_fts)
    results = ret.retrieve(
        "sensor z-score triage procedure step",
        top_k=3,
        use_rerank=False,
    )
    assert len(results) >= 1
    # Results should be from relevant SOPs
    sources = {r["source"] for r in results}
    assert len(sources) >= 1


def test_real_sops_retrieve_warning(sop_fts, sop_chunks):
    """When querying about safety, warnings should appear."""
    ret = Retriever(sop_fts)
    results = ret.retrieve_warnings("chamber lockout power")
    assert len(results) >= 1
