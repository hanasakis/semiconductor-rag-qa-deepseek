# Sensor Drift Investigation — SOP-CAL-007

**Version**: v2.4
**Owner**: Equipment Engineering / Metrology
**Last Updated**: 2024-05-10

## 1. Purpose

This document defines the procedure for investigating sensor drift in
semiconductor manufacturing equipment. Sensor drift can cause systematic
process shift that leads to yield loss, often before the sensor triggers
an out-of-spec alarm.

## 2. Sensor Categories

| Category | Examples | Drift Tolerance | Calibration Interval |
|----------|---------|-----------------|---------------------|
| Pressure | Chamber manometer, gas line transducer | ±1% full scale | 30 days |
| Temperature | Thermocouple, pyrometer | ±0.5 C | 90 days |
| RF Power | Forward/reflected power sensor | ±2% | 60 days |
| Gas Flow | MFC (Mass Flow Controller) | ±1% of setpoint | 90 days |
| Optical | OES, endpoint detection | ±5% intensity | 30 days |

## 3. Detection Criteria

### 3.1 Statistical Indicators

A sensor is flagged for drift investigation when **any** of the following
conditions are met across a rolling 30-day window:

1. **Mean shift**: population mean moves >1.5 sigma from historical baseline.
2. **Variance increase**: population std exceeds 2x historical std.
3. **Trend**: linear regression of daily means has slope with p < 0.01.
4. **z-score persistence**: >5% of samples in a week have |z| > 2.5 for the sensor.

### 3.2 Cross-Sensor Confirmation

A single sensor flagging may indicate sensor drift OR a real process change.
To differentiate:

- If the flagged sensor belongs to a correlated group (r > 0.8 historical):
  - Check group members. If only the flagged sensor is anomalous → sensor drift.
  - If multiple group members are anomalous → likely real process shift.
- Cross-check with downstream measurement (e.g., CD-SEM after etch).
  - If downstream measurement is stable → likely sensor drift.
  - If downstream measurement also shifted → likely real process change.

## 4. Investigation Procedure

### Step 1 — Data Review

- Pull 90-day trend for the flagged sensor.
- Overlay maintenance logs: any recent PM, part replacement, or recipe change?
- Check calibration history: when was the last calibration? Was it in-spec?

### Step 2 — Physical Inspection

WARNING: Power down equipment and follow lockout/tagout procedure
before physical inspection. Chamber surfaces may retain heat.

- Visual inspection of sensor and cable connections.
- Check for signs of deposition, corrosion, or mechanical damage.
- Verify sensor is mounted correctly (torque, alignment, thermal contact).

### Step 3 — Calibration Check

- Perform zero-point check:
  - Pressure sensor: vent chamber to atmosphere, verify reading.
  - Temperature sensor: ice-point reference check.
  - RF sensor: connect to calibration standard.
- Perform span check at 2-3 points across the operating range.
- If out-of-spec: recalibrate. If calibration fails: replace sensor.

### Step 4 — Re-qualification

After recalibration or replacement:
- Run qualification wafer through standard recipe.
- Measure all parameters against golden-wafer baseline.
- If within spec: return tool to production. Document in calibration log.
- If out-of-spec: escalate to process engineering for recipe adjustment.

## 5. Documentation

File a Calibration Incident Report with:
- Sensor ID, type, and location
- Drift magnitude and direction (positive/negative)
- Root cause (drift / damage / end-of-life / installation error)
- Corrective action (recalibrated / replaced / re-mounted)
- Post-correction verification data

## 6. References

- SOP-YLD-001: Yield Triage SOP
- SOP-MISS-003: Missing Data Handling Policy
