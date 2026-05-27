"""Tests for semiconductor question routing and parameter extraction."""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.workflow.question_router import (
    QuestionType,
    RouterOutput,
    _extract_json_block,
    _normalize,
    _repair_json,
    _try_parse,
    route_question,
)


# ── RouterOutput model tests ─────────────────────────────

def test_router_output_concept_qa():
    out = RouterOutput(
        question_type=QuestionType.CONCEPT_QA,
        need_sop=True,
        need_data_tool=False,
    )
    assert out.question_type == QuestionType.CONCEPT_QA
    assert out.sample_id is None
    assert out.feature_ids == []
    assert out.need_sop is True
    assert out.need_data_tool is False


def test_router_output_sample_analysis():
    out = RouterOutput(
        question_type=QuestionType.SAMPLE_ANALYSIS,
        sample_id="S0042",
        feature_ids=["Sensor_15", "Sensor_42"],
        need_sop=True,
        need_data_tool=True,
    )
    assert out.sample_id == "S0042"
    assert len(out.feature_ids) == 2
    assert out.need_data_tool is True


def test_router_output_invalid_question_type():
    with pytest.raises(ValidationError):
        RouterOutput(question_type="invalid_type")  # type: ignore


def test_router_output_defaults():
    out = RouterOutput(question_type=QuestionType.UNKNOWN)
    assert out.sample_id is None
    assert out.feature_ids == []
    assert out.need_sop is True   # default
    assert out.need_data_tool is False  # default


# ── _try_parse ───────────────────────────────────────────

def test_try_parse_valid():
    assert _try_parse('{"a": 1}') == {"a": 1}


def test_try_parse_array():
    assert _try_parse("[1, 2]") == [1, 2]


def test_try_parse_malformed():
    assert _try_parse('{"a": 1') is None


def test_try_parse_empty():
    assert _try_parse("") is None


# ── _extract_json_block ──────────────────────────────────

def test_extract_fenced_json():
    text = 'Here is result:\n```json\n{"key": "value"}\n```'
    assert _extract_json_block(text) == '{"key": "value"}'


def test_extract_no_fence():
    text = 'The answer is {"question_type": "concept_qa"} done.'
    result = _extract_json_block(text)
    assert result == '{"question_type": "concept_qa"}'


def test_extract_no_braces():
    assert _extract_json_block("Just some text.") is None


# ── _repair_json ─────────────────────────────────────────

def test_repair_trailing_comma():
    repaired = _repair_json('{"a": 1, "b": 2,}')
    assert _try_parse(repaired) == {"a": 1, "b": 2}


def test_repair_unquoted_keys():
    repaired = _repair_json('{question_type: "sample_analysis", sample_id: "S0042"}')
    parsed = _try_parse(repaired)
    assert parsed["question_type"] == "sample_analysis"
    assert parsed["sample_id"] == "S0042"


def test_repair_single_quotes():
    repaired = _repair_json("{'question_type': 'concept_qa'}")
    parsed = _try_parse(repaired)
    assert parsed["question_type"] == "concept_qa"


def test_repair_python_bools():
    repaired = _repair_json("{'need_sop': True, 'need_data_tool': False}")
    parsed = _try_parse(repaired)
    assert parsed["need_sop"] is True
    assert parsed["need_data_tool"] is False


def test_repair_no_braces():
    assert _repair_json("just text") is None


# ── _normalize ───────────────────────────────────────────

def test_normalize_null_sample_id():
    raw = {"question_type": "concept_qa", "sample_id": None, "feature_ids": [],
           "need_sop": True, "need_data_tool": False}
    out = _normalize(raw)
    assert out.sample_id is None


def test_normalize_string_bools():
    raw = {"question_type": "concept_qa", "sample_id": None, "feature_ids": [],
           "need_sop": "true", "need_data_tool": "false"}
    out = _normalize(raw)
    assert out.need_sop is True
    assert out.need_data_tool is False


def test_normalize_missing_feature_ids():
    raw = {"question_type": "concept_qa", "sample_id": None,
           "need_sop": True, "need_data_tool": False}
    out = _normalize(raw)
    assert out.feature_ids == []


# ── route_question (mocked LLM) ──────────────────────────

def _mock_generate(answer: str):
    return {
        "reasoning": "",
        "answer": answer,
        "raw": "",
        "model": "test",
        "usage": {},
    }


def test_route_concept_qa(monkeypatch):
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '{"question_type": "concept_qa", "sample_id": null, '
        '"feature_ids": [], "need_sop": true, "need_data_tool": false}'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("What is photolithography?")
    assert result.question_type == QuestionType.CONCEPT_QA
    assert result.need_sop is True
    assert result.need_data_tool is False


def test_route_sample_analysis(monkeypatch):
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '{"question_type": "sample_analysis", "sample_id": "S0042", '
        '"feature_ids": ["Sensor_15", "Sensor_42"], '
        '"need_sop": true, "need_data_tool": true}'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("Analyze S0042 for Sensor_15 and Sensor_42 anomalies")
    assert result.question_type == QuestionType.SAMPLE_ANALYSIS
    assert result.sample_id == "S0042"
    assert "Sensor_15" in result.feature_ids
    assert result.need_data_tool is True


def test_route_cohort_analysis(monkeypatch):
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '{"question_type": "cohort_analysis", "sample_id": null, '
        '"feature_ids": ["Sensor_3"], '
        '"need_sop": false, "need_data_tool": true}'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("Compare Sensor_3 distribution between pass and fail lots")
    assert result.question_type == QuestionType.COHORT_ANALYSIS
    assert result.need_data_tool is True


def test_route_report_generation(monkeypatch):
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '{"question_type": "report_generation", "sample_id": "S0042", '
        '"feature_ids": [], '
        '"need_sop": true, "need_data_tool": true}'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("Generate a failure report for sample S0042")
    assert result.question_type == QuestionType.REPORT_GENERATION


def test_route_with_fenced_json(monkeypatch):
    """Router should handle markdown-fenced JSON from LLM."""
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '```json\n{"question_type": "concept_qa", "sample_id": null, '
        '"feature_ids": [], "need_sop": true, "need_data_tool": false}\n```'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("What is RTA?")
    assert result.question_type == QuestionType.CONCEPT_QA


def test_route_with_repair_needed(monkeypatch):
    """Repair unquoted keys and trailing comma."""
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        '{question_type: "concept_qa", sample_id: null, '
        'feature_ids: [], need_sop: True, need_data_tool: False,}'
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    result = route_question("Explain CVD process")
    assert result.question_type == QuestionType.CONCEPT_QA


def test_route_unparseable_raises(monkeypatch):
    """Completely broken output should raise ValueError."""
    client_mock = MagicMock()
    client_mock.generate.return_value = _mock_generate(
        "I'm sorry, I cannot process this request right now."
    )
    monkeypatch.setattr(
        "src.workflow.question_router.get_client", lambda: client_mock
    )
    with pytest.raises(ValueError, match="Failed to parse"):
        route_question("???")


# ── QuestionType enum ────────────────────────────────────

def test_question_type_values():
    assert QuestionType.CONCEPT_QA.value == "concept_qa"
    assert QuestionType.SAMPLE_ANALYSIS.value == "sample_analysis"
    assert QuestionType.COHORT_ANALYSIS.value == "cohort_analysis"
    assert QuestionType.REPORT_GENERATION.value == "report_generation"
    assert QuestionType.UNKNOWN.value == "unknown"
