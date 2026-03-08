# Unit Master Bootstrap Import — CSV Analysis Report

**Source file:** `refecerence_context/Reports/data/Units.csv`  
**Context:** One-time structural bootstrap (or rare full restore). Only columns of interest: **unit**, **floor plan**, **gross sq ft**.  
**Analysis:** Read-only; no DB state changes, no schema changes, no migrations.

---

## 1) Data profile summary

### CSV structure

| Item | Value |
|------|--------|
| **Exact column names (verbatim)** | `Unit`, `Floor Plan`, `Gross Sq. Ft.`, `Status`, `Account`, `Market Rent`, `Effective Rent`, `Base Rent`, `Amenities Amount` |
| **Duplicate column names** | None |
| **Header / data start** | Lines 1–4: title/metadata; line 5: header; line 6+: data rows |
| **Total data rows** | **2,224** |
| **Inferred data types** | Unit: string. Floor Plan: string. Gross Sq. Ft.: numeric (integer in file). |

### Null counts (columns of interest)

| Column | Null/blank count |
|--------|-------------------|
| Unit | 0 |
| Floor Plan | 0 |
| Gross Sq. Ft. | 0 |

### Duplicate rows

| Key | Count |
|-----|--------|
| Duplicate rows by **raw** `Unit` value | 0 (each raw unit value appears once) |
| Duplicate rows by **normalized** `unit_identity_key` (canonical) | 0 (no collapse) |

---

## 2) Identity normalization summary

**Canonical rules used:** `domain.unit_identity.normalize_unit_code`, `parse_unit_parts`, `compose_identity_key`.

### Sample rows (first 10)

| raw (Unit column) | unit_code_norm | parse_unit_parts (phase, building, unit) | unit_identity_key |
|-------------------|----------------|------------------------------------------|-------------------|
| `4-25-0206` | `4-25-0206` | `('4','25','0206')` | `4-25-0206` |
| `4-25-0207` | `4-25-0207` | `('4','25','0207')` | `4-25-0207` |
| `4-25-0208` | `4-25-0208` | `('4','25','0208')` | `4-25-0208` |
| … | … | … | … |

(All 10 parse as 3 segments: phase = first, building = second, unit = third.)

### Rows rejected by canonical parser

**0** rows. Every row has a non-empty unit segment after strip; no row raises `ValueError` from `parse_unit_parts` or `compose_identity_key`.

### Units collapsing to the same identity_key

**None.** No two distinct raw unit strings normalize to the same `unit_identity_key`; 2,224 unique keys.

### Format note

- **Leading space:** Every value in the `Unit` column in the file has a leading space (e.g. `"  4-25-0206"`). Analysis strips before normalize; normalization removes spaces, so behavior is consistent and no rejections.

---

## 3) Data quality assessment

### Inconsistent formats

- **Unit:** 2,224/2,224 rows have leading (and sometimes trailing) space in the raw column. After strip + canonical normalize, all are valid; no mixed-case or embedded-space issues that would break parsing.
- **Floor Plan:** Values like ` 4a2 - 4a2`, `7B1 - 7B1`, `8A3.2 - 8A3.2` (leading space, mixed case, hyphen pattern). 133 unique values; no normalization applied for this analysis.
- **Gross Sq. Ft.:** No inconsistencies observed.

### Gross Sq. Ft.

- **Numeric:** All 2,224 values parse as numeric (int/float).
- **Range:** min = **529**, max = **3,788** (sq ft).
- **Non-numeric:** 0.

### Floor Plan

- **Standardization:** Values follow patterns like `4a2 - 4a2`, `7A7.1 - 7A7.1`, `8B6 - 8B6` (code, space, hyphen, space, same code). Appears standardized by pattern but with many variants (133 distinct values).
- **Top 5 by frequency:** `5a5 - 5a5` (151), `4a2 - 4a2` (116), `5a4 - 5a4` (108), `4a3 - 4a3` (90), `5b1 - 5b1` (75).

### Conflicting attributes for same normalized unit

- **Same identity_key, different Floor Plan:** 0.
- **Same identity_key, different Gross Sq. Ft.:** 0.

So each normalized unit has a single floor plan and a single gross sq ft in this file.

---

## 4) Structural risk report

### Units in CSV but not in DB

- **When DB is present and migrated:** Run comparison with `COCKPIT_DB_PATH` set (or default `data/cockpit.db`). Script reports: “Units in CSV but not in DB (property_id=1): &lt;count&gt;” and a sample.
- **When DB is missing or unit table not migrated:** Comparison was skipped. **2,224** distinct identity keys in CSV; if DB is empty or pre-migration, all 2,224 would be “in CSV not in DB” for that property.

### Units in DB but not in CSV

- Same as above: only meaningful when DB exists and has migrated `unit` table with `unit_identity_key`. Then the script reports “Units in DB but not in CSV” and a sample.

### Identity collisions

- **Within CSV:** No duplicate `unit_identity_key`; no collision.
- **Within DB:** Enforced by `UNIQUE(property_id, unit_identity_key)`; no read-only check run.

### Phase coverage

- CSV contains phases **4**, **7**, **8** (e.g. `4-25-...`, `7-09-...`, `8-01-...`). If managed phases are only 5, 7, 8, then phase 4 units are “outside managed phases” but are still valid for a full structural bootstrap.

---

## 5) Recommended import contract

### Strict mode (fail on missing unit)

- **Behavior:** Do **not** create units. For each CSV row, resolve unit by `(property_id, unit_identity_key)` (or by `unit_code_norm` if using legacy lookup). If no unit exists → **fail row or fail entire import** with a clear error (e.g. “Unit not found: &lt;identity_key&gt;”).
- **Use when:** You expect the DB to already contain all units (e.g. after a prior full bootstrap or manual load). Ensures no accidental creation of new units from the CSV.

### Repair mode (create missing unit)

- **Behavior:** For each CSV row, resolve unit by `(property_id, unit_identity_key)`. If not found → **create unit** with: `unit_code_raw` = raw Unit value, `unit_code_norm` = canonical normalize(Unit), `phase_code`/`building_code`/`unit_number`/`unit_identity_key` from `parse_unit_parts` + `compose_identity_key`; optional attributes from CSV: floor_plan, gross_sq_ft (if schema supports them).
- **Use when:** One-time bootstrap or full restore; DB may be empty or missing many units. Idempotent if same CSV is re-run and “upsert” updates only attributes (e.g. floor_plan, gross_sq_ft) when unit already exists.

### Required schema changes (if any)

- **Current unit table (post migration 004):** Has `phase_code`, `building_code`, `unit_number`, `unit_identity_key`. Does **not** have `floor_plan` or `gross_sq_ft`.
- **For Unit Master bootstrap:** Add columns (e.g. `floor_plan TEXT`, `gross_sq_ft REAL` or `INTEGER`) if you want to store Floor Plan and Gross Sq. Ft. from this CSV. No schema change is required for identity-only bootstrap (only unit creation/lookup by identity_key).

### Additional validation rules

1. **Unit (required):** Non-blank after strip; must parse via `parse_unit_parts` without raising (reject row and report if not).
2. **Gross Sq. Ft.:** If present, must be numeric; optional range check (e.g. 0 &lt; value &lt; 50_000) to catch obvious errors.
3. **Floor Plan:** Optional; store as-is or normalize (e.g. strip, consistent case) per product rules.
4. **Idempotency:** Use `(property_id, unit_identity_key)` as the unique key for upsert; update floor_plan / gross_sq_ft when row exists.
5. **Import kind:** Tag this import as **Unit Master Bootstrap** (e.g. `IMPORT_KIND=UNIT_MASTER` or `report_type=UNIT_MASTER`) so it does **not** touch turnover/task/operational tables and does not trigger operational import logic.

---

## How to re-run this analysis

From repo root (or `the-dmrb`):

```bash
# Optional: set DB path to include CSV vs DB comparison
export COCKPIT_DB_PATH=/path/to/cockpit.db
python3 the-dmrb/scripts/analyze_units_csv.py
```

Script is read-only: no DB writes, no schema changes, no migrations.
