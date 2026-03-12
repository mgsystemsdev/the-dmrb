import json
import os
from datetime import date

from db import repository
from services import import_service
from services.imports.available_units import _parse_available_units
from tests.helpers.db_bootstrap import bootstrap_runtime_db


def _fresh_db():
    return bootstrap_runtime_db()


def test_vacant_row_creates_turnover_and_import_row_metadata():
    """
    Invariant: for an AVAILABLE_UNITS row where
      - status is Vacant ready, and
      - Available Date <= today, and
      - no existing turnover,
    the importer must create a turnover using move_out_date = Available Date
    and record the import_row as OK with conflict_reason CREATED_TURNOVER_FROM_AVAILABILITY.
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

        # Re-parse the same file to find at least one qualifying Vacant row.
        parsed_rows = _parse_available_units(file_path)

        target_row = None
        for row in parsed_rows:
            raw_status = row.get("status")
            status_norm = None
            if isinstance(raw_status, str):
                status_norm = raw_status.strip().lower() or None

            available_date = row.get("available_date")

            if status_norm != "vacant ready":
                continue
            if available_date is None or available_date > today:
                continue

            target_row = row
            break

        assert target_row is not None, "Expected at least one Vacant ready row with Available Date <= today"

        unit_norm = target_row["unit_norm"]
        available_date = target_row["available_date"]

        # Verify turnover was created and move_out_date matches Available Date.
        unit_row = repository.get_unit_by_norm(conn, property_id=1, unit_code_norm=unit_norm)
        assert unit_row is not None

        unit_id = unit_row["unit_id"]
        open_turnover = repository.get_open_turnover_by_unit(conn, unit_id)
        assert open_turnover is not None, "Expected open turnover for vacant unit"
        assert (
            open_turnover["move_out_date"][:10] == available_date.isoformat()
        ), "Expected move_out_date == Available Date for vacant unit"

        # Verify import_row metadata matches invariant expectations.
        rows = import_service.get_latest_available_units_rows(conn)
        matching_import_rows = []
        for r in rows:
            raw = json.loads(r["raw_json"])
            if str(raw.get("Unit")).strip() == target_row["unit_raw"]:
                matching_import_rows.append(r)

        assert matching_import_rows, "Expected at least one import_row for target vacant unit"

        # The latest row for this unit should reflect successful turnover creation.
        latest_row = matching_import_rows[-1]
        assert latest_row["validation_status"] == "OK"
        assert latest_row["conflict_reason"] == "CREATED_TURNOVER_FROM_AVAILABILITY"
        assert latest_row["move_out_date"][:10] == available_date.isoformat()
    finally:
        conn.close()

