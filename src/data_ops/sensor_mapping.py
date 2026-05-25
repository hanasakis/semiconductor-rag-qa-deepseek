"""Simulated sensor group mapping for SECOM features.

IMPORTANT: This mapping is DEMONSTRATION ONLY.
All SECOM features are anonymized. These group assignments are fabricated
for educational purposes and do NOT represent real sensor identities.

The mapping simulates what a domain expert might know about their fab:
which sensors belong to which process step or equipment subsystem.
In a real deployment, this file would be replaced with actual engineering
metadata provided by the fab's process integration team.
"""

# fmt: off
SENSOR_GROUPS: dict[str, list[int]] = {
    "Pressure":    list(range(1, 51)),      # Sensors 1-50
    "Temperature": list(range(51, 101)),    # Sensors 51-100
    "RF_Power":    list(range(101, 151)),   # Sensors 101-150
    "Gas_Flow":    list(range(151, 201)),   # Sensors 151-200
    "Optical":     list(range(201, 251)),   # Sensors 201-250
    "Vacuum":      list(range(251, 301)),   # Sensors 251-300
    "Chemical":    list(range(301, 351)),   # Sensors 301-350
    "Mechanical":  list(range(351, 401)),   # Sensors 351-400
    "Electrical":  list(range(401, 451)),   # Sensors 401-450
    "Timing":      list(range(451, 501)),   # Sensors 451-500
    "Alignment":   list(range(501, 551)),   # Sensors 501-550
    "Misc":        list(range(551, 592)),   # Sensors 551-591
}
# fmt: on


def get_group_for_sensor(sensor_id: str) -> str:
    """Return the simulated process group for a sensor.

    Args:
        sensor_id: e.g. "Sensor_42" or "42".

    Returns:
        Group name (e.g. "Pressure") or "Unknown".
    """
    num = _parse_sensor_number(sensor_id)
    if num is None:
        return "Unknown"
    for group, ids in SENSOR_GROUPS.items():
        if num in ids:
            return group
    return "Unknown"


def get_sensors_for_group(group: str) -> list[str]:
    """Return all sensor names in a simulated group.

    Args:
        group: Group name from SENSOR_GROUPS keys.

    Returns:
        List of sensor names like ["Sensor_1", "Sensor_2", ...].
    """
    ids = SENSOR_GROUPS.get(group, [])
    return [f"Sensor_{i}" for i in ids]


def get_anomaly_summary_by_group(
    top_anomalous: pd.DataFrame,
) -> pd.DataFrame:
    """Annotate a top-anomalous-features DataFrame with simulated groups.

    Args:
        top_anomalous: Output from anomaly.get_top_anomalous_features().

    Returns:
        Same DataFrame with an added 'sensor_group' column.
    """
    import pandas as pd

    df = top_anomalous.copy()
    df["sensor_group"] = df["sensor"].apply(get_group_for_sensor)
    return df


def all_groups() -> list[str]:
    """Return all simulated group names."""
    return list(SENSOR_GROUPS.keys())


def _parse_sensor_number(sensor_id: str) -> int | None:
    """Extract sensor number from 'Sensor_N' or 'N'."""
    s = str(sensor_id).strip()
    if s.startswith("Sensor_"):
        s = s[len("Sensor_"):]
    try:
        return int(s)
    except (ValueError, TypeError):
        return None
