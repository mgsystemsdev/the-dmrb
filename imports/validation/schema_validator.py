from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd


@dataclass(frozen=True)
class ValidationDiagnostic:
    row_index: Optional[int]
    error_type: str
    error_message: str
    column: Optional[str] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_index": self.row_index,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "column": self.column,
            "suggestion": self.suggestion,
        }


class ImportValidationError(Exception):
    def __init__(
        self,
        *,
        report_type: str,
        message: str,
        diagnostics: Optional[list[ValidationDiagnostic]] = None,
    ) -> None:
        super().__init__(message)
        self.report_type = report_type
        self.message = message
        self.diagnostics = diagnostics or []

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_type": "IMPORT_VALIDATION_FAILED",
            "report_type": self.report_type,
            "message": self.message,
            "errors": [d.to_dict() for d in self.diagnostics],
        }


@dataclass(frozen=True)
class SchemaRules:
    required_columns: tuple[str, ...]
    required_fields: tuple[str, ...]
    date_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]


SCHEMA_RULES: dict[str, SchemaRules] = {
    "MOVE_OUTS": SchemaRules(
        required_columns=("Unit", "Move-Out Date"),
        required_fields=("Unit", "Move-Out Date"),
        date_columns=("Move-Out Date",),
        numeric_columns=(),
    ),
    "PENDING_MOVE_INS": SchemaRules(
        required_columns=("Unit", "Move In Date"),
        required_fields=("Unit", "Move In Date"),
        date_columns=("Move In Date",),
        numeric_columns=(),
    ),
    "AVAILABLE_UNITS": SchemaRules(
        required_columns=("Unit", "Status", "Available Date", "Move-In Ready Date"),
        required_fields=("Unit",),
        date_columns=("Available Date", "Move-In Ready Date"),
        numeric_columns=(),
    ),
    "PENDING_FAS": SchemaRules(
        required_columns=("Unit", "MO / Cancel Date"),
        required_fields=("Unit",),
        date_columns=("MO / Cancel Date",),
        numeric_columns=(),
    ),
    "DMRB": SchemaRules(
        required_columns=("Unit", "Ready_Date", "Move_out", "Move_in", "Status"),
        required_fields=("Unit",),
        date_columns=("Ready_Date", "Move_out", "Move_in"),
        numeric_columns=(),
    ),
}


CSV_SKIPROWS: dict[str, int] = {
    "MOVE_OUTS": 6,
    "PENDING_MOVE_INS": 5,
    "AVAILABLE_UNITS": 5,
    "PENDING_FAS": 4,
}

REQUIRED_SHEET_BY_REPORT: dict[str, str] = {
    "DMRB": "DMRB ",
}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() == ""


def _read_for_validation(report_type: str, file_path: str) -> pd.DataFrame:
    if report_type == "DMRB":
        df = pd.read_excel(file_path, sheet_name=REQUIRED_SHEET_BY_REPORT["DMRB"])
        df.columns = df.columns.map(str).str.strip()
        return df

    if report_type == "PENDING_FAS":
        try:
            df = pd.read_csv(file_path, skiprows=CSV_SKIPROWS["PENDING_FAS"])
        except pd.errors.EmptyDataError:
            df = pd.read_csv(file_path)
        if df.empty or len(df.columns) == 0:
            df = pd.read_csv(file_path)
    else:
        df = pd.read_csv(file_path, skiprows=CSV_SKIPROWS.get(report_type, 0))

    df.columns = df.columns.map(str).str.strip()
    if report_type == "PENDING_FAS":
        df = df.rename(columns={"Unit Number": "Unit"})
    return df


def validate_import_schema(report_type: str, file_path: str) -> None:
    rules = SCHEMA_RULES.get(report_type)
    if rules is None:
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

    df = _read_for_validation(report_type, file_path)
    if df.empty:
        raise ImportValidationError(
            report_type=report_type,
            message=f"{report_type} import file has no data rows after header parsing.",
            diagnostics=[
                ValidationDiagnostic(
                    row_index=None,
                    error_type="EMPTY_DATASET",
                    error_message="Import file contains no data rows.",
                    suggestion="Verify the report export includes data rows.",
                )
            ],
        )

    diagnostics: list[ValidationDiagnostic] = []

    col_names = [str(c).strip() for c in df.columns]
    seen: set[str] = set()
    dupes: set[str] = set()
    for col in col_names:
        if col in seen:
            dupes.add(col)
        seen.add(col)
    if dupes:
        for col in sorted(dupes):
            diagnostics.append(
                ValidationDiagnostic(
                    row_index=None,
                    column=col,
                    error_type="DUPLICATE_COLUMN",
                    error_message=f"Duplicate column name detected: {col}",
                    suggestion="Ensure each column name appears only once in the header row.",
                )
            )

    for col in rules.required_columns:
        if col not in df.columns:
            diagnostics.append(
                ValidationDiagnostic(
                    row_index=None,
                    column=col,
                    error_type="MISSING_REQUIRED_COLUMN",
                    error_message=f"Missing required column: {col}",
                    suggestion="Confirm the report template has the expected header names.",
                )
            )

    if diagnostics:
        raise ImportValidationError(
            report_type=report_type,
            message=f"{report_type} import failed schema validation.",
            diagnostics=diagnostics,
        )

    for idx, row in df.iterrows():
        row_number = int(idx) + 1
        for col in rules.required_fields:
            if _is_blank(row.get(col)):
                diagnostics.append(
                    ValidationDiagnostic(
                        row_index=row_number,
                        column=col,
                        error_type="MISSING_REQUIRED_FIELD",
                        error_message=f"Row {row_number}: required field '{col}' is missing.",
                        suggestion=f"Populate '{col}' for row {row_number}.",
                    )
                )
        for col in rules.date_columns:
            value = row.get(col)
            if _is_blank(value):
                continue
            dt = pd.to_datetime(value, errors="coerce")
            if pd.isna(dt):
                diagnostics.append(
                    ValidationDiagnostic(
                        row_index=row_number,
                        column=col,
                        error_type="INVALID_DATE_FORMAT",
                        error_message=f"Row {row_number}: invalid date value in '{col}': {value!r}",
                        suggestion="Use a valid date (for example YYYY-MM-DD).",
                    )
                )
        for col in rules.numeric_columns:
            value = row.get(col)
            if _is_blank(value):
                continue
            try:
                float(value)
            except (TypeError, ValueError):
                diagnostics.append(
                    ValidationDiagnostic(
                        row_index=row_number,
                        column=col,
                        error_type="INVALID_NUMERIC_VALUE",
                        error_message=f"Row {row_number}: invalid numeric value in '{col}': {value!r}",
                        suggestion="Provide a valid numeric value.",
                    )
                )

    if diagnostics:
        raise ImportValidationError(
            report_type=report_type,
            message=f"{report_type} import failed data validation.",
            diagnostics=diagnostics,
        )
