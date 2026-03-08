# Canonical Unit Identity

Single source of truth for unit code normalization, parsing (phase/building/unit), and identity key composition. Used by import, manual entry, and (future) property master import.

## Module

`domain.unit_identity`

- **normalize_unit_code(raw: str) -> str**  
  Strip, remove optional `"UNIT "` prefix (case-insensitive), uppercase, collapse whitespace.

- **parse_unit_parts(unit_code_norm: str) -> tuple[str, str, str]**  
  Returns `(phase_code, building_code, unit_number)`. Segment separator: `"-"`.  
  - 3+ segments: phase=parts[0], building=parts[1], unit=parts[2]  
  - 2 segments: phase=parts[0], building="", unit=parts[1]  
  - 1 segment: phase="", building="", unit=parts[0]  
  Raises **ValueError** if `unit_number` is empty after strip.

- **compose_identity_key(phase_code, building_code, unit_number) -> str**  
  - If `phase_code` non-empty: `f"{phase_code}-{building_code}-{unit_number}".strip("-")`  
  - Else: `unit_number`  
  Raises **ValueError** if `unit_number` is empty.

## Examples

| raw              | normalize_unit_code | parse_unit_parts   | compose_identity_key |
|------------------|---------------------|--------------------|----------------------|
| `  UNIT 5-1-101` | `5-1-101`           | `("5","1","101")`  | `5-1-101`            |
| `5-1-101`        | `5-1-101`           | `("5","1","101")`  | `5-1-101`            |
| `5-101`          | `5-101`             | `("5","","101")`   | `5--101`             |
| `101`            | `101`               | `("","","101")`    | `101`                |
| `7-2-201`        | `7-2-201`           | `("7","2","201")`  | `7-2-201`            |

## Rejection cases

- **parse_unit_parts**
  - `"5-1-"` → ValueError (unit_number empty)
  - `""` → ValueError (no segments / empty unit_number)
  - `"  "` → ValueError after strip

- **compose_identity_key**
  - `("5","1","")` → ValueError (unit_number required)

## DB enforcement (migration 004)

- **unit** table has: `phase_code`, `building_code`, `unit_number`, `unit_identity_key` (all NOT NULL after backfill).
- **UNIQUE(property_id, unit_identity_key)** — duplicate keys fail at insert/update.
- Backfill computes key from existing `unit_code_norm`; duplicates cause migration to fail with conflicting rows printed.

## Idempotency

Same logical unit string (after normalization) always yields the same identity key. Variants like `"  UNIT  5-1-101  "` and `"5-1-101"` normalize to `"5-1-101"` and compose to `"5-1-101"`.

## How to run migrations

Migrations run **automatically** when the app starts with backend enabled: `ensure_database_ready(db_path)` is called before any DB read (see `app_prototype_v2.py`). It applies `db/schema.sql` if the `turnover` table is missing, then runs `db/migrations/001_...` through `004_...` in order and updates `schema_version`. No manual CLI step is required for normal runs.

To apply migrations against a specific DB file without starting the app (e.g. script or one-off):

```python
from db.connection import ensure_database_ready
ensure_database_ready("/path/to/cockpit.db")
```
