"""Missing-value analysis for SECOM samples and features.

Helps engineers understand which features are unreliable and how
missing data patterns correlate with yield outcomes.
"""

import logging
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


def get_feature_missing_rate(
    measurements: pd.DataFrame,
    sort: bool = True,
) -> pd.DataFrame:
    """Compute missing-value rate for every feature.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        sort: If True, sort by missing rate descending.

    Returns:
        DataFrame with columns: sensor, total, missing, missing_rate.
    """
    n_total = len(measurements)
    records = []
    for sensor in measurements.columns:
        missing = int(measurements[sensor].isna().sum())
        records.append({
            "sensor": sensor,
            "total": n_total,
            "missing": missing,
            "missing_rate": round(missing / n_total, 4),
        })

    df = pd.DataFrame(records)
    if sort:
        df = df.sort_values("missing_rate", ascending=False)
    return df.reset_index(drop=True)


def get_sample_missing_summary(
    measurements: pd.DataFrame,
    sample_id: str,
) -> Dict:
    """Summarize missing values for a single sample.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        sample_id: Row index (e.g. "S0042").

    Returns:
        dict with keys: sample_id, total_features, missing_count, missing_rate,
        missing_sensors (list of sensor names).
    """
    if sample_id not in measurements.index:
        raise KeyError(
            f"Sample '{sample_id}' not found. "
            f"Valid range: {measurements.index[0]} to {measurements.index[-1]}"
        )

    row = measurements.loc[sample_id]
    missing_mask = row.isna()
    missing_count = int(missing_mask.sum())
    total = len(row)

    missing_sensors = sorted(row[missing_mask].index.tolist())

    logger.info(
        "Sample %s: %d/%d features missing (%.1f%%)",
        sample_id, missing_count, total, 100 * missing_count / total,
    )

    return {
        "sample_id": sample_id,
        "total_features": total,
        "missing_count": missing_count,
        "missing_rate": round(missing_count / total, 4),
        "missing_sensors": missing_sensors,
    }


def compare_missing_rate_by_label(
    measurements: pd.DataFrame,
    labels: pd.Series,
    top_n: int = 20,
) -> pd.DataFrame:
    """Find features whose missing rate differs most between pass and fail.

    A feature that is missing significantly more often in failing samples
    may indicate a measurement failure correlated with the yield excursion.

    Args:
        measurements: DataFrame from secom_schema.parse_secom_data().
        labels: Series (1=pass, 0=fail).
        top_n: Number of features to return.

    Returns:
        DataFrame sorted by |missing_rate_diff| descending.
    """
    fail_idx = labels[labels == 0].index
    pass_idx = labels[labels == 1].index

    fail_sub = measurements.loc[fail_idx]
    pass_sub = measurements.loc[pass_idx]

    records = []
    for sensor in measurements.columns:
        mr_fail = fail_sub[sensor].isna().mean()
        mr_pass = pass_sub[sensor].isna().mean()
        diff = mr_fail - mr_pass

        records.append({
            "sensor": sensor,
            "missing_rate_fail": round(float(mr_fail), 4),
            "missing_rate_pass": round(float(mr_pass), 4),
            "missing_rate_diff": round(float(diff), 4),
        })

    df = pd.DataFrame(records)
    df["abs_diff"] = df["missing_rate_diff"].abs()
    df = df.sort_values("abs_diff", ascending=False)
    df = df.drop(columns=["abs_diff"])

    n_flagged = (df["missing_rate_diff"].abs() > 0.05).sum()
    logger.info(
        "%d features with >5pp missing-rate difference between pass/fail", n_flagged
    )
    return df.head(top_n).reset_index(drop=True)
