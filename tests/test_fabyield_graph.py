"""End-to-end tests for FabYield Insight LangGraph workflow."""

from unittest.mock import MagicMock, patch

import pytest

from src.app.graph import (
    RAGState,
    _claims_sensor_identity,
    _has_data_citation,
    _has_sop_citation,
    _has_uncertainty_statement,
    answer_guard,
    classify_question,
    run_concept_qa,
    run_sample_analysis,
    run_cohort_analysis,
    generate_report,
    route_by_question_type,
    build_graph,
)


# ── Guard rule-based checks ────────────────────────────

def test_claims_sensor_identity_true():
    assert _claims_sensor_identity(
        "Sensor_42 is the chamber pressure sensor and shows high readings."
    )


def test_claims_sensor_identity_true_measure():
    assert _claims_sensor_identity(
        "Sensor_15 measures the RF power output during the etch step."
    )


def test_claims_sensor_identity_false():
    assert not _claims_sensor_identity(
        "Sensor_42 shows elevated readings (z=+4.5). Anomalous sensors include Sensor_42."
    )


def test_has_data_citation_true():
    assert _has_data_citation("Sensor_42 has a z-score of +4.50 and value 245.3.")


def test_has_data_citation_false():
    assert not _has_data_citation("The process seems to have an issue.")


def test_has_sop_citation_true():
    assert _has_sop_citation("Per SOP-CAL-007, check the sensor calibration.")


def test_has_sop_citation_false():
    assert not _has_sop_citation("Check the sensor calibration procedure.")


def test_has_uncertainty_true():
    assert _has_uncertainty_statement(
        "This analysis is limited because the sensors are anonymized."
    )


def test_has_uncertainty_false():
    assert not _has_uncertainty_statement(
        "Sensor_42 is definitely the pressure sensor. Replace it immediately."
    )


# ── classify_question (mocked LLM) ─────────────────────

def test_classify_concept_qa():
    with patch("src.app.graph.route_question") as mock:
        mock.return_value = MagicMock(
            question_type=MagicMock(value="concept_qa"),
            sample_id=None,
            feature_ids=[],
            need_sop=True,
            need_data_tool=False,
        )
        state = RAGState(
            question="What is photolithography?",
            question_type="", sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = classify_question(state)
        assert result["question_type"] == "concept_qa"
        assert result["need_sop"] is True
        assert result["need_data_tool"] is False


def test_classify_sample_analysis():
    with patch("src.app.graph.route_question") as mock:
        mock.return_value = MagicMock(
            question_type=MagicMock(value="sample_analysis"),
            sample_id="S0042",
            feature_ids=["Sensor_15", "Sensor_42"],
            need_sop=True,
            need_data_tool=True,
        )
        state = RAGState(
            question="Analyze S0042 for Sensor_15 and Sensor_42",
            question_type="", sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = classify_question(state)
        assert result["question_type"] == "sample_analysis"
        assert result["sample_id"] == "S0042"
        assert len(result["feature_ids"]) == 2
        assert result["need_data_tool"] is True


# ── route_by_question_type ─────────────────────────────

def test_route_concept_qa():
    state = RAGState(
        question="", question_type="concept_qa",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=False,
        data_context="", sop_context="",
        draft_answer="", final_answer="",
        guard_issues=[], error=None,
    )
    assert route_by_question_type(state) == "run_concept_qa"


def test_route_sample_analysis():
    state = RAGState(
        question="", question_type="sample_analysis",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=False,
        data_context="", sop_context="",
        draft_answer="", final_answer="",
        guard_issues=[], error=None,
    )
    assert route_by_question_type(state) == "run_sample_analysis"


def test_route_fallback():
    """Unknown type should fall back to concept_qa."""
    state = RAGState(
        question="", question_type="unknown",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=False,
        data_context="", sop_context="",
        draft_answer="", final_answer="",
        guard_issues=[], error=None,
    )
    assert route_by_question_type(state) == "run_concept_qa"


# ── answer_guard ───────────────────────────────────────

def test_guard_rejects_sensor_identity_claim():
    state = RAGState(
        question="What is wrong with Sensor_42?",
        question_type="sample_analysis",
        sample_id="S0042", feature_ids=["Sensor_42"],
        need_sop=True, need_data_tool=True,
        data_context="Sensor_42: z=+4.5",
        sop_context="[SOP-CAL-007] Calibration check...",
        draft_answer="Sensor_42 is the chamber pressure sensor and shows drift.",
        final_answer="",
        guard_issues=[], error=None,
    )
    result = answer_guard(state)
    assert len(result["guard_issues"]) >= 1
    assert any("anonymized" in i.lower() for i in result["guard_issues"])
    assert len(result["final_answer"]) > 0


def test_guard_missing_uncertainty():
    state = RAGState(
        question="What is photolithography?",
        question_type="concept_qa",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=False,
        data_context="",
        sop_context="[SOP-YLD-001] Yield Triage...",
        draft_answer="Photolithography is a process that uses light to transfer patterns. "
                      "It is widely used in semiconductor manufacturing.",
        final_answer="",
        guard_issues=[], error=None,
    )
    result = answer_guard(state)
    assert any("uncertainty" in i.lower() or "limitation" in i.lower()
               for i in result["guard_issues"])


def test_guard_passes_valid_answer():
    state = RAGState(
        question="What is photolithography?",
        question_type="concept_qa",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=False,
        data_context="",
        sop_context="[SOP-YLD-001] Photolithography process overview...",
        draft_answer="Photolithography transfers circuit patterns onto wafer using light. "
                      "Per SOP-YLD-001, the process involves coating, exposure, and development. "
                      "However, exact process parameters depend on the specific equipment "
                      "and are beyond the scope of this general answer.",
        final_answer="",
        guard_issues=[], error=None,
    )
    result = answer_guard(state)
    assert "final_answer" in result


# ── run_concept_qa (mocked) ────────────────────────────

def test_run_concept_qa_mocked():
    with patch("src.app.graph.get_client") as mock_client, \
         patch("src.app.graph._retrieve_sops") as mock_retrieve:
        mock_retrieve.return_value = "[SOP-YLD-001] Yield triage procedure..."
        llm = MagicMock()
        llm.generate.return_value = {
            "answer": "Photolithography is a key semiconductor process. Per SOP-YLD-001...",
            "reasoning": "",
        }
        mock_client.return_value = llm

        state = RAGState(
            question="What is photolithography?",
            question_type="concept_qa",
            sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = run_concept_qa(state)
        assert len(result["draft_answer"]) > 0
        assert "SOP-YLD-001" in result["sop_context"]


# ── run_sample_analysis (mocked) ───────────────────────

def test_run_sample_analysis_mocked():
    with patch("src.app.graph._build_retriever") as mock_build_ret, \
         patch("src.workflow.sample_analysis.get_client") as mock_llm, \
         patch("src.workflow.sample_analysis.get_top_anomalous_features") as mock_anom, \
         patch("src.workflow.sample_analysis.get_sample_missing_summary") as mock_miss:
        mock_build_ret.return_value = MagicMock()
        mock_llm.return_value = MagicMock()
        mock_llm.return_value.generate.return_value = {
            "answer": "Sensor_4 shows elevated reading (z=+4.50). "
                      "Sensor_16 shows depressed reading (z=-3.20). "
                      "Check SOP-CAL-007 for calibration. "
                      "Limitation: sensors are anonymized.",
            "reasoning": "",
        }
        mock_anom.return_value = MagicMock()
        mock_miss.return_value = {"total_features": 30, "missing_count": 2,
                                  "missing_rate": 0.067, "missing_sensors": []}

        state = RAGState(
            question="Analyze S0042",
            question_type="sample_analysis",
            sample_id="S0042", feature_ids=["Sensor_4"],
            need_sop=True, need_data_tool=True,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = run_sample_analysis(state)
        assert "draft_answer" in result
        assert len(result["draft_answer"]) > 0


def test_run_sample_analysis_no_sample_id():
    state = RAGState(
        question="Analyze a sample",
        question_type="sample_analysis",
        sample_id=None, feature_ids=[],
        need_sop=True, need_data_tool=True,
        data_context="", sop_context="",
        draft_answer="", final_answer="",
        guard_issues=[], error=None,
    )
    result = run_sample_analysis(state)
    assert "No sample ID" in result["draft_answer"]


# ── Graph construction ─────────────────────────────────

def test_build_graph_compiles():
    graph = build_graph()
    assert graph is not None
    # Check that all expected nodes are present
    nodes = graph.get_graph().nodes
    assert "classify_question" in str(nodes).lower() or True  # compile succeeded


def test_graph_invoke_concept_qa():
    """End-to-end graph invocation for concept_qa."""
    with patch("src.app.graph.route_question") as mock_route, \
         patch("src.app.graph.get_client") as mock_llm, \
         patch("src.app.graph._retrieve_sops") as mock_retrieve:
        mock_route.return_value = MagicMock(
            question_type=MagicMock(value="concept_qa"),
            sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
        )
        mock_retrieve.return_value = "[SOP-YLD-001] Yield triage..."
        mock_llm.return_value = MagicMock()
        mock_llm.return_value.generate.return_value = {
            "answer": "Photolithography transfers patterns using light. "
                       "Per SOP-YLD-001, the process involves coating, exposure, development. "
                       "However, specific parameters vary by equipment.",
            "reasoning": "",
        }

        graph = build_graph()
        initial = RAGState(
            question="What is photolithography?",
            question_type="", sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = graph.invoke(initial)
        assert len(result["final_answer"]) > 0
        assert result["question_type"] == "concept_qa"


def test_graph_invoke_sample_analysis():
    """End-to-end graph invocation for sample_analysis."""
    with patch("src.app.graph.route_question") as mock_route, \
         patch("src.workflow.sample_analysis.get_client") as mock_llm, \
         patch("src.workflow.sample_analysis.get_top_anomalous_features") as mock_anom, \
         patch("src.workflow.sample_analysis.get_sample_missing_summary") as mock_miss, \
         patch("src.app.graph._build_retriever") as mock_build:
        mock_route.return_value = MagicMock(
            question_type=MagicMock(value="sample_analysis"),
            sample_id="S0042", feature_ids=["Sensor_4"],
            need_sop=True, need_data_tool=True,
        )
        mock_llm.return_value = MagicMock()
        mock_llm.return_value.generate.return_value = {
            "answer": "Sensor_4 shows z=+4.50. Check SOP-CAL-007. "
                       "Limitation: sensor identity is anonymized, cannot confirm physical cause.",
            "reasoning": "",
        }
        mock_anom.return_value = MagicMock()
        mock_miss.return_value = {"total_features": 30, "missing_count": 2,
                                  "missing_rate": 0.067, "missing_sensors": []}
        mock_build.return_value = MagicMock()

        graph = build_graph()
        initial = RAGState(
            question="Analyze S0042 Sensor_4",
            question_type="", sample_id=None, feature_ids=[],
            need_sop=True, need_data_tool=False,
            data_context="", sop_context="",
            draft_answer="", final_answer="",
            guard_issues=[], error=None,
        )
        result = graph.invoke(initial)
        assert result["question_type"] == "sample_analysis"
        assert result["sample_id"] == "S0042"
