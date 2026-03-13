#!/usr/bin/env python3
"""
Diagnostic: Inspect turnover table for a unit that shows a blank Ready Date on the board.

Returns for that unit (all turnovers, sorted by created_at):
  unit_id, turnover_id, move_out_date, report_ready_date, available_date,
  ready_manual_override_at, closed_at, canceled_at

Then compares which turnover_id the board is rendering and explains:
  - board rendering a different turnover
  - ready date skipped due to override
  - ready date stored as NULL
  - value exists but board cache is stale

Usage (from repo root):
  # SQLite (e.g. test or local DB)
  TEST_MODE=true python scripts/diagnose_blank_ready_date.py
  # Or with explicit path (SQLite)
  python scripts/diagnose_blank_ready_date.py --db path/to/data.db

  # Postgres (uses DATABASE_URL / app config)
  python scripts/diagnose_blank_ready_date.py

  # Inspect a specific unit (unit_id or unit_code e.g. 5-7-101)
  python scripts/diagnose_blank_ready_date.py --unit 5-7-101
  python scripts/diagnose_blank_ready_date.py --db path/to/data.db --unit 42
"""
from __future__ import annotations

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Optional: force TEST_MODE for SQLite when --db is passed
def _resolve_unit(conn, unit_arg):
    """Resolve --unit (unit_id int or unit_code_raw / unit_code_norm string) to unit_id. Returns (unit_id, unit_display) or (None, None)."""
    def row_to_dict(r):
        if r is None:
            return None
        return dict(r) if hasattr(r, "keys") else r
    if unit_arg is None:
        return None, None
    # Integer → unit_id
    try:
        uid = int(unit_arg)
        row = conn.execute("SELECT unit_id, unit_code_raw, phase_code, building_code, unit_number FROM unit WHERE unit_id = ?", (uid,)).fetchone()
        if row:
            r = row_to_dict(row)
            display = r.get("unit_code_raw") or f"{r.get('phase_code') or ''}-{r.get('building_code') or ''}-{r.get('unit_number') or ''}".strip("-") or str(uid)
            return r["unit_id"], display
        return None, None
    except (ValueError, TypeError):
        pass
    # String → unit_code_raw or unit_code_norm
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
    parser = argparse.ArgumentParser(description="Diagnose blank Ready Date on board")
    parser.add_argument("--db", type=str, default=None, help="SQLite DB path (optional; else use app config)")
    parser.add_argument("--unit", type=str, default=None, help="Unit to inspect: unit_id or unit_code (e.g. 5-7-101). If omitted, picks a unit with blank Ready Date or first open.")
    args = parser.parse_args()

    if args.db:
        os.environ["TEST_MODE"] = "true"
        if not os.path.isfile(args.db):
            print(f"DB not found: {args.db}")
            sys.exit(1)

    from db.connection import get_connection
    from db import repository

    conn = get_connection(db_path=args.db) if args.db else get_connection()
    if conn is None:
        print("Could not get database connection.")
        sys.exit(1)

    try:
        def row_to_dict(r):
            if r is None:
                return None
            return dict(r) if hasattr(r, "keys") else r

        # Optional: resolve --unit to unit_id
        unit_id, unit_display = _resolve_unit(conn, args.unit)
        if args.unit and (unit_id is None):
            print(f"Unit not found: {args.unit}")
            sys.exit(1)

        # 1) Open turnovers (same criteria as board)
        open_turnovers = repository.list_open_turnovers(conn, property_ids=None, phase_ids=None)
        open_list = [row_to_dict(r) for r in open_turnovers]

        if not open_list:
            print("No open turnovers found. Board would be empty.")
            return

        if unit_id is not None:
            # Diagnostic for specific unit: find its open turnover (if any)
            chosen = next((t for t in open_list if t.get("unit_id") == unit_id), None)
            if chosen is None:
                print(f"No open turnover for unit {unit_display or unit_id}. Listing all turnovers for this unit below.\n")
                board_turnover_id = None
            else:
                board_turnover_id = chosen["turnover_id"]
                print(f"Unit: {unit_display or unit_id} (unit_id={unit_id}). Open turnover_id = {board_turnover_id}\n")
        else:
            # 2) Find a unit that shows blank Ready Date, or first open
            blank_ready = [
                t for t in open_list
                if t.get("report_ready_date") is None and t.get("available_date") is None
            ]
            if not blank_ready:
                chosen = open_list[0]
                unit_id = chosen["unit_id"]
                board_turnover_id = chosen["turnover_id"]
                print("No open turnover with both report_ready_date and available_date NULL.")
                print("Showing first open unit for reference (Ready Date may be non-blank).\n")
            else:
                chosen = blank_ready[0]
                unit_id = chosen["unit_id"]
                board_turnover_id = chosen["turnover_id"]
                print("Found open turnover with blank Ready Date (report_ready_date and available_date NULL).\n")

        # 3) All turnovers for this unit, sorted by created_at
        cursor = conn.execute(
            """SELECT unit_id, turnover_id, move_out_date, report_ready_date, available_date,
                      ready_manual_override_at, closed_at, canceled_at, created_at
               FROM turnover
               WHERE unit_id = ?
               ORDER BY created_at""",
            (unit_id,),
        )
        rows = cursor.fetchall()
        all_turnovers = [row_to_dict(r) for r in rows] if rows else []

        # 4) Print requested columns (excluding created_at from output per spec, but we used it for sort)
        print("Turnovers for this unit (sorted by created_at):")
        print("-" * 100)
        cols = ["unit_id", "turnover_id", "move_out_date", "report_ready_date", "available_date",
                "ready_manual_override_at", "closed_at", "canceled_at"]
        header = "  ".join(f"{c:24}" for c in cols)
        print(header)
        print("-" * 100)
        for t in all_turnovers:
            line = "  ".join(str(t.get(c) if t.get(c) is not None else "NULL")[:24].ljust(24) for c in cols)
            print(line)
        print("-" * 100)

        # 5) Which turnover the board renders
        if board_turnover_id is not None:
            print(f"\nBoard renders: turnover_id = {board_turnover_id} (the single open turnover for this unit).")
        else:
            print("\nBoard does not show this unit (no open turnover).")

        # 6) Explanation (only when we have an open turnover for this unit)
        if chosen is not None:
            board_row = chosen
            rr = board_row.get("report_ready_date")
            av = board_row.get("available_date")
            override_at = board_row.get("ready_manual_override_at")

            print("\nExplanation:")
            if board_turnover_id not in [t["turnover_id"] for t in all_turnovers]:
                print("  • The board is rendering a different turnover (open turnover_id not in list above — data inconsistency).")
            elif override_at is not None and (rr is None and av is None):
                print("  • Ready date was skipped due to override: ready_manual_override_at is set; report_ready_date and available_date are NULL (import did not overwrite manual override, and no value was set).")
            elif rr is None and av is None:
                print("  • The ready date was stored as NULL: both report_ready_date and available_date are NULL for the open turnover, so the board correctly shows a blank Ready Date.")
            elif rr is not None or av is not None:
                print("  • Value exists in DB (report_ready_date or available_date). If the board still shows blank, the board cache may be stale (e.g. cached_get_dmrb_board_rows TTL 5s — refresh the board or wait a few seconds).")
            else:
                print("  • See above: board shows the open turnover for this unit; check NULL vs override vs cache.")
        else:
            print("\n(No open turnover for this unit; no board explanation.)")
    finally:
        conn.close()


if __name__ == "__main__":
    _main()
