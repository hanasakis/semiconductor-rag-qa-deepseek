"""Tests for SECOM schema parser with synthetic data."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data_ops.secom_schema import (
    N_FEATURES,
    N_SAMPLES,
    LABEL_MAP,
    compute_feature_missingness,
    compute_feature_stats,
    parse_secom_data,
    parse_secom_labels,
)


def _write_secom_data(path: Path, n_samples: int, n_features: int, seed: int = 42):
    """Write a synthetic secom.data file."""
    rng = np.random.default_rng(seed)
    data = rng.normal(loc=0, scale=1, size=(n_samples, n_features))
    # Inject NaN at ~5% rate
    mask = rng.random(data.shape) < 0.05
    data[mask] = np.nan
    lines = []
    for row in data:
        line = " ".join("NaN" if np.isnan(v) else f"{v:.6f}" for v in row)
        lines.append(line)
    path.write_text("\n".join(lines))


def _write_secom_labels(path: Path, n_samples: int, fail_rate: float = 0.066, seed: int = 42):
    """Write a synthetic secom_labels.data file."""
    rng = np.random.default_rng(seed)
    labels = np.full(n_samples, -1.0)
    n_fail = int(n_samples * fail_rate)
    fail_idx = rng.choice(n_samples, size=n_fail, replace=False)
    labels[fail_idx] = 1.0
    path.write_text("\n".join(str(int(v)) for v in labels))


@pytest.fixture
def secom_dir():
    """Create a temporary directory with synthetic SECOM files."""
    with tempfile.TemporaryDirectory() as tmp:
        data_path = Path(tmp) / "secom.data"
        labels_path = Path(tmp) / "secom_labels.data"
        n = 100  # small test size
        _write_secom_data(data_path, n, 10)
        _write_secom_labels(labels_path, n, fail_rate=0.06)
        yield data_path, labels_path


# ── parse_secom_data ─────────────────────────────────────

def test_parse_secom_data_shape(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    assert df.shape == (100, 10)


def test_parse_secom_data_column_names(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    assert list(df.columns) == [f"Sensor_{i}" for i in range(1, 11)]


def test_parse_secom_data_index_names(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    assert df.index.name == "sample_id"
    assert df.index[0] == "S0000"
    assert df.index[99] == "S0099"


def test_parse_secom_data_has_nans(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    # With ~5% NaN injection, some columns should have NaN
    assert df.isna().any().any()


def test_parse_secom_data_file_not_found():
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        parse_secom_data(Path("nonexistent/secom.data"))


# ── parse_secom_labels ───────────────────────────────────

def test_parse_secom_labels_shape(secom_dir):
    _, labels_path = secom_dir
    labels = parse_secom_labels(labels_path)
    assert len(labels) == 100
    assert labels.name == "pass_fail"


def test_parse_secom_labels_values(secom_dir):
    _, labels_path = secom_dir
    labels = parse_secom_labels(labels_path)
    # Unified: 1 = pass, 0 = fail
    assert labels.isin([0, 1]).all()
    # With 6% fail rate → should have both 0 and 1
    assert (labels == 0).any()  # at least one fail
    assert (labels == 1).any()  # at least one pass


def test_parse_secom_labels_encoding_map():
    """Verify -1→1 (pass), +1→0 (fail)."""
    assert LABEL_MAP[-1] == 1
    assert LABEL_MAP[1] == 0


def test_parse_secom_labels_file_not_found():
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        parse_secom_labels(Path("nonexistent/secom_labels.data"))


# ── compute_feature_missingness ──────────────────────────

def test_compute_feature_missingness(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    miss = compute_feature_missingness(df)
    assert list(miss.columns) == [
        "sensor", "missing_count", "missing_rate", "recommendation"
    ]
    assert len(miss) == 10
    assert miss["missing_rate"].between(0, 1).all()


def test_compute_feature_missingness_recommendations(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    miss = compute_feature_missingness(df)
    valid_recs = {"mean_impute", "multiple_impute", "flag_and_impute",
                  "consider_drop", "drop"}
    assert miss["recommendation"].isin(valid_recs).all()


# ── compute_feature_stats ────────────────────────────────

def test_compute_feature_stats_columns(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    stats = compute_feature_stats(df)
    expected_cols = [
        "sensor", "mean", "std", "min", "max",
        "p25", "p50", "p75", "outlier_3sigma_low", "outlier_3sigma_high",
    ]
    assert list(stats.columns) == expected_cols
    assert len(stats) == 10


def test_compute_feature_stats_outlier_bounds(secom_dir):
    data_path, _ = secom_dir
    df = parse_secom_data(data_path)
    stats = compute_feature_stats(df)
    # outlier_3sigma_low < mean < outlier_3sigma_high
    valid = stats.dropna(subset=["mean", "outlier_3sigma_high"])
    assert (valid["mean"] < valid["outlier_3sigma_high"]).all()


def test_compute_feature_stats_all_nan_column():
    """Column with 100% NaN should produce None stats without crashing."""
    df = pd.DataFrame({"Sensor_1": [np.nan, np.nan, np.nan]})
    df.index = ["S0000", "S0001", "S0002"]
    stats = compute_feature_stats(df)
    assert stats.iloc[0]["mean"] is None


# ── Constants ────────────────────────────────────────────

def test_secom_constants():
    assert N_SAMPLES == 1567
    assert N_FEATURES == 591
