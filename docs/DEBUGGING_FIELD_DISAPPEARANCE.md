# Debugging Field Disappearance — Prompt Playbook (Refined)

When a field (Ready Date, move-out, move-in, tasks, etc.) **mysteriously disappears** between import and UI, use this playbook.

The goal is to force the agent to **trace the data pipeline and verify the actual row being rendered**.

Most bugs fall into one of five categories:

1. Field never written to DB  
2. Field renamed during pipeline  
3. Field dropped during row construction  
4. UI reading wrong key  
5. UI showing **a different record than expected**

---

## Prompt 1 — Trace the Field Lifecycle

Trace the full lifecycle of **[FIELD_NAME]** from import to board (or target screen) rendering.

Specifically track the value originating from **[SOURCE]** (e.g. report column name or API field).

For each step, identify:

1. Where the value is parsed (CSV column, API, etc.).
2. What internal field name the value is assigned.
3. Where that field is written to the database.
4. Which database column stores it.
5. Where the board/query loads that column.
6. Where the row dictionary is constructed.
7. What key name the row dictionary uses.
8. Where the UI reads that key.

Produce a step-by-step trace including:

* file name  
* function name  
* line numbers if possible  
* field name used at each step  

**Goal:** Confirm whether the value is **dropped, renamed, or overwritten**.

---

## Prompt 2 — Inspect Row Construction

Inspect how **[board/table]** rows are constructed.

Locate the function responsible for building the row dictionary (e.g. `_build_flat_row()`).

Identify:

* which DB fields are read  
* what keys are written into the row dictionary  
* whether **[FIELD_NAME]** is computed or derived  

Check for merge logic like:

```
field_a OR field_b
```

Document any fallback logic and how it affects the displayed value.

---

## Prompt 3 — Verify UI Column Mapping

Inspect the UI component rendering **[FIELD_LABEL]**.

Identify:

1. The column/cell label.
2. The row dictionary key the UI reads.
3. Any fallback logic used in rendering.

Confirm whether the UI expects:

```
row["field_name"]
```

or a different key.

Explain whether the UI mapping matches the query/service output.

---

## Prompt 4 — Verify Database Write Path

Verify where **[FIELD_NAME]** is written into the **database table**.

Locate all code paths that update the record during **[import/source]**.

Confirm:

* which source column populates **[db_column]**  
* whether fallback logic writes another field into that column  
* whether update logic can skip writing the field  

Examples of skip conditions:

* override protection  
* validation failures  
* missing turnover record  
* import ignore rules  

Document the exact functions responsible for writing the field.

---

## Prompt 5 — Validate End-to-End Consistency

Verify that **[FIELD_NAME]** is consistent across the pipeline.

Check the following layers:

* Database column  
* Repository query  
* Row construction  
* Enrichment logic  
* UI rendering  

If different names are used, identify where aliases occur.

Example mismatch:

```
report_ready_date → ready_date
```

Confirm whether the pipeline is internally consistent.

---

## Prompt 6 — Identify Fallback / Merge Logic Impact

Analyze whether the system merges related fields.

Look for logic like:

```
primary_field OR fallback_field
```

Explain the **operational meaning** of each field.

Example:

* Available Date = vacancy  
* Move-In Ready Date = readiness  

Determine whether fallback logic could produce **incorrect lifecycle interpretation**.

---

## Prompt 7 — Verify Record Selection

Confirm the UI is rendering the **correct record**.

Check whether multiple records exist for the same entity (e.g. multiple turnovers for a unit).

Ask the agent to verify:

* which record the UI query selects  
* how that record is chosen  
* whether another record contains the missing value  

Common pattern:

```
Turnover A → report_ready_date NULL
Turnover B → report_ready_date 02/28
```

If the board renders Turnover A, the field appears missing even though it exists.

---

## Prompt 8 — Database Reality Check

Before assuming a code bug, confirm the data actually exists.

Ask the agent to produce a diagnostic query like:

```sql
SELECT
  turnover_id,
  report_ready_date,
  available_date
FROM turnover
WHERE unit_id = ?
ORDER BY created_at;
```

**Goal:** Confirm whether the missing value exists in the database.

If the DB value is NULL, the issue is upstream (import logic).

---

## Universal Debugging Prompt

Use this when **any field disappears**.

```
A field is disappearing between [SOURCE] and [TARGET_UI].

Field: [FIELD_NAME]
Source: [report column / API field]
Target: [UI column]

Please:

1. Trace the full lifecycle:
   parsing → internal name → DB write → query → row construction → UI.

2. Inspect row construction for fallback logic like:
   "field_a OR field_b".

3. Verify the database write path and identify conditions where the field is not written.

4. Confirm the UI reads the same key produced by the row builder.

5. Check whether multiple records exist and verify the UI is rendering the correct one.

6. Provide a diagnostic SQL query to confirm the field value in the database.

Goal:
Identify where the value is dropped, renamed, or overwritten, and recommend the correct fix.
```

---

## Why This Playbook Works

It systematically eliminates the five common causes:

| Category        | Prompt |
| --------------- | ------ |
| Pipeline rename | 1      |
| Row builder bug | 2      |
| UI mismatch     | 3      |
| Importer issue  | 4      |
| Wrong record    | 7      |

Instead of guessing, it forces the agent to **prove the data flow**.

---

## What This Playbook Discovered in Your Case

**Root issue:**

```
report_ready_date OR available_date
```

This caused:

```
vacancy date → displayed as readiness
```

**Fix:** Board now displays:

```
report_ready_date only
```

**Result:** Ready Date correctly represents **Move-In Ready Date only**.

---

## Reference: Ready Date Fix (Detail)

For **Ready Date**, the issue was:

* **Symptom:** Board sometimes showed a date when the “real” Move-In Ready Date was missing.  
* **Cause:** Logic like `report_ready_date OR available_date` in board row construction and in the importer, so vacancy (Available Date) was shown as readiness.  
* **Fix:**  
  * Board: use only `report_ready_date` in `_build_flat_row()` (no fallback).  
  * Importer: write only the parsed “Move-In Ready Date” into `report_ready_date`; write “Available Date” only into `available_date` (no cross-fill).  

Result: Ready Date = Move-In Ready only; when it’s missing, the column is blank.
