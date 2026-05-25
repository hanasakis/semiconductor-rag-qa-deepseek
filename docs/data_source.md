# SECOM Dataset — Data Source Reference

## Origin

- **Name**: SECOM (SEmiconductor COnstruction/Manufacturing)
- **Source**: UCI Machine Learning Repository
- **URL**: https://archive.ics.uci.edu/dataset/179/secom
- **License**: Creative Commons Attribution 4.0 (CC BY 4.0)
- **Citation**: McCann, M. & Johnston, A. (2008). SECOM. UCI Machine Learning Repository.

## Dataset Description

SECOM contains measurements from a semi-conductor manufacturing process.
Each sample represents a single production unit (wafer or die) with sensor
readings collected during fabrication.

| Property | Value |
|----------|-------|
| Samples | 1,567 |
| Features | 591 |
| Pass (yield) | 1,463 (93.4%) |
| Fail (yield loss) | 104 (6.6%) |
| Files | `secom.data` (5.1 MB), `secom_labels.data` (39.7 KB), `secom.names` (4.1 KB) |
| Format | Space-separated values, one sample per line |
| Missing encoding | `NaN` (MatLab convention) |

## Feature Anonymization

**All 591 features are anonymized.** The original sensor names, process steps,
equipment identifiers, and measurement units have been removed by the dataset
authors. Features are named `Sensor_1` through `Sensor_591` in our pipeline.

This anonymization means:

1. We **cannot** say "Sensor_42 is the etch chamber pressure sensor."
2. We **can** say "Sensor_42 shows elevated readings in 23 of 104 failing samples."
3. We **can** compute statistical relationships between sensors.
4. We **can** identify which sensors are most discriminative for pass/fail.
5. We **cannot** directly map statistical findings to physical root causes
   without domain expert interpretation.

## Why Anonymous Features Are Still Useful for Anomaly Analysis

### What we CAN do

- **Statistical anomaly detection**: identify samples where sensor readings
  deviate significantly from the population distribution (3-sigma, IQR).
- **Sensor correlation analysis**: find groups of sensors that co-vary,
  suggesting they monitor the same or related process steps.
- **Pass/fail classification**: train a model to predict yield loss based
  on sensor readings. The model weights reveal which sensors matter most.
- **Feature importance ranking**: rank sensors by their ability to separate
  passing and failing samples.
- **Missing data patterns**: sensors with high missing rates may indicate
  intermittent measurement failures that correlate with yield loss.

### What we CANNOT do

- **Root cause attribution**: "Sensor_42 is abnormal → the etch chamber RF
  power supply needs recalibration." This requires knowing that Sensor_42
  measures RF power in the etch chamber.
- **Process recipe adjustment**: "Sensor_42 should be tuned to 250 ± 10."
  Without units and physical meaning, thresholds are purely statistical.
- **Cross-fab comparison**: anonymized features from one fab cannot be
  directly compared to those from another fab.

### The bridge: RAG + SOP documents

FabYield Insight bridges this gap by combining SECOM statistical analysis
with SOP document retrieval. When the system detects that samples failing
yield share abnormally high Sensor_42 readings, it retrieves SOP documents
that reference sensor calibration procedures. The LLM then synthesizes:
"The 23 failing samples show Sensor_42 elevated beyond 3 sigma. Based on
SOP-CAL-007 (Sensor Calibration Procedure), this pattern is consistent with
a drifted pressure transducer requiring recalibration."

The LLM does NOT know that Sensor_42 is a pressure transducer — it infers
the connection from SOP document context, not from the feature identity.

## Label Encoding

| Raw UCI | Meaning | Unified |
|---------|---------|---------|
| -1 | Pass (good die) | 1 |
| +1 | Fail (yield loss) | 0 |

We invert the encoding so that `pass_fail=1` means "good" (intuitive for
yield engineers: 1 = kept, 0 = scrapped).

## Missing Values

Missing values in SECOM are not random. The original paper notes that
missingness "varies depending on the individual features." Some possible
causes in semiconductor context:

- Sensor offline during measurement
- Measurement out of range → recorded as NaN
- Different process recipes use different sensor subsets
- Data acquisition system errors

Our pipeline classifies features by missing rate and recommends actions:
- `<1%`: mean imputation
- `1-5%`: multiple imputation
- `5-20%`: flag + impute
- `20-50%`: consider dropping
- `>50%`: drop

## References

- McCann, M. and Johnston, A. (2008). SECOM. UCI Machine Learning Repository.
- SECOM paper: https://www.semanticscholar.org/ (search "SECOM semiconductor")
