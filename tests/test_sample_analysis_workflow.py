"""Tests for sample-level semiconductor analysis workflow."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.workflow.sample_analysis import (
    SampleAnalysisResult,
    SAMPLE_ANALYSIS_PROMPT,
    _extract_actions,
    _extract_conclusion,
    _extract_uncertainty,
    _format_anomaly_table,
    _format_missing,
    _format_sop_context,
    _retrieve_relevant_sops,
    analyze_sample,
)


# ── synthetic data ───────────────────────────────────────

def _make_synth_measurements(n_samples=100, n_features=30, seed=42):
    rng = np.random.default_rng(seed)
    data = rng.normal(0, 1, (n_samples, n_features))
    # Inject anomalies in S0042 on Sensor_3, Sensor_15
    data[42, 3] += 4.5
    data[42, 15] += -3.2
    # Inject NaN
    data[42, 5] = np.nan
    data[42, 8] = np.nan
    df = pd.DataFrame(
        data,
        columns=[f"Sensor_{i}" for i in range(1, n_features + 1)],
    )
    df.index = [f"S{i:04d}" for i in range(n_samples)]
    df.index.name = "sample_id"
    return df


def _make_synth_labels(n_samples=100, seed=42):
    rng = np.random.default_rng(seed)
    labels = pd.Series(np.ones(n_samples, dtype=np.int8), name="pass_fail")
    labels.index = [f"S{i:04d}" for i in range(n_samples)]
    fail_idx = [42, 57, 75]  # S0042, S0057, S0075
    labels.iloc[fail_idx] = 0
    return labels


@pytest.fixture
def synth_measurements():
    return _make_synth_measurements()


@pytest.fixture
def synth_labels():
    return _make_synth_labels()


# ── SampleAnalysisResult ─────────────────────────────────

def test_result_dataclass():
    r = SampleAnalysisResult(
        sample_id="S0042",
        conclusion="Sensor_3 shows elevated reading.",
        top_features=[{"sensor": "Sensor_3", "z_score": 4.5}],
        missingness={"total_features": 30, "missing_count": 2, "missing_rate": 0.067},
        recommended_actions=["Check Sensor_3 calibration."],
        sources=["SOP-CAL-007.md"],
        uncertainty_note="Missing data in 2 sensors.",
    )
    assert r.sample_id == "S0042"
    assert r.conclusion
    assert len(r.top_features) == 1
    assert len(r.recommended_actions) == 1
    assert len(r.sources) == 1


def test_result_defaults():
    r = SampleAnalysisResult(sample_id="S0000", conclusion="OK")
    assert r.top_features == []
    assert r.recommended_actions == []
    assert r.sources == []
    assert r.uncertainty_note == ""


# ── _extract helpers ─────────────────────────────────────

MOCK_LLM_OUTPUT = """1. **Conclusion**: Sensor_3 shows elevated RF power (+4.5 sigma) and Sensor_15 shows depressed pressure (-3.2 sigma). This pattern suggests an RF matching network issue affecting chamber pressure stability.

2. **Key Evidence**:
- Sensor_3: z=+4.50, value=4.52, population mean=-0.02
- Sensor_15: z=-3.20, value=-3.18, population mean=-0.01

3. **Missing Data Impact**: 2/30 sensors missing (6.7%), not affecting the primary anomaly signals.

4. **Recommended Actions**:
1. Check RF power supply calibration (SOP-CAL-007).
2. Verify matching network tuning for Sensor_3.
3. Cross-check Sensor_15 against group members Sensor_14, Sensor_16.
4. If both sensors confirmed anomalous, inspect chamber for arcing damage.

5. **Uncertainty Note**: Sensor_5 and Sensor_8 are missing, which limits full cross-correlation analysis."""


def test_extract_conclusion():
    assert "Sensor_3 shows" in _extract_conclusion(MOCK_LLM_OUTPUT)


def test_extract_actions():
    actions = _extract_actions(MOCK_LLM_OUTPUT)
    assert len(actions) >= 3
    assert any("RF power" in a for a in actions) or any("calibration" in a for a in actions)


def test_extract_uncertainty():
    note = _extract_uncertainty(MOCK_LLM_OUTPUT)
    assert "Sensor_5" in note or "missing" in note.lower()


def test_extract_conclusion_fallback():
    """If no structured conclusion found, return first substantial paragraph."""
    text = "This is a test\n\nShort.\n\nThis longer paragraph should be the fallback conclusion for the analysis."
    result = _extract_conclusion(text)
    assert "fallback" in result


def test_extract_actions_fallback():
    text = "Some text without clear actions.\n1. First action.\n2. Second action.\n3. Third action."
    actions = _extract_actions(text)
    assert len(actions) == 3
    assert "First action" in actions[0]


# ── _format helpers ──────────────────────────────────────

def test_format_anomaly_table(synth_measurements):
    from src.data_ops.anomaly import get_top_anomalous_features
    top = get_top_anomalous_features(synth_measurements, "S0042", top_n=5)
    table = _format_anomaly_table(top)
    assert "Sensor" in table
    assert "z-score" in table
    assert "MISSING" in table or "|" in table


def test_format_missing():
    assert _format_missing({"missing_rate": 0.067, "missing_count": 4, "total_features": 60}) == (
        "4/60 features missing (6.7%)."
    )


def test_format_sop_context():
    chunks = [
        {
            "source": "SOP-CAL-007.md",
            "section_path": "3. Calibration",
            "text": "Check sensor calibration.",
        },
    ]
    ctx = _format_sop_context(chunks)
    assert "SOP-CAL-007.md" in ctx
    assert "3. Calibration" in ctx


def test_format_sop_context_empty():
    assert _format_sop_context([]) == "(No relevant SOP sections found.)"


# ── SAMPLE_ANALYSIS_PROMPT ───────────────────────────────

def test_prompt_contains_placeholders():
    assert "{sample_id}" in SAMPLE_ANALYSIS_PROMPT
    assert "{anomaly_table}" in SAMPLE_ANALYSIS_PROMPT
    assert "{missing_summary}" in SAMPLE_ANALYSIS_PROMPT
    assert "{sop_context}" in SAMPLE_ANALYSIS_PROMPT


# ── analyze_sample (mocked LLM) ──────────────────────────

@pytest.fixture
def mock_llm():
    with patch("src.workflow.sample_analysis.get_client") as mock:
        client = MagicMock()
        client.generate.return_value = {"answer": MOCK_LLM_OUTPUT, "reasoning": ""}
        mock.return_value = client
        yield mock


@pytest.fixture
def mock_retriever():
    ret = MagicMock()
    ret.retrieve.return_value = [
        {
            "chunk_id": "abc123",
            "text": "Check RF power supply for drift. Recalibrate if >1.5 sigma.",
            "source": "SOP-CAL-007.md",
            "section_path": "3. Calibration Check",
            "content_type": "procedure",
            "rank": 0.5,
            "score": 0.5,
        },
    ]
    ret.retrieve_warnings.return_value = [
        {
            "chunk_id": "warn1",
            "text": "WARNING: Power down equipment before checking RF matching network.",
            "source": "SOP-CAL-007.md",
            "section_path": "1. Safety",
            "content_type": "warning",
            "rank": 0.3,
            "score": 0.3,
        },
    ]
    return ret


def test_analyze_sample_basic(mock_llm, mock_retriever, synth_measurements, synth_labels):
    result = analyze_sample(
        sample_id="S0042",
        measurements=synth_measurements,
        labels=synth_labels,
        retriever=mock_retriever,
        top_n=5,
        recall_n=2,
    )
    assert isinstance(result, SampleAnalysisResult)
    assert result.sample_id == "S0042"
    assert len(result.conclusion) > 0
    assert len(result.top_features) > 0
    assert result.missingness["missing_rate"] >= 0
    assert len(result.recommended_actions) >= 1
    assert len(result.sources) >= 1
    assert len(result.uncertainty_note) > 0


def test_analyze_sample_calls_llm(mock_llm, mock_retriever, synth_measurements, synth_labels):
    analyze_sample(
        "S0042", synth_measurements, synth_labels,
        retriever=mock_retriever, top_n=5, recall_n=2,
    )
    mock_llm.return_value.generate.assert_called_once()


def test_analyze_sample_calls_retriever(mock_llm, mock_retriever, synth_measurements, synth_labels):
    analyze_sample(
        "S0042", synth_measurements, synth_labels,
        retriever=mock_retriever, top_n=5, recall_n=2,
    )
    mock_retriever.retrieve.assert_called()
    mock_retriever.retrieve_warnings.assert_called()


def test_analyze_sample_without_labels(mock_llm, mock_retriever, synth_measurements):
    """Should work even without labels (label_text = Unknown)."""
    result = analyze_sample(
        sample_id="S0042",
        measurements=synth_measurements,
        labels=None,
        retriever=mock_retriever,
        top_n=5,
        recall_n=2,
    )
    assert isinstance(result, SampleAnalysisResult)


def test_analyze_sample_top_features_anomalous(mock_llm, mock_retriever, synth_measurements, synth_labels):
    """Injected anomaly sensors should appear in top_features."""
    result = analyze_sample(
        "S0042", synth_measurements, synth_labels,
        retriever=mock_retriever, top_n=10, recall_n=2,
    )
    sensor_names = [f["sensor"] for f in result.top_features]
    # Sensor_4 (index 3) and Sensor_16 (index 15) should be in top results
    anomaly_hits = [s for s in ["Sensor_4", "Sensor_16"] if s in sensor_names[:8]]
    assert len(anomaly_hits) >= 1, f"Expected anomaly sensors in top, got {sensor_names[:8]}"


def test_analyze_sample_invalid_id(mock_llm, mock_retriever, synth_measurements):
    with pytest.raises(KeyError):
        analyze_sample(
            "NONEXIST", synth_measurements, None,
            retriever=mock_retriever, top_n=5, recall_n=2,
        )
