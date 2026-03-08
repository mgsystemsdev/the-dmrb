#!/usr/bin/env python3
"""
Stage 2D verification: run after one MOVE_OUTS import, one AVAILABLE_UNITS import,
and one PENDING_FAS import. Checks dual-write columns and that lifecycle (DV/phase) is unchanged.

Usage (from repo root):
  python the-dmrb/scripts/verify_stage2_dual_write.py <db_path> <turnover_id>

Replace <turnover_id> with the actual integer ID (e.g. 1), not the literal text.

Example:
  python the-dmrb/scripts/verify_stage2_dual_write.py the-dmrb/data/cockpit.db 1

To get a turnover_id after importing: sqlite3 the-dmrb/data/cockpit.db "SELECT turnover_id FROM turnover ORDER BY turnover_id DESC LIMIT 1;"
"""
from __future__ import annotations

import os
import sys
from datetime import date

# the-dmrb on path so db, domain, services are importable
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_SCRIPT_DIR, ".."))

import sqlite3


def run_checks(db_path: str, turnover_id: int) -> None:
    if not os.path.isfile(db_path):
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT turnover_id FROM turnover WHERE turnover_id = ?",
            (turnover_id,),
        )
        if cur.fetchone() is None:
            print(f"Turnover id {turnover_id} not found.")
            sys.exit(1)

        print("=" * 60)
        print("1️⃣  MOVE_OUTS check")
        print("=" * 60)
        cur = conn.execute(
            """SELECT move_out_date, scheduled_move_out_date
               FROM turnover WHERE turnover_id = ?""",
            (turnover_id,),
        )
        row = cur.fetchone()
        if row:
            mo = row["move_out_date"]
            sched = row["scheduled_move_out_date"]
            print(f"  move_out_date           = {mo}")
            print(f"  scheduled_move_out_date = {sched}")
            if mo == sched:
                print("  Expected: both equal after first MOVE_OUTS import. OK.")
            else:
                print("  Note: if report changed date later, scheduled may differ; move_out_date must be unchanged.")
        print()

        print("=" * 60)
        print("2️⃣  AVAILABLE_UNITS check")
        print("=" * 60)
        cur = conn.execute(
            """SELECT report_ready_date, available_date, availability_status
               FROM turnover WHERE turnover_id = ?""",
            (turnover_id,),
        )
        row = cur.fetchone()
        if row:
            rr = row["report_ready_date"]
            av = row["available_date"]
            status = row["availability_status"]
            print(f"  report_ready_date   = {rr}")
            print(f"  available_date     = {av}")
            print(f"  availability_status = {status}")
            if rr == av:
                print("  Expected: report_ready_date == available_date. OK.")
            if status is not None and str(status).strip():
                print("  availability_status populated (AVAILABLE_UNITS). OK.")
        print()

        print("=" * 60)
        print("3️⃣  FAS check")
        print("=" * 60)
        cur = conn.execute(
            """SELECT confirmed_move_out_date, legal_confirmation_source, legal_confirmed_at
               FROM turnover WHERE turnover_id = ?""",
            (turnover_id,),
        )
        row = cur.fetchone()
        if row:
            conf_mo = row["confirmed_move_out_date"]
            src = row["legal_confirmation_source"]
            at = row["legal_confirmed_at"]
            print(f"  confirmed_move_out_date  = {conf_mo}")
            print(f"  legal_confirmation_source = {src}")
            print(f"  legal_confirmed_at        = {at}")
            if conf_mo and src == "fas" and at:
                print("  Expected: confirmed = FAS mo/cancel date, source = 'fas', legal_confirmed_at set. OK.")
            print("  Run FAS again → no change (manual wins or already set).")
        print()

        print("=" * 60)
        print("4️⃣  Lifecycle unchanged (DV / phase)")
        print("=" * 60)
        from db import repository
        from domain import enrichment
        from services.board_query_service import _build_flat_row

        t = conn.execute("SELECT * FROM turnover WHERE turnover_id = ?", (turnover_id,)).fetchone()
        if t is None:
            print("  Turnover not found.")
        else:
            t = dict(t)
            unit_id = t.get("unit_id")
            u = repository.get_unit_by_id(conn, unit_id)
            if u is None:
                u = {}
            else:
                u = dict(u)
            tasks = repository.get_tasks_by_turnover(conn, turnover_id)
            tasks = [dict(r) for r in tasks]
            notes = repository.get_notes_by_turnover(conn, turnover_id)
            notes = [dict(r) for r in notes]
            flat = _build_flat_row(t, u, tasks, notes)
            today = date.today()
            enriched = enrichment.enrich_row(flat, today)
            dv = enriched.get("dv")
            phase = enriched.get("phase")
            nvm = enriched.get("nvm")
            print(f"  DV    = {dv}")
            print(f"  phase = {phase}")
            print(f"  nvm   = {nvm}")
            print("  These must be identical before and after Stage 2C (lifecycle uses move_out_date only).")

    finally:
        conn.close()


def main():
    if len(sys.argv) != 3:
        print("Usage: python verify_stage2_dual_write.py <db_path> <turnover_id>")
        print("Example: python verify_stage2_dual_write.py the-dmrb/data/cockpit.db 1")
        print("(Replace <turnover_id> with the actual integer from the DB, e.g. 1)")
        sys.exit(1)
    db_path = sys.argv[1]
    try:
        turnover_id = int(sys.argv[2])
    except ValueError:
        print("turnover_id must be an integer (e.g. 1). You passed:", repr(sys.argv[2]))
        sys.exit(1)
    run_checks(db_path, turnover_id)


if __name__ == "__main__":
    main()
