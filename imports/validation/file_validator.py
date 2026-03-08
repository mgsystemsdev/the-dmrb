from __future__ import annotations

import os

import pandas as pd

from imports.validation.schema_validator import ImportValidationError, ValidationDiagnostic


SUPPORTED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "MOVE_OUTS": (".csv",),
    "PENDING_MOVE_INS": (".csv",),
    "AVAILABLE_UNITS": (".csv",),
    "PENDING_FAS": (".csv",),
    "DMRB": (".xlsx", ".xls"),
}

REQUIRED_SHEET_BY_REPORT: dict[str, str] = {
    "DMRB": "DMRB ",
}


def validate_import_file(report_type: str, file_path: str) -> None:
    if report_type not in SUPPORTED_EXTENSIONS:
        raise ImportValidationError(
            report_type=report_type,
            message=f"Unknown report_type: {report_type}",
            diagnostics=[
                ValidationDiagnostic(
                    row_index=None,
                    error_type="UNKNOWN_REPORT_TYPE",
                    error_message=f"Unsupported report type: {report_type}",
                    suggestion="Select a supported report type and try again.",
                )
            ],
        )

    ext = os.path.splitext(file_path)[1].lower()
    supported = SUPPORTED_EXTENSIONS[report_type]
    if ext not in supported:
        raise ImportValidationError(
            report_type=report_type,
            message=f"Unsupported file type for {report_type}: {ext or '<none>'}",
            diagnostics=[
                ValidationDiagnostic(
                    row_index=None,
                    error_type="UNSUPPORTED_FILE_TYPE",
                    error_message=f"{report_type} expects file type(s): {', '.join(supported)}.",
                    suggestion="Upload the correct report file format.",
                )
            ],
        )

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        raise ImportValidationError(
            report_type=report_type,
            message=f"{report_type} import file is empty.",
            diagnostics=[
                ValidationDiagnostic(
                    row_index=None,
                    error_type="EMPTY_FILE",
                    error_message="Import file is empty.",
                    suggestion="Export the report again and verify it contains data.",
                )
            ],
        )

    required_sheet = REQUIRED_SHEET_BY_REPORT.get(report_type)
    if required_sheet:
        try:
            xls = pd.ExcelFile(file_path)
        except Exception as exc:
            raise ImportValidationError(
                report_type=report_type,
                message=f"Could not read Excel file for {report_type}.",
                diagnostics=[
                    ValidationDiagnostic(
                        row_index=None,
                        error_type="UNREADABLE_FILE",
                        error_message=str(exc),
                        suggestion="Ensure the file is a valid Excel workbook.",
                    )
                ],
            ) from exc
        if required_sheet not in xls.sheet_names:
            raise ImportValidationError(
                report_type=report_type,
                message=f"Missing required sheet '{required_sheet}' for {report_type}.",
                diagnostics=[
                    ValidationDiagnostic(
                        row_index=None,
                        error_type="MISSING_REQUIRED_SHEET",
                        error_message=f"Required sheet '{required_sheet}' was not found.",
                        suggestion="Verify the workbook contains the expected sheet name.",
                    )
                ],
            )
