#!/usr/bin/env python3
"""
Query unit and turnover rows for a given list of unit codes (unit_code_norm).

Uses Postgres by default (DATABASE_URL / app config). SQLite is emergency-only.

Usage:
  PYTHONPATH=. python scripts/query_units_turnovers.py
  PYTHONPATH=. python scripts/query_units_turnovers.py --sqlite path/to/emergency.db
"""
import os
import sys

# Unit codes from the user list (format: phase-building-unit or property-phase-unit)
UNIT_CODES = [
    "5-12-0307",
    "5-18-0238",
    "8-01-3001",
    "8-01-2001",
    "5-18-0202",
    "7-10-0303",
    "8-01-3013",
    "5-11-0106",
    "7-11-0315",
    "5-01-0221",
    "7-04-0303",
    "7-02-0302",
    "7-09-0111",
    "7-11-0318",
    "8-01-3096",
]


def main():
    db_path = None
    use_sqlite = "--sqlite" in sys.argv
    if use_sqlite:
        i = sys.argv.index("--sqlite")
        if i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]
        if not db_path or not os.path.isfile(db_path):
            print("Usage: python scripts/query_units_turnovers.py [--sqlite PATH]", file=sys.stderr)
            print("Default: Postgres (DATABASE_URL). Use --sqlite only for emergency/offline.", file=sys.stderr)
            sys.exit(1)
        os.environ["TEST_MODE"] = "true"

    from db.connection import get_connection

    conn = get_connection(db_path=db_path) if db_path else get_connection()
    if conn is None:
        print("Could not get database connection.", file=sys.stderr)
        sys.exit(1)

    def row_dict(r):
        if r is None:
            return None
        return dict(r) if hasattr(r, "keys") else r

    # Resolve units: unit_code_norm is unique per (property_id, unit_code_norm)
    placeholders = ",".join("?" * len(UNIT_CODES))
    cursor = conn.execute(
        f"""SELECT u.unit_id, u.property_id, u.unit_code_raw, u.unit_code_norm,
                   u.phase_code, u.building_code, u.unit_number
            FROM unit u
            WHERE u.unit_code_norm IN ({placeholders})
            ORDER BY u.unit_code_norm""",
        UNIT_CODES,
    )
    units = [row_dict(r) for r in cursor.fetchall()]

    if not units:
        print("No units found for the given unit codes.")
        print("Tried:", UNIT_CODES)
        return

    unit_ids = [u["unit_id"] for u in units]
    unit_by_id = {u["unit_id"]: u for u in units}

    # All turnovers for these units (open and closed)
    placeholders = ",".join("?" * len(unit_ids))
    cursor = conn.execute(
        f"""SELECT t.turnover_id, t.unit_id, t.move_out_date, t.move_in_date,
                   t.report_ready_date, t.available_date, t.manual_ready_status,
                   t.availability_status, t.closed_at, t.canceled_at, t.created_at
            FROM turnover t
            WHERE t.unit_id IN ({placeholders})
            ORDER BY t.unit_id, t.created_at""",
        unit_ids,
    )
    turnovers = [row_dict(r) for r in cursor.fetchall()]

    # Print table: Unit | Status | Available Date | Move-In Ready Date (from turnover)
    print("Unit (norm)\tStatus\tAvailable Date\treport_ready_date\tmove_out_date\tmove_in_date\tclosed_at\tturnover_id")
    print("-" * 120)

    for u in units:
        uid = u["unit_id"]
        norm = u.get("unit_code_norm") or ""
        tovs = [t for t in turnovers if t["unit_id"] == uid]
        if not tovs:
            print(f"{norm}\t(no turnover)\t\t\t\t")
            continue
        for t in tovs:
            status = (t.get("manual_ready_status") or t.get("availability_status") or "").strip() or "—"
            avail = (t.get("available_date") or "")[:10] if t.get("available_date") else ""
            ready = (t.get("report_ready_date") or "")[:10] if t.get("report_ready_date") else ""
            move_out = (t.get("move_out_date") or "")[:10] if t.get("move_out_date") else ""
            move_in = (t.get("move_in_date") or "")[:10] if t.get("move_in_date") else ""
            closed = (t.get("closed_at") or "")[:10] if t.get("closed_at") else ""
            tid = t.get("turnover_id", "")
            print(f"{norm}\t{status}\t{avail}\t{ready}\t{move_out}\t{move_in}\t{closed}\t{tid}")

    print()
    print(f"Units found: {len(units)}. Turnovers total: {len(turnovers)}.")


if __name__ == "__main__":
    main()
