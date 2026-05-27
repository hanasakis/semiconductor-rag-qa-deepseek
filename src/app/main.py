"""FabYield Insight — Streamlit Workbench for Semiconductor Yield Analysis.

Launch:
    streamlit run src/app/main.py
"""

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
import pandas as pd

from src.app.graph import (
    build_graph,
    RAGState,
    _build_retriever,
    _get_or_create_measurements,
    _get_or_create_labels,
)
from src.workflow.question_router import route_question, RouterOutput
from src.data_ops.anomaly import get_top_anomalous_features
from src.data_ops.missingness import get_sample_missing_summary
from src.docs_pipeline.convert import convert_markdown
from src.docs_pipeline.chunker import chunk_document
from src.docs_pipeline.fts_index import FTSIndex
from src.docs_pipeline.retriever import Retriever
from src.llm.output_cleaner import clean_r1_output

st.set_page_config(
    page_title="FabYield Insight",
    page_icon="wafer",
    layout="wide",
)

# ── Page header ──────────────────────────────────────────

st.title("FabYield Insight")
st.caption("Semiconductor Yield Analysis & Knowledge QA — Powered by Local DeepSeek-R1")


# ── Sidebar ──────────────────────────────────────────────

with st.sidebar:
    st.header("Configuration")

    analysis_mode = st.radio(
        "Analysis Mode",
        ["Auto (Router)", "Sample Analysis", "Concept QA"],
        help="Auto: Let the router classify your question. "
             "Sample Analysis: Force single-sample anomaly analysis. "
             "Concept QA: Force SOP-based knowledge retrieval.",
    )

    st.divider()

    sample_id_quick = st.text_input(
        "Quick Sample ID",
        value="S0042",
        placeholder="e.g. S0042",
        help="Enter a sample ID for quick lookup.",
    )

    if st.button("Quick Analyze Sample", use_container_width=True):
        st.session_state["question"] = f"Analyze sample {sample_id_quick} for anomalies"

    st.divider()

    st.markdown("### Example Questions")
    examples = [
        "What is the yield triage procedure?",
        "Analyze sample S0042 for failure causes",
        "Compare Sensor_4 between pass and fail samples",
        "Generate a failure report for S0042",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state["question"] = ex

    st.divider()
    st.markdown(
        "**Model**: `deepseek-r1:8b` (local Ollama)\n\n"
        "**SOPs**: 4 documents indexed via FTS5\n\n"
        "**Data**: Synthetic SECOM (30 sensors × 200 samples)"
    )


# ── Main input ───────────────────────────────────────────

question = st.text_area(
    "Engineering Question",
    value=st.session_state.get("question", ""),
    placeholder="e.g. What should I do if Sensor_42 shows a z-score of +4.5?",
    height=80,
    key="question_input",
)

col1, col2 = st.columns([1, 4])
with col1:
    run_btn = st.button("Submit Query", type="primary", use_container_width=True)


# ── Initialize session state ─────────────────────────────

if "history" not in st.session_state:
    st.session_state["history"] = []


# ── Run pipeline ─────────────────────────────────────────

if run_btn and question.strip():
    with st.spinner("Classifying question..."):
        try:
            router_output = route_question(question)
        except Exception as e:
            st.error(f"Router error: {e}")
            st.stop()

    qtype = router_output.question_type.value
    sample_id = router_output.sample_id

    if analysis_mode == "Sample Analysis":
        qtype = "sample_analysis"
        if not sample_id:
            sample_id = "S0042"
    elif analysis_mode == "Concept QA":
        qtype = "concept_qa"

    # ── Display router result ──────────────────────────
    st.divider()
    st.subheader("Question Classification")

    rcol1, rcol2, rcol3, rcol4 = st.columns(4)
    with rcol1:
        st.metric("Question Type", qtype.replace("_", " ").title())
    with rcol2:
        st.metric("Sample ID", sample_id or "N/A")
    with rcol3:
        st.metric("Need SOP", "Yes" if router_output.need_sop else "No")
    with rcol4:
        st.metric("Need Data", "Yes" if router_output.need_data_tool else "No")

    if router_output.feature_ids:
        st.caption(f"Features mentioned: {', '.join(router_output.feature_ids)}")

    # ── Run the appropriate pipeline ────────────────────
    st.divider()

    if qtype in ("sample_analysis", "concept_qa"):
        with st.spinner(f"Running {qtype} pipeline..."):
            try:
                _run_analysis_pipeline(
                    question=question,
                    qtype=qtype,
                    sample_id=sample_id,
                    feature_ids=router_output.feature_ids,
                    need_sop=router_output.need_sop,
                    need_data=router_output.need_data_tool,
                )
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                import traceback
                st.code(traceback.format_exc())
    else:
        st.info(
            f"Mode '{qtype}' is not yet implemented in the interactive workbench. "
            "Try 'Sample Analysis' or 'Concept QA' mode."
        )


# ── History ──────────────────────────────────────────────

if st.session_state["history"]:
    st.divider()
    st.subheader("Query History")
    for i, entry in enumerate(reversed(st.session_state["history"][-10:])):
        with st.expander(f"Q{i+1}: {entry['question'][:80]}... ({entry['qtype']})"):
            st.markdown(entry["answer"])
            if entry.get("sources"):
                st.caption(f"Sources: {', '.join(entry['sources'])}")


# ── Pipeline runner ──────────────────────────────────────

def _run_analysis_pipeline(
    question: str,
    qtype: str,
    sample_id: str | None,
    feature_ids: list[str],
    need_sop: bool,
    need_data: bool,
):
    """Execute the analysis workflow and render results in Streamlit."""

    # Load data
    measurements = _get_or_create_measurements()
    labels = _get_or_create_labels()

    # ── Data tools (if needed) ────────────────────────
    top_features = []
    missing_info = {}
    data_ctx = ""

    if need_data and sample_id and sample_id in measurements.index:
        with st.spinner("Computing anomaly scores..."):
            anomalies = get_top_anomalous_features(measurements, sample_id, top_n=10)
            missing_info = get_sample_missing_summary(measurements, sample_id)

        # ── Anomaly table ────────────────────────────
        st.subheader("Top Anomalous Features")
        anomaly_data = []
        for _, r in anomalies.iterrows():
            anomaly_data.append({
                "Sensor": r["sensor"],
                "Value": f"{r['value']:.3f}" if not r["is_missing"] else "MISSING",
                "Pop Mean": f"{r['population_mean']:.3f}" if not r["is_missing"] else "—",
                "z-score": f"{r['z_score']:.2f}" if not r["is_missing"] else "—",
                "|z|": f"{r['abs_z_score']:.2f}" if not r["is_missing"] else "—",
            })
        st.dataframe(
            pd.DataFrame(anomaly_data),
            use_container_width=True,
            hide_index=True,
        )

        # ── Missingness ──────────────────────────────
        st.subheader("Missing Data Summary")
        mcol1, mcol2, mcol3 = st.columns(3)
        with mcol1:
            st.metric("Total Features", missing_info.get("total_features", "N/A"))
        with mcol2:
            st.metric("Missing Count", missing_info.get("missing_count", "N/A"))
        with mcol3:
            st.metric("Missing Rate", f"{missing_info.get('missing_rate', 0):.1%}")

        if missing_info.get("missing_sensors"):
            st.caption(
                f"Missing sensors: {', '.join(missing_info['missing_sensors'][:10])}"
            )

        top_features = anomaly_data
        data_ctx = _build_data_context(anomalies, missing_info)

    # ── SOP retrieval (if needed) ────────────────────
    sop_chunks = []
    if need_sop:
        with st.spinner("Retrieving relevant SOPs..."):
            try:
                retriever = _build_retriever()
                if retriever:
                    search_query = (
                        f"{' '.join(feature_ids)} {sample_id or ''} "
                        f"anomaly investigation procedure"
                    )
                    sop_chunks = retriever.retrieve(
                        search_query, top_k=5, use_rerank=False
                    )
            except Exception as e:
                st.warning(f"SOP retrieval unavailable: {e}")

        if sop_chunks:
            st.subheader("SOP Sources")
            sop_data = []
            for c in sop_chunks[:5]:
                sop_data.append({
                    "Document": c["source"],
                    "Section": c["section_path"],
                    "Type": c["content_type"],
                })
            st.dataframe(
                pd.DataFrame(sop_data),
                use_container_width=True,
                hide_index=True,
            )

    # ── LLM Generation ───────────────────────────────
    with st.spinner("Generating analysis with DeepSeek-R1..."):
        draft = _generate_analysis(
            question=question,
            qtype=qtype,
            sample_id=sample_id,
            data_context=data_ctx,
            sop_chunks=sop_chunks,
        )

    # Clean think tags
    cleaned = clean_r1_output(draft)

    # ── Guard check ──────────────────────────────────
    from src.app.graph import (
        _claims_sensor_identity,
        _has_sop_citation,
        _has_uncertainty_statement,
    )
    guard_notes = []
    if _claims_sensor_identity(cleaned):
        guard_notes.append(
            "Answer claims physical identity of anonymized SECOM features. "
            "Treat all sensor identity statements as statistical correlations, not physical facts."
        )
    if need_sop and sop_chunks and not _has_sop_citation(cleaned):
        guard_notes.append(
            "Answer does not cite specific SOP documents. Sources may need manual verification."
        )
    if not _has_uncertainty_statement(cleaned):
        guard_notes.append(
            "Answer lacks an explicit uncertainty statement. "
            "Reminder: all findings based on anonymized features require physical verification."
        )

    # ── Display answer ──────────────────────────────
    st.divider()
    st.subheader("Engineering Analysis")
    st.markdown(cleaned)

    if guard_notes:
        st.divider()
        st.subheader("Quality Notes")
        for note in guard_notes:
            st.warning(note)

    # ── Save to history ─────────────────────────────
    st.session_state["history"].append({
        "question": question,
        "qtype": qtype,
        "answer": cleaned,
        "sources": [c["source"] for c in sop_chunks[:3]] if sop_chunks else [],
    })


def _build_data_context(anomalies, missing_info) -> str:
    """Build a text summary of data findings for the LLM prompt."""
    lines = [f"## SECOM Data Analysis\n"]
    lines.append("### Top Anomalous Features (by |z-score|)")
    for _, r in anomalies.head(8).iterrows():
        if r["is_missing"]:
            lines.append(f"- {r['sensor']}: MISSING")
        else:
            lines.append(
                f"- {r['sensor']}: value={r['value']:.3f}, mean={r['population_mean']:.3f}, "
                f"z={r['z_score']:.2f}"
            )
    lines.append(
        f"\n### Missing Data: {missing_info.get('missing_count', 0)}/"
        f"{missing_info.get('total_features', '?')} features "
        f"({missing_info.get('missing_rate', 0):.1%})"
    )
    return "\n".join(lines)


def _generate_analysis(
    question: str,
    qtype: str,
    sample_id: str | None,
    data_context: str,
    sop_chunks: list[dict],
) -> str:
    """Generate analysis using DeepSeek-R1."""
    from src.llm.ollama_client import get_client

    sop_text = ""
    if sop_chunks:
        sop_lines = []
        for i, c in enumerate(sop_chunks[:5], 1):
            sop_lines.append(
                f"[{i}] {c['source']} — {c['section_path']}\n{c['text'][:400]}"
            )
        sop_text = "\n\n".join(sop_lines)

    prompt = f"""You are a semiconductor process engineer. Answer the following question.

## User Question
{question}

## Sample ID
{sample_id or 'Not specified'}

## Data Evidence
{data_context or 'No SECOM data available.'}

## SOP Documentation
{sop_text or 'No SOP documents available.'}

## Instructions
1. Provide a direct engineering answer.
2. Cite specific sensor z-scores or values from the data evidence.
3. If SOP documents are available, reference them by document name.
4. State clearly what CANNOT be confirmed due to sensor anonymization.
5. End with a brief uncertainty note.
"""
    client = get_client()
    result = client.generate(prompt=prompt)
    return result["answer"]


# ── Main entrypoint ──────────────────────────────────────

if __name__ == "__main__":
    # Streamlit runs this automatically; this guard prevents
    # execution during import by pytest
    pass
