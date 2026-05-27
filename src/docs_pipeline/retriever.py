"""Semiconductor SOP document retriever.

Combines FTS5 full-text search with DeepSeek-R1 relevance re-ranking.
No separate embedding model — uses structured metadata + local LLM for
relevance judgment.

Pipeline:
  1. FTS5 keyword recall (broad, ~20 candidates)
  2. Metadata boost (warning > procedure > general)
  3. DeepSeek-R1 relevance re-rank (precise, top_k)
"""

import json
import logging
import re
from typing import List

import ollama

from src.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from src.docs_pipeline.chunker import DocChunk
from src.docs_pipeline.fts_index import FTSIndex

logger = logging.getLogger(__name__)

# Content-type boost multipliers for semiconductor domain
CTYPE_BOOST = {
    "warning": 1.5,
    "parameter_table": 1.2,
    "procedure": 1.2,
    "bkm": 1.1,
    "glossary": 1.0,
    "report_template": 0.9,
    "general": 1.0,
}

RERANK_PROMPT = """You are a semiconductor document retrieval evaluator.
Rate the relevance of each document chunk to the user's question.

Question: {question}

Chunks:
{chunks_json}

For each chunk, output a relevance score from 0 to 10:
- 10: Directly answers the question with specific procedures or parameters.
- 7-9: Highly relevant, provides context or partial answer.
- 4-6: Somewhat relevant, same general topic.
- 0-3: Not relevant or only tangentially related.

Output ONLY a JSON array of scores in the same order as chunks:
[scores]"""


class Retriever:
    """Two-stage retrieval with FTS5 recall and LLM re-ranking."""

    def __init__(
        self,
        index: FTSIndex,
        model: str = OLLAMA_MODEL,
        base_url: str = OLLAMA_BASE_URL,
    ):
        self._index = index
        self._model = model
        self._client = ollama.Client(host=base_url)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        recall_n: int = 20,
        use_rerank: bool = True,
        content_type: str | None = None,
    ) -> List[dict]:
        """Retrieve relevant SOP chunks for a query.

        Args:
            query: Natural language question about semiconductor processes.
            top_k: Number of chunks to return after re-ranking.
            recall_n: Number of candidates from FTS5 (before re-rank).
            use_rerank: Whether to use DeepSeek-R1 for re-ranking.
            content_type: Optional content-type filter.

        Returns:
            List of dicts: chunk_id, text, source, section_path, content_type,
            score, relevance.
        """
        # Stage 1: FTS5 recall
        candidates = self._index.search(query, top_k=recall_n, content_type=content_type)

        if not candidates:
            logger.info("No FTS5 results for: %s", query)
            return []

        # Stage 1.5: Apply content-type boosts (normalize rank→score)
        for c in candidates:
            ctype = c.get("content_type", "general")
            c["score"] = c["rank"] * CTYPE_BOOST.get(ctype, 1.0)

        # Sort by boosted score
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Stage 2: DeepSeek-R1 relevance re-rank
        if use_rerank and len(candidates) > top_k:
            relevance_scores = self._llm_rerank(query, candidates[:recall_n])
            for i, rel in enumerate(relevance_scores):
                if i < len(candidates):
                    candidates[i]["relevance"] = rel
            candidates.sort(
                key=lambda x: x.get("relevance", 0), reverse=True
            )

        result = candidates[:top_k]
        logger.info(
            "Retrieved %d chunks for '%s' (from %d candidates)",
            len(result), query, len(candidates),
        )
        return result

    def retrieve_by_source(
        self, query: str, source: str, top_k: int = 5
    ) -> List[dict]:
        """Retrieve chunks from a specific SOP document."""
        return self.retrieve(query, top_k=top_k, recall_n=10, use_rerank=False)

    def retrieve_warnings(self, query: str, top_k: int = 3) -> List[dict]:
        """Retrieve only warning-type chunks."""
        return self.retrieve(
            query, top_k=top_k, content_type="warning", use_rerank=False
        )

    def _llm_rerank(self, query: str, candidates: List[dict]) -> List[int]:
        """Use DeepSeek-R1 to score candidate relevance to the query."""
        chunks_for_prompt = [
            {
                "id": c["chunk_id"][:8],
                "source": c["source"],
                "section": c["section_path"],
                "text": c["text"][:500],
            }
            for c in candidates
        ]

        prompt = RERANK_PROMPT.format(
            question=query,
            chunks_json=json.dumps(chunks_for_prompt, indent=2, ensure_ascii=False),
        )

        try:
            response = self._client.generate(
                model=self._model,
                prompt=prompt,
                options={"temperature": 0.0, "num_predict": 256},
            )
            raw = response.get("response", "")
            scores = self._parse_scores(raw, len(candidates))
            if len(scores) != len(candidates):
                logger.warning(
                    "Re-rank score count mismatch: got %d, expected %d. "
                    "Falling back to FTS5 ordering.",
                    len(scores), len(candidates),
                )
                return [5] * len(candidates)
            return scores
        except Exception as e:
            logger.warning("LLM re-rank failed, using FTS5 ordering: %s", e)
            return [5] * len(candidates)

    def _parse_scores(self, raw: str, expected_len: int) -> List[int]:
        """Extract relevance scores from raw LLM output."""
        # Try to find a JSON array in the response
        match = re.search(r"\[[\d,\s]+\]", raw)
        if match:
            try:
                scores = json.loads(match.group())
                return [int(s) for s in scores]
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        # Fallback: extract all numbers
        numbers = re.findall(r"\b([0-9]|10)\b", raw)
        if len(numbers) >= expected_len:
            return [int(n) for n in numbers[:expected_len]]

        return []


def build_retriever(
    chunks: List[DocChunk],
    db_path: str = "data/processed/fts_index.db",
) -> Retriever:
    """Convenience: build and populate an FTS index, return a Retriever."""
    index = FTSIndex(db_path)
    index.index(chunks)
    return Retriever(index)
