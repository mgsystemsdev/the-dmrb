from datetime import datetime, date
from typing import Optional

from db import repository
from domain.sla_engine import evaluate_sla_state, SLA_THRESHOLD_DAYS


_UNSET = object()


def reconcile_sla_for_turnover(
    *,
    conn,
    turnover_id: int,
    move_out_date: Optional[date],
    manual_ready_confirmed_at: Optional[str],
    today: date,
    actor: str = "manager",
    source: str = "system",
    correlation_id: Optional[str] = None,
    previous_effective_move_out_date=_UNSET,
) -> None:
    now_iso = datetime.utcnow().isoformat()
    result = "NOOP"

    if move_out_date is None:
        repository.upsert_risk(
            conn,
            {
                "turnover_id": turnover_id,
                "risk_type": "DATA_INTEGRITY",
                "severity": "WARNING",
                "triggered_at": now_iso,
                "auto_resolve": 0,
            },
        )
        repository.insert_audit_log(
            conn,
            {
                "entity_type": "turnover",
                "entity_id": turnover_id,
                "field_name": "risk_flag",
                "old_value": None,
                "new_value": "DATA_INTEGRITY",
                "changed_at": now_iso,
                "actor": actor,
                "source": "system",
                "correlation_id": correlation_id,
            },
        )
        result = "FAILED"
    else:
        open_event = repository.get_open_sla_event(conn, turnover_id)
        open_breach_exists = open_event is not None

        anchor_changed = (
            previous_effective_move_out_date is not _UNSET
            and previous_effective_move_out_date != move_out_date
        )
        if anchor_changed:
            repository.insert_audit_log(
                conn,
                {
                    "entity_type": "turnover",
                    "entity_id": turnover_id,
                    "field_name": "effective_move_out_date",
                    "old_value": previous_effective_move_out_date.isoformat()
                    if previous_effective_move_out_date is not None
                    else None,
                    "new_value": move_out_date.isoformat(),
                    "changed_at": now_iso,
                    "actor": actor,
                    "source": source,
                    "correlation_id": correlation_id,
                },
            )

        state = evaluate_sla_state(
            move_out_date=move_out_date,
            manual_ready_confirmed_at=manual_ready_confirmed_at,
            today=today,
            open_breach_exists=open_breach_exists,
        )

        # Stop dominance: once manual_ready_confirmed_at is set, do not allow re-open.
        handled_stop = False
        if manual_ready_confirmed_at is not None:
            state["should_open_breach"] = False
            state["breach_active"] = False

        evaluated_threshold_days = SLA_THRESHOLD_DAYS

        if anchor_changed and open_event is not None and bool(state["breach_active"]):
            repository.update_sla_event_current_anchor(
                conn,
                open_event["sla_event_id"],
                move_out_date.isoformat(),
            )

        # Hard close on stop dominance even if evaluation did not request close.
        if manual_ready_confirmed_at is not None and open_event is not None:
            repository.close_sla_event(conn, open_event["sla_event_id"], now_iso)
            repository.insert_audit_log(
                conn,
                {
                    "entity_type": "turnover",
                    "entity_id": turnover_id,
                    "field_name": "sla_breach",
                    "old_value": "OPENED",
                    "new_value": "RESOLVED",
                    "changed_at": now_iso,
                    "actor": actor,
                    "source": source,
                    "correlation_id": correlation_id,
                },
            )
            result = "RESOLVED"
            handled_stop = True

        if not handled_stop:
            if state["should_open_breach"]:
                repository.insert_sla_event(
                    conn,
                    {
                        "turnover_id": turnover_id,
                        "breach_started_at": now_iso,
                        "breach_resolved_at": None,
                        "opened_anchor_date": move_out_date.isoformat(),
                        "current_anchor_date": move_out_date.isoformat(),
                        "evaluated_threshold_days": evaluated_threshold_days,
                    },
                )
                repository.insert_audit_log(
                    conn,
                    {
                        "entity_type": "turnover",
                        "entity_id": turnover_id,
                        "field_name": "sla_breach",
                        "old_value": None,
                        "new_value": "OPENED",
                        "changed_at": now_iso,
                        "actor": actor,
                        "source": source,
                        "correlation_id": correlation_id,
                    },
                )
                result = "OPENED"

            if state["should_close_breach"] and open_event is not None:
                repository.close_sla_event(conn, open_event["sla_event_id"], now_iso)
                repository.insert_audit_log(
                    conn,
                    {
                        "entity_type": "turnover",
                        "entity_id": turnover_id,
                        "field_name": "sla_breach",
                        "old_value": "OPENED",
                        "new_value": "RESOLVED",
                        "changed_at": now_iso,
                        "actor": actor,
                        "source": source,
                        "correlation_id": correlation_id,
                    },
                )
                result = "RESOLVED"
            elif state["should_close_breach"] and open_event is None:
                # Persistence drift: evaluation expects a close but no open event exists. Flag integrity; never crash.
                repository.upsert_risk(
                    conn,
                    {
                        "turnover_id": turnover_id,
                        "risk_type": "DATA_INTEGRITY",
                        "severity": "WARNING",
                        "triggered_at": now_iso,
                        "auto_resolve": 0,
                    },
                )
                repository.insert_audit_log(
                    conn,
                    {
                        "entity_type": "turnover",
                        "entity_id": turnover_id,
                        "field_name": "risk_flag",
                        "old_value": None,
                        "new_value": "DATA_INTEGRITY",
                        "changed_at": now_iso,
                        "actor": actor,
                        "source": "system",
                        "correlation_id": correlation_id,
                    },
                )
                import logging

                logging.getLogger(__name__).warning(
                    "SLA close requested but no open_event found: turnover_id=%s eval_breach_active=%s",
                    turnover_id,
                    bool(state["breach_active"]),
                )
                result = "FAILED"

        # Convergence check: if persisted open/closed != evaluation, flag data integrity but do not crash.
        try:
            persisted_open = repository.get_open_sla_event(conn, turnover_id) is not None
            if bool(state["breach_active"]) != persisted_open:
                repository.upsert_risk(
                    conn,
                    {
                        "turnover_id": turnover_id,
                        "risk_type": "DATA_INTEGRITY",
                        "severity": "WARNING",
                        "triggered_at": now_iso,
                        "auto_resolve": 0,
                    },
                )
                repository.insert_audit_log(
                    conn,
                    {
                        "entity_type": "turnover",
                        "entity_id": turnover_id,
                        "field_name": "risk_flag",
                        "old_value": None,
                        "new_value": "DATA_INTEGRITY",
                        "changed_at": now_iso,
                        "actor": actor,
                        "source": "system",
                        "correlation_id": correlation_id,
                    },
                )
                import logging

                logging.getLogger(__name__).warning(
                    "SLA state mismatch after reconcile: turnover_id=%s eval_breach_active=%s persisted_open=%s",
                    turnover_id,
                    bool(state["breach_active"]),
                    persisted_open,
                )
                result = "FAILED"
        except Exception:
            # Hard safety: never crash production paths for integrity checks.
            pass

    # Summary audit row for this reconcile call.
    repository.insert_audit_log(
        conn,
        {
            "entity_type": "turnover",
            "entity_id": turnover_id,
            "field_name": "sla_reconcile",
            "old_value": None,
            "new_value": result,
            "changed_at": now_iso,
            "actor": actor,
            "source": source,
            "correlation_id": correlation_id,
        },
    )
