#!/usr/bin/env python3
"""
Read-only analysis of Units.csv for Unit Master Bootstrap Import.
No DB writes, no schema changes. Uses domain.unit_identity for normalization.
Run from repo root: python3 the-dmrb/scripts/analyze_units_csv.py
"""
import csv
import os
import sys
from collections import Counter, defaultdict

# the-dmrb on path so domain, db are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.unit_identity import normalize_unit_code, parse_unit_parts, compose_identity_key

CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "refecerence_context", "Reports", "data", "Units.csv"
)


def main():
    import io
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    lines = content.splitlines()
    # Line 0-3: title/metadata, line 4 (index 4): column header, line 5+: data
    data_block = "\n".join(lines[4:])
    reader = csv.DictReader(io.StringIO(data_block))
    rows = list(reader)

    # Column names verbatim
    if rows:
        colnames = list(rows[0].keys())
    else:
        colnames = []
    print("=== 1) CSV STRUCTURE ===")
    print("Exact column names (verbatim):", colnames)
    dup_cols = [c for c in colnames if colnames.count(c) > 1]
    if dup_cols:
        print("Duplicate column names:", set(dup_cols))
    else:
        print("Duplicate column names: None")

    n = len(rows)
    print("Total data rows:", n)

    # Infer types from first 100 rows
    unit_vals = [r.get("Unit", r.get("unit", "")) for r in rows[:100]]
    fp_vals = [r.get("Floor Plan", r.get("floor plan", "")) for r in rows[:100]]
    sq_vals = [r.get("Gross Sq. Ft.", r.get("gross sq ft", "")) for r in rows[:100]]
    print("Inferred types: Unit=str, Floor Plan=str, Gross Sq. Ft.=numeric (int/float)")

    # Null counts for unit, floor plan, gross sq ft
    def blank(s):
        return s is None or (isinstance(s, str) and s.strip() == "")

    unit_key = next((k for k in colnames if k.strip().lower() == "unit"), "Unit")
    fp_key = next((k for k in colnames if "floor" in k.lower() and "plan" in k.lower()), "Floor Plan")
    gsf_key = next((k for k in colnames if "gross" in k.lower() and "sq" in k.lower()), "Gross Sq. Ft.")

    null_unit = sum(1 for r in rows if blank(r.get(unit_key)))
    null_fp = sum(1 for r in rows if blank(r.get(fp_key)))
    null_gsf = sum(1 for r in rows if blank(r.get(gsf_key)))
    print(f"Null/blank counts: unit={null_unit}, floor plan={null_fp}, gross sq ft={null_gsf}")

    # Duplicate rows by raw unit
    raw_units = [str(r.get(unit_key, "")).strip() for r in rows]
    from collections import Counter
    raw_counts = Counter(raw_units)
    dup_raw = {u: c for u, c in raw_counts.items() if c > 1}
    print("Duplicate rows by raw unit column:", len(dup_raw), "unit values with count>1")
    if dup_raw:
        for u, c in list(dup_raw.items())[:5]:
            print(f"  {u!r}: {c}")

    # Normalized identity_key
    norm_to_key = {}
    key_to_rows = defaultdict(list)
    reject = []
    for i, r in enumerate(rows):
        raw = str(r.get(unit_key, "")).strip()
        try:
            norm = normalize_unit_code(raw)
            pc, bc, un = parse_unit_parts(norm)
            key = compose_identity_key(pc, bc, un)
            norm_to_key[raw] = (norm, key)
            key_to_rows[key].append((i, raw, norm))
        except (ValueError, Exception) as e:
            reject.append((i, raw, str(e)))
    dup_key = {k: v for k, v in key_to_rows.items() if len(v) > 1}
    print("Duplicate rows by normalized unit_identity_key:", len(dup_key), "keys with >1 row")
    if dup_key:
        for k, v in list(dup_key.items())[:5]:
            print(f"  {k!r}: {len(v)} rows")

    print("\n=== 2) IDENTITY NORMALIZATION (10 samples) ===")
    reject_by_idx = {x[0]: x[2] for x in reject}
    for idx in range(0, min(10, len(rows))):
        r = rows[idx]
        raw = str(r.get(unit_key, "")).strip()
        if idx in reject_by_idx:
            print(f"  raw={raw!r} -> REJECTED: {reject_by_idx[idx]}")
        elif raw in norm_to_key:
            norm, key = norm_to_key[raw]
            pc, bc, un = parse_unit_parts(norm)
            print(f"  raw={raw!r} -> norm={norm!r} -> parts=({pc!r},{bc!r},{un!r}) -> key={key!r}")
        else:
            print(f"  raw={raw!r} -> (not in norm_to_key)")

    print("\nRows rejected by canonical parser:", len(reject))
    for i, raw, err in reject[:15]:
        print(f"  row {i}: {raw!r} -> {err}")

    print("\nUnits that collapse to same identity_key (first 10 groups):")
    for k, v in list(dup_key.items())[:10]:
        raws = [x[1] for x in v]
        print(f"  key={k!r}: raws={raws}")

    print("\n=== 3) DATA QUALITY ===")
    # Inconsistent formats
    leading_space = sum(1 for r in rows if str(r.get(unit_key, "")).startswith(" ") or str(r.get(unit_key, "")).endswith(" "))
    mixed_case = sum(1 for r in rows if str(r.get(unit_key, "")) != normalize_unit_code(str(r.get(unit_key, ""))))
    print("Unit: leading/trailing space:", leading_space, "| different after normalize (mixed/space):", mixed_case)
    gsf_numeric = 0
    gsf_non_numeric = []
    for r in rows:
        v = r.get(gsf_key, "").strip().replace(",", "")
        try:
            float(v)
            gsf_numeric += 1
        except (ValueError, TypeError):
            if v and v not in ("", "N/A"):
                gsf_non_numeric.append((r.get(unit_key), v))
    print("Gross Sq. Ft.: numeric count:", gsf_numeric, "| non-numeric sample:", gsf_non_numeric[:5])
    gsf_nums = []
    for r in rows:
        v = r.get(gsf_key, "").strip().replace(",", "")
        try:
            gsf_nums.append(float(v))
        except (ValueError, TypeError):
            pass
    if gsf_nums:
        print("Gross Sq. Ft. range: min={}, max={}".format(min(gsf_nums), max(gsf_nums)))
    fp_vals_all = [str(r.get(fp_key, "")).strip() for r in rows if r.get(fp_key)]
    fp_unique = len(set(fp_vals_all))
    fp_counts = Counter(fp_vals_all)
    print("Floor Plan: unique values:", fp_unique, "| total rows with value:", len(fp_vals_all))
    print("Floor Plan sample (top 5 by count):", fp_counts.most_common(5))
    # Conflicting attributes for same normalized unit
    by_key = defaultdict(list)
    for r in rows:
        raw = str(r.get(unit_key, "")).strip()
        if raw in norm_to_key:
            _, key = norm_to_key[raw]
            by_key[key].append({"unit": raw, "floor_plan": r.get(fp_key), "gross_sq_ft": r.get(gsf_key)})
    conflicts_fp = {k: v for k, v in by_key.items() if len(set(x["floor_plan"] for x in v)) > 1}
    conflicts_gsf = {k: v for k, v in by_key.items() if len(set(str(x["gross_sq_ft"]) for x in v)) > 1}
    print("Same identity_key, different floor plan:", len(conflicts_fp))
    print("Same identity_key, different gross sq ft:", len(conflicts_gsf))
    if conflicts_gsf:
        k = list(conflicts_gsf.keys())[0]
        print("  Example:", k, [x["gross_sq_ft"] for x in conflicts_gsf[k][:5]])

    print("\n=== 4) STRUCTURAL RISK (DB comparison) ===")
    db_path = os.environ.get("COCKPIT_DB_PATH") or os.path.join(os.path.dirname(__file__), "..", "data", "cockpit.db")
    csv_identity_keys = set()
    for r in rows:
        raw = str(r.get(unit_key, "")).strip()
        if raw in norm_to_key:
            _, key = norm_to_key[raw]
            csv_identity_keys.add(key)
    if os.path.isfile(db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT unit_identity_key, property_id FROM unit")
            db_units = {(r["unit_identity_key"], r["property_id"]) for r in cur.fetchall()}
            # Assume single property_id=1 for CSV for comparison
            db_keys_p1 = {k for k, p in db_units if p == 1}
            in_csv_not_db = csv_identity_keys - db_keys_p1
            in_db_not_csv = db_keys_p1 - csv_identity_keys
            print("Units in CSV but not in DB (property_id=1):", len(in_csv_not_db))
            if in_csv_not_db:
                print("  Sample:", list(in_csv_not_db)[:10])
            print("Units in DB but not in CSV (property_id=1):", len(in_db_not_csv))
            if in_db_not_csv:
                print("  Sample:", list(in_db_not_csv)[:10])
            print("Identity collisions (duplicate key in DB): check UNIQUE(property_id, unit_identity_key) - N/A for read-only")
        except sqlite3.OperationalError as e:
            print("DB open but unit table missing or not migrated:", e)
            print("Units in CSV (by identity_key count):", len(csv_identity_keys))
        finally:
            conn.close()
    else:
        print("DB file not found at", db_path, "- skipping CSV vs DB comparison")
        print("Units in CSV (by identity_key count):", len(csv_identity_keys))

    print("\n=== 5) RECOMMENDATIONS ===")
    print("Strict mode: fail import if any unit row fails parse or if duplicate identity_key with conflicting attributes.")
    print("Repair mode: create missing unit when not in DB (upsert by identity_key).")
    print("Schema: unit table already has phase_code, building_code, unit_number, unit_identity_key; add floor_plan, gross_sq_ft if not present for bootstrap.")
    print("Validation: require unit non-blank; gross_sq_ft numeric; optional floor_plan.")


if __name__ == "__main__":
    main()
