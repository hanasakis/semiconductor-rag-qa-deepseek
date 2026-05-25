"""Tests for SECOM anomaly analysis and missingness tools."""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.data_ops.anomaly import (
    compare_failed_vs_passed_features,
    compute_z_scores,
    get_top_anomalous_features,
)
from src.data_ops.missingness import (
    compare_missing_rate_by_label,
    get_feature_missing_rate,
    get_sample_missing_summary,
)
from src.data_ops.sensor_mapping import (
    SENSOR_GROUPS,
    get_anomaly_summary_by_group,
    get_group_for_sensor,
    get_sensors_for_group,
)


# ── synthetic data fixture ───────────────────────────────

def _make_synth_data(n_samples=200, n_features=30, seed=42):
    """Generate synthetic SECOM-like measurements and labels.

    Fail samples (label=0) get shifted means on some features to create
    realistic anomaly patterns.
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(loc=0, scale=1, size=(n_samples, n_features))
    sample_ids = [f"S{i:04d}" for i in range(n_samples)]
    labels = pd.Series(np.ones(n_samples, dtype=np.int8), name="pass_fail", index=sample_ids)

    n_fail = int(n_samples * 0.07)
    fail_idx = rng.choice(n_samples, size=n_fail, replace=False)
    labels.iloc[fail_idx] = 0

    # Inject anomalies: shift 3 features in fail samples
    anomaly_sensors = [3, 14, 25]
    for i in fail_idx:
        for sensor in anomaly_sensors:
            data[i, sensor] += rng.normal(3.0, 0.5)

    # Inject NaN at ~5% rate, slightly more in fail samples
    for i in range(n_samples):
        for j in range(n_features):
            if labels.iloc[i] == 0 and rng.random() < 0.08:
                data[i, j] = np.nan
            elif rng.random() < 0.03:
                data[i, j] = np.nan

    df = pd.DataFrame(
        data,
        columns=[f"Sensor_{i}" for i in range(1, n_features + 1)],
    )
    df.index = sample_ids
    df.index.name = "sample_id"

    return df, labels


@pytest.fixture
def synth():
    return _make_synth_data()


# ── compute_z_scores ─────────────────────────────────────

def test_compute_z_scores_shape(synth):
    df, labels = synth
    z = compute_z_scores(df, "S0000")
    assert len(z) == 30
    assert z.name == "z_score_S0000"


def test_compute_z_scores_range(synth):
    df, labels = synth
    z = compute_z_scores(df, "S0000")
    valid = z.dropna()
    # Most z-scores in synthetic normal data should be within [-3, 3]
    assert valid.abs().mean() < 2.0


def test_compute_z_scores_invalid_sample(synth):
    df, labels = synth
    with pytest.raises(KeyError, match="NONEXIST"):
        compute_z_scores(df, "NONEXIST")


def test_compute_z_scores_missing_features_get_nan(synth):
    df, labels = synth
    # Create a sample with a forced NaN
    df.loc["S0001", "Sensor_1"] = np.nan
    z = compute_z_scores(df, "S0001")
    assert pd.isna(z["Sensor_1"])


# ── get_top_anomalous_features ───────────────────────────

def test_get_top_anomalous_columns(synth):
    df, labels = synth
    top = get_top_anomalous_features(df, "S0042", top_n=5)
    expected_cols = [
        "sensor", "value", "population_mean", "population_std",
        "z_score", "abs_z_score", "is_missing",
    ]
    assert list(top.columns) == expected_cols
    assert len(top) <= 5


def test_get_top_anomalous_missing_first(synth):
    df, labels = synth
    # Force NaN on several sensors for a specific sample
    df.loc["S0010", "Sensor_1"] = np.nan
    df.loc["S0010", "Sensor_2"] = np.nan
    top = get_top_anomalous_features(df, "S0010", top_n=10)
    # Missing values should be ranked first
    assert bool(top.iloc[0]["is_missing"]), "First entry should be a missing value"


def test_get_top_anomalous_fail_sample_has_high_z(synth):
    """Fail samples should show high |z| on the injected anomaly sensors."""
    df, labels = synth
    fail_ids = labels[labels == 0].index[:5]
    found_anomaly = False
    for sid in fail_ids:
        top = get_top_anomalous_features(df, sid, top_n=10)
        top_sensors = top[top["is_missing"] == False]["sensor"].tolist()
        if any(s in top_sensors for s in ["Sensor_4", "Sensor_15", "Sensor_26"]):
            found_anomaly = True
            break
    # At least one fail sample should flag the injected anomalies
    assert found_anomaly


# ── compare_failed_vs_passed_features ────────────────────

def test_compare_failed_vs_passed_shape(synth):
    df, labels = synth
    result = compare_failed_vs_passed_features(df, labels, top_n=10)
    assert len(result) <= 10
    assert "cohens_d" in result.columns
    assert "mean_fail" in result.columns
    assert "mean_pass" in result.columns


def test_compare_failed_vs_passed_detects_anomalies(synth):
    """The injected anomaly sensors should have large |Cohen's d|."""
    df, labels = synth
    result = compare_failed_vs_passed_features(df, labels, top_n=30)
    top_sensors = result.head(10)["sensor"].tolist()
    # Sensor_4, 15, 26 correspond to injected anomaly indices 3, 14, 25
    anomaly_hits = [s for s in ["Sensor_4", "Sensor_15", "Sensor_26"] if s in top_sensors]
    assert len(anomaly_hits) >= 1


# ── missingness tools ────────────────────────────────────

def test_get_feature_missing_rate(synth):
    df, labels = synth
    mr = get_feature_missing_rate(df)
    assert len(mr) == 30
    assert mr["missing_rate"].between(0, 1).all()


def test_get_sample_missing_summary(synth):
    df, labels = synth
    summary = get_sample_missing_summary(df, "S0000")
    assert summary["sample_id"] == "S0000"
    assert summary["total_features"] == 30
    assert 0 <= summary["missing_rate"] <= 1


def test_get_sample_missing_summary_invalid(synth):
    df, labels = synth
    with pytest.raises(KeyError, match="INVALID"):
        get_sample_missing_summary(df, "INVALID")


def test_compare_missing_rate_by_label(synth):
    df, labels = synth
    result = compare_missing_rate_by_label(df, labels)
    assert "missing_rate_fail" in result.columns
    assert "missing_rate_pass" in result.columns
    assert "missing_rate_diff" in result.columns


# ── sensor_mapping ───────────────────────────────────────

def test_sensor_groups_coverage():
    """Each sensor 1-591 should belong to exactly one group."""
    all_ids = set()
    for group, ids in SENSOR_GROUPS.items():
        all_ids.update(ids)
    assert all_ids == set(range(1, 592))


def test_get_group_for_sensor():
    assert get_group_for_sensor("Sensor_42") == "Pressure"
    assert get_group_for_sensor("Sensor_150") == "RF_Power"
    assert get_group_for_sensor("42") == "Pressure"
    assert get_group_for_sensor("Sensor_999") == "Unknown"


def test_get_sensors_for_group():
    sensors = get_sensors_for_group("Pressure")
    assert len(sensors) == 50
    assert sensors[0] == "Sensor_1"
    assert sensors[-1] == "Sensor_50"


def test_get_anomaly_summary_by_group(synth):
    df, labels = synth
    top = get_top_anomalous_features(df, "S0042", top_n=10)
    annotated = get_anomaly_summary_by_group(top)
    assert "sensor_group" in annotated.columns
    assert annotated.iloc[0]["sensor_group"] is not None
