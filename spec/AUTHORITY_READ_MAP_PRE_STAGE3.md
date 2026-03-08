# AUTHORITY READ MAP — PRE STAGE 3 (Read-only)

**Scan: entire repository. No edits, no refactors, no suggestions. Mapping only.**

---

## Table: Reads of move_out_date that influence lifecycle phase, DV, SLA, risk, or UI derivations

| File | Function | How move_out_date is used | If replaced with effective_move_out_date, what changes? |
|------|----------|---------------------------|----------------------------------------------------------|
| domain/lifecycle.py | derive_lifecycle_phase | Parameter; compared to today and move_in_date to decide NOTICE, NOTICE_SMI, VACANT, SMI, MOVE_IN_COMPLETE, STABILIZATION, CLOSED, CANCELED. | Phase boundaries would follow effective date; NOTICE vs VACANT vs SMI would shift to effective. |
| domain/enrichment.py | derive_phase | t.get("move_out_date") parsed and passed to derive_lifecycle_phase. | Same as lifecycle; phase would follow effective. |
| domain/enrichment.py | compute_facts | row.get("move_out_date") parsed; used for dv = business_days(move_out, today) and passed into derive_phase via row dict for phase/nvm. | DV would be business days since effective move-out; phase/nvm as above. |
| domain/sla_engine.py | evaluate_sla_state | Parameter; if move_out_date &lt;= today and no manual_ready_confirmed_at, days_since_move_out = today - move_out_date; breach if &gt; 10 days. | SLA breach start and “days since move-out” would key off effective date. |
| domain/risk_engine.py | evaluate_risks | Parameter move_out_date accepted; not used in current risk logic (only move_in_date, tasks, report_ready_date, etc. used). | No behavioral change unless future risk logic uses move_out_date; API would receive effective. |
| services/board_query_service.py | _build_flat_row | turnover.get("move_out_date") put into flat row dict; row is passed to enrichment.compute_facts and derive_phase. | Enrichment would see effective if row carries it (or row["move_out_date"] is set to effective); lifecycle/DV/UI would follow. |
| services/turnover_service.py | create_turnover_from_import | move_out_date is argument (from import); passed to reconcile_sla_for_turnover and reconcile_risks_for_turnover. | Would pass effective (e.g. same as move_out at creation) into SLA/risk. |
| services/turnover_service.py | set_manual_ready_status | row["move_out_date"] from _get_turnover; passed to reconcile_sla_for_turnover and reconcile_risks_for_turnover. | SLA and risk reconciliation would use effective. |
| services/turnover_service.py | confirm_manual_ready | row["move_out_date"] from _get_turnover; passed to reconcile_sla_for_turnover and reconcile_risks_for_turnover. | Same as above. |
| services/turnover_service.py | update_wd_panel | row["move_out_date"] from _get_turnover; passed to reconcile_risks_for_turnover. | Risk reconciliation would use effective. |
| services/turnover_service.py | update_turnover_dates | row["move_out_date"] read for current value and for mo_eff after update; mo_eff passed to reconcile_sla_for_turnover and reconcile_risks_for_turnover. | After manual date edit, reconciliation would use effective (e.g. updated value or effective rule). |
| services/turnover_service.py | reconcile_after_task_change | row["move_out_date"] from _get_turnover; passed to reconcile_risks_for_turnover. | Risk reconciliation would use effective. |
| services/turnover_service.py | reconcile_risks_only | row["move_out_date"] from _get_turnover; passed to reconcile_risks_for_turnover. | Same. |
| services/sla_service.py | reconcile_sla_for_turnover | Receives move_out_date from caller (turnover_service); passes to domain.sla_engine.evaluate_sla_state. | Would receive effective from turnover_service; breach logic would follow effective. |
| services/risk_service.py | reconcile_risks_for_turnover | Receives move_out_date from caller (turnover_service); passes to domain.risk_engine.evaluate_risks. | Would receive effective from turnover_service. |
| app.py | render_dmrb_board | row.get("move_out_date") formatted via _fmt_date for "Move-Out" column in board table. | Display would show effective (or second line) if row carries it. |
| app.py | render_detail | t.get("move_out_date") used as value for Move-Out date_input and for turnover_service_mod.update_turnover_dates(move_out_date=new_mo). | Detail would show/edit effective or move_out_date per product choice; update would write to chosen field. |

---

## Reads not in table (do not influence lifecycle/DV/SLA/risk/UI in app)

- **db/repository.py:** SELECT returns turnover rows including move_out_date; no interpretation. All app reads go through repository.
- **services/import_service.py:** open_turnover["move_out_date"] used for comparison (MOVE_OUTS match, PENDING_FAS mismatch) and for _write_import_row payload; does not feed lifecycle/DV/SLA/risk/UI.
- **scripts/verify_stage2_dual_write.py:** SELECT move_out_date for verification printout; not app runtime.
- **tests/** and **ui/mock_data*.py:** Test fixtures and mock data; not production flow.

---

## Confirmation 1: No service mutates move_out_date outside import or manual edit flows

**Confirmed.**

- **import_service.py:** Sets move_out_date only on **insert_turnover** (new turnover). On existing open turnover (match by unit), it updates only `last_seen_moveout_batch_id`, `missing_moveout_count`, `updated_at`, `scheduled_move_out_date` — it does **not** update move_out_date.
- **turnover_service.py:** Updates move_out_date only in **update_turnover_dates** when the caller passes a new move_out_date (manual edit from app detail page).
- **manual_availability_service.py:** Does not update turnover; it calls turnover_service.create_turnover_from_import with move_out_date from the form (manual add flow). Creation is not “mutation” of an existing row.
- **repository.py:** update_turnover_fields and insert_turnover are the only writers; callers are import_service, turnover_service, and (for insert) manual_availability via turnover_service. No other service mutates move_out_date.

---

## Confirmation 2: No direct SQL reads bypass repository

**Confirmed for application path.**

- All turnover reads in the app and services go through **db/repository.py**: list_open_turnovers, get_turnover_by_id, get_open_turnover_by_unit. These use `SELECT * FROM turnover` (or equivalent) only inside repository.
- **db/connection.py:** Only turnover-related use is `SELECT 1 FROM sqlite_master WHERE ... name = 'turnover'` (schema check) and migration/backfill logic; no read of turnover row data for app logic.
- **scripts/verify_stage2_dual_write.py:** Uses `conn.execute("SELECT * FROM turnover WHERE turnover_id = ?")` and `SELECT move_out_date, scheduled_move_out_date` directly. This is a one-off verification script, not the application runtime; it intentionally bypasses repository to inspect raw DB state.

**End of map. No edits. No refactors. No suggestions.**
