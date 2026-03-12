# Ready Date Lifecycle Semantics — Board Rendering Pipeline Analysis

**Document type:** Analysis (no code changes)  
**Purpose:** Evaluate whether the current fallback logic (`report_ready_date OR available_date`) for the Ready Date column is lifecycle-correct or introduces ambiguity.  
**Constraint:** Analysis only; no refactor implemented.

---

## 1. Current Behavior of Ready Date Rendering

### 1.1 Where the fallback is applied

The fallback is implemented in **one place** in the board pipeline:

| Location | Code | Effect |
|----------|------|--------|
| `services/board_query_service.py` | `_build_flat_row()` lines 83–86 | `effective_report_ready_date = turnover.get("report_ready_date") or turnover.get("available_date")`; this value is assigned to both `report_ready_date` and `ready_date` in the flat row dict. |

So every consumer of the flat row (board, export, enrichment, morning workflow, turnover detail, AI context, flag bridge, risk radar) receives a row where:

- `row["report_ready_date"]` = DB `report_ready_date` if present, else DB `available_date`
- `row["ready_date"]` = same value

The UI then displays this merged value:

| Location | Code | Effect |
|----------|------|--------|
| `ui/screens/board.py` line 271 | `parse_date(row.get("report_ready_date") or row.get("ready_date"))` | Displays the Ready Date column; redundant with _build_flat_row since both keys already hold the effective value. |

### 1.2 Data flow summary

1. **DB** → `turnover.report_ready_date`, `turnover.available_date` (separate columns).
2. **Board query** → `_build_flat_row()` merges them into `effective_report_ready_date` and puts it in `report_ready_date` and `ready_date`.
3. **Enrichment** → `enrichment.enrich_row(row, today)` receives the flat row; it reads `row.get("report_ready_date")` for `is_ready_declared` and `plan_breach`. So enrichment uses the **effective** (fallback) value.
4. **Board UI** → Renders Ready Date from that same row.
5. **Export** → `get_dmrb_board_rows()` is used for the Final Report; the “Move-In Ready Date” column is `t.get("report_ready_date")`, i.e. the effective value.
6. **Risk service** → Does **not** use the flat row. It loads `turnover_row["report_ready_date"]` directly from the DB for `evaluate_risks()` (EXPOSURE_RISK). So risk uses **only** `report_ready_date`, never `available_date`.

Result: **Display, enrichment (plan_breach, is_ready_declared), and export** use the fallback. **Risk (EXPOSURE_RISK)** does not.

---

## 2. Lifecycle Meaning of available_date vs report_ready_date

### 2.1 Source report semantics (Available Units)

From product and spec:

- **Available Units report columns:**
  - **Available Date** → when the resident has vacated the unit (vacancy).
  - **Move-In Ready Date** → when the unit is ready for leasing / occupancy (readiness).

So in the source report they are two distinct lifecycle events: vacancy vs. readiness.

### 2.2 How the system stores them

- **report_ready_date**  
  - Populated from:
    - **AVAILABLE_UNITS:** “Move-In Ready Date” (and in some code paths, fallback to Available Date — see §4).
    - **DMRB:** “Ready_Date” (single column; same value is also written to `available_date` in DMRB import).
  - Intended meaning: date the unit is declared or expected to be **ready for move-in**.

- **available_date**  
  - Populated from:
    - **AVAILABLE_UNITS:** “Available Date” (vacancy date).
    - **DMRB:** same as Ready_Date (DMRB has no separate Available Date column).
  - Intended meaning: **vacancy** (resident has vacated).

So by design:

- **available_date** = vacancy.
- **report_ready_date** = readiness (move-in ready).

Using `available_date` as a stand-in for “Ready Date” when `report_ready_date` is NULL is therefore **semantically incorrect**: it treats a vacancy date as if it were a readiness date.

### 2.3 Import behavior and persistence of the fallback

The fallback is also applied **on write** in the AVAILABLE_UNITS import:

| File | Behavior |
|------|----------|
| `services/imports/available_units.py` | `effective_ready = ready_date or available_date` (e.g. lines 270, 527). When updating or creating a turnover, the code sometimes writes `effective_ready` into `report_ready_date` in the DB. So the DB can already contain a date that originated from “Available Date” in the `report_ready_date` column. |

So lifecycle ambiguity exists in both:

1. **Board (and export) rendering** — fallback at read time in `_build_flat_row`.
2. **Import** — fallback at write time, persisting “available” into `report_ready_date`.

This analysis focuses on the **board rendering pipeline**; import semantics are noted as a related concern.

---

## 3. Risks Introduced by the Fallback Logic

### 3.1 Displaying a value that does not exist in the source report

- When the source report has **Move-In Ready Date** blank and **Available Date** set, the board shows that Available Date in the “Ready Date” column.
- So the board can show a date that **does not exist** in the “Move-In Ready Date” column of the source report. That is a traceability and correctness issue.

### 3.2 Operational misinterpretation (vacant vs ready)

- **Available Date** = unit vacant (resident out).
- **Move-In Ready Date** = unit ready for occupancy (work complete, etc.).
- If the board shows Available Date under “Ready Date,” leasing or operations may treat the unit as **ready for move-in** when it is only **vacant**. That can lead to:
  - Scheduling move-ins before the unit is actually ready.
  - Plan breach / exposure logic that is driven by the wrong date (see below).

### 3.3 Inconsistent downstream logic

| Consumer | Uses | Effect of fallback |
|----------|------|--------------------|
| Board, Export, Morning workflow, Turnover detail | Flat row → `report_ready_date` / `ready_date` | Sees effective = report_ready_date OR available_date. |
| Enrichment (`is_ready_declared`, `plan_breach`) | Flat row → `report_ready_date` | Same: can be True / fire when only `available_date` is set. |
| Risk service (EXPOSURE_RISK) | DB `turnover.report_ready_date` only | Does **not** use fallback. EXPOSURE_RISK only fires when `report_ready_date` is set. |

So:

- **plan_breach** can trigger when “ready date” has passed and unit is not ready — but that “ready date” may actually be `available_date` (vacancy). So “plan breach” can mean “available date passed, unit not ready,” which is not the same as “declared ready date passed, unit not ready.”
- **EXPOSURE_RISK** only considers `report_ready_date`. So a unit with only `available_date` set will show a Ready Date on the board and can have plan_breach, but will **not** get EXPOSURE_RISK. Behavior is inconsistent and can confuse users.

### 3.4 Should available_date ever be interpreted as a readiness signal?

**No.** By definition:

- **available_date** = vacancy (resident vacated).
- **report_ready_date** = readiness (ready for leasing / move-in).

Using available_date as a readiness signal blurs two different lifecycle events and encourages the operational misinterpretation above. The fallback is what causes that blur in the board pipeline.

---

## 4. Whether the Board Should Render Only report_ready_date

**Yes.** For lifecycle correctness and consistency with the source report:

1. **Single meaning for “Ready Date”**  
   The board column should represent “Move-In Ready Date” only. That corresponds to `report_ready_date`. Showing `available_date` when `report_ready_date` is NULL makes the column sometimes mean “vacancy” and sometimes “readiness.”

2. **Traceability**  
   The value in the Ready Date column should, when present, correspond to a value that exists in the source report’s “Move-In Ready Date” (or DMRB Ready_Date). Falling back to Available Date breaks that.

3. **Operational safety**  
   Showing blank when `report_ready_date` is NULL is safer than showing a vacancy date as if it were a ready date. It avoids the “unit appears ready when it is only vacant” misinterpretation.

4. **Alignment with risk logic**  
   Risk already uses only `report_ready_date`. If the board and enrichment also use only `report_ready_date`, plan_breach and EXPOSURE_RISK are aligned to the same readiness signal.

**Conclusion:** The board (and any other display of “Ready Date” that is intended to mean “move-in ready”) should render **only** `report_ready_date` and show **blank** when it is missing. The fallback to `available_date` should be removed from the board rendering pipeline.

---

## 5. If a Refactor Is Recommended — Safest Minimal Change

### 5.1 Recommendation

**Remove the fallback in the board pipeline** so that Ready Date is sourced only from `report_ready_date`. When `report_ready_date` is NULL, Ready Date should be blank.

### 5.2 Safest minimal change (when implementing)

1. **`services/board_query_service.py` — `_build_flat_row()`**  
   - Remove the merge: stop computing `effective_report_ready_date` from `available_date`.  
   - Set the flat row from the DB only:
     - `report_ready_date` = `turnover.get("report_ready_date")` (no fallback).
     - `ready_date` can be set to the same as `report_ready_date` for backward compatibility, or dropped if no longer needed.  
   - Optionally keep `available_date` in the flat row as a separate key so that future UI (e.g. a separate “Available Date” column) or export can show it without conflating it with Ready Date.

2. **`ui/screens/board.py`**  
   - Ready Date column can remain `parse_date(row.get("report_ready_date") or row.get("ready_date"))`. After (1), both will be the same and will be NULL when `report_ready_date` is NULL. No need to change unless you want to display only `report_ready_date` explicitly.

3. **Enrichment**  
   - No change required. `domain/enrichment.py` already reads `row.get("report_ready_date")`. Once the flat row no longer overwrites it with the fallback, enrichment will naturally use only `report_ready_date`. So:
     - `is_ready_declared` will be True only when `report_ready_date` is set.
     - `plan_breach` will fire only when that same readiness date has passed and the unit is not ready.

4. **Export**  
   - Final Report uses the same flat row. After (1), “Move-In Ready Date” in the export will be only `report_ready_date`. If the export is intended to mirror the source report’s “Available Date” and “Move-In Ready Date” columns, ensure “Available Date” in the export is sourced from `available_date` (or the existing export logic for that column) and “Move-In Ready Date” from `report_ready_date` only. (Export currently overwrites `available_date` with confirmed_move_out/move_out_date in one code path; that is separate from this change.)

5. **Risk service**  
   - No change; it already uses only DB `report_ready_date`.

6. **Diagnostics / scripts**  
   - `scripts/diagnose_blank_ready_date.py` already treats “blank Ready Date” as both `report_ready_date` and `available_date` NULL. After removing the fallback, “blank Ready Date” on the board will match that definition. No change required unless you want the script to explicitly call out that the board no longer falls back to available_date.

### 5.3 What will change for users

- **Before:** When `report_ready_date` was NULL and `available_date` was set, the board (and export) showed `available_date` in the Ready Date column.  
- **After:** In that case the Ready Date column will be **blank**.  
- **When both are set:** No change; Ready Date will still show `report_ready_date`.  
- **When only report_ready_date is set:** No change.

So the only behavioral change is: some units that currently show a date in Ready Date (the vacancy date) will show blank instead. That is the intended, lifecycle-correct behavior.

### 5.4 Optional follow-up (import semantics)

To fully align lifecycle semantics, consider a **separate** change to the AVAILABLE_UNITS import: **do not** write `available_date` into `report_ready_date` when “Move-In Ready Date” is blank. Only write the parsed “Move-In Ready Date” into `report_ready_date`, and keep “Available Date” in `available_date` only. That would prevent the fallback from being persisted in the DB and would match the intended meanings of the two source columns. This is outside the minimal “board rendering only” refactor.

---

## 6. Summary

| Question | Answer |
|----------|--------|
| Should available_date ever be interpreted as a readiness signal? | **No.** It means vacancy; report_ready_date means readiness. |
| Does the board display a value that does not exist in the source report? | **Yes.** When Move-In Ready Date is blank and Available Date is set, the board shows Available Date in the Ready Date column. |
| Can the fallback cause operational misinterpretation? | **Yes.** A unit can appear “ready” on a date when it is only “vacant.” |
| Should the board render only report_ready_date? | **Yes.** Render only report_ready_date; show blank when it is missing. |
| Safest minimal change? | Remove the fallback in `_build_flat_row()` so the flat row’s `report_ready_date` (and `ready_date`) come only from DB `report_ready_date`. Enrichment and export then automatically use the correct signal; risk already does. |

**Conclusion:** The fallback logic is **not** lifecycle-correct. It conflates vacancy and readiness and can cause misinterpretation and inconsistent behavior (plan_breach vs EXPOSURE_RISK). The board (and the flat row consumed by enrichment and export) should render and propagate **only** `report_ready_date` for the Ready Date concept, and show blank when it is missing. The refactor above is the minimal change to achieve that in the board rendering pipeline.
