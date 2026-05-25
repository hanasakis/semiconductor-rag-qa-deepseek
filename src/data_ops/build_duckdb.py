"""Build a DuckDB database from parsed SECOM data.

Creates data/processed/secom.duckdb with four tables:
  - secom_measurements: sample_id x sensor (wide format)
  - secom_labels:       sample_id -> pass_fail
  - feature_missingness: per-sensor missing value stats
  - feature_stats:       per-sensor descriptive statistics
"""

import logging
from pathlib import Path

import pandas as pd

from src.data_ops.secom_schema import (
    compute_feature_missingness,
    compute_feature_stats,
    load_secom,
)

logger = logging.getLogger(__name__)

DB_PATH = Path("data/processed/secom.duckdb")


def build(db_path: Path | None = None) -> Path:
    """Build the SECOM DuckDB database.

    Args:
        db_path: Target path. Defaults to data/processed/secom.duckdb.

    Returns:
        Path to the created database file.
    """
    if db_path is None:
        db_path = DB_PATH

    db_path.parent.mkdir(parents=True, exist_ok=True)

    measurements, labels = load_secom()
    missingness = compute_feature_missingness(measurements)
    stats = compute_feature_stats(measurements)

    try:
        import duckdb
    except ImportError:
        raise ImportError(
            "duckdb is required to build the database. "
            "Install with: pip install duckdb"
        )

    con = duckdb.connect(str(db_path))

    con.execute("DROP TABLE IF EXISTS secom_measurements")
    con.execute("DROP TABLE IF EXISTS secom_labels")
    con.execute("DROP TABLE IF EXISTS feature_missingness")
    con.execute("DROP TABLE IF EXISTS feature_stats")

    con.execute("CREATE TABLE secom_measurements AS SELECT * FROM measurements")
    con.execute("CREATE TABLE secom_labels AS SELECT * FROM labels")
    con.execute("CREATE TABLE feature_missingness AS SELECT * FROM missingness")
    con.execute("CREATE TABLE feature_stats AS SELECT * FROM stats")

    # Verify row counts
    tables = {
        "secom_measurements": len(measurements),
        "secom_labels": len(labels),
        "feature_missingness": len(missingness),
        "feature_stats": len(stats),
    }
    for name, expected in tables.items():
        actual = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        if actual != expected:
            logger.warning(
                "%s: expected %d rows, got %d", name, expected, actual
            )

    con.close()
    logger.info("Database built: %s (%d bytes)", db_path, db_path.stat().st_size)

    return db_path


def query_sample(db_path: Path | None = None, sample_id: str = "S0000"):
    """Query a single sample from the database for inspection."""
    if db_path is None:
        db_path = DB_PATH

    try:
        import duckdb
    except ImportError:
        raise ImportError("duckdb is required. Install with: pip install duckdb")

    con = duckdb.connect(str(db_path))
    row = con.execute(
        f"SELECT * FROM secom_measurements WHERE sample_id = '{sample_id}'"
    ).fetchone()
    label = con.execute(
        f"SELECT pass_fail FROM secom_labels WHERE sample_id = '{sample_id}'"
    ).fetchone()
    con.close()

    if row is None:
        logger.warning("Sample %s not found", sample_id)
        return None

    return {"sample_id": sample_id, "label": label[0] if label else None, "values": row}
