#!/usr/bin/env python3
"""
Turnover Timeline Debug View: for a unit, print lifecycle dates and last-import context.

Shows per turnover:
  move_out_date, available_date, report_ready_date, move_in_date
  last_import_* (from DB)
  import batch (report_type, imported_at, source_file_name) when available

Use this to see why the board shows blank Ready Date: wrong turnover, importer
never wrote report_ready_date, or fallback removal exposed real NULLs.

Usage (from repo root):
  python scripts/turnover_timeline_debug.py --unit 5-7-101
  python scripts/turnover_timeline_debug.py --db path/to/data.db --unit 42
"""
from __future__ import annotations

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _resolve_unit(conn, unit_arg):
    """Resolve --unit (unit_id int or unit_code string) to (unit_id, unit_display)."""
    def row_to_dict(r):
        if r is None:
            return None
        return dict(r) if hasattr(r, "keys") else r
    if unit_arg is None:
        return None, None
    try:
        uid = int(unit_arg)
        row = conn.execute(
            "SELECT unit_id, unit_code_raw, phase_code, building_code, unit_number FROM unit WHERE unit_id = ?",
            (uid,),
        ).fetchone()
        if row:
            r = row_to_dict(row)
            display = (
                r.get("unit_code_raw")
                or f"{r.get('phase_code') or ''}-{r.get('building_code') or ''}-{r.get('unit_number') or ''}".strip("-")
                or str(uid)
            )
            return r["unit_id"], display
        return None, None
    except (ValueError, TypeError):
        pass
    s = str(unit_arg).strip()
    if not s:
        return None, None
    row = conn.execute(
        "SELECT unit_id, unit_code_raw FROM unit WHERE unit_code_raw = ? OR unit_code_norm = ? LIMIT 1",
        (s, s),
    ).fetchone()
    if row:
        r = row_to_dict(row)
        return r["unit_id"], r.get("unit_code_raw") or s
    return None, None


def _main():
    parser = argparse.ArgumentParser(description="Turnover timeline debug view for a unit")
    parser.add_argument("--db", type=str, default=None, help="SQLite DB path (optional)")
    parser.add_argument("--unit", type=str, required=True, help="Unit: unit_id or unit_code (e.g. 5-7-101)")
    args = parser.parse_args()

    if args.db:
        os.environ["TEST_MODE"] = "true"
        if not os.path.isfile(args.db):
            print(f"DB not found: {args.db}")
            sys.exit(1)

    from db.connection import get_connection

    conn = get_connection(db_path=args.db) if args.db else get_connection()
    if conn is None:
        print("Could not get database connection.")
        sys.exit(1)

    def row_to_dict(r):
        if r is None:
            return None
        return dict(r) if hasattr(r, "keys") else r

    try:
        unit_id, unit_display = _resolve_unit(conn, args.unit)
        if unit_id is None:
            print(f"Unit not found: {args.unit}")
            sys.exit(1)

        # Turnovers for this unit + batch info when last_seen_moveout_batch_id is set
        cursor = conn.execute(
            """SELECT
                   t.turnover_id,
                   t.move_out_date,
                   t.available_date,
                   t.report_ready_date,
                   t.move_in_date,
                   t.closed_at,
                   t.canceled_at,
                   t.ready_manual_override_at,
                   t.last_import_move_out_date,
                   t.last_import_ready_date,
                   t.last_import_move_in_date,
                   t.last_import_status,
                   t.last_seen_moveout_batch_id,
                   t.created_at,
                   b.report_type AS last_batch_report_type,
                   b.imported_at AS last_batch_imported_at,
                   b.source_file_name AS last_batch_source_file
               FROM turnover t
               LEFT JOIN import_batch b ON t.last_seen_moveout_batch_id = b.batch_id
               WHERE t.unit_id = ?
               ORDER BY t.created_at""",
            (unit_id,),
        )
        rows = cursor.fetchall()
        turnovers = [row_to_dict(r) for r in rows] if rows else []

        print(f"Turnover timeline — unit: {unit_display} (unit_id={unit_id})")
        print("=" * 100)

        if not turnovers:
            print("No turnovers for this unit.")
            return

        date_cols = ["move_out_date", "available_date", "report_ready_date", "move_in_date"]
        for t in turnovers:
            tid = t.get("turnover_id")
            open_marker = " (OPEN)" if t.get("closed_at") is None and t.get("canceled_at") is None else ""
            print(f"\n  turnover_id = {tid}{open_marker}")
            print("  " + "-" * 60)
            for c in date_cols:
                val = t.get(c)
                print(f"    {c}: {val if val is not None else 'NULL'}")
            print("    closed_at / canceled_at: {} / {}".format(
                t.get("closed_at") or "NULL",
                t.get("canceled_at") or "NULL",
            ))
            if t.get("ready_manual_override_at"):
                print("    ready_manual_override_at: {}".format(t.get("ready_manual_override_at")))
            print("    last_import_*: move_out={}  ready={}  move_in={}  status={}".format(
                t.get("last_import_move_out_date") or "NULL",
                t.get("last_import_ready_date") or "NULL",
                t.get("last_import_move_in_date") or "NULL",
                t.get("last_import_status") or "NULL",
            ))
            batch_id = t.get("last_seen_moveout_batch_id")
            if batch_id is not None:
                print("    import batch: report_type={}  imported_at={}  file={}".format(
                    t.get("last_batch_report_type") or "?",
                    t.get("last_batch_imported_at") or "?",
                    (t.get("last_batch_source_file") or "?")[:50],
                ))
            else:
                print("    import batch: (none)")
            print("    created_at: {}".format(t.get("created_at") or "NULL"))

        print("\n" + "=" * 100)
        print("Interpretation:")
        open_t = [x for x in turnovers if x.get("closed_at") is None and x.get("canceled_at") is None]
        if len(open_t) > 1:
            print("  • Multiple open turnovers for this unit; board shows one (check list_open_turnovers).")
        elif len(open_t) == 1:
            ot = open_t[0]
            rr = ot.get("report_ready_date")
            av = ot.get("available_date")
            if rr is None and av is None:
                print("  • Open turnover has report_ready_date=NULL and available_date=NULL → board correctly shows blank Ready Date.")
            elif rr is not None:
                print("  • Open turnover has report_ready_date set → board should show it (if still blank, check cache/UI key).")
            else:
                print("  • Open turnover has report_ready_date=NULL but available_date set → after fallback removal, board correctly shows blank Ready Date.")
        else:
            print("  • No open turnover for this unit; board will not list it.")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
