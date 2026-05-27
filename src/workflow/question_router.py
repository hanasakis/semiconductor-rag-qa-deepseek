"""Question router and parameter extractor for FabYield Insight.

Classifies user queries into structured intent and extracts entities
(sample IDs, feature IDs) using DeepSeek-R1 with strict JSON output.
"""

import json
import logging
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from src.llm.ollama_client import get_client
from src.llm.output_cleaner import clean_r1_output

logger = logging.getLogger(__name__)


# ── Pydantic model ───────────────────────────────────────

class QuestionType(str, Enum):
    CONCEPT_QA = "concept_qa"
    SAMPLE_ANALYSIS = "sample_analysis"
    COHORT_ANALYSIS = "cohort_analysis"
    REPORT_GENERATION = "report_generation"
    UNKNOWN = "unknown"


class RouterOutput(BaseModel):
    """Structured output from the question router."""

    question_type: QuestionType = Field(
        description="The type of question the user is asking"
    )
    sample_id: Optional[str] = Field(
        default=None,
        description="Sample ID if the user mentioned one (e.g. S0042)",
    )
    feature_ids: list[str] = Field(
        default_factory=list,
        description="Sensor/feature IDs mentioned (e.g. Sensor_42, Sensor_15)",
    )
    need_sop: bool = Field(
        default=True,
        description="Whether SOP documents are needed to answer",
    )
    need_data_tool: bool = Field(
        default=False,
        description="Whether SECOM data tools are needed (z-score, missingness, etc.)",
    )


# ── Router prompt ────────────────────────────────────────

ROUTER_SYSTEM = """You are a semiconductor manufacturing query classifier.
Your job is to analyze a user's question and output a STRICT JSON object.

Classification rules:
- concept_qa: General questions about semiconductor processes, terminology, or SOP content. No specific sample mentioned.
- sample_analysis: Questions about a specific sample (wafer/die). A sample ID like S0042 is mentioned.
- cohort_analysis: Questions comparing groups (pass vs fail, lot vs lot, tool vs tool) or analyzing multiple samples.
- report_generation: Requests to generate a failure report, summary, or documentation.
- unknown: Cannot determine the intent.

Extraction rules:
- sample_id: A single sample identifier like S0042, S0156. Format is S followed by 4 digits. Extract ONLY if explicitly mentioned.
- feature_ids: Sensor names like Sensor_42, Sensor_15. Include all mentioned.
- need_sop: True for concept_qa, report_generation. False for pure data questions. True if the question asks "how to"/"what should I do".
- need_data_tool: True for sample_analysis, cohort_analysis. True if the question mentions sensors, z-score, anomaly, values, readings.

Output ONLY valid JSON, no other text.
"""

ROUTER_PROMPT = """Classify this user question:

"{question}"

Output this exact JSON structure:
{{
    "question_type": "concept_qa|sample_analysis|cohort_analysis|report_generation|unknown",
    "sample_id": null or "Sxxxx",
    "feature_ids": [],
    "need_sop": true|false,
    "need_data_tool": true|false
}}"""


# ── Router ───────────────────────────────────────────────

def route_question(question: str) -> RouterOutput:
    """Classify a user question and extract structured parameters.

    Args:
        question: Natural language question from the user.

    Returns:
        RouterOutput with question_type, sample_id, feature_ids, flags.

    Raises:
        ValueError: If the LLM output cannot be parsed after repair attempts.
    """
    client = get_client()
    prompt = ROUTER_PROMPT.format(question=question)

    result = client.generate(prompt=prompt, system=ROUTER_SYSTEM)
    answer = result["answer"]

    # Attempt 1: Direct parse
    parsed = _try_parse(answer)
    if parsed is not None:
        return _normalize(parsed)

    # Attempt 2: Extract JSON block from markdown code fences
    json_block = _extract_json_block(answer)
    if json_block:
        parsed = _try_parse(json_block)
        if parsed is not None:
            return _normalize(parsed)

    # Attempt 3: Repair common JSON errors
    repaired = _repair_json(answer)
    if repaired:
        parsed = _try_parse(repaired)
        if parsed is not None:
            logger.warning("Router JSON repaired for: %s", question[:60])
            return _normalize(parsed)

    # All attempts failed
    raise ValueError(
        f"Failed to parse router output for question: {question[:80]}\n"
        f"Raw LLM answer: {answer[:300]}"
    )


# ── Parse helpers ────────────────────────────────────────

def _try_parse(text: str) -> Optional[dict]:
    """Try to parse text as JSON. Returns dict or None."""
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _extract_json_block(text: str) -> Optional[str]:
    """Extract JSON from markdown ```json ... ``` fences."""
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    # Try without fence: find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start:end + 1]
    return None


def _repair_json(text: str) -> Optional[str]:
    """Repair common JSON errors in LLM output."""
    # Extract JSON-like structure
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    candidate = text[start:end + 1]

    # Fix 1: Remove trailing commas before closing braces
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    # Fix 2: Unquoted keys (very common LLM mistake)
    candidate = re.sub(
        r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
        r'\1"\2":',
        candidate,
    )

    # Fix 3: Single-quoted strings → double-quoted
    # (only outside already-double-quoted strings — rough heuristic)
    in_string = False
    chars = list(candidate)
    for i, ch in enumerate(chars):
        if ch == '"' and (i == 0 or chars[i - 1] != '\\'):
            in_string = not in_string
        elif ch == "'" and not in_string:
            chars[i] = '"'
    candidate = "".join(chars)

    # Fix 4: Python-style True/False/None → JSON
    candidate = candidate.replace("True", "true").replace("False", "false").replace("None", "null")

    return candidate


def _normalize(raw: dict) -> RouterOutput:
    """Validate and normalize parsed dict into RouterOutput."""
    # Handle None → null → None round-trip
    for key in ("sample_id",):
        if key in raw and raw[key] in (None, "null", ""):
            raw[key] = None

    # Handle missing feature_ids
    if "feature_ids" not in raw or raw["feature_ids"] is None:
        raw["feature_ids"] = []

    # Handle boolean fields
    for bool_key in ("need_sop", "need_data_tool"):
        if bool_key in raw:
            val = raw[bool_key]
            if isinstance(val, str):
                raw[bool_key] = val.lower() in ("true", "yes", "1")

    return RouterOutput(**raw)
