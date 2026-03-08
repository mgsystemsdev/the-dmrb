"""
Canonical unit identity: normalization, parsing, and identity key composition.
Importable from import_service, manual entry, and future property master import.
No DB or UI imports; pure functions only.
"""
import re


def normalize_unit_code(raw: str) -> str:
    """
    Normalize a raw unit code string for storage and identity.
    Rules: strip, remove optional "UNIT " prefix (case-insensitive), uppercase, collapse whitespace.
    """
    if raw is None:
        return ""
    s = raw.strip()
    if s.upper().startswith("UNIT "):
        s = s[5:].lstrip()
    s = s.upper()
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_unit_parts(unit_code_norm: str) -> tuple[str, str, str]:
    """
    Parse normalized unit code into (phase_code, building_code, unit_number).
    Segment separator: "-". Strips each segment.
    Rules:
      - 3+ segments: phase=parts[0], building=parts[1], unit=parts[2]
      - 2 segments: phase=parts[0], building="", unit=parts[1]
      - 1 segment: phase="", building="", unit=parts[0]
    Raises ValueError if unit_number is empty after strip.
    """
    if unit_code_norm is None:
        unit_code_norm = ""
    parts = [p.strip() for p in unit_code_norm.strip().split("-") if p is not None]
    if not parts:
        raise ValueError("unit_code_norm produced no segments")
    unit_number = ""
    phase_code = ""
    building_code = ""
    if len(parts) >= 3:
        phase_code = parts[0]
        building_code = parts[1]
        unit_number = parts[2]
    elif len(parts) == 2:
        phase_code = parts[0]
        building_code = ""
        unit_number = parts[1]
    else:
        phase_code = ""
        building_code = ""
        unit_number = parts[0]
    if not unit_number:
        raise ValueError("unit_number is empty after strip")
    return (phase_code, building_code, unit_number)


def compose_identity_key(phase_code: str, building_code: str, unit_number: str) -> str:
    """
    Compose a deterministic identity key from parsed parts.
    If phase_code non-empty: "{phase_code}-{building_code}-{unit_number}".strip("-")
    Else: unit_number only.
    """
    if not unit_number:
        raise ValueError("unit_number is required")
    if phase_code:
        key = f"{phase_code}-{building_code}-{unit_number}".strip("-")
        return key if key else unit_number
    return unit_number
