"""Full-text search index using SQLite FTS5.

No external dependencies — FTS5 is built into Python's sqlite3 module.
Provides keyword and phrase search over semiconductor SOP chunks.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List

from src.docs_pipeline.chunker import DocChunk

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/processed/fts_index.db")


class FTSIndex:
    """SQLite FTS5 index for semiconductor SOP document chunks."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id,
                text,
                source,
                section_path,
                content_type,
                tokenize='porter unicode61'
            )
        """)
        self._conn.commit()

    def index(self, chunks: List[DocChunk]):
        """Insert or replace chunks in the FTS index."""
        self._conn.execute("DELETE FROM chunks_fts")
        rows = [
            (
                c.chunk_id,
                c.text,
                c.source,
                c.section_path,
                c.content_type,
            )
            for c in chunks
        ]
        with self._conn:
            self._conn.executemany(
                "INSERT INTO chunks_fts(chunk_id, text, source, section_path, content_type) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        logger.info("Indexed %d chunks into FTS5", len(rows))

    def search(
        self,
        query: str,
        top_k: int = 10,
        content_type: str | None = None,
        source: str | None = None,
    ) -> List[dict]:
        """Full-text search with optional content_type and source filters.

        Args:
            query: Natural language query or keywords.
            top_k: Max results to return.
            content_type: Filter by content type (procedure, warning, etc.).
            source: Filter by source document name.

        Returns:
            List of dicts with keys: chunk_id, text, source, section_path,
            content_type, score.
        """
        # Escape FTS5 special characters in query
        safe_query = _escape_fts5(query)
        sql = """
            SELECT chunk_id, text, source, section_path, content_type, rank
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
        """
        params: list = [safe_query]

        if content_type:
            sql += " AND content_type = ?"
            params.append(content_type)
        if source:
            sql += " AND source = ?"
            params.append(source)

        sql += " ORDER BY rank LIMIT ?"
        params.append(top_k)

        cursor = self._conn.execute(sql, params)
        results = []
        for row in cursor.fetchall():
            results.append({
                "chunk_id": row["chunk_id"],
                "text": row["text"],
                "source": row["source"],
                "section_path": row["section_path"],
                "content_type": row["content_type"],
                "rank": row["rank"],
            })
        logger.info("FTS search '%s': %d results", query, len(results))
        return results

    def phrase_search(self, phrase: str, top_k: int = 10) -> List[dict]:
        """Exact phrase search using double-quote wrapping."""
        return self.search(f'"{phrase}"', top_k=top_k)

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM chunks_fts").fetchone()
        return row["cnt"] if row else 0

    def close(self):
        self._conn.close()


def _escape_fts5(query: str) -> str:
    """Escape special FTS5 characters and wrap query if it contains column-like patterns.

    FTS5 interprets "column:term" and "prefix-column" as column filters.
    Words containing hyphens followed by known schema names (like "z-score"
    → "score" interpreted as a column) cause syntax errors.
    """
    # Remove FTS5 special syntax characters and trailing punctuation
    for ch in r'*"():^~?,.!;':
        query = query.replace(ch, "")

    stripped = query.strip()
    if not stripped:
        return "*"

    # If the query contains hyphens or colons that could trigger FTS5
    # column-filter parsing, wrap each word in double quotes
    if "-" in stripped or ":" in stripped:
        words = stripped.split()
        quoted = " ".join(f'"{w}"' for w in words)
        return quoted

    return stripped
