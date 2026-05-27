"""Sample-level semiconductor anomaly analysis workflow.

Orchestrates data tools, SOP retrieval, and LLM generation to produce
a structured failure investigation for a single sample (wafer/die).
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

from src.data_ops.anomaly import get_top_anomalous_features
from src.data_ops.missingness import get_sample_missing_summary
from src.docs_pipeline.fts_index import FTSIndex
from src.docs_pipeline.retriever import build_retriever, Retriever
from src.llm.ollama_client import get_client
from src.llm.output_cleaner import clean_r1_output

logger = logging.getLogger(__name__)


@dataclass
class SampleAnalysisResult:
    """Structured output of a single-sample failure investigation."""

    sample_id: str
    conclusion: str
    top_features: list[dict] = field(default_factory=list)
    missingness: dict = field(default_factory=dict)
    recommended_actions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    uncertainty_note: str = ""


SAMPLE_ANALYSIS_PROMPT = """You are a semiconductor process engineer investigating a yield excursion.

## Sample Information
Sample ID: {sample_id}
Label: {label}

## Anomalous Sensor Readings (top features by |z-score|)
{anomaly_table}

## Missing Data
{missing_summary}

## Relevant SOP Sections
{sop_context}

## Instructions
Based on the data above, write a concise failure investigation analysis.
Structure your response with these sections:

1. **Conclusion** (1-2 sentences): What is the most likely issue with this sample?
2. **Key Evidence** (bullet points): Which sensors are abnormal and what does this suggest?
3. **Missing Data Impact**: Does the missing data affect confidence?
4. **Recommended Actions** (numbered list): What should the engineer do next?
5. **Uncertainty Note** (1 sentence): What is the main limitation of this analysis?

Be specific. Cite sensor IDs and SOP document names. If the data is inconclusive, say so clearly.
"""


def analyze_sample(
    sample_id: str,
    measurements: pd.DataFrame,
    labels: pd.Series | None = None,
    retriever: Retriever | None = None,
    top_n: int = 10,
    recall_n: int = 5,
) -> SampleAnalysisResult:
    """Run a full failure investigation for a single sample.

    Orchestration order:
      1. Data tools: anomalous features + missingness  (data evidence)
      2. SOP retrieval: relevant troubleshooting docs    (document evidence)
      3. LLM generation: synthesize into structured report

    Args:
        sample_id: Sample to analyze (e.g. "S0042").
        measurements: SECOM measurements DataFrame.
        labels: SECOM labels Series (1=pass, 0=fail). Optional.
        retriever: Pre-built Retriever. If None, uses a default path.
        top_n: Number of anomalous features to pull.
        recall_n: Number of SOP chunks to retrieve.

    Returns:
        SampleAnalysisResult with conclusion, evidence, and recommendations.
    """
    # ── Stage 1: Collect data evidence ───────────────────
    anomalies = get_top_anomalous_features(measurements, sample_id, top_n=top_n)
    missing = get_sample_missing_summary(measurements, sample_id)

    label_text = "Unknown"
    if labels is not None and sample_id in labels.index:
        label_val = labels[sample_id]
        label_text = "PASS" if label_val == 1 else "FAIL"

    # ── Stage 2: Collect SOP evidence ────────────────────
    if retriever is None:
        retriever = _default_retriever()

    sop_chunks = _retrieve_relevant_sops(retriever, anomalies, missing, recall_n)

    # ── Stage 3: Generate with LLM ────────────────────────
    anomaly_table = _format_anomaly_table(anomalies)
    missing_text = _format_missing(missing)
    sop_text = _format_sop_context(sop_chunks)

    prompt = SAMPLE_ANALYSIS_PROMPT.format(
        sample_id=sample_id,
        label=label_text,
        anomaly_table=anomaly_table,
        missing_summary=missing_text,
        sop_context=sop_text,
    )

    client = get_client()
    result = client.generate(prompt=prompt)
    raw_answer = result["answer"]

    # ── Stage 4: Structure the result ─────────────────────
    feature_list = anomalies[["sensor", "z_score", "abs_z_score"]].to_dict("records")

    actions = _extract_actions(raw_answer)

    sources_list = [c["source"] for c in sop_chunks[:5]]
    sources_list = list(dict.fromkeys(sources_list))  # dedupe preserving order

    uncertainty = _extract_uncertainty(raw_answer)

    return SampleAnalysisResult(
        sample_id=sample_id,
        conclusion=_extract_conclusion(raw_answer),
        top_features=feature_list,
        missingness={
            "total_features": missing["total_features"],
            "missing_count": missing["missing_count"],
            "missing_rate": missing["missing_rate"],
        },
        recommended_actions=actions,
        sources=sources_list,
        uncertainty_note=uncertainty,
    )


# ── Internal helpers ─────────────────────────────────────

def _default_retriever() -> Retriever:
    """Build a retriever from the default SOP directory."""
    from pathlib import Path
    from src.docs_pipeline.convert import convert_markdown
    from src.docs_pipeline.chunker import chunk_document

    sop_dir = Path("docs/sop")
    all_chunks = []
    for md_file in sop_dir.glob("*.md"):
        elements = convert_markdown(md_file)
        chunks = chunk_document(elements, md_file.name)
        all_chunks.extend(chunks)
    return build_retriever(all_chunks)


def _retrieve_relevant_sops(
    retriever: Retriever,
    anomalies: pd.DataFrame,
    missing: dict,
    recall_n: int,
) -> list[dict]:
    """Build queries from anomaly data and retrieve relevant SOP chunks."""
    chunks = []

    # Query 1: Based on top anomalous sensor groups
    top_sensors = anomalies[anomalies["is_missing"] == False].head(5)
    if len(top_sensors) > 0:
        sensor_names = " ".join(top_sensors["sensor"].tolist())
        chunks.extend(
            retriever.retrieve(
                f"{sensor_names} anomaly investigation procedure",
                top_k=recall_n,
                use_rerank=False,
            )
        )

    # Query 2: Based on missing data
    if missing["missing_rate"] > 0.01:
        chunks.extend(
            retriever.retrieve(
                "missing data imputation handling policy",
                top_k=2,
                use_rerank=False,
            )
        )

    # Query 3: Warning content
    chunks.extend(retriever.retrieve_warnings("safety procedure", top_k=2))

    # Deduplicate by chunk_id
    seen = set()
    unique = []
    for c in chunks:
        if c["chunk_id"] not in seen:
            seen.add(c["chunk_id"])
            unique.append(c)
    return unique


def _format_anomaly_table(anomalies: pd.DataFrame) -> str:
    """Format anomaly DataFrame as a markdown table for the LLM prompt."""
    rows = []
    for _, r in anomalies.iterrows():
        if r["is_missing"]:
            rows.append(
                f"| {r['sensor']} | MISSING | — | — | — |"
            )
        else:
            rows.append(
                f"| {r['sensor']} | {r['value']} | {r['population_mean']} | "
                f"{r['z_score']} | {r['abs_z_score']} |"
            )
    header = "| Sensor | Value | Pop Mean | z-score | |z-score| |\n|--------|-------|----------|---------|----------|"
    return header + "\n" + "\n".join(rows)


def _format_missing(missing: dict) -> str:
    """Format missing data summary for the prompt."""
    pct = missing["missing_rate"] * 100
    return (
        f"{missing['missing_count']}/{missing['total_features']} features missing "
        f"({pct:.1f}%)."
    )


def _format_sop_context(chunks: list[dict]) -> str:
    """Format retrieved SOP chunks for the LLM prompt."""
    if not chunks:
        return "(No relevant SOP sections found.)"
    lines = []
    for i, c in enumerate(chunks[:8], 1):
        lines.append(
            f"### [{i}] {c['source']} — {c['section_path']}\n{c['text'][:500]}"
        )
    return "\n\n".join(lines)


def _extract_conclusion(text: str) -> str:
    """Extract the conclusion section from LLM output."""
    import re
    match = re.search(
        r"(?:Conclusion|## Conclusion|1\.\s*\*\*Conclusion\*\*)[:\s]*(.+?)(?=\n\n|\n(?:##|2\.|\*\*Key))",
        text, re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    # Fallback: first non-empty paragraph
    for para in text.split("\n\n"):
        stripped = para.strip()
        if stripped and not stripped.startswith("#") and len(stripped) > 30:
            return stripped
    return text.strip()[:500]


def _extract_actions(text: str) -> list[str]:
    """Extract numbered recommended actions from LLM output."""
    import re
    actions = []
    # Match numbered items under "Recommended Actions"
    section = re.search(
        r"Recommended Actions[:\s]*(.+?)(?=\n\n(?:##|\*\*Uncertainty|$))",
        text, re.DOTALL | re.IGNORECASE,
    )
    target = section.group(1) if section else text
    for line in target.split("\n"):
        match = re.match(r"\s*(?:\d+[\.\)]\s*)(.+)", line)
        if match:
            actions.append(match.group(1).strip())
    if not actions:
        # Fallback: any numbered lines in the whole text
        for line in text.split("\n"):
            match = re.match(r"\s*\d+[\.\)]\s*\*\*(.+?)\*\*[:]?\s*(.+)", line)
            if match:
                actions.append(f"{match.group(1)}: {match.group(2)}".strip())
            else:
                match = re.match(r"\s*\d+[\.\)]\s*(.+)", line)
                if match:
                    actions.append(match.group(1).strip())
    return actions[:6]


def _extract_uncertainty(text: str) -> str:
    """Extract the uncertainty note from LLM output."""
    import re
    match = re.search(
        r"(?:Uncertainty Note|## Uncertainty Note)[:\s]*(.+?)(?=\n\n|$)",
        text, re.DOTALL | re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return ""
