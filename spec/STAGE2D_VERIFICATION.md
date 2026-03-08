# Stage 2D — Verification (run manually)

Run these after **one MOVE_OUTS import**, **one AVAILABLE_UNITS import**, and **one PENDING_FAS import**.

Use a single turnover that received all three (same unit: MOVE_OUTS to create, AVAILABLE_UNITS to set ready/available, PENDING_FAS to confirm).

---

## Option A: Verification script (recommended)

From repo root:

```bash
python3 the-dmrb/scripts/verify_stage2_dual_write.py <db_path> <turnover_id>
```

Example:

```bash
python3 the-dmrb/scripts/verify_stage2_dual_write.py the-dmrb/data/cockpit.db 1
```

The script prints all four checks and lifecycle (DV / phase / nvm).

---

## Option B: Run SQL yourself

Replace `<test_id>` with your turnover_id.

### 1️⃣ MOVE_OUTS check

```sql
SELECT
  move_out_date,
  scheduled_move_out_date
FROM turnover
WHERE turnover_id = <test_id>;
```

**Expected:** Both equal after first import. If the report changes the date later: `scheduled_move_out_date` changes; `move_out_date` stays unchanged (match branch does not update move_out_date).

---

### 2️⃣ AVAILABLE_UNITS check

```sql
SELECT
  report_ready_date,
  available_date,
  availability_status
FROM turnover
WHERE turnover_id = <test_id>;
```

**Expected:** `report_ready_date` = `available_date`; `availability_status` populated (AVAILABLE_UNITS only). If the report changes, both update (latest report wins).

---

### 3️⃣ FAS check

```sql
SELECT
  confirmed_move_out_date,
  legal_confirmation_source,
  legal_confirmed_at
FROM turnover
WHERE turnover_id = <test_id>;
```

**Expected:** `confirmed_move_out_date` = FAS mo/cancel date; `legal_confirmation_source` = `'fas'`; `legal_confirmed_at` set. Run FAS again → no change (guard: only write when `legal_confirmation_source` IS NULL; manual wins if already set).

---

### 4️⃣ Lifecycle unchanged

Check DV / phase before and after Stage 2C. They must be identical (lifecycle uses `move_out_date` only; no read from new columns).

- Use the app board view, or
- Run the verification script (it prints DV, phase, nvm via the same enrichment as the app).

If anything changed → a read path is using the wrong column (should not happen after Stage 2C).

---

## If all 4 checks pass

You have earned **Stage 3**.

Stage 3 will introduce an **“effective move-out date” derivation layer** without breaking lifecycle/SLA.
