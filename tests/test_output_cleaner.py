"""Tests for DeepSeek-R1 output cleaner."""

import pytest
from src.llm.output_cleaner import (
    clean_r1_output,
    clean_r1_output_full,
    extract_reasoning,
    strip_whitespace_artifacts,
)

# XML delimiters used by DeepSeek-R1 — constructed at runtime
# to avoid any tool-level character escaping.
LT = chr(60)   # left angle bracket
RT = chr(62)   # right angle bracket

OPEN = f"{LT}think{RT}"
CLOSE = f"{LT}/think{RT}"
RESP = f"{LT}response{RT}"


# ── clean_r1_output ──────────────────────────────────────

@pytest.mark.parametrize(
    "raw,expected",
    [
        (f" {OPEN}reasoning{CLOSE}{RESP}answer text", "answer text"),
        (
            f" {OPEN}step 1: check sensors{CLOSE}{RESP}Sensor V1 is at +3.2 sigma",
            "Sensor V1 is at +3.2 sigma",
        ),
        ("plain answer without thinking", "plain answer without thinking"),
        ("", ""),
        (f"{RESP}bare answer", "bare answer"),
    ],
)
def test_clean_r1_output_parametrized(raw, expected):
    assert clean_r1_output(raw) == expected


def test_clean_r1_output_no_think_tags():
    text = "The chamber pressure is 245 mTorr."
    assert clean_r1_output(text) == text


def test_clean_r1_output_whitespace_trimmed():
    assert clean_r1_output(f" {OPEN} ok  {CLOSE} {RESP} final  ") == "final"


def test_clean_r1_output_format_b():
    """Format B: no response tag, answer directly after closing think."""
    assert clean_r1_output(f"{OPEN}reasoning{CLOSE}answer") == "answer"


# ── extract_reasoning ────────────────────────────────────

def test_extract_reasoning_standard():
    raw = f" {OPEN}Let me analyze the sensor data.{CLOSE}{RESP}Answer here."
    assert "Let me analyze the sensor data" in extract_reasoning(raw)


def test_extract_reasoning_no_tags():
    assert extract_reasoning("plain answer") == ""


def test_extract_reasoning_empty():
    assert extract_reasoning("") == ""


# ── strip_whitespace_artifacts ───────────────────────────

def test_strip_removes_extra_newlines():
    text = "Line1\n\n\n\n\nLine2"
    result = strip_whitespace_artifacts(text)
    assert result == "Line1\n\nLine2"


def test_strip_trims():
    assert strip_whitespace_artifacts("  hello  ") == "hello"


# ── clean_r1_output_full ─────────────────────────────────

def test_clean_r1_output_full_both():
    raw = f" {OPEN}reasoning text{CLOSE}{RESP}final answer"
    result = clean_r1_output_full(raw)
    assert result["reasoning"] == "reasoning text"
    assert result["answer"] == "final answer"


def test_clean_r1_output_full_no_think():
    raw = "Direct answer with no reasoning."
    result = clean_r1_output_full(raw)
    assert result["reasoning"] == ""
    assert result["answer"] == "Direct answer with no reasoning."
