"""Tests for semiconductor document conversion pipeline."""

import tempfile
from pathlib import Path

import pytest

from src.docs_pipeline.convert import (
    CONTENT_TYPES,
    DocumentElement,
    _clean_heading,
    _infer_content_type,
    _make_element_id,
    _split_by_headings,
    _split_paragraphs,
    convert,
    convert_directory,
    convert_markdown,
)


# ── synthetic markdown ───────────────────────────────────

MARKDOWN_WITH_SECTIONS = """# Title (ignored — only ##+ is sectioned)

Some preamble text that belongs to no section.

## 1. Investigation Procedure

This is the first step. Check the sensors.

### 1.1 Sensor Check

Pull all sensor traces for the affected lot.

## 2. Parameter Table

| Step | Temp (C) | Pressure (mTorr) |
|------|----------|------------------|
| 1    | 25       | 760              |
| 2    | 300      | 5                |

## 3. Warnings

WARNING: Chamber must be vented before sensor removal.

CAUTION: High temperature surface. Allow 30 min cooldown.
"""


@pytest.fixture
def md_file():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(MARKDOWN_WITH_SECTIONS)
        path = Path(f.name)
    yield path
    path.unlink()


# ── DocumentElement ──────────────────────────────────────

def test_document_element_fields():
    el = DocumentElement(
        text="Check sensor calibration.",
        source="SOP-CAL-007.md",
        section="3.1 Calibration Check",
        page=0,
        content_type="procedure",
    )
    assert el.text == "Check sensor calibration."
    assert el.source == "SOP-CAL-007.md"
    assert el.section == "3.1 Calibration Check"
    assert el.page == 0
    assert el.content_type == "procedure"
    assert len(el.element_id) == 12


def test_document_element_auto_id():
    el1 = DocumentElement(text="hello", source="a.md", section="s1")
    el2 = DocumentElement(text="hello", source="a.md", section="s1")
    # Same inputs → same element_id (stable hash)
    assert el1.element_id == el2.element_id


def test_document_element_unique_id():
    el1 = DocumentElement(text="text A", source="a.md", section="s1")
    el2 = DocumentElement(text="text B", source="a.md", section="s1")
    assert el1.element_id != el2.element_id


# ── Markdown conversion ──────────────────────────────────

def test_convert_markdown_sections(md_file):
    elements = convert_markdown(md_file)
    sections = {e.section for e in elements}
    expected = {
        "1. Investigation Procedure",
        "1.1 Sensor Check",
        "2. Parameter Table",
        "3. Warnings",
    }
    assert expected.issubset(sections)


def test_convert_markdown_all_have_source(md_file):
    elements = convert_markdown(md_file)
    for el in elements:
        assert el.source == md_file.name


def test_convert_markdown_all_have_element_id(md_file):
    elements = convert_markdown(md_file)
    for el in elements:
        assert len(el.element_id) == 12


def test_convert_markdown_all_have_content_type(md_file):
    elements = convert_markdown(md_file)
    for el in elements:
        assert el.content_type in CONTENT_TYPES


def test_convert_markdown_detects_warning(md_file):
    elements = convert_markdown(md_file)
    warnings = [e for e in elements if e.content_type == "warning"]
    assert len(warnings) >= 1
    assert any("Chamber must be vented" in w.text for w in warnings)


def test_convert_markdown_detects_table(md_file):
    elements = convert_markdown(md_file)
    tables = [e for e in elements if e.content_type == "parameter_table"]
    assert len(tables) >= 1
    assert any("Temp (C)" in t.text for t in tables)


def test_convert_markdown_detects_procedure(md_file):
    elements = convert_markdown(md_file)
    procs = [e for e in elements if e.content_type == "procedure"]
    assert len(procs) >= 1


def test_convert_markdown_not_empty(md_file):
    elements = convert_markdown(md_file)
    assert len(elements) > 0
    for el in elements:
        assert len(el.text.strip()) > 0


# ── convert() auto-detect ────────────────────────────────

def test_convert_auto_detect_markdown(md_file):
    elements = convert(md_file)
    assert len(elements) > 0


def test_convert_file_not_found():
    with pytest.raises(FileNotFoundError):
        convert("nonexistent/file.md")


# ── convert_directory ────────────────────────────────────

def test_convert_directory(md_file):
    elements = convert_directory(md_file.parent)
    assert len(elements) > 0


# ── Internal helpers ─────────────────────────────────────

def test_split_by_headings():
    text = "Preamble\n## Section A\nBody A\n## Section B\nBody B"
    result = _split_by_headings(text)
    assert len(result) >= 2
    headings = {h for h, _ in result}
    assert "Section A" in headings
    assert "Section B" in headings


def test_split_by_headings_no_headings():
    text = "Just plain text without any headings."
    result = _split_by_headings(text)
    assert len(result) == 1
    assert result[0][0] == ""
    assert "plain text" in result[0][1]


def test_split_paragraphs_preserves_tables():
    text = "Some intro\n| A | B |\n|---|----|\n| 1 | 2 |\n\nMore text"
    paragraphs = _split_paragraphs(text)
    table_paras = [p for p in paragraphs if "|" in p]
    assert len(table_paras) >= 1


def test_clean_heading():
    assert _clean_heading("## 1. Purpose") == "1. Purpose"
    assert _clean_heading("### 3.2 Calibration") == "3.2 Calibration"
    assert _clean_heading("No heading markers") == "No heading markers"


@pytest.mark.parametrize("heading,body,expected", [
    ("## WARNING: High Voltage", "Dangerous area.", "warning"),
    ("## CAUTION", "Hot surface.", "warning"),
    ("## Parameter Settings", "| A | B |\n|---|---|", "parameter_table"),
    ("## Step 1 — Check Sensors", "Pull trace data.", "procedure"),
    ("## Report Template", "Fill in the fields.", "report_template"),
    ("## BKM: Best Practice", "Always calibrate weekly.", "bkm"),
    ("## Glossary", "RTA: Rapid Thermal Anneal.", "glossary"),
    ("## Overview", "General description.", "general"),
])
def test_infer_content_type(heading, body, expected):
    assert _infer_content_type(heading, body) == expected


def test_make_element_id_stable():
    id1 = _make_element_id("a.md", "s1", "hello world")
    id2 = _make_element_id("a.md", "s1", "hello world")
    assert id1 == id2


def test_make_element_id_different():
    id1 = _make_element_id("a.md", "s1", "text one")
    id2 = _make_element_id("b.md", "s1", "text one")
    assert id1 != id2


# ── Real SOP documents ───────────────────────────────────

SOP_DIR = Path("docs/sop")


@pytest.mark.skipif(not SOP_DIR.exists(), reason="SOP directory not found")
def test_real_sops_convert_without_error():
    docs = list(SOP_DIR.glob("*.md"))
    assert len(docs) >= 4, f"Expected >=4 SOP docs, found {len(docs)}"
    for doc in docs:
        elements = convert_markdown(doc)
        assert len(elements) > 0, f"No elements from {doc.name}"


@pytest.mark.skipif(not (SOP_DIR / "yield_triage_sop.md").exists(),
                    reason="SOP not found")
def test_yield_triage_sop_has_procedures():
    elements = convert_markdown(SOP_DIR / "yield_triage_sop.md")
    procs = [e for e in elements if e.content_type == "procedure"]
    assert len(procs) > 0


@pytest.mark.skipif(not (SOP_DIR / "failure_report_template.md").exists(),
                    reason="SOP not found")
def test_failure_report_template_has_report_template_type():
    elements = convert_markdown(SOP_DIR / "failure_report_template.md")
    templates = [e for e in elements if e.content_type == "report_template"]
    assert len(templates) > 0


@pytest.mark.skipif(not (SOP_DIR / "missing_value_policy.md").exists(),
                    reason="SOP not found")
def test_missing_value_policy_has_tables():
    elements = convert_markdown(SOP_DIR / "missing_value_policy.md")
    tables = [e for e in elements if e.content_type == "parameter_table"]
    assert len(tables) > 0


@pytest.mark.skipif(not (SOP_DIR / "sensor_drift_investigation.md").exists(),
                    reason="SOP not found")
def test_sensor_drift_has_warnings():
    elements = convert_markdown(SOP_DIR / "sensor_drift_investigation.md")
    warnings = [e for e in elements if e.content_type == "warning"]
    assert len(warnings) >= 1
