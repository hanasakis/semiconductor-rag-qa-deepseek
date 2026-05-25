# Missing Data Handling Policy — SOP-MISS-003

**Version**: v1.3
**Owner**: Data Quality & Process Control
**Last Updated**: 2024-03-22

## 1. Purpose

Define when and how to handle missing sensor data in SECOM process monitoring.
Missing data can indicate sensor failure, data acquisition problems, or process
conditions outside measurement range — each requiring a different response.

## 2. Missing Data Categories

| Category | Missing Rate | Interpretation | Action |
|----------|-------------|----------------|--------|
| A — Normal | < 1% | Random acquisition gaps | Impute with population median |
| B — Elevated | 1-5% | Intermittent sensor issue | Multiple imputation; flag for PM review |
| C — High | 5-20% | Persistent sensor degradation | Create NA_FLAG column; schedule sensor replacement |
| D — Critical | 20-50% | Sensor near end-of-life | Exclude from real-time monitoring; immediate replacement ticket |
| E — Failed | > 50% | Sensor offline | Remove from active feature set; root-cause investigation required |

## 3. Missing Data Investigation Procedure

### 3.1 Temporal Pattern Check

- Is missingness correlated with time?
  - **Batch pattern**: entire lot missing → likely recipe/config issue.
  - **Drifting pattern**: missing rate increases over time → sensor degradation.
  - **Random pattern**: no temporal structure → acquisition hardware glitch.

### 3.2 Correlation with Yield

- Compute `compare_missing_rate_by_label()` between pass and fail samples.
- A feature with >5pp difference in missing rate between pass/fail requires:
  - Sensor health check (see SOP-CAL-007).
  - Review of whether the measurement is critical-to-quality (CTQ).
  - If CTQ: immediate sensor swap and re-qualification.

### 3.3 Correlation with Other Sensors

- For each sensor with elevated missing rate, compute correlation with all other sensors.
- If a pair of sensors has r > 0.9 and one has high missingness:
  - The available sensor can serve as a proxy during the missing data period.
  - Flag the pair for physical verification: they may share a common subsystem.

## 4. Imputation Guidelines

**WARNING**: Imputed values must be clearly marked in all downstream analyses.
Never present imputed data as measured data.

| Method | When to Use | Limitations |
|--------|------------|-------------|
| Median imputation | Category A (<1%) | Assumes symmetric distribution |
| Multiple imputation (MICE) | Category B (1-5%) | Computationally expensive |
| k-NN imputation | Category C (5-20%) | Sensitive to feature scaling |
| Model-based imputation | Category C with strong sensor correlations | Risk of overfitting |
| Deletion | Category D-E (>20%) | Loss of sample; document reason |

## 5. Reporting

When missing data exceeds Category B in any sensor, file a Data Quality Incident
Report containing:
- Affected sensor ID(s)
- Time window of elevated missingness
- Yield correlation check results
- Recommended action (monitor / replace / recalibrate)

## 6. References

- SOP-CAL-007: Sensor Calibration Procedure
- SOP-YLD-001: Yield Triage SOP
