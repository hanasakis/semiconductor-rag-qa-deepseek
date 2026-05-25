# Failure Investigation Report Template — SOP-RPT-001

**Version**: v1.5
**Owner**: Quality & Reliability Engineering
**Last Updated**: 2024-04-01

## 1. Purpose

Standard template for documenting semiconductor yield excursion investigations.
Every L2-L4 triage event (per SOP-YLD-001) must generate a report using this
template within the response-time window.

## 2. Report Structure

### Section A — Event Summary

| Field | Description |
|-------|-------------|
| Report ID | Auto-generated (RPT-YYYY-MM-XXX) |
| Date/Time | When the event was first detected |
| Triage Level | L1 / L2 / L3 / L4 |
| Affected Lot(s) | Lot ID(s) |
| Affected Tool(s) | Equipment ID(s) |
| Affected Process Step | Etch / Litho / CMP / etc. |
| Reported By | Engineer name |

### Section B — Yield Impact

```
Baseline yield:    ___ %
Event yield:       ___ %
Delta:             ___ %
Affected wafers:   ___ / ___
Wafer map pattern: (center / edge / random / stripe / other)
```

### Section C — SECOM Analysis

**Top 10 Anomalous Sensors by |z-score|:**

| Rank | Sensor | z-score | Value | Population Mean | Sensor Group |
|------|--------|---------|-------|-----------------|-------------|
| 1    |        |         |       |                 |             |
| 2    |        |         |       |                 |             |
| ...  |        |         |       |                 |             |

**Top 5 Sensors with Elevated Missing Rate:**

| Rank | Sensor | Missing Rate (Event) | Missing Rate (Baseline) | Delta |
|------|--------|---------------------|------------------------|-------|
| 1    |        |                     |                        |       |
| ...  |        |                     |                        |       |

### Section D — Root Cause Analysis

- [ ] Sensor drift confirmed (SOP-CAL-007)
- [ ] Equipment malfunction confirmed (which component?)
- [ ] Process recipe deviation confirmed (which parameter?)
- [ ] Raw material variation suspected
- [ ] Environmental excursion (temperature, humidity, particles)
- [ ] Operator error
- [ ] Other: _________________

### Section E — Containment Actions

- [ ] Tool confined for PM
- [ ] WIP held at affected step
- [ ] Incoming lots diverted
- [ ] Q-Note issued to operators
- [ ] Supplier notification sent (if material-related)

### Section F — Corrective Actions

- [ ] Sensor recalibrated / replaced (specify)
- [ ] Recipe adjusted (specify parameter and new value)
- [ ] PM procedure updated
- [ ] Training conducted
- [ ] SPC limit updated

### Section G — Verification

```
Re-qualification wafer result: PASS / FAIL
Number of lots monitored post-fix: ___
Post-fix yield: ___ % (target: ___ %)
Closure approved by: _________________  Date: __________
```

## 3. Distribution

- Process Integration Engineering
- Equipment Engineering
- Area Manager (L2+)
- Fab Director (L3+)
- VP Operations (L4)

## 4. References

- SOP-YLD-001: Yield Triage SOP
- SOP-CAL-007: Sensor Drift Investigation
- SOP-MISS-003: Missing Data Handling Policy
