"""SECOM dataset schema and parser.

Parses the raw UCI SECOM files into structured DataFrames.
All features are anonymized (Sensor_1 through Sensor_591).
No real equipment names, process steps, or fab identifiers are inferred.
"""

import logging
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# SECOM constants
N_SAMPLES = 1567
N_FEATURES = 591
RAW_DIR = Path("data/raw")

# Label encoding
#   UCI raw:  -1 = pass,  +1 = fail
#   Unified:   1 = pass,   0 = fail
LABEL_MAP = {-1: 1, 1: 0}


def parse_secom_data(path: Path | None = None) -> pd.DataFrame:
    """Parse secom.data into a DataFrame.

    Each row is one sample (wafer/die/measurement).
    Each column is an anonymized sensor/process feature.
    Missing values are encoded as NaN (MatLab convention in the raw file).

    Args:
        path: Path to secom.data. Defaults to data/raw/secom.data.

    Returns:
        DataFrame of shape (1567, 591) with column names Sensor_1..Sensor_591.
    """
    if path is None:
        path = RAW_DIR / "secom.data"

    _check_file(path)

    # secom.data: space-separated, NaN for missing values
    df = pd.read_csv(
        path,
        sep=r"\s+",
        header=None,
        na_values=["NaN", "nan", ""],
        dtype=np.float64,
        engine="python",
    )

    df.index.name = "sample_id"
    df.index = df.index.map(lambda i: f"S{i:04d}")
    df.columns = [f"Sensor_{i}" for i in range(1, df.shape[1] + 1)]

    logger.info("Parsed secom.data: %d samples x %d features", *df.shape)
    return df


def parse_secom_labels(path: Path | None = None) -> pd.Series:
    """Parse secom_labels.data into a unified pass/fail Series.

    Raw encoding:  -1 = pass, 1 = fail
    Unified:        1 = pass, 0 = fail

    Args:
        path: Path to secom_labels.data.

    Returns:
        Series with index=sample_id, values 1 (pass) or 0 (fail).
    """
    if path is None:
        path = RAW_DIR / "secom_labels.data"

    _check_file(path)

    raw = pd.read_csv(
        path,
        sep=r"\s+",
        header=None,
        dtype=np.float64,
        engine="python",
    ).squeeze("columns")

    labels = raw.map(LABEL_MAP).astype(np.int8)
    labels.index = labels.index.map(lambda i: f"S{i:04d}")
    labels.name = "pass_fail"

    n_pass = int(labels.sum())
    n_fail = len(labels) - n_pass
    logger.info("Parsed secom_labels: %d pass, %d fail", n_pass, n_fail)
    return labels


def compute_feature_missingness(measurements: pd.DataFrame) -> pd.DataFrame:
    """Compute missing-value statistics for every sensor.

    Args:
        measurements: DataFrame from parse_secom_data().

    Returns:
        DataFrame with columns: sensor, missing_count, missing_rate, recommendation.
    """
    n_total = len(measurements)
    rows = []
    for col in measurements.columns:
        missing = int(measurements[col].isna().sum())
        rate = missing / n_total
        if rate < 0.01:
            rec = "mean_impute"
        elif rate < 0.05:
            rec = "multiple_impute"
        elif rate < 0.20:
            rec = "flag_and_impute"
        elif rate < 0.50:
            rec = "consider_drop"
        else:
            rec = "drop"

        rows.append({
            "sensor": col,
            "missing_count": missing,
            "missing_rate": round(rate, 4),
            "recommendation": rec,
        })

    logger.info(
        "Feature missingness: %d features, %d with >50%% missing",
        len(rows),
        sum(1 for r in rows if r["recommendation"] == "drop"),
    )
    return pd.DataFrame(rows).sort_values("missing_rate", ascending=False)


def compute_feature_stats(measurements: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive statistics for every sensor.

    Args:
        measurements: DataFrame from parse_secom_data().

    Returns:
        DataFrame with columns: sensor, mean, std, min, max, p25, p50, p75,
        outlier_3sigma_low, outlier_3sigma_high.
    """
    rows = []
    for col in measurements.columns:
        series = measurements[col].dropna()
        if len(series) == 0:
            rows.append({
                "sensor": col, "mean": None, "std": None,
                "min": None, "max": None,
                "p25": None, "p50": None, "p75": None,
                "outlier_3sigma_low": None, "outlier_3sigma_high": None,
            })
            continue

        mean = float(series.mean())
        std = float(series.std())
        q25, q50, q75 = series.quantile([0.25, 0.50, 0.75]).tolist()

        rows.append({
            "sensor": col,
            "mean": round(mean, 6),
            "std": round(std, 6),
            "min": round(float(series.min()), 6),
            "max": round(float(series.max()), 6),
            "p25": round(q25, 6),
            "p50": round(q50, 6),
            "p75": round(q75, 6),
            "outlier_3sigma_low": round(mean - 3 * std, 6),
            "outlier_3sigma_high": round(mean + 3 * std, 6),
        })

    return pd.DataFrame(rows)


def load_secom() -> Tuple[pd.DataFrame, pd.Series]:
    """Load both SECOM data and labels.

    Returns:
        (measurements, labels) tuple.
    """
    df = parse_secom_data()
    labels = parse_secom_labels()
    return df, labels


def _check_file(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download the SECOM dataset from "
            f"https://archive.ics.uci.edu/dataset/179/secom "
            f"and place the files in {RAW_DIR.resolve()}/"
        )
