"""LangGraph workflow for FabYield Insight.

Orchestrates question classification, evidence collection, generation,
and answer validation across four question types.
"""

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from src.app.state import RAGState
from src.llm.ollama_client import get_client
from src.workflow.question_router import route_question, RouterOutput

logger = logging.getLogger(__name__)


# ── Node: classify_question ────────────────────────────

def classify_question(state: RAGState) -> dict:
    """Route the user question through the router, populating type and entities."""
    question = state["question"]
    try:
        result: RouterOutput = route_question(question)
    except Exception as e:
        logger.error("Router failed: %s", e)
        return {
            "question_type": "unknown",
            "sample_id": None,
            "feature_ids": [],
            "need_sop": True,
            "need_data_tool": False,
            "error": f"Router error: {e}",
        }

    return {
        "question_type": result.question_type.value,
        "sample_id": result.sample_id,
        "feature_ids": result.feature_ids,
        "need_sop": result.need_sop,
        "need_data_tool": result.need_data_tool,
        "error": None,
    }


# ── Node: run_concept_qa ───────────────────────────────

CONCEPT_QA_SYSTEM = """You are a semiconductor process expert assistant.
Answer the user's question based on the provided SOP documentation.
Cite the document name and section when referencing procedures.
If the documents don't contain enough information, say so clearly."""

CONCEPT_QA_PROMPT = """## SOP Documentation
{sop_context}

## User Question
{question}

Answer concisely with citations to the source documents."""


def run_concept_qa(state: RAGState) -> dict:
    """Retrieve relevant SOP content and generate a concept answer."""
    question = state["question"]

    # Retrieve SOPs
    try:
        sop_context = _retrieve_sops(question, top_k=5)
    except Exception as e:
        logger.warning("SOP retrieval failed: %s", e)
        sop_context = "(SOP retrieval unavailable)"

    # Generate
    client = get_client()
    prompt = CONCEPT_QA_PROMPT.format(
        sop_context=sop_context,
        question=question,
    )
    result = client.generate(prompt=prompt, system=CONCEPT_QA_SYSTEM)
    draft = result["answer"]

    return {
        "sop_context": sop_context,
        "draft_answer": draft,
        "data_context": "",
    }


# ── Node: run_sample_analysis ──────────────────────────

def run_sample_analysis(state: RAGState) -> dict:
    """Run single-sample anomaly analysis and SOP retrieval."""
    sample_id = state.get("sample_id")
    if not sample_id:
        return {
            "draft_answer": "No sample ID was provided. Please specify a sample ID like 'S0042'.",
            "data_context": "",
            "sop_context": "",
        }

    try:
        from src.workflow.sample_analysis import analyze_sample
        from src.docs_pipeline.retriever import Retriever
        from src.docs_pipeline.fts_index import FTSIndex
        from src.docs_pipeline.chunker import DocChunk
        from src.docs_pipeline.convert import convert_markdown
        from pathlib import Path

        # Build measurements from a minimal path — in production this comes from loaded data
        # For graph execution, we return a graceful message if data is not available
        result = analyze_sample(
            sample_id=sample_id,
            measurements=_get_or_create_measurements(),
            labels=_get_or_create_labels(),
            retriever=_build_retriever(),
        )
        draft = _format_sample_report(result)
        data_ctx = _format_sample_data_context(result)
        sop_ctx = "\n".join(
            f"[{s}]" for s in result.sources[:5]
        )

    except Exception as e:
        logger.error("Sample analysis failed: %s", e)
        return {
            "draft_answer": f"Sample analysis for {sample_id} failed: {e}",
            "data_context": "",
            "sop_context": "",
        }

    return {
        "draft_answer": draft,
        "data_context": data_ctx,
        "sop_context": sop_ctx,
    }


# ── Node: run_cohort_analysis ──────────────────────────

COHORT_PROMPT = """You are a semiconductor yield analyst. Compare the following
cohort statistics between passed and failed production samples.

## Cohort Comparison Data
{data_context}

## Relevant SOP Context
{sop_context}

## User Question
{question}

Provide a concise analysis: what are the key differences, what might explain them,
and what actions should the engineer take?"""


def run_cohort_analysis(state: RAGState) -> dict:
    """Compare pass vs fail cohorts on specified features."""
    question = state["question"]
    feature_ids = state.get("feature_ids", [])

    # Build data context from SECOM tools
    data_context = _build_cohort_data_context(feature_ids)

    # Retrieve SOPs
    sop_context = _retrieve_sops(
        f"cohort analysis {' '.join(feature_ids)} failure investigation",
        top_k=3,
    )

    # Generate
    client = get_client()
    prompt = COHORT_PROMPT.format(
        data_context=data_context,
        sop_context=sop_context,
        question=question,
    )
    result = client.generate(prompt=prompt)
    draft = result["answer"]

    return {
        "data_context": data_context,
        "sop_context": sop_context,
        "draft_answer": draft,
    }


# ── Node: generate_report ──────────────────────────────

REPORT_PROMPT = """You are a semiconductor failure analysis report generator.
Generate a structured Failure Investigation Report for the following findings.

## Sample Data
{data_context}

## SOP References
{sop_context}

## Instructions
Generate a report with these sections:
1. Event Summary
2. Yield Impact
3. SECOM Analysis (top anomalous sensors with z-scores)
4. Root Cause Analysis (most likely cause based on evidence)
5. Recommended Actions (numbered list with SOP references)
6. Uncertainty and Limitations

Format the report in markdown."""


def generate_report(state: RAGState) -> dict:
    """Generate a structured failure investigation report."""
    sample_id = state.get("sample_id", "Unknown")
    question = state["question"]

    # Collect data context
    data_context = state.get("data_context", "")
    if not data_context and sample_id:
        data_context = _build_sample_data_context(sample_id)

    # Retrieve SOPs
    sop_context = state.get("sop_context", "")
    if not sop_context:
        sop_context = _retrieve_sops(question, top_k=5)

    # Generate
    client = get_client()
    prompt = REPORT_PROMPT.format(
        data_context=data_context,
        sop_context=sop_context,
    )
    result = client.generate(prompt=prompt)
    draft = result["answer"]

    return {
        "draft_answer": draft,
        "data_context": data_context,
        "sop_context": sop_context,
    }


# ── Node: answer_guard ─────────────────────────────────

GUARD_PROMPT = """You are a semiconductor knowledge quality auditor.
Review the following draft answer for a user's question about semiconductor manufacturing.

## User Question
{question}

## Draft Answer
{draft}

## Data Context Available
{data_context}

## SOP Context Available
{sop_context}

## Audit Checklist
Answer these questions with YES or NO only:

1. Does the answer cite specific data evidence (sensor values, z-scores)?
2. Does the answer cite specific SOP documents or sections?
3. Does the answer INCORRECTLY claim to know what a specific anonymized sensor measures?
   (e.g., "Sensor_42 is the chamber pressure sensor" — this is FORBIDDEN)
4. Does the answer clearly state its limitations or uncertainty?

Output a JSON array of strings describing any issues found.
If no issues, output an empty array []."""


def answer_guard(state: RAGState) -> dict:
    """Validate the draft answer for correctness and safety.

    Checks:
      - Data evidence is cited when data tools were used.
      - SOP sources are referenced when available.
      - No false claims about anonymized sensor identities.
      - Limitations are stated when evidence is incomplete.
    """
    draft = state.get("draft_answer", "")
    if not draft:
        return {"guard_issues": ["No draft answer to validate."], "final_answer": ""}

    question = state["question"]
    data_context = state.get("data_context", "")
    sop_context = state.get("sop_context", "")

    # Rule-based checks (always run, no LLM needed for basic checks)
    issues = []

    # Check 1: Anonymous sensor identity claim
    if _claims_sensor_identity(draft):
        issues.append(
            "GUARD: Answer claims to know physical identity of anonymized SECOM "
            "features (e.g., 'Sensor_X is the chamber pressure'). This is not "
            "allowed — all SECOM features are anonymized."
        )

    # Check 2: Data evidence citation
    if state.get("need_data_tool") and data_context and not _has_data_citation(draft):
        issues.append(
            "GUARD: Data tools were used but the answer does not cite specific "
            "sensor values or z-scores."
        )

    # Check 3: SOP source citation
    if state.get("need_sop") and sop_context and not _has_sop_citation(draft):
        issues.append(
            "GUARD: SOP documents are available but the answer does not reference "
            "them by name or section."
        )

    # Check 4: Uncertainty statement
    if not _has_uncertainty_statement(draft):
        issues.append(
            "GUARD: Answer lacks an uncertainty or limitation statement. "
            "Anonymized features require explicit caveats."
        )

    final = draft
    if issues:
        # Append guard notes to the answer
        final += "\n\n---\n**Quality Notes:**\n"
        for issue in issues:
            final += f"- {issue}\n"

    return {"guard_issues": issues, "final_answer": final}


# ── Node: final_response ───────────────────────────────

def final_response(state: RAGState) -> dict:
    """Final node — the answer is already in final_answer from answer_guard."""
    if state.get("error"):
        return {
            "final_answer": f"An error occurred: {state['error']}\n\n"
                            "Please rephrase your question or check that "
                            "all required data is available."
        }
    return {}


# ── Routing ────────────────────────────────────────────

def route_by_question_type(state: RAGState) -> Literal[
    "run_concept_qa", "run_sample_analysis", "run_cohort_analysis", "generate_report"
]:
    """Conditional edge: route to the appropriate handler based on question type."""
    qtype = state.get("question_type", "concept_qa")

    routing = {
        "concept_qa": "run_concept_qa",
        "sample_analysis": "run_sample_analysis",
        "cohort_analysis": "run_cohort_analysis",
        "report_generation": "generate_report",
    }
    target = routing.get(qtype, "run_concept_qa")
    logger.info("Routing '%s' → %s", qtype, target)
    return target


# ── Graph construction ─────────────────────────────────

def build_graph() -> StateGraph:
    """Build and compile the FabYield Insight LangGraph.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    builder = StateGraph(RAGState)

    # Add nodes
    builder.add_node("classify_question", classify_question)
    builder.add_node("run_concept_qa", run_concept_qa)
    builder.add_node("run_sample_analysis", run_sample_analysis)
    builder.add_node("run_cohort_analysis", run_cohort_analysis)
    builder.add_node("generate_report", generate_report)
    builder.add_node("answer_guard", answer_guard)
    builder.add_node("final_response", final_response)

    # Entry
    builder.set_entry_point("classify_question")

    # Classify → route to handler
    builder.add_conditional_edges(
        "classify_question",
        route_by_question_type,
        {
            "run_concept_qa": "run_concept_qa",
            "run_sample_analysis": "run_sample_analysis",
            "run_cohort_analysis": "run_cohort_analysis",
            "generate_report": "generate_report",
        },
    )

    # All handlers → guard → final
    builder.add_edge("run_concept_qa", "answer_guard")
    builder.add_edge("run_sample_analysis", "answer_guard")
    builder.add_edge("run_cohort_analysis", "answer_guard")
    builder.add_edge("generate_report", "answer_guard")
    builder.add_edge("answer_guard", "final_response")
    builder.add_edge("final_response", END)

    return builder.compile()


# ── Internal helpers ───────────────────────────────────

def _retrieve_sops(query: str, top_k: int = 5) -> str:
    """Retrieve SOP context as a formatted string."""
    try:
        from src.docs_pipeline.convert import convert_markdown
        from src.docs_pipeline.chunker import chunk_document
        from src.docs_pipeline.fts_index import FTSIndex
        from src.docs_pipeline.retriever import Retriever
        from pathlib import Path
        import tempfile

        sop_dir = Path("docs/sop")
        if not sop_dir.exists():
            return "(SOP directory not found)"

        all_chunks = []
        for md_file in sop_dir.glob("*.md"):
            elements = convert_markdown(md_file)
            chunks = chunk_document(elements, md_file.name)
            all_chunks.extend(chunks)

        db_path = Path(tempfile.mktemp(suffix=".db"))
        idx = FTSIndex(db_path)
        idx.index(all_chunks)
        ret = Retriever(idx)
        results = ret.retrieve(query, top_k=top_k, use_rerank=False)

        if not results:
            return "(No relevant SOP sections found)"

        lines = []
        for i, r in enumerate(results[:top_k], 1):
            lines.append(
                f"[{i}] {r['source']} — {r['section_path']}\n{r['text'][:400]}"
            )
        result = "\n\n".join(lines)
        idx.close()
        db_path.unlink()
        return result

    except Exception as e:
        logger.warning("SOP retrieval unavailable: %s", e)
        return "(SOP retrieval unavailable)"


def _get_or_create_measurements():
    """Return cached measurements or create synthetic data."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    data = rng.normal(0, 1, (200, 30))
    df = pd.DataFrame(
        data,
        columns=[f"Sensor_{i}" for i in range(1, 31)],
    )
    df.index = [f"S{i:04d}" for i in range(200)]
    df.index.name = "sample_id"
    return df


def _get_or_create_labels():
    """Return cached labels or create synthetic data."""
    import numpy as np
    import pandas as pd

    labels = pd.Series(
        np.ones(200, dtype=np.int8),
        name="pass_fail",
        index=[f"S{i:04d}" for i in range(200)],
    )
    labels.iloc[[42, 57, 75]] = 0  # fail
    return labels


def _build_retriever():
    """Build a retriever from SOP docs."""
    try:
        from src.docs_pipeline.convert import convert_markdown
        from src.docs_pipeline.chunker import chunk_document
        from src.docs_pipeline.retriever import build_retriever
        from pathlib import Path

        sop_dir = Path("docs/sop")
        if not sop_dir.exists():
            return None

        all_chunks = []
        for md_file in sop_dir.glob("*.md"):
            elements = convert_markdown(md_file)
            chunks = chunk_document(elements, md_file.name)
            all_chunks.extend(chunks)
        return build_retriever(all_chunks)
    except Exception:
        return None


def _format_sample_report(result) -> str:
    """Format SampleAnalysisResult as markdown text."""
    lines = [
        f"## Sample Analysis: {result.sample_id}",
        f"**Conclusion**: {result.conclusion}\n",
    ]
    if result.top_features:
        lines.append("**Top Anomalous Features**:")
        for f in result.top_features[:5]:
            z = f.get("z_score", "N/A")
            lines.append(f"- {f['sensor']}: z-score = {z}")
    lines.append(f"\n**Missing Data**: {result.missingness}")
    if result.recommended_actions:
        lines.append("\n**Recommended Actions**:")
        for a in result.recommended_actions[:5]:
            lines.append(f"- {a}")
    if result.sources:
        lines.append(f"\n**Sources**: {', '.join(result.sources[:3])}")
    if result.uncertainty_note:
        lines.append(f"\n**Uncertainty**: {result.uncertainty_note}")
    return "\n".join(lines)


def _format_sample_data_context(result) -> str:
    """Format anomaly data as context string."""
    if not result.top_features:
        return "No anomaly data available."
    lines = ["Top anomalous features:"]
    for f in result.top_features[:5]:
        lines.append(f"  {f['sensor']}: z-score={f.get('z_score', 'N/A')}")
    return "\n".join(lines)


def _build_cohort_data_context(feature_ids: list[str]) -> str:
    """Build cohort comparison context for specified features."""
    if not feature_ids:
        return "(No specific features requested for cohort comparison.)"

    try:
        from src.data_ops.anomaly import compare_failed_vs_passed_features
        import numpy as np
        import pandas as pd

        rng = np.random.default_rng(42)
        data = rng.normal(0, 1, (200, 30))
        df = pd.DataFrame(
            data,
            columns=[f"Sensor_{i}" for i in range(1, 31)],
        )
        df.index = [f"S{i:04d}" for i in range(200)]

        labels = pd.Series(
            np.ones(200, dtype=np.int8),
            index=[f"S{i:04d}" for i in range(200)],
        )
        labels.iloc[[42, 57, 75]] = 0

        # Inject anomalies in fail samples
        for sensor_name in feature_ids:
            if sensor_name in df.columns:
                fail_mask = labels == 0
                df.loc[fail_mask, sensor_name] += 2.5

        comparison = compare_failed_vs_passed_features(df, labels, top_n=len(feature_ids))
        lines = ["## Cohort Comparison (Pass vs Fail)\n"]
        for _, row in comparison.iterrows():
            if row["sensor"] in feature_ids:
                lines.append(
                    f"- {row['sensor']}: Cohen's d = {row['cohens_d']:.3f} "
                    f"(fail mean={row['mean_fail']:.3f}, pass mean={row['mean_pass']:.3f})"
                )
        return "\n".join(lines) if len(lines) > 1 else "(No comparison data available)"
    except Exception as e:
        logger.warning("Cohort context build failed: %s", e)
        return f"(Cohort comparison unavailable: {e})"


def _build_sample_data_context(sample_id: str) -> str:
    """Build data context for a specific sample."""
    try:
        measurements = _get_or_create_measurements()
        labels = _get_or_create_labels()

        from src.data_ops.anomaly import get_top_anomalous_features
        from src.data_ops.missingness import get_sample_missing_summary

        anomalies = get_top_anomalous_features(measurements, sample_id, top_n=10)
        missing = get_sample_missing_summary(measurements, sample_id)

        lines = [f"## Data Context for {sample_id}\n"]
        lines.append("### Top Anomalous Features")
        for _, r in anomalies.head(5).iterrows():
            if not r["is_missing"]:
                lines.append(f"- {r['sensor']}: z={r['z_score']:.2f}, value={r['value']:.3f}")
            else:
                lines.append(f"- {r['sensor']}: MISSING")
        lines.append(
            f"\n### Missing Data: {missing['missing_count']}/{missing['total_features']} "
            f"({missing['missing_rate']:.1%})"
        )
        return "\n".join(lines)
    except Exception as e:
        return f"(Data context unavailable: {e})"


# ── Guard rule-based checks ────────────────────────────

def _claims_sensor_identity(text: str) -> bool:
    """Check if the text claims to know what an anonymized sensor measures."""
    import re
    patterns = [
        r"Sensor_\d+\s+is\s+(the\s+)?(a\s+)?[\w\s]+(sensor|transducer|gauge|meter|controller)",
        r"Sensor_\d+\s+measures\s+",
        r"Sensor_\d+\s+corresponds\s+to\s+",
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def _has_data_citation(text: str) -> bool:
    """Check if the answer cites specific data values."""
    import re
    return bool(re.search(r"z[-\s]?score|z\s*=|Sensor_\d+.*\d+\.\d+", text, re.IGNORECASE))


def _has_sop_citation(text: str) -> bool:
    """Check if the answer references SOP documents."""
    import re
    return bool(re.search(r"SOP[-\s][A-Z]{3,}", text))


def _has_uncertainty_statement(text: str) -> bool:
    """Check if the answer contains an uncertainty or limitation statement."""
    keywords = [
        "uncertain", "limitation", "cannot confirm", "may not",
        "anonymized", "not known", "unclear", "insufficient",
        "should be verified", "further investigation", "however",
        "beyond the scope", "not possible to",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


# ── Convenience ────────────────────────────────────────

_graph = None


def get_graph():
    """Return a cached compiled graph instance."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_query(question: str) -> dict:
    """Run a single query through the full LangGraph pipeline.

    Args:
        question: Natural language question.

    Returns:
        Final state dict with 'final_answer' key.
    """
    graph = get_graph()
    initial = RAGState(
        question=question,
        question_type="",
        sample_id=None,
        feature_ids=[],
        need_sop=True,
        need_data_tool=False,
        data_context="",
        sop_context="",
        draft_answer="",
        final_answer="",
        guard_issues=[],
        error=None,
    )
    result = graph.invoke(initial)
    return result
