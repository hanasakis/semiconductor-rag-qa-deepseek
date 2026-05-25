"""Semiconductor process anomaly detection tools.

Computes per-sample z-scores, ranks anomalous features, and compares
feature distributions between passed and failed samples.

All computations are statistical. Anonymized sensor identities mean
findings must be correlated with SOP documents for physical interpretation.
"""

import logging
from typing import List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_z_scores(
    measurements: pd.DataFrame,
    sample_id: str,
) -> pd.Series:
    """Compute z-scores for every feature in a single sample.

    z = (x - population_mean) / population_std
    A positive z-score means the feature value is above the population mean.
    The magnitude |z| indicates how many standard deviations away from mean.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        sample_id: Row index (e.g. "S0042").

    Returns:
        Series indexed by sensor name, value = z-score. NaN where
        population std == 0 or the sample value is missing.
    """
    _check_sample_id(measurements, sample_id)

    row = measurements.loc[sample_id]
    pop_mean = measurements.mean()
    pop_std = measurements.std()

    with np.errstate(invalid="ignore"):
        z = (row - pop_mean) / pop_std

    # Features where std == 0 get NaN
    z.replace([np.inf, -np.inf], np.nan, inplace=True)
    z.name = f"z_score_{sample_id}"

    not_nan = z.notna().sum()
    logger.info("Sample %s: %d/%d features with valid z-scores", sample_id, not_nan, len(z))
    return z


def get_top_anomalous_features(
    measurements: pd.DataFrame,
    sample_id: str,
    top_n: int = 20,
) -> pd.DataFrame:
    """Return the top_n most anomalous features for a sample.

    Features are ranked by absolute z-score. If the sample value is missing,
    the feature is included separately with z_score=NaN and a missing flag.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        sample_id: Row index.
        top_n: Number of features to return.

    Returns:
        DataFrame with columns: sensor, value, population_mean, population_std,
        z_score, abs_z_score, is_missing.
    """
    z_scores = compute_z_scores(measurements, sample_id)
    row = measurements.loc[sample_id]

    records = []
    for sensor in measurements.columns:
        val = row[sensor]
        z = z_scores[sensor]
        pop_mean = measurements[sensor].mean()
        pop_std = measurements[sensor].std()

        records.append({
            "sensor": sensor,
            "value": None if pd.isna(val) else round(float(val), 6),
            "population_mean": round(float(pop_mean), 6) if not pd.isna(pop_mean) else None,
            "population_std": round(float(pop_std), 6) if not pd.isna(pop_std) else None,
            "z_score": None if pd.isna(z) else round(float(z), 4),
            "abs_z_score": None if pd.isna(z) else round(abs(float(z)), 4),
            "is_missing": bool(pd.isna(val)),
        })

    df = pd.DataFrame(records)

    # Sort: missing values first, then by |z| descending
    df["_sort1"] = df["is_missing"].astype(int)
    df["_sort2"] = df["abs_z_score"].fillna(-1)
    df = df.sort_values(["_sort1", "_sort2"], ascending=[False, False])
    df = df.drop(columns=["_sort1", "_sort2"])

    return df.head(top_n).reset_index(drop=True)


def compare_failed_vs_passed_features(
    measurements: pd.DataFrame,
    labels: pd.Series,
    top_n: int = 20,
) -> pd.DataFrame:
    """Find features with the largest statistical difference between
    failed and passed samples.

    Uses Cohen's d as the effect-size measure:
      d = (mean_fail - mean_pass) / pooled_std
    |d| > 0.8 is conventionally a "large" effect.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        labels: Series from secom_schema.parse_secom_labels() (1=pass, 0=fail).
        top_n: Number of features to return.

    Returns:
        DataFrame sorted by |cohens_d| descending.
    """
    fail_idx = labels[labels == 0].index
    pass_idx = labels[labels == 1].index

    fail_df = measurements.loc[fail_idx]
    pass_df = measurements.loc[pass_idx]

    records = []
    for sensor in measurements.columns:
        f_vals = fail_df[sensor].dropna()
        p_vals = pass_df[sensor].dropna()

        if len(f_vals) < 2 or len(p_vals) < 2:
            records.append({
                "sensor": sensor,
                "mean_fail": None, "mean_pass": None,
                "std_fail": None, "std_pass": None,
                "cohens_d": None,
            })
            continue

        mean_f = float(f_vals.mean())
        mean_p = float(p_vals.mean())
        std_f = float(f_vals.std())
        std_p = float(p_vals.std())

        # Pooled standard deviation
        n_f, n_p = len(f_vals), len(p_vals)
        pooled_var = ((n_f - 1) * std_f**2 + (n_p - 1) * std_p**2) / (n_f + n_p - 2)
        pooled_std = np.sqrt(pooled_var) if pooled_var > 0 else 1e-10

        d = (mean_f - mean_p) / pooled_std

        records.append({
            "sensor": sensor,
            "mean_fail": round(mean_f, 6),
            "mean_pass": round(mean_p, 6),
            "std_fail": round(std_f, 6),
            "std_pass": round(std_p, 6),
            "cohens_d": round(float(d), 4),
        })

    df = pd.DataFrame(records)
    df["abs_cohens_d"] = df["cohens_d"].abs()
    df = df.sort_values("abs_cohens_d", ascending=False)
    df = df.drop(columns=["abs_cohens_d"])

    n_large = (df["cohens_d"].abs() > 0.8).sum()
    logger.info(
        "Failed vs passed: %d features with |d| > 0.8 (large effect)", n_large
    )
    return df.head(top_n).reset_index(drop=True)


def _check_sample_id(measurements: pd.DataFrame, sample_id: str):
    if sample_id not in measurements.index:
        raise KeyError(
            f"Sample '{sample_id}' not found. "
            f"Valid range: {measurements.index[0]} to {measurements.index[-1]}"
        )
