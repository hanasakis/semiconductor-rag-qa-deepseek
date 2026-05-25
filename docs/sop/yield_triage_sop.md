# Yield Triage SOP — SOP-YLD-001

**Version**: v2.1
**Owner**: Process Integration Engineering
**Last Updated**: 2024-06-15

## 1. Purpose

This document defines the standard procedure for triaging yield excursions
in semiconductor manufacturing. When an in-line test or final test flags
a yield drop, the engineer on duty follows this procedure to determine
scope, severity, and initial containment actions.

## 2. Scope

Applies to all process areas: Lithography, Etch, Deposition, CMP,
Implant, and Metrology.

## 3. Triage Levels

| Level | Yield Loss | Response Time | Escalation |
|-------|-----------|---------------|------------|
| L1    | < 2%      | 8 hours       | None       |
| L2    | 2-5%      | 4 hours       | Area Manager |
| L3    | 5-10%     | 2 hours       | Fab Director |
| L4    | > 10%     | 1 hour        | VP Operations |

## 4. Triage Procedure

### Step 1 — Confirm Signal (L1-L4)

- Verify the yield drop is not a measurement artifact.
- Check metrology tool status for the last 24 hours.
- Compare against baseline: is the drop within 3 sigma of historical variation?
- If measurement artifact: document, close ticket. If real: proceed to Step 2.

### Step 2 — Spatial Pattern Analysis (L1-L4)

- Generate wafer map for the affected lot.
- Check for spatial signatures:
  - Center-heavy: likely CMP or spin-coat issue.
  - Edge ring: likely etch or edge-bead removal issue.
  - Random scatter: likely particles or handling defect.
  - Stripe pattern: likely scanner or stepper issue.
- Cross-reference with known spatial signatures in the yield database.

### Step 3 — Sensor Trace Review (L2-L4)

- Pull all sensor traces for the affected lot from SECOM data.
- For each process step in the lot's route, compute z-scores.
- Flag sensors with |z| > 3.0 in at least 3 wafers within the lot.
- Identify sensors with elevated missing-data rates (>10% in affected lot vs <2% baseline).
- Open investigation ticket with top 10 anomalous sensors.

### Step 4 — Commonality Analysis (L3-L4)

- Check whether previous lots on the same tool show similar patterns.
- Query: same chamber? same recipe? same PM cycle?
- If tool-common: escalate to equipment engineering. Confine tool pending PM.
- If recipe-common: escalate to process engineering. Review recipe change history.

### Step 5 — Containment (L3-L4)

- Hold all WIP at the suspected tool/chamber.
- Divert incoming lots to backup tool if available.
- Notify production control of WIP impact.
- Issue Q-Note to operators at the affected station.

## 5. Documentation

Every triage event must generate a Failure Investigation Report (see SOP-RPT-001).
Attach SECOM z-score rankings, wafer maps, and tool commonality data.

## 6. References

- SOP-CAL-007: Sensor Calibration Procedure
- SOP-MISS-003: Missing Data Handling Policy
- SOP-RPT-001: Failure Report Template
