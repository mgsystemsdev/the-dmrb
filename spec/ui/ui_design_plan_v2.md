# Turnover Cockpit — UI Design Plan v2

## Design Philosophy

Replace the DMRB Excel sheet entirely. The user's daily operational surface is ONE flat table —
that's where 80% of time is spent. The new UI keeps that flat-table mental model but adds
inline editing, system-computed risk flags, and the visual quality of Unit Overview + Flag Bridge.

**Three design sources merged:**

1. **DMRB Excel sheet** → column set, data model, daily workflow (the "what")
2. **Unit Overview + Flag Bridge** → visual patterns, row layout, breach overlay (the "how it looks")
3. **Current app_prototype.py** → inline editing via selectboxes, session state (the "how it edits")

---

## 1. Page Architecture

```
Sidebar
├── DMRB Board          ← PRIMARY (replaces Excel sheet)
├── Flag Bridge         ← Breach/violation overlay
├── Turnover Detail     ← Single-unit deep control
└── Import              ← File upload + conflicts
```

**No Dashboard, no Control Board 1/2.** Those were intermediate prototype pages.
The DMRB Board IS the dashboard. Flag Bridge IS the risk overlay.
Detail IS the deep dive. Three surfaces + import — matches the cockpit spec philosophy.

---

## 2. DMRB Board (Primary View)

### 2.1 Purpose

Replaces the Excel DMRB sheet. One row per active turnover. Every column the user
had in Excel, plus system-computed columns. Inline editing on key fields.

### 2.2 Layout Pattern

Uses **Unit Overview's row layout** (st.columns + dividers per row) — NOT st.dataframe.
This allows inline st.selectbox/st.date_input widgets per cell.

### 2.3 Top Bar (Filter Strip)

Adapted from current app_prototype.py top bar + outside UI filter_controls:

```
┌──────────────┬──────────┬──────────┬──────────┬──────────┬──────────┬───────────────┐
│ Search unit   │ Phase    │ Status   │ N/V/M    │ Assign   │ QC       │ Active │ CRIT │
│ [text input]  │ [All/5/  │ [All/VR/ │ [All/N/  │ [All/    │ [All/    │  12    │  2   │
│               │  7/8]    │  VNR/ON] │  V/M]    │  names]  │  Done/   │        │      │
│               │          │          │          │          │  NotDone]│        │      │
└──────────────┴──────────┴──────────┴──────────┴──────────┴──────────┴───────────────┘
```

**Filters map to:**
- Phase → property_id (5, 7, 8) — from Excel "P" column
- Status → manual_ready_status (Vacant Ready / Vacant Not Ready / On Notice)
- N/V/M → derived lifecycle category (Notice / Vacant / Move-in scheduled)
- Assign → assignee field
- QC → QC task confirmation_status == CONFIRMED or not

### 2.4 Metrics Strip

Horizontal row of st.metric, computed from the enrichment pipeline:

```
┌──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ Active Units  │ Violations   │ Plan Breach  │ SLA Breach   │ Move-In Risk │ Work Stalled │
│     12        │      4       │      3       │      2       │      1       │      2       │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

- **Active Units** — count of filtered turnovers
- **Violations** — count where has_violation == True (any breach flag)
- **Plan Breach** — count where Plan_Breach == True (company said ready but isn't)
- **SLA Breach** — count where SLA_Breach == True (> 10 biz days, not ready)
- **Move-In Risk** — count where Operational_State == "Move-In Risk"
- **Work Stalled** — count where Is_Task_Stalled == True

### 2.5 Table — The DMRB Flat Row

**Header row (matches DMRB Excel column order):**

```
Unit │ Status │ Move-Out │ Ready │ DV │ Move-In │ DTBR │ N/V/M │ Insp │ Paint │ MR │ HK │ CC │ Assign │ W/D │ QC │ P │ B │ U │ Notes │ Alert │ ▶
```

**Each data row (per turnover):**

```
┌──────┬─────────────┬──────────┬──────────┬────┬──────────┬──────┬───────┬──────┬───────┬─────┬─────┬─────┬────────┬─────┬──────┬───┬───┬──────┬───────────────┬───────────────────────┬───┐
│5-101 │[▼ VNR     ] │ 02/12/26 │ 02/19/26 │ 12 │ 02/26/26 │   5  │  V    │[▼D ] │[▼ D ] │[▼IP] │[▼NS] │[▼NS] │Michael │ ⚠  │[▼P ] │ 5 │18 │0206│ Key delivery  │ 🔴 Move-In Risk      │[→]│
├──────┴─────────────┴──────────┴──────────┴────┴──────────┴──────┴───────┴──────┴───────┴─────┴─────┴─────┴────────┴─────┴──────┴───┴───┴──────┴───────────────┴───────────────────────┴───┤
│ divider                                                                                                                                                                                    │
├──────┬─────────────┬──────────┬──────────┬────┬──────────┬──────┬───────┬──────┬───────┬─────┬─────┬─────┬────────┬─────┬──────┬───┬───┬──────┬───────────────┬───────────────────────┬───┤
│7-201 │[▼ On Notice]│ 02/21/26 │    —     │  3 │ 03/21/26 │  18  │  N    │[▼NS] │[▼ NS] │[▼NS] │[▼NS] │[▼NS] │Miguel A│  —  │[▼P ] │ 7 │22 │0101│               │ 📋 On Notice         │[→]│
└──────┴─────────────┴──────────┴──────────┴────┴──────────┴──────┴───────┴──────┴───────┴─────┴─────┴─────┴────────┴─────┴──────┴───┴───┴──────┴───────────────┴───────────────────────┴───┘
```

### 2.6 Column Definitions

| Column | Source | Display | Editable | Widget |
|--------|--------|---------|----------|--------|
| **Unit** | unit.unit_code_raw | Bold text | No | st.markdown |
| **Status** | turnover.manual_ready_status | Dropdown | **Yes** | st.selectbox: VR / VNR / ON |
| **Move-Out** | turnover.move_out_date | MM/DD/YYYY | No | st.markdown |
| **Ready** | turnover.report_ready_date | MM/DD/YYYY | No | st.markdown |
| **DV** | computed: business_days(move_out, today) | Number, large font | No | st.markdown |
| **Move-In** | turnover.move_in_date | MM/DD/YYYY | No | st.markdown |
| **DTBR** | computed: business_days(today, move_in) | Number | No | st.markdown |
| **N/V/M** | derived from lifecycle phase | N / V / M | No | st.markdown |
| **Insp** | task(Insp).execution_status | Dropdown | **Yes** | st.selectbox: exec statuses |
| **Paint** | task(Paint).execution_status | Dropdown | **Yes** | st.selectbox: exec statuses |
| **MR** | task(MR).execution_status | Dropdown | **Yes** | st.selectbox: exec statuses |
| **HK** | task(HK).execution_status | Dropdown | **Yes** | st.selectbox: exec statuses |
| **CC** | task(CC).execution_status | Dropdown | **Yes** | st.selectbox: exec statuses |
| **Assign** | turnover.assignee | Text | No | st.markdown |
| **W/D** | WD flags (present/notified/installed) | Icon: ✅/⚠/— | No | st.markdown |
| **QC** | task(QC).confirmation_status | Dropdown | **Yes** | st.selectbox: conf statuses |
| **P** | unit.property_id (5/7/8) | Number | No | st.markdown |
| **B** | building from unit_code | Text | No | st.markdown |
| **U** | unit number from unit_code | Text | No | st.markdown |
| **Notes** | notes for turnover | Truncated text | No | st.markdown |
| **Alert** | Attention_Badge (from intelligence engine) | Badge text | No | st.markdown |
| **▶** | navigation | Button | — | st.button → Detail |

> Column order matches the DMRB Excel sheet exactly:
> Unit, Status, Move_out, Ready_Date, DV, Move_in, DTBR, N/V/M,
> Insp, Paint, MR, HK, CC, Assign, W_D, QC, P, B, U, Notes

### 2.7 Inline Edit Behavior

**Status dropdown** (per row):
- Options: `["Vacant ready", "Vacant not ready", "On notice"]`
- On change → update session_state turnover → (when wired) call `turnover_service.set_manual_ready_status`
- Rerun to reflect change

**Task execution dropdowns** (Insp, Paint, MR, HK, CC per row):
- Options: `["—", "Not Started", "Scheduled", "In Progress", "Done", "N/A"]`
- Label map: `"Done" → "VENDOR_COMPLETED"`, `"N/A" → "NA"`, etc.
- On change → update session_state task → (when wired) call `task_service.mark_vendor_completed` or `update_task_fields`
- Rerun to reflect

**QC confirmation dropdown** (per row):
- Options: `["Pending", "Confirmed", "Rejected", "Waived"]`
- On change → update session_state task → (when wired) call `task_service.confirm_task` or `reject_task`

### 2.8 Sort Order

Primary sort (matches Unit Overview):
1. Has move-in date (yes first)
2. Move-in date ascending (soonest first)
3. Days vacant descending (longest first)

This puts the most urgent units at the top — same behavior as the outside UI's
`sort_by_movein_then_dv`.

### 2.9 Attention Badge (Alert Column)

The Alert column uses the **Attention_Badge** logic from the Intelligence Engine
(Stage 2 of the DMRB Excel pipeline). This is NOT just a risk severity icon — it's
a rich operational state badge that tells the user exactly what to focus on.

**Attention Badge rules** (priority order, first match wins):

| Condition | Badge | Meaning |
|-----------|-------|---------|
| On Notice + has move-in scheduled | 📋 On Notice - Scheduled | Pre-vacancy prep |
| On Notice (no move-in) | 📋 On Notice | Tenant gave notice |
| SMI + has move-in date | 📅 Scheduled to Move In | Move-in is booked |
| Move-In Risk (SMI + not ready + in turn) | 🔴 Move-In Risk | **Cannot meet move-in date** |
| QC Hold (ready but QC not done) | 🚫 QC Hold | Blocked on QC confirmation |
| Work Stalled (task stalled > expected days) | ⏸️ Work Stalled | Progress stopped |
| In Progress + Prevention Risk | 🟡 Needs Attention | Has hold/issue/no assignment |
| In Progress (normal) | 🔧 In Progress | Tasks being executed |
| Pending Start (vacant, no work started) | ⏳ Pending Start | Waiting to begin |
| Apartment Ready | 🟢 Apartment Ready | **Company is ready** |
| Out of Scope | Out of Scope | Not in active turnover |

**Operational State derivation** (from Intelligence Engine):

```python
def derive_operational_state(row):
    if is_on_notice:
        return "On Notice - Scheduled" if has_move_in else "On Notice"
    if not (is_vacant or is_smi):
        return "Out of Scope"
    if has_move_in and not is_ready_for_moving and in_turn_execution:
        return "Move-In Risk"
    if is_unit_ready and has_move_in and not is_qc_done:
        return "QC Hold"
    if is_task_stalled:
        return "Work Stalled"
    if task_state == "In Progress":
        return "In Progress"
    if is_unit_ready:
        return "Apartment Ready"
    return "Pending Start"
```

---

## 3. Flag Bridge (Breach Overlay)

### 3.1 Purpose

Same data as DMRB Board, but focused on breaches and violations.
Directly adapted from outside UI's `flag_bridge_view.py`.

**Critical function:** Plan_Breach tells you when the company said it would be ready
but ISN'T — this is the accountability signal. The Flag Bridge is where you see ALL
breach types at a glance and filter to isolate problems.

### 3.2 Layout

**Filter strip** (same as DMRB Board filters + breach filter):

```
┌──────────┬──────────┬──────────┬─────────────────────┬──────────┐
│ Phase    │ Status   │ N/V/M    │ Flag Bridge         │ Value    │
│ [All/5/  │ [All/VR/ │ [All/N/  │ [All/Insp Breach/  │ [All/    │
│  7/8]    │  VNR/ON] │  V/M]    │  SLA/MI Breach/    │  Yes/No] │
│          │          │          │  Plan Bridge]       │          │
└──────────┴──────────┴──────────┴─────────────────────┴──────────┘
```

**Metrics strip:**

```
┌──────────────┬──────────────┬──────────────┐
│ Total Units   │ Violations   │ Units w/ Breach│
│     12        │      4       │      6         │
└──────────────┴──────────────┴────────────────┘
```

### 3.3 Breach Types — The Four SLA Flags

These come directly from the SLA Engine (Stage 3 of the DMRB Excel pipeline).
Each is a boolean per turnover:

| Flag | Name | Predicate | Why it matters |
|------|------|-----------|----------------|
| **Inspection_SLA_Breach** | Insp Breach | Vacant + Insp not done + aging > 1 biz day | Inspection should happen within 1 business day of move-out |
| **SLA_Breach** | SLA Breach | Vacant + not ready + aging > 10 biz days | Global turn SLA — unit should be ready within 10 business days |
| **SLA_MoveIn_Breach** | SLA MI Breach | Has move-in + not ready for moving + ≤ 2 days to move-in | **Cannot meet the move-in date** |
| **Plan_Breach** | Plan Bridge | Ready_Date declared + Ready_Date has passed + unit not actually ready | **Company said it would be ready but it ISN'T** |

**"Violation"** = any of the 4 breach flags is True.

### 3.4 Table Columns

```
Unit │ Status │ DV │ Move-In │ Alert │ Violation │ Insp Breach │ SLA Breach │ SLA MI Breach │ Plan Bridge │ ▶
```

| Column | Display | Source |
|--------|---------|--------|
| Unit | Bold text | unit_code_raw |
| Status | Text (read-only) | manual_ready_status |
| DV | Number | business_days(move_out, today) |
| Move-In | Date | move_in_date |
| Alert | Attention Badge | from intelligence engine |
| Violation | "Yes" / "No" | any breach flag is True |
| Insp Breach | "Yes" / "No" | Inspection_SLA_Breach |
| SLA Breach | "Yes" / "No" | SLA_Breach |
| SLA MI Breach | "Yes" / "No" | SLA_MoveIn_Breach |
| Plan Bridge | "Yes" / "No" | Plan_Breach |
| ▶ | Button | → Detail |

### 3.5 Flag Bridge Filter

Breach category dropdown maps to the 4 SLA flags (matching the outside UI exactly):

```python
BRIDGE_MAP = {
    "All":               None,
    "Insp Breach":       "Inspection_SLA_Breach",
    "SLA Breach":        "SLA_Breach",
    "SLA MI Breach":     "SLA_MoveIn_Breach",
    "Plan Bridge":       "Plan_Breach",
}
```

When a breach category is selected + Value="Yes", show only turnovers with that breach True.
When Value="No", show only turnovers WITHOUT that breach.

### 3.6 Display Mode

Use `st.dataframe` (like outside Flag Bridge) for this view — it's read-only with
column sorting built in. The "▶" column uses a row-select or separate button column.

---

## 4. Turnover Detail (Single-Unit Deep Control)

### 4.1 Entry Points

- Click "▶" on any row in DMRB Board or Flag Bridge
- Unit search (text input → finds turnover by unit_code)

### 4.2 Layout (Vertical Flow)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [← Back]                                                           │
│                                                                     │
│  ██  5-101  ██                                                      │
│  Phase: SMI  │  MO: 02/12  │  MI: 02/26  │  DV: 12  │  Ready: Y   │
│  [▼ Status: Vacant not ready]                                       │
│                                                                     │
│  ┌ RISKS ─────────────────────────────────────────────────────────┐ │
│  │ 🔴 QC_RISK (CRITICAL) — QC not confirmed, 2 days to move-in  │ │
│  │ 🟡 WD_RISK (WARNING) — WD not notified, 7 days to move-in    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌ LIFECYCLE ─────────────────────────────────────────────────────┐ │
│  │  NOTICE → [VACANT] → SMI → STABILIZATION → CLOSED            │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌ WASHER / DRYER ────────────────────────────────────────────────┐ │
│  │  Expected: Yes │ Present: Yes │ Notified: No │ Installed: No  │ │
│  │  [Mark Notified]  [Mark Installed]                             │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌ TASKS ─────────────────────────────────────────────────────────┐ │
│  │  Task   │ Required │ Blocking │ Due      │ Exec      │ Confirm│ │
│  │─────────┼──────────┼──────────┼──────────┼───────────┼────────│ │
│  │  Insp   │ Yes      │ Yes      │ 02/14    │ [▼ Done ] │ [▼   ] │ │
│  │  Paint  │ Yes      │ No       │ 02/16    │ [▼ IP   ] │ [▼   ] │ │
│  │  MR     │ Yes      │ Yes      │ 02/18    │ [▼ Sched] │ [▼   ] │ │
│  │  HK     │ Yes      │ No       │ 02/20    │ [▼ NS   ] │ [▼   ] │ │
│  │  CC     │ No       │ No       │ 02/22    │ [▼ N/A  ] │ [▼   ] │ │
│  │  QC     │ Yes      │ Yes      │ 02/25    │ [▼ NS   ] │ [▼   ] │ │
│  └─────────┴──────────┴──────────┴──────────┴───────────┴────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────┐                      │
│  │        [ ✅ CONFIRM QC ]                  │   ← big one-click   │
│  └──────────────────────────────────────────┘                      │
│                                                                     │
│  ┌ NOTES ─────────────────────────────────────────────────────────┐ │
│  │  - Waiting on key delivery (blocking) [Resolve]               │ │
│  │  - Expedited request (info)                                    │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.3 Detail Inline Edits

| Field | Widget | Backend call (when wired) |
|-------|--------|--------------------------|
| Status | st.selectbox (VR/VNR/ON) | turnover_service.set_manual_ready_status |
| Task Exec | st.selectbox per task row | task_service.mark_vendor_completed / update |
| Task Confirm | st.selectbox per task row | task_service.confirm_task / reject_task |
| WD Notified | st.button | turnover_service.update_wd_panel |
| WD Installed | st.button | turnover_service.update_wd_panel |
| Confirm QC | st.button (large) | task_service.confirm_task for QC task |
| Resolve Note | st.button per note | note repository (resolve_note) |

---

## 5. Import (Unchanged from Current)

Keep current import page as-is. It already matches the spec:
- File uploader → report type selector → Run Import button
- Summary display (batch ID, status, records, conflicts)
- Conflict list with unit code and reason

---

## 6. Enrichment Pipeline (from DMRB Excel — reference only)

The DMRB Excel sheet runs a 3-stage pipeline that computes every derived column.
The mock data layer must replicate this logic. These stages are **reference code**
from the Excel Python cells — NOT imported, but the logic must match.

### 6.1 Stage 1 — Fact Engine

Computes raw facts from the base DMRB columns:

| Derived Field | Logic |
|---------------|-------|
| `Aging_Business_Days` | `business_days(move_out_date, today)` — numpy busday_count |
| `Is_Vacant` | N/V/M == "VACANT" |
| `Is_SMI` | N/V/M contains "SMI" or "MOVE IN" |
| `Is_On_Notice` | N/V/M contains "NOTICE" |
| `Is_MoveIn_Present` | move_in_date is not null |
| `Is_Ready_Declared` | report_ready_date is not null |
| `Is_QC_Done` | QC task status == "DONE" |
| `Has_Assignment` | Assign is not empty and not "total" |
| `Note_Category` | Extract HOLD/ISSUE/REOPEN/DECISION from Notes |
| `Task_State` | "All Tasks Complete" / "Not Started" / "In Progress" |
| `Task_Completion_Ratio` | % of 5 tasks (Insp/Paint/MR/HK/CC) that are Done |
| `Table_Current_Task` | First task in sequence that is NOT done |
| `Table_Next_Task` | Task after current |
| `Is_Task_Stalled` | Vacant + task not done + aging > task's expected business day |

**Task stall detection** uses expected business days per task in sequence:

```python
TASK_EXPECTED_DAYS = {
    "Insp": 1,     # Should complete by business day 1
    "Paint": 2,    # By business day 2
    "MR": 3,       # By business day 3
    "HK": 6,       # By business day 6
    "CC": 7,       # By business day 7
}
# Stalled = Vacant AND task not Done AND Aging_Business_Days > (expected + 1)
```

### 6.2 Stage 2 — Intelligence Engine

Builds operational state and attention badges from Stage 1 facts:

| Derived Field | Logic |
|---------------|-------|
| `Status_Norm` | lowercase(manual_ready_status) |
| `Is_Unit_Ready` | Status == "Vacant Ready" AND Task_State == "All Tasks Complete" |
| `Is_Unit_Ready_For_Moving` | Is_Unit_Ready AND Is_MoveIn_Present AND Is_QC_Done |
| `In_Turn_Execution` | Is_Vacant AND NOT Is_Unit_Ready |
| `Operational_State` | See §2.9 — state machine |
| `Prevention_Risk_Flag` | In_Turn_Execution AND (has HOLD/ISSUE note OR no assignment OR in-progress but not stalled) |
| `Attention_Badge` | See §2.9 — badge rules |

### 6.3 Stage 3 — SLA Engine

Computes the 4 breach flags (see §3.3 for full definitions):

| Derived Field | Predicate | SLA Config |
|---------------|-----------|------------|
| `Days_To_MoveIn` | `(move_in_date - today).days` | — |
| `Inspection_SLA_Breach` | Vacant + Insp not Done + Aging > 1 biz day | `INSPECTION_SLA_DAYS = 1` |
| `SLA_Breach` | Vacant + not ready + Aging > 10 biz days | `TURN_SLA_DAYS = 10` |
| `SLA_MoveIn_Breach` | Has move-in + not ready for moving + Days_To_MoveIn ≤ 2 | `MOVE_IN_BUFFER_DAYS = 2` |
| `Plan_Breach` | Ready_Date declared + Ready_Date passed + not actually ready | — |

**Plan_Breach is the "company readiness accountability" flag:**
```python
Plan_Breach = (
    report_ready_date is not None
    AND today >= report_ready_date
    AND NOT Is_Unit_Ready
)
```

---

## 7. Mock Data Changes Required

### 7.1 Task Types — Match DMRB Excel Columns

Current mock tasks use: "Make Ready", "QC", "Paint", "Carpet Clean".
Need to match the Excel column set exactly:

```python
TASK_TYPES_SEQUENCE = ["Insp", "Paint", "MR", "HK", "CC"]  # execution pipeline
TASK_TYPES_ALL = ["Insp", "Paint", "MR", "HK", "CC", "QC"]  # + QC confirmation
```

Mapping:
- **Insp** = Inspection (pre-move-in walkthrough)
- **Paint** = Paint
- **MR** = Make Ready (general maintenance)
- **HK** = Housekeeping (cleaning)
- **CC** = Carpet Clean
- **QC** = Quality Control (final confirmation — uses confirmation_status, not execution)

Each turnover gets ALL 6 task types (some may be NA/not required).

**Each task has BOTH a date column and a status column** (matching Excel):
- `Insp` (date) + `Insp_status` (Done/Not Started/In Progress/etc.)
- `Paint` (date) + `Paint_status`
- `MR` (date) + `MR_Status`
- `HK` (date) + `HK_Status`
- `CC` (date) + `CC_status`

### 7.2 Computed Fields for Mock Data

All derived from the 3-stage pipeline:

```python
# Stage 1 — Facts
"dv": business_days(move_out_date, today),    # Aging_Business_Days
"dtbr": business_days(today, move_in_date),   # Days To Be Ready
"nvm": "N" | "V" | "M",                       # Notice/Vacant/Move-in
"task_state": "All Tasks Complete" | "In Progress" | "Not Started",
"task_completion_ratio": 80,                   # % of 5 tasks done
"current_task": "Paint",                       # first not-done task
"next_task": "MR",
"is_task_stalled": True/False,

# Stage 2 — Intelligence
"is_unit_ready": True/False,
"is_ready_for_moving": True/False,
"in_turn_execution": True/False,
"operational_state": "In Progress",
"prevention_risk_flag": True/False,
"attention_badge": "🔧 In Progress",

# Stage 3 — SLA Breaches
"days_to_move_in": 5,
"inspection_sla_breach": True/False,
"sla_breach": True/False,
"sla_movein_breach": True/False,
"plan_breach": True/False,
"has_violation": True/False,                   # any breach is True

# WD
"wd_summary": "✅" | "⚠" | "—",
```

### 7.3 N/V/M Derivation

```python
def derive_nvm(phase: str) -> str:
    if phase in ("NOTICE", "NOTICE_SMI"):
        return "N"
    if phase in ("VACANT",):
        return "V"
    if phase in ("SMI", "MOVE_IN_COMPLETE", "STABILIZATION"):
        return "M"
    return "—"
```

### 7.4 Mock Data Shape

Each mock turnover provides a flat row for the DMRB Board:

```python
{
    # Identity
    "turnover_id": 1,
    "unit_code": "5-101",
    "property_id": 5,
    "building": "18",                # B — from unit_code parsing
    "unit_number": "0206",           # U — from unit_code parsing

    # Dates
    "move_out_date": "2026-02-12",
    "move_in_date": "2026-02-26",
    "report_ready_date": "2026-02-19",

    # Status (inline editable)
    "manual_ready_status": "Vacant not ready",

    # Stage 1 — Facts
    "dv": 12,                        # business days since move-out
    "dtbr": 5,                       # business days to move-in
    "phase": "SMI",
    "nvm": "M",
    "assignee": "Michael",
    "task_state": "In Progress",
    "task_completion_ratio": 40,
    "current_task": "MR",
    "next_task": "HK",
    "is_task_stalled": False,

    # Tasks (flat — one field per DMRB column)
    "task_insp": {"task_id": 1, "execution_status": "VENDOR_COMPLETED",
                  "confirmation_status": "CONFIRMED",
                  "vendor_due_date": "2026-02-13",
                  "vendor_completed_at": "2026-02-13"},
    "task_paint": {"task_id": 2, "execution_status": "VENDOR_COMPLETED", ...},
    "task_mr": {"task_id": 3, "execution_status": "IN_PROGRESS", ...},
    "task_hk": {"task_id": 4, "execution_status": "NOT_STARTED", ...},
    "task_cc": {"task_id": 5, "execution_status": "NOT_STARTED", ...},
    "task_qc": {"task_id": 6, "execution_status": "NOT_STARTED",
                "confirmation_status": "PENDING", ...},

    # Stage 2 — Intelligence
    "is_unit_ready": False,
    "is_ready_for_moving": False,
    "operational_state": "In Progress",
    "attention_badge": "🔧 In Progress",

    # Stage 3 — SLA Breaches
    "days_to_move_in": 5,
    "inspection_sla_breach": False,   # Insp is done
    "sla_breach": True,              # aging > 10 biz days, not ready
    "sla_movein_breach": False,       # > 2 days to move-in
    "plan_breach": True,             # ready_date passed, not ready
    "has_violation": True,            # sla_breach or plan_breach

    # WD
    "wd_present": 1,
    "wd_supervisor_notified": 0,
    "wd_installed": 0,
    "wd_summary": "⚠",

    # Notes
    "notes_text": "Waiting on key delivery",
}
```

### 7.5 Helper: Flatten Turnovers for DMRB Board

```python
def get_dmrb_board_rows(
    turnovers, units, tasks, risks,
    search_unit=None, filter_phase=None, filter_status=None,
    filter_nvm=None, filter_assignee=None, filter_qc=None,
) -> list[dict]:
    """
    Returns flat rows matching DMRB Excel columns + all 3 enrichment stages.
    Each row = one turnover with tasks embedded as flat fields.
    Runs the enrichment pipeline (facts → intelligence → SLA) on each row.
    Filtered and sorted by move-in proximity then DV.
    """
```

---

## 8. Execution Status Label Mapping

For the DMRB Board inline dropdowns, use short user-friendly labels
(matching the Excel column feel) with backend value mapping:

### Task Execution (Insp, Paint, MR, HK, CC columns)

| Display Label | Backend Value |
|---------------|---------------|
| — | (no task / NA) |
| Not Started | NOT_STARTED |
| Scheduled | SCHEDULED |
| In Progress | IN_PROGRESS |
| Done | VENDOR_COMPLETED |
| N/A | NA |
| Canceled | CANCELED |

### Task Confirmation (QC column + Detail view)

| Display Label | Backend Value |
|---------------|---------------|
| Pending | PENDING |
| Confirmed | CONFIRMED |
| Rejected | REJECTED |
| Waived | WAIVED |

### Unit Status

| Display Label | Backend Value |
|---------------|---------------|
| Vacant Ready | Vacant ready |
| Vacant Not Ready | Vacant not ready |
| On Notice | On notice |

---

## 9. Visual Design Decisions

### 8.1 Row Layout (from Unit Overview)

Each row uses `st.columns` with proportional widths + `st.divider()` between rows.
Unit code is **bold**. DV uses slightly larger font. Dates formatted MM/DD/YYYY.

### 8.2 Color Coding

- **Status badge colors** (from unit_cards.py):
  - Vacant Ready: green `#28a745`
  - Vacant Not Ready: amber `#ffc107`
  - On Notice: teal `#17a2b8`

- **Risk severity colors** (for Alert column):
  - CRITICAL: 🔴 red
  - WARNING: 🟠 orange
  - INFO: 🟡 yellow
  - Clean: no icon

### 8.3 Compact Dropdowns

Task execution dropdowns in the DMRB Board should be **compact** — no label text,
just the selectbox. Use `st.selectbox("", options, key=..., label_visibility="collapsed")`
to minimize visual noise. The column header provides context.

### 8.4 Dividers Between Rows

Following Unit Overview pattern:
```python
for row in filtered_rows:
    with st.container():
        cols = st.columns([...])
        # render cells
        st.divider()
```

---

## 10. Page Rendering Flow

```
app_prototype.py
│
├── _init_session_state()
│   ├── turnovers (deep copy of mock)
│   ├── tasks (deep copy of mock)
│   ├── page: "dmrb_board"
│   ├── selected_turnover_id: None
│   └── filter_* states
│
├── Sidebar radio: DMRB Board │ Flag Bridge │ Turnover Detail │ Import
│
├── if page == "dmrb_board":
│   ├── render_filter_strip()        # Phase, Status, N/V/M, Assign, QC
│   ├── render_metrics_strip()       # Active, SLA, Conf, QC, Exposure
│   └── render_dmrb_table()          # Row-per-turnover with inline edits
│       ├── for each turnover:
│       │   ├── Unit (bold)
│       │   ├── Status [selectbox]    ← INLINE EDIT
│       │   ├── DV (computed)
│       │   ├── Move-In, Move-Out, Ready (text)
│       │   ├── P, N/V/M (text)
│       │   ├── Insp [selectbox]      ← INLINE EDIT
│       │   ├── Paint [selectbox]     ← INLINE EDIT
│       │   ├── MR [selectbox]        ← INLINE EDIT
│       │   ├── HK [selectbox]        ← INLINE EDIT
│       │   ├── CC [selectbox]        ← INLINE EDIT
│       │   ├── QC [selectbox]        ← INLINE EDIT
│       │   ├── W/D (icon)
│       │   ├── Assign (text)
│       │   ├── Alert (icon)
│       │   └── [→] button → Detail
│       └── st.divider()
│
├── elif page == "flag_bridge":
│   ├── render_filter_strip()
│   ├── render_breach_filter()       # Bridge category + Yes/No
│   ├── render_bridge_metrics()      # Total, Violations, Breach count
│   └── st.dataframe(breach_table)   # Read-only with Yes/No columns
│
├── elif page == "detail":
│   ├── render_detail_header()       # Unit, phase, dates, status dropdown
│   ├── render_risks_panel()         # Active risks list
│   ├── render_lifecycle_strip()     # Phase timeline
│   ├── render_wd_panel()            # WD status + action buttons
│   ├── render_task_table()          # Full task table with exec/confirm dropdowns
│   ├── render_qc_button()           # Big one-click QC confirm
│   └── render_notes()               # Notes list + resolve buttons
│
└── elif page == "import":
    └── render_import()              # (existing, keep as-is)
```

---

## 11. What Changes from Current Prototype

| Current | New Design | Why |
|---------|-----------|-----|
| Dashboard page | → **DMRB Board** | Replaces Excel; flat table is the primary surface |
| Control Board 1 | → **Removed** (merged into DMRB Board) | Status editing is in the DMRB Board Status column |
| Control Board 2 | → **Removed** (merged into DMRB Board) | Task editing is in the DMRB Board task columns |
| 4 task types (Make Ready, QC, Paint, Carpet Clean) | → **6 task types** (Insp, Paint, MR, HK, CC, QC) | Match Excel DMRB columns exactly |
| No DV column | → **DV column** (business days) | Core DMRB metric |
| No DTBR column | → **DTBR column** (Days To Be Ready) | Shows urgency to move-in |
| No N/V/M column | → **N/V/M column** | Excel workflow parity |
| No breach flags | → **Flag Bridge with 4 breach types** | Insp, SLA, MI, **Plan_Breach** |
| No Plan_Breach | → **Plan Bridge column** | Company readiness accountability |
| No Attention_Badge | → **Alert column with operational state badges** | From intelligence engine |
| No Operational_State | → **Drives Attention_Badge** | Move-In Risk, QC Hold, Work Stalled, etc. |
| No task stall detection | → **Is_Task_Stalled** computed per task sequence | From fact engine |
| No sort by move-in | → **Sort by move-in then DV** | From Unit Overview |
| No dividers between rows | → **Dividers** | From Unit Overview visual pattern |
| No B/U/Notes columns | → **B, U, Notes** | Match full Excel column set |
| Basic metrics | → **DMRB-specific metrics** | SLA, Conf, QC, Exposure |
| st.selectbox labels raw | → **User-friendly labels** (Done, IP, NS) | Excel feel |
| No enrichment pipeline | → **3-stage pipeline** (Facts → Intelligence → SLA) | Replicates Excel Python logic |

---

## 12. Implementation Order

1. **Restructure mock_data.py** — Add 6 task types per turnover (Insp/Paint/MR/HK/CC/QC with both date + status per task); add 3-stage enrichment pipeline (facts → intelligence → SLA); add `get_dmrb_board_rows()` helper with all filters + sort.

2. **Enrichment pipeline in mock_data** — Implement `compute_facts()`, `compute_intelligence()`, `compute_sla_breaches()` as pure functions that take a flat row dict and return enriched row. Must produce: Aging_Business_Days, Task_State, Is_Task_Stalled, Operational_State, Attention_Badge, and all 4 breach flags (Inspection_SLA_Breach, SLA_Breach, SLA_MoveIn_Breach, **Plan_Breach**).

3. **Rewrite app_prototype.py pages** — Replace Dashboard + CB1 + CB2 with DMRB Board. Add Flag Bridge. Keep Detail (enhanced with 6 task types + lifecycle strip). Keep Import.

4. **DMRB Board rendering** — Filter strip, metrics strip, row-per-turnover with inline edits using the Unit Overview `st.columns` + divider pattern. Column order matches Excel exactly.

5. **Flag Bridge rendering** — 4 breach columns (Insp Breach, SLA Breach, SLA MI Breach, **Plan Bridge**) + Violation. Breach category filter + Yes/No. Metrics strip.

6. **Detail view enhancement** — Lifecycle strip, risks panel, 6 task rows with date + status, QC button, WD panel, notes. Show breach flags in header.

7. **Polish** — Attention Badge rendering, status badge colors, compact dropdown styling, sort order, DTBR column.

---

## 13. Future: Wiring to Backend

When connecting to the real backend, replace:
- `st.session_state.turnovers` → `repository.list_open_turnovers_by_property(conn, property_id=1)`
- `st.session_state.tasks` → `repository.get_tasks_by_turnover(conn, tid)` per turnover
- Inline edit callbacks → service layer calls (turnover_service, task_service)
- Risk computation → `risk_service.reconcile_risks_for_turnover` after each edit
- DV, N/V/M, phase → computed from `domain.lifecycle.derive_lifecycle_phase`

The UI layout, columns, filters, and widgets remain identical. Only the data source changes.
