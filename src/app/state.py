"""LangGraph state definition for FabYield Insight workflow."""

from typing import Annotated, Any, Optional, TypedDict


class RAGState(TypedDict):
    """State object flowing through the FabYield Insight LangGraph.

    Each node reads from and writes to this state. The reducer
    for list fields is append (not replace), allowing nodes to
    accumulate context incrementally.
    """

    # ── Input ─────────────────────────────────────────
    question: str

    # ── Router output ─────────────────────────────────
    question_type: str
    sample_id: Optional[str]
    feature_ids: list[str]
    need_sop: bool
    need_data_tool: bool

    # ── Collected evidence ────────────────────────────
    data_context: str
    sop_context: str

    # ── Generation ────────────────────────────────────
    draft_answer: str
    final_answer: str

    # ── Guard output ──────────────────────────────────
    guard_issues: list[str]

    # ── Error handling ────────────────────────────────
    error: Optional[str]
