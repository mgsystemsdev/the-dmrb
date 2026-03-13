#!/usr/bin/env python3
"""
Print units with their turnover.report_ready_date (the Ready Date column source).

Uses Postgres by default. For SQLite: python scripts/show_ready_date_column.py --sqlite path/to.db

Usage (from repo root):
  PYTHONPATH=. python scripts/show_ready_date_column.py       # first 10
  PYTHONPATH=. python scripts/show_ready_date_column.py --all # all open turnovers
  PYTHONPATH=. python scripts/show_ready_date_column.py --limit 20
"""
import os
import sys

def main():
    limit = 10
    if "--all" in sys.argv:
        limit = 999999
    elif "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        if i + 1 < len(sys.argv):
            try:
                limit = max(1, int(sys.argv[i + 1]))
            except ValueError:
                pass
    use_sqlite = "--sqlite" in sys.argv
    db_path = None
    if use_sqlite:
        idx = sys.argv.index("--sqlite")
        if idx + 1 < len(sys.argv):
            db_path = sys.argv[idx + 1]
        if db_path:
            os.environ["TEST_MODE"] = "true"

    from db.connection import get_connection

    conn = get_connection(db_path=db_path) if db_path else get_connection()
    if not conn:
        print("Could not get database connection.", file=sys.stderr)
        sys.exit(1)

    def row_dict(r):
        if r is None:
            return None
        return dict(r) if hasattr(r, "keys") else r

    # Unit display: prefer phase_code-building_code-unit_number, else unit_code_norm
    sql = """
        SELECT
            u.unit_code_norm,
            u.phase_code,
            u.building_code,
            u.unit_number,
            t.turnover_id,
            t.report_ready_date,
            t.closed_at,
            t.canceled_at
        FROM turnover t
        JOIN unit u ON u.unit_id = t.unit_id
        WHERE t.closed_at IS NULL AND t.canceled_at IS NULL
        ORDER BY t.updated_at DESC
        LIMIT ?
    """
    cursor = conn.execute(sql, (limit,))
    rows = [row_dict(r) for r in cursor.fetchall()]

    if not rows:
        print("No open turnovers found.")
        return

    print("Unit (display)\treport_ready_date\tturnover_id")
    print("-" * 60)
    for r in rows:
        pc = (r.get("phase_code") or "").strip()
        bc = (r.get("building_code") or "").strip()
        un = (r.get("unit_number") or "").strip()
        if pc or bc or un:
            unit_display = f"{pc}-{bc}-{un}".strip("-")
        else:
            unit_display = (r.get("unit_code_norm") or "").strip()
        rr = r.get("report_ready_date")
        rr_show = (rr[:10] if rr else "") or "(NULL)"
        tid = r.get("turnover_id", "")
        print(f"{unit_display}\t{rr_show}\t{tid}")

    print()
    print(f"Shown: {len(rows)} open turnover(s). Column: turnover.report_ready_date (board Ready Date).")


if __name__ == "__main__":
    main()
