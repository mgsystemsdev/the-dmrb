"""
Validation harness: compare domain.enrichment output to mock_data_v2.get_dmrb_board_rows.
Asserts row count, order stability, and key computed fields (dv, phase, nvm, operational_state, has_violation).
No DB required; uses mock data only.
"""
import sys
from datetime import date
from copy import deepcopy

# Project root on path
sys.path.insert(0, __file__.rsplit("/", 2)[0] or ".")

from domain import enrichment
from ui import mock_data_v2


# Fixed today for deterministic comparison
FIXED_TODAY = date(2025, 2, 20)


def test_enrichment_matches_mock_board_rows():
    """Build board rows using mock_data_v2.build_flat_row + domain.enrichment.enrich_row; compare to mock_data_v2.get_dmrb_board_rows."""
    turnovers = deepcopy(mock_data_v2.MOCK_TURNOVERS_V2)
    units = deepcopy(mock_data_v2.MOCK_UNITS_V2)
    tasks = deepcopy(mock_data_v2.MOCK_TASKS_V2)
    notes = deepcopy(mock_data_v2.MOCK_NOTES_V2)

    # Reference: full mock pipeline (mock enrich_row includes attention_badge)
    reference = mock_data_v2.get_dmrb_board_rows(
        turnovers, units, tasks, notes,
        search_unit=None,
        filter_phase=None,
        filter_status=None,
        filter_nvm=None,
        filter_assignee=None,
        filter_qc=None,
        today=FIXED_TODAY,
    )

    # Computed: mock build_flat_row + domain enrichment only (no attention_badge)
    unit_by_id = {u["unit_id"]: u for u in units}
    tasks_by_tid = {}
    for t in tasks:
        tid = t.get("turnover_id")
        if tid is not None:
            tasks_by_tid.setdefault(tid, []).append(t)
    notes_by_tid = {}
    for n in notes:
        tid = n.get("turnover_id")
        if tid is not None:
            notes_by_tid.setdefault(tid, []).append(n)

    computed = []
    for t in turnovers:
        u = unit_by_id.get(t["unit_id"])
        if not u:
            continue
        tasks_for_t = tasks_by_tid.get(t["turnover_id"], [])
        notes_for_t = notes_by_tid.get(t["turnover_id"], [])
        flat = mock_data_v2.build_flat_row(t, u, tasks_for_t, notes_for_t)
        row = enrichment.enrich_row(flat, FIXED_TODAY)
        computed.append(row)

    def sort_key(r):
        move_in = enrichment._parse_date(r.get("move_in_date"))
        dv = r.get("dv") or 0
        return (0 if move_in is None else 1, move_in or date.max, -dv)

    computed.sort(key=sort_key)

    assert len(computed) == len(reference), (
        f"Row count mismatch: computed={len(computed)}, reference={len(reference)}"
    )

    key_fields = ("dv", "dtbr", "phase", "nvm", "task_state", "operational_state", "has_violation", "is_qc_done")
    for i, (c, r) in enumerate(zip(computed, reference)):
        assert c["turnover_id"] == r["turnover_id"], f"Row {i}: turnover_id mismatch"
        for k in key_fields:
            assert c.get(k) == r.get(k), (
                f"Row {i} turnover_id={c['turnover_id']} field {k}: computed={c.get(k)!r}, reference={r.get(k)!r}"
            )
        # wd_summary and assign_display (mock may use same symbols)
        assert c.get("wd_summary") == r.get("wd_summary"), f"Row {i}: wd_summary mismatch"
        assert c.get("assign_display") == r.get("assign_display"), f"Row {i}: assign_display mismatch"


def test_enrichment_no_exceptions():
    """Run enrichment on mock flat rows; confirm no exceptions."""
    turnovers = deepcopy(mock_data_v2.MOCK_TURNOVERS_V2)
    units = deepcopy(mock_data_v2.MOCK_UNITS_V2)
    tasks = deepcopy(mock_data_v2.MOCK_TASKS_V2)
    notes = deepcopy(mock_data_v2.MOCK_NOTES_V2)
    unit_by_id = {u["unit_id"]: u for u in units}
    tasks_by_tid = {}
    for t in tasks:
        tid = t.get("turnover_id")
        if tid is not None:
            tasks_by_tid.setdefault(tid, []).append(t)
    notes_by_tid = {}
    for n in notes:
        tid = n.get("turnover_id")
        if tid is not None:
            notes_by_tid.setdefault(tid, []).append(n)

    for t in turnovers:
        u = unit_by_id.get(t["unit_id"])
        if not u:
            continue
        flat = mock_data_v2.build_flat_row(
            t, u,
            tasks_by_tid.get(t["turnover_id"], []),
            notes_by_tid.get(t["turnover_id"], []),
        )
        _ = enrichment.enrich_row(flat, FIXED_TODAY)
