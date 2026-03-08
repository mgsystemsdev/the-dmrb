# Import Contract v1 — DMRB ETL Analysis

**Document class:** Spec (derived from reverse-engineering of existing DMRB ETL + Canonical Master Blueprint v1)  
**Scope:** v1 import and reconciliation behavior for Turnover Cockpit  
**Purpose:** Define the deterministic import contract so `import_service` and parsers can be implemented without ambiguity.

---

## 1. Report Inventory

### 1.1 Input reports (in repo)

| Report | Path | Format | Skip rows (script usage) | Notes |
|--------|------|--------|---------------------------|--------|
| Available Units | `Reports/data/Available Units.csv` | CSV | 5 | Property + date header lines |
| Move-Outs | `Reports/data/Move-Outs.csv` | CSV | 6 | Different header offset |
| Pending Move Ins | `Reports/data/Pending Move Ins.csv` | CSV | 5 | Title + property + date + total |
| Pending FAS | `Reports/data/PendingFAS-.csv` | CSV | 4 | Multiple header/blank rows |

### 1.2 Referenced but not in repo

| Artifact | Path | Role |
|----------|------|------|
| DMRB_raw | `Reports/data/DMRB_raw.xlsx` | Sheet `"DMRB "` (trailing space); used as source for backfilling blanks and for reconciliation comparison |
| Final_Report | `Reports/output/Final_Report.xlsx` | Master workbook produced by `clean_up.py`; contains Reconciliation (and others). Updated in place by `backfill_recon.py`. |
| reconciliation_output | `Reports/output/reconciliation_output.xlsx` | Output of `reconciliation_check.py`; mismatch report only (rows with issues). |
| MoveIn_Records | `Reports/output/MoveIn_Records.xlsx` | Ledger of (Unit, Move-In Date); updated by move-in flow; purge 30+ days. |

### 1.3 Script execution order (existing ETL)

1. **clean_up.py** — Runs first. Reads the four CSVs; writes `Final_Report.xlsx` (sheets: Available Units, Move Ins, Move Outs, Pending FAS, Move Activity, Reconciliation) and updates `MoveIn_Records.xlsx`.
2. **backfill_recon.py** — Optional. Reads `Final_Report.xlsx` (Reconciliation) and `DMRB_raw.xlsx`; fills blanks in Reconciliation from DMRB; writes back to `Final_Report.xlsx` and adds "Split View" sheet.
3. **reconciliation_check.py** — Compares Reconciliation (source of truth) to DMRB; writes `reconciliation_output.xlsx` (Mismatches, Not in DMRB).
4. **movein_records.py** — Standalone module for Move-In Records ledger; can be fed from DMRB-style DataFrame (Unit, Move_in); not invoked by clean_up in the same process but clean_up has its own inline `update_movein_records(move_ins_df)`.

---

## 2. Raw Schemas

### 2.1 Available Units.csv

- **Headers (after skiprows=5):**  
  `Unit`, `Amenity`, `Floor Plan`, `Floor Plan Group`, `Rentable Sq Ft`, `Status`, `Available Date`, `Move-In Ready Date`, `Specials`, `Deposit`, `Price`, `Best Price`, `Accessibility`
- **Used columns:** `Unit`, `Status`, `Available Date`, `Move-In Ready Date`
- **Unit identifier:** `Unit` (values have leading space in sample, e.g. ` Unit 4-26-0417`); script strips with `.str.strip()`.
- **Date columns:** `Available Date`, `Move-In Ready Date`
- **Status column:** `Status` (e.g. "Vacant ready")
- **Filter:** Rows kept only where phase ∈ {5, 7, 8} (parsed from Unit: prefix "Unit " removed, then first segment before "-").
- **Formatting:** Unit has leading space in CSV; script strips. Dates parsed with `pd.to_datetime(..., errors="coerce")`.

### 2.2 Move-Outs.csv

- **Headers (after skiprows=6):**  
  `Last Name`, `First Name`, `Unit`, `Move-Out Date`, `Lease End Date`, `Notice to Vacate`, `Collect forwarding address`, `Final Utility Charges`, `Documents`, `Optional Tasks`, `MO Ready`
- **Used columns:** `Unit`, `Move-Out Date`
- **Unit identifier:** `Unit` (e.g. ` 3-33-0201`); script prepends `"Unit "` after strip.
- **Date column:** `Move-Out Date`
- **Filter:** phase ∈ {5, 7, 8} (same as Available Units).
- **Formatting:** Unit stored without "Unit " in CSV; script adds "Unit " for consistency with other sheets.

### 2.3 Pending Move Ins.csv

- **Headers (after skiprows=5):**  
  `Name`, `Unit`, `Move In Date`, `Manage Lease`, `Fees  Deposits & Concessions`, … (plus multiple task/checklist columns), `Move In Ready`
- **Used columns:** `Unit`, `Move In Date`
- **Unit identifier:** `Unit` (e.g. ` 3-11-0107`); script prepends `"Unit "` after strip.
- **Date column:** `Move In Date`
- **Filter:** phase ∈ {5, 7, 8}.
- **Formatting:** Same Unit normalization as Move-Outs.

### 2.4 PendingFAS-.csv

- **Headers (after skiprows=4):**  
  `PropertyName`, `Account`, `Status`, `Unit Number`, `Subjournal`, `Mail To`, `Forward Address`, `MO / Cancel Date`, `Lease End`, `Ledger Balance`, `Addtl Charges`, `Balance Due`, `FAS Balance`
- **Used columns:** `Unit Number` (renamed to `Unit`), `MO / Cancel Date`, `Lease End`
- **Unit identifier:** `Unit Number` → renamed to `Unit`; script prepends `"Unit "` after strip.
- **Date columns:** `MO / Cancel Date`, `Lease End`
- **Filter:** phase ∈ {5, 7, 8}.
- **User state:** Script reads previous `Final_Report.xlsx` Pending FAS sheet to restore user-typed `Completed` values; column not in CSV, added during processing.

### 2.5 DMRB_raw.xlsx (inferred from scripts)

- **Sheet name:** `"DMRB "` (trailing space).
- **Columns used in backfill_recon.py:** `Unit`, `Status`, `Move_out`, `Ready_Date` (no `Move_in` in FILL_MAP; backfill only fills Status, Available Date, Move-In Ready Date).
- **Columns used in reconciliation_check.py:** `Unit`, `Move_out`, `Ready_Date`, `Move_in`.
- **Inferred full set for contract:** `Unit`, `Status`, `Move_out`, `Ready_Date`, `Move_in`.
- **Formatting:** Column names stripped; Unit stripped. Dates: `Move_out`, `Move_in`, `Ready_Date` parsed with `pd.to_datetime(..., errors="coerce")`.
- **Duplicate units:** If multiple rows per Unit in DMRB, backfill uses first match (`dmrb_row.iloc[0]`).

---

## 3. Transformation Pipeline

Text pipeline (execution order):

```
Step 1  → Read Available Units.csv (skip 5 rows); select Unit, Status, Available Date, Move-In Ready Date.
Step 2  → Normalize Unit: strip; add phase from first segment (Unit → remove "Unit " → split "-" → [0]); filter phase in [5,7,8].
Step 3  → Parse Available Date, Move-In Ready Date (coerce errors).
Step 4  → Read Pending Move Ins.csv (skip 5); select Unit, Move In Date; normalize Unit ("Unit " + strip); same phase filter; parse Move In Date.
Step 5  → Read Move-Outs.csv (skip 6); select Unit, Move-Out Date; normalize Unit ("Unit " + strip); same phase filter; parse Move-Out Date.
Step 6  → Read PendingFAS-.csv (skip 4); select Unit Number→Unit, MO / Cancel Date, Lease End; "Unit " + strip; phase filter; parse dates; restore previous "Completed" from existing Final_Report Pending FAS.
Step 7  → Build Move Activity: outer merge Move Ins (Unit, Move In Date) and Move Outs (Unit, Move-Out Date) on Unit.
Step 8  → Build Reconciliation: outer merge Available (Unit, Status, Available Date, Move-In Ready Date) with Move Ins (Unit, Move In Date), then outer merge with Pending FAS (Unit, MO / Cancel Date). Where MO / Cancel Date is present: set Available Date = MO / Cancel Date, Status = "Vacant Not Ready", set MO / Confirm = "Yes"; then drop MO / Cancel Date.
Step 9  → Write Final_Report.xlsx (Available Units, Move Ins, Move Outs, Pending FAS, Move Activity, Reconciliation).
Step 10 → Update Move-In Records ledger: dedupe by (Unit, Move-In Date); purge Move-In Date &lt; today - 30 days; write MoveIn_Records.xlsx.
```

Optional backfill (backfill_recon.py):

```
Step B1 → Read Final_Report.xlsx Reconciliation; strip Unit.
Step B2 → Read DMRB_raw.xlsx sheet "DMRB "; strip column names and Unit; build lookup by Unit.
Step B3 → For each Reconciliation row: if Unit in DMRB, for each of (Status, Available Date, Move-In Ready Date), if Recon value is blank/NaN, fill from DMRB (Status, Move_out, Ready_Date). Duplicate Units in DMRB: take first row.
Step B4 → Write reconciled values back to Final_Report.xlsx Reconciliation sheet only.
Step B5 → Add "Split View" sheet (No Move In / Has Move In) from reconciled DataFrame.
```

Reconciliation check (reconciliation_check.py):

```
Step C1 → Read Reconciliation (source of truth); strip Unit; coerce dates.
Step C2 → Read DMRB; strip columns and Unit; coerce Move_out, Ready_Date, Move_in.
Step C3 → Left merge Reconciliation with DMRB on Unit (DMRB columns renamed to DMRB Available Date, DMRB Ready Date, DMRB Move In Date).
Step C4 → Flag: Missing in DMRB; Avail Date Mismatch (|Available Date - DMRB Available Date| > 2 days); Move In Mismatch (|Move In Date - DMRB Move In Date| > 2 days); Move In Missing in DMRB; Avail Date Missing in DMRB.
Step C5 → Output only rows with issues to reconciliation_output.xlsx (Mismatches, Not in DMRB).
```

---

## 4. Authoritative Source Hierarchy

### 4.1 Per-field authority (Reconciliation build — clean_up.py)

| Fact | Authoritative source | Precedence / notes |
|------|----------------------|---------------------|
| Unit existence (list of units) | Union of: Available Units, Pending Move Ins, Pending FAS (after outer merges). Move-Outs contribute only via Move Activity, not Reconciliation row set. | Outer merge: any unit in Available, Move Ins, or Pending FAS appears in Reconciliation. |
| move_out_date (canonical) | Available Units "Available Date" initially; **overridden** by Pending FAS "MO / Cancel Date" when that is present. | In process_reconciliation: `confirmed = df["MO / Cancel Date"].notna()`; then `df.loc[confirmed, "Available Date"] = df.loc[confirmed, "MO / Cancel Date"]`. So Pending FAS wins for Available Date when MO / Cancel Date exists. |
| move_in_date (canonical) | Pending Move Ins "Move In Date". | Brought in by outer merge; no override from other reports. |
| ready_date (Move-In Ready Date) | Available Units "Move-In Ready Date". | Not overwritten by Pending FAS in clean_up; only backfill can fill blanks from DMRB Ready_Date. |
| Status | Available Units "Status" initially; **overridden** to "Vacant Not Ready" when Pending FAS "MO / Cancel Date" is present. | Same `confirmed` block: `df.loc[confirmed, "Status"] = "Vacant Not Ready"`. |
| turnover existence | Implicit: a row in Reconciliation represents a unit with at least one of (Available Date, Move In Date, or MO/Confirm). No explicit "turnover" entity; one row per unit. | One-open-per-unit is not enforced by current ETL; duplicate units can appear if sources have duplicates. |

### 4.2 Backfill (backfill_recon.py)

- **DMRB_raw** is used only to **fill blanks** in Reconciliation. It does not overwrite non-blank values.
- **Blanks:** `pd.isna(...)` or string that is strip-empty.
- **Column mapping:** Reconciliation `Status` ← DMRB `Status`; `Available Date` ← DMRB `Move_out`; `Move-In Ready Date` ← DMRB `Ready_Date`.
- **Precedence:** Reconciliation (existing value) wins; DMRB fills only when Reconciliation value is blank.

### 4.3 Reconciliation check (reconciliation_check.py)

- **Source of truth for comparison:** Reconciliation (Final_Report.xlsx).
- **Comparison target:** DMRB. Mismatches are reported; Reconciliation is not updated by this script.
- **±2 days:** Differences within 2 days are not flagged as mismatches (reporting-only tolerance).

### 4.4 Priority tree (summary)

1. **Reconciliation build:**  
   - Available Date: Pending FAS "MO / Cancel Date" if present, else Available Units "Available Date".  
   - Move In Date: Pending Move Ins "Move In Date".  
   - Move-In Ready Date: Available Units "Move-In Ready Date" (no override from FAS).  
   - Status: "Vacant Not Ready" if Pending FAS MO/Cancel present, else Available Units "Status".
2. **After build:** Backfill can set Status, Available Date, Move-In Ready Date only where Reconciliation value is blank, using DMRB_raw.
3. **Reconciliation check:** Compares Reconciliation to DMRB; no write-back; ±2 day tolerance for mismatch flags only.

---

## 5. Matching & Tolerance Rules

### 5.1 Current ETL (no explicit strong/weak match)

- **Matching key for merges:** Unit (after normalization: strip, and for Move-Outs/Move Ins/Pending FAS, "Unit " prefix added so all use same format).
- **No move_out_date in merge key:** Reconciliation is built by outer merge on Unit only. So one row per unit in the merged set; if Available Units has one Available Date and Pending FAS has another for same unit, Pending FAS overwrites (as above). There is no ±day matching in the build; it is overwrite by source precedence.
- **Duplicate units in a single report:** If Available Units has two rows for same Unit, both appear until merged; then pandas merge keeps one row per Unit with the last-seen values (depends on order). Requires clarification for deterministic behavior in new system.

### 5.2 Tolerance in reconciliation_check only

- **Available Date:** Mismatch if both sides non-null and `|Available Date - DMRB Available Date| > 2 days`.
- **Move In Date:** Mismatch if both sides non-null and `|Move In Date - DMRB Move In Date| > 2 days`.
- **Use:** Reporting only; no data written using tolerance. No "weak match" merge.

### 5.3 Blueprint alignment (target for v1 import)

- **Strong match:** `(property_id, unit_code_norm, move_out_date)` exact → create or update turnover.
- **Weak match:** same unit_code_norm, move_out_date within ±2 days → **never apply**; create conflict row and DATA_INTEGRITY risk.
- **±2 day:** Reporting / mismatch detection only; never used to write canonical move_out_date.

---

## 6. Derived Field Definitions

### 6.1 phase

- **Definition:** First numeric segment of Unit after removing "Unit " and splitting on "-". Example: "Unit 5-12-0307" → "5".
- **Use:** Filter to phase ∈ {5, 7, 8} only. Not persisted as a column in blueprint; v1 may use property_id instead.

### 6.2 MO / Confirm

- **Definition:** "Yes" when Pending FAS "MO / Cancel Date" is present for that unit in the merge; else "".
- **Derived:** In process_reconciliation, `confirmed = df["MO / Cancel Date"].notna()`; `df["MO / Confirm"] = confirmed.map({True: "Yes", False: ""})`.

### 6.3 Move-In Records ledger (Unit, Move-In Date)

- **Definition:** Append-only style list of (Unit, Move-In Date) from move-ins; deduplicated by (Unit, Move-In Date); purged when Move-In Date &lt; today - 30 days.
- **Source:** clean_up uses Pending Move Ins "Move In Date"; movein_records module can use DMRB "Move_in".
- **Not canonical for turnover:** Ledger is for reporting/history; canonical move_in_date in new system is report-authoritative from import.

---

## 7. Ready-Day & SLA Logic

### 7.1 Ready day in current ETL

- **Available Units:** "Move-In Ready Date" is a **raw** column from the report.
- **Reconciliation:** "Move-In Ready Date" comes from Available Units; backfill can fill blanks from DMRB "Ready_Date". No formula in scripts that derives ready from other dates.
- **Override:** When Pending FAS has MO / Cancel Date, "Available Date" is set to that (move-out semantics); Status set to "Vacant Not Ready". "Move-In Ready Date" is **not** set from Pending FAS in clean_up.
- **Conclusion:** Ready is treated as a report-supplied field (or backfilled from DMRB); not derived from move-in or stabilization in the scripts.

### 7.2 Blueprint (v1)

- **manual_ready_status** / **manual_ready_confirmed_at** are manual-authoritative; import must not overwrite them.
- **SLA:** Window is move_out_date → manual_ready_confirmed_at; breach when today - move_out_date &gt; 10 and no manual_ready_confirmed_at. Ready-day in ETL maps conceptually to manual ready confirmation in blueprint, but blueprint does not take "Move-In Ready Date" from report as canonical for SLA; manual confirmation is.

---

## 8. Conflict & Duplicate Handling

### 8.1 Current ETL

- **Duplicate units in one report:** Not explicitly deduplicated before merge (e.g. last row wins in pandas). Requires clarification for v1.
- **Move-out “disappearance”:** Not implemented in scripts. A unit present in Reconciliation is not removed if it disappears from Move-Outs.
- **Move-in without move-out:** Can occur in Reconciliation (outer merge); no conflict flag. Row exists with Move In Date and possibly blank Available Date until backfill.
- **Weak match (±2 days):** Only used in reconciliation_check to decide if a row is a "mismatch"; no merge or conflict row in current ETL.

### 8.2 Blueprint (v1)

- **Weak match:** Never apply; set `import_row.conflict_flag`, `conflict_reason = WEAK_MATCH_MOVE_OUT_DATE_WINDOW`, add DATA_INTEGRITY risk.
- **Move-out disappearance:** After two consecutive Move-Out imports without seeing the open turnover, set canceled_at, cancel_reason, audit.
- **Move-in without turnover:** Conflict row, DATA_INTEGRITY CRITICAL, manual "Create turnover from this row".
- **Duplicate open turnover:** Prevented by partial unique index; any attempt to create second open turnover for unit must fail or be conflict.

---

## 9. Edge Cases & Defaults

### 9.1 Missing dates

- **Scripts:** `pd.to_datetime(..., errors="coerce")` → NaT for unparseable or missing. No default date substituted.
- **Blanks:** Backfill treats blank or NaN as “fillable” from DMRB.

### 9.2 Blank unit codes

- **Scripts:** Strip only. Empty unit after strip remains; phase becomes NaN, row dropped by `phase.isin([5,7,8])`. So effectively blank-unit rows are dropped.

### 9.3 Malformed dates

- **Scripts:** Coerced to NaT; no exception. Row remains with NaT.

### 9.4 One open turnover per unit

- **Current ETL:** Not enforced. Reconciliation is one row per unit in the merged set, but the concept of "open" vs "closed" turnover does not exist; there is no cancellation or closure.
- **Blueprint:** Enforced by partial unique index; one open turnover per unit.

### 9.5 Units without move-out

- **Current ETL:** Unit can appear from Pending Move Ins or Available Units only; then Available Date may be blank (filled later by backfill or remain blank).
- **Blueprint:** Turnover requires move_out_date NOT NULL; unit existence is separate (unit table). Turnover creation requires strong match including move_out_date.

### 9.6 Move-in without move-out

- **Current ETL:** Allowed; Reconciliation row can have Move In Date and no Available Date (until backfill or never).
- **Blueprint:** Move-in row for unit with no open turnover → conflict, no auto-create.

### 9.7 Silent corrections

- **Current ETL:** Pending FAS overwrites Available Date and Status when MO / Cancel Date present (not a “correction” but precedence). Backfill fills only blanks. No silent ±day merge.
- **Blueprint:** No silent merges; weak match must produce conflict.

---

## 10. Output Contract

### 10.1 Final_Report.xlsx (sheets)

- **Available Units, Move Ins, Move Outs, Pending FAS:** Normalized and filtered CSVs; phase + selected columns; dates coerced.
- **Move Activity:** Outer join of Move Ins and Move Outs on Unit; columns phase, Unit, Move-Out Date, Move In Date.
- **Reconciliation:** Union on Unit; Status, Available Date, Move-In Ready Date, Move In Date, MO / Confirm; precedence as in §4; optional backfill from DMRB.
- **Split View (backfill_recon):** Same columns as Reconciliation; split into “Has Move In” and “No Move In” tables.

### 10.2 Fields that are canonical for v1 DB

- **From reports → DB:** unit_code (raw + norm), move_out_date (from Available Date / MO Cancel precedence), move_in_date (from Pending Move Ins / DMRB Move_in), and optionally ready_date for display only (blueprint canonical ready is manual_ready_confirmed_at).
- **Reporting-only (do not persist as canonical):** phase (filter only), MO / Confirm (derived flag), Issue (reconciliation_check), Avail Date Diff, Move In Diff.

### 10.3 reconciliation_output.xlsx

- **Mismatches:** Reconciliation rows with any of: Missing in DMRB, Avail Date Mismatch, Move In Mismatch, Move In Missing in DMRB, Avail Date Missing in DMRB; plus Issue text.
- **Not in DMRB:** Subset of rows where unit is missing from DMRB; columns renamed for export (Move Out, Ready Date, Move In, Status mapped, DV empty).

---

## 11. Blueprint Gap Analysis

### 11.1 Where current ETL violates blueprint

| Blueprint rule | Current ETL | Gap |
|----------------|-------------|-----|
| No silent merges | No ±day merge in build; ±2 days only in check for reporting | ETL is aligned on “no weak merge.” New system must keep it. |
| Idempotency (same report_type + checksum = no-op) | Not implemented; scripts overwrite/append without checksum or idempotency | New import must implement batch checksum and NO_OP. |
| Deterministic matching | Merge on Unit only; duplicate units in one report undefined (last row) | New system must define strong match on (property_id, unit_code_norm, move_out_date) and handle duplicates explicitly. |
| Append-only audit / import_batch, import_row | No batch or row-level audit; Final_Report overwritten in place | New system must write import_batch and import_row, never overwrite. |
| One open turnover per unit | Not modeled | New system enforces via schema and import logic. |
| Move-out disappearance (2-import window) | Not implemented | New system must implement missing_moveout_count and auto-cancel. |
| Move-in without turnover → conflict | Allowed in Reconciliation | New system must create conflict and CRITICAL risk. |
| Manual-authoritative fields never overwritten by import | N/A in current ETL (no manual fields) | New system must never overwrite manual_ready_*, wd_*, etc. |

### 11.2 Tolerance

- **Current:** ±2 days used only for mismatch reporting in reconciliation_check.
- **Blueprint:** ±2 days is reporting-only; never used to write canonical move_out_date. Aligned.

### 11.3 Lifecycle

- **Current:** No lifecycle states; only Status and dates.
- **Blueprint:** Lifecycle derived from move_out_date, move_in_date, closed_at, canceled_at. Import only writes raw facts; lifecycle is derived.

### 11.4 Manual-authoritative

- **Current:** “Completed” in Pending FAS is user state restored from previous run; not overwritten by CSV. No other manual-authoritative fields.
- **Blueprint:** manual_ready_status, manual_ready_confirmed_at, expedited_flag, wd_*, etc. must never be overwritten by import.

### 11.5 Business rules that conflict

- **Reconciliation overwrites Available Date from Pending FAS when MO / Cancel present:** In v1, move_out_date should be report-authoritative from a single defined report type (e.g. Move-Out) with clear precedence; Pending FAS could be a second report type that can update move_out_date only when allowed by contract (e.g. same strong match). Requires clarification: which report_type is authoritative for move_out_date in v1?
- **Backfill “fill blanks” from DMRB:** In v1, multiple report types and order of import could be formalized; “blank fill” could be a separate report type or a defined precedence in the contract.

---

## Document control

- **Source:** Reverse-engineering of `Reports/clean_up.py`, `Reports/backfill_recon.py`, `Reports/movein_records.py`, `Reports/reconciliation_check.py`, and CSVs under `Reports/data/`; aligned with Canonical Master Blueprint v1 (§8 Import & Reconciliation, §3.13–3.14 import_batch/import_row).
- **Inferred only (no file in repo):** DMRB_raw.xlsx column list; Final_Report.xlsx / reconciliation_output.xlsx full column semantics.
- **Requires clarification:** Duplicate unit handling per report; which report_type is authoritative for move_out_date in v1; formalization of “backfill” as report type or precedence rule.
