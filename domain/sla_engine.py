from datetime import date, timedelta
from typing import Optional


SLA_THRESHOLD_DAYS = 10


def evaluate_sla_state(
    *,
    move_out_date: date,
    manual_ready_confirmed_at: Optional[str],
    today: date,
    open_breach_exists: bool,
) -> dict:
    if move_out_date > today:
        breach_active = False
    elif manual_ready_confirmed_at is not None:
        breach_active = False
    else:
        days_since_move_out = today - move_out_date
        breach_active = days_since_move_out > timedelta(days=SLA_THRESHOLD_DAYS)

    should_open_breach = breach_active and not open_breach_exists
    should_close_breach = not breach_active and open_breach_exists

    return {
        "breach_active": breach_active,
        "should_open_breach": should_open_breach,
        "should_close_breach": should_close_breach,
    }
