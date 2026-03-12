import os
from datetime import date

from db import repository
from services import import_service
from services.imports.available_units import _parse_available_units
from tests.helpers.db_bootstrap import bootstrap_runtime_db


def _fresh_db():
    return bootstrap_runtime_db()


def test_available_units_vacant_rows_create_open_turnovers():
    """
    Invariant: for AVAILABLE_UNITS rows where
      - status is Vacant ready or Vacant not ready, and
      - available_date <= today
    the unit must have an open turnover after import.
    """
    conn, db_path = _fresh_db()
    try:
        # Seed property
        conn.execute("INSERT OR IGNORE INTO property (property_id, name) VALUES (1, 'Test Property')")
        conn.commit()

        # Use the real Available Units report from RAWW
        repo_root = os.path.dirname(os.path.dirname(__file__))
        file_path = os.path.join(repo_root, "RAWW", "Available Units.csv")

        # As-of date from the report header: 03/10/2026
        today = date(2026, 3, 10)

        # Run the actual import pipeline
        import_service.import_report_file(
            conn=conn,
            report_type=import_service.AVAILABLE_UNITS,
            file_path=file_path,
            property_id=1,
            today=today,
        )
        conn.commit()

        # Re-parse the same file using the production parser to know which rows qualify.
        parsed_rows = _parse_available_units(file_path)

        for row in parsed_rows:
            raw_status = row.get("status")
            status_norm = None
            if isinstance(raw_status, str):
                status_norm = raw_status.strip().lower() or None

            available_date = row.get("available_date")

            if status_norm not in ("vacant ready", "vacant not ready"):
                continue
            if available_date is None or available_date > today:
                continue

            unit_norm = row["unit_norm"]
            unit_row = repository.get_unit_by_norm(conn, property_id=1, unit_code_norm=unit_norm)
            assert unit_row is not None, f"Expected unit for vacant row {unit_norm}"

            unit_id = unit_row["unit_id"]
            open_turnover = repository.get_open_turnover_by_unit(conn, unit_id)
            assert (
                open_turnover is not None
            ), f"Expected open turnover for vacant unit {unit_norm} with available_date <= today"

            # Optional stronger check: move_out_date should equal Available Date.
            assert (
                open_turnover["move_out_date"][:10] == available_date.isoformat()
            ), f"Expected move_out_date == Available Date for vacant unit {unit_norm}"
    finally:
        conn.close()
