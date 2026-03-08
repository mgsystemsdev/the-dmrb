# UI v2 — Refinement Plan

## Design Position

The prototype v2 has the right structure. Page architecture, column set, enrichment pipeline,
inline editing, and data flow are all aligned with Design Plan v2 and the DMRB raw spreadsheet.
What is missing is not *what* we show — it is *how* we present it.

The DMRB raw Excel sheet works because it is **dense, scannable, and visually quiet**.
Every column earns its space. Headers stay fixed. The eye can sweep left-to-right across
a row and absorb unit status in under two seconds. The two views the user relies on —
the flat DMRB Board and the Flag Bridge — succeed because they feel like
**controlled spreadsheets**, not application screens.

The prototype currently feels like a collection of Streamlit widgets placed on a page.
It does not yet feel like a cockpit. The refinements below close that gap without
changing architecture, data model, or page structure.

---

## 1. DMRB Board — From Cramped to Controlled

### 1.1 Problem

The board renders 22 columns of `st.columns` per row with inline selectboxes.
The result is dense — but not the *useful* density of a spreadsheet. It is cramped:

- Selectbox widgets consume vertical space (Streamlit adds padding above/below each widget)
- Column widths compete — editable columns (Status, Insp, Paint, MR, HK, CC, QC) need
  dropdown room, while read-only columns (DV, DTBR, N/V/M, P, B, U) only need a number
- The filter strip, metrics strip, header row, and data rows all run together with no
  visual separation between zones
- There is no row containment — each row bleeds into the next; the divider helps but
  does not create the "row as a unit" feeling the Excel sheet has

### 1.2 Refinements

**A. Three visual zones with clear boundaries**

The DMRB Board is three stacked zones. Each needs its own visual containment:

```
┌─────────────────────────────────────────────────────────────────┐
│  ZONE 1 — FILTERS                                               │
│  Search │ Phase │ Status │ N/V/M │ Assign │ QC │ Active │ CRIT  │
└─────────────────────────────────────────────────────────────────┘
                            ↕ gap
┌─────────────────────────────────────────────────────────────────┐
│  ZONE 2 — METRICS                                               │
│  Active Units │ Violations │ Plan Breach │ SLA │ MI Risk │ Stall│
└─────────────────────────────────────────────────────────────────┘
                            ↕ gap
┌─────────────────────────────────────────────────────────────────┐
│  ZONE 3 — TABLE                                                 │
│  Header row (sticky feel, bold, slightly different background)  │
│  ─────────────────────────────────────────────────────────────  │
│  Row 1                                                          │
│  ─────────────────────────────────────────────────────────────  │
│  Row 2                                                          │
│  ...                                                            │
└─────────────────────────────────────────────────────────────────┘
```

Implementation: wrap each zone in `st.container(border=True)`. The `border=True`
parameter (Streamlit 1.29+) draws a subtle rounded border that creates visual
containment without custom CSS. Add `st.divider()` or vertical whitespace between zones.

**B. Column width rebalancing**

Current widths give equal space to DV (a 2-digit number) and Status (a dropdown
with "Vacant not ready" text). Rebalance so:

- Read-only narrow columns (DV, DTBR, N/V/M, P, B, U, W/D) get **0.4–0.5**
- Editable dropdown columns (Status, Insp–CC, QC) get **0.7–0.8**
- Text columns (Unit, Notes, Alert) get **1.0–1.5**
- The ▶ button gets **0.3**

This tightens the metadata columns and gives breathing room to the dropdowns,
matching the feel of Excel where "DV" is a narrow column and "Status" is wider.

**C. Assign column — read-only text, not dropdown**

Design Plan v2 §2.6 specifies Assign as `Text | No | st.markdown`. The prototype
renders a selectbox. On the DMRB Board the Assign column should show the assignee
name as plain text — fast to scan, no widget overhead. Per-task assignment editing
belongs in the Turnover Detail page.

This removes one selectbox per row (6 rows × 1 selectbox = 6 fewer widgets on screen),
reducing visual noise and improving render performance.

**D. DV column — visual weight**

DV (Days Vacant) is the single most-scanned number on the board. In the Excel sheet,
DV stands out because of conditional formatting. In the prototype it renders identically
to every other text cell.

Refinement: render DV with `st.markdown(f"**{dv}**")` (bold) and, when DV > 10,
apply a color tint: `st.markdown(f'<span style="color:#dc3545;font-weight:bold">{dv}</span>')`.
This gives DV the visual prominence the spec calls for ("Number, large font" in §2.6)
without requiring custom CSS.

**E. Row containment**

Wrap each data row in `with st.container():` before the `st.columns` call.
This gives Streamlit a rendering boundary per row and produces slightly tighter
vertical grouping. Combined with `st.divider()` between containers, each row
reads as a discrete horizontal unit — closer to the spreadsheet row feel.

**F. Header row — visual distinction**

The header row currently uses the same `st.columns` + `st.markdown("**label**")`
as data rows, making it hard to distinguish header from data at a glance.

Refinement: render the header inside its own `st.container()` and add a
`st.divider()` immediately after. This creates a "frozen header" effect.
Optional: use `st.caption`-style smaller text or a subtle background via
`st.container(border=True)` to differentiate.

---

## 2. Flag Bridge — Open Detail Inside the Table

### 2.1 Problem

The Flag Bridge renders a `st.dataframe` for the breach table, then places
▶ navigation buttons *below* the table as a separate "Open to detail:" section.

This breaks the contextual relationship between the data row and its action.
In the DMRB raw sheet, you click a row and you're *in* it. Here, you read row 3,
then scroll down past all the buttons, find "▶ 7-201", and click it.
The action is disconnected from the data.

### 2.2 Refinements

**A. Replace st.dataframe with st.columns row rendering (same pattern as DMRB Board)**

Render each Flag Bridge row using `st.columns` with the ▶ button as the
last column — identical to the DMRB Board pattern. This places the Open
action inline with each row, exactly where the user's eye already is.

```
┌──────┬───────────┬────┬──────────┬──────────────────┬─────┬──────┬──────┬──────┬──────┬───┐
│ Unit │ Status    │ DV │ Move-In  │ Alert            │Viol │ Insp │ SLA  │ MI   │ Plan │ ▶ │
├──────┼───────────┼────┼──────────┼──────────────────┼─────┼──────┼──────┼──────┼──────┼───┤
│5-101 │ VNR       │ 12 │ 02/26/26 │ 🔴 Move-In Risk │ Yes │ No   │ Yes  │ No   │ Yes  │[→]│
│──────┼───────────┼────┼──────────┼──────────────────┼─────┼──────┼──────┼──────┼──────┼───│
│7-202 │ VNR       │ 15 │ 02/26/26 │ ⏸ Work Stalled  │ Yes │ Yes  │ Yes  │ Yes  │ No   │[→]│
└──────┴───────────┴────┴──────────┴──────────────────┴─────┴──────┴──────┴──────┴──────┴───┘
```

This is read-only (no selectboxes) so rendering is fast, and the ▶ button sits
at the end of each row — contextually attached to the data it acts on.

**B. Visual indicators for breach columns**

Replace "Yes"/"No" text with visual indicators:

- **Yes** → `🔴` or `⚠️` (draws the eye immediately)
- **No** → `—` (quiet, does not compete for attention)

This matches how conditional formatting works in the Excel sheet — breaches
*pop*, clean rows stay quiet. The user can scan a column vertically and
instantly see which units are flagged.

**C. Same three-zone layout as DMRB Board**

Apply the same containment pattern: Filters zone → Metrics zone → Table zone.
Each in its own `st.container(border=True)`. This makes the Flag Bridge feel
like a sibling of the DMRB Board, not a different application.

---

## 3. Turnover Detail — From Scattered to Structured

### 3.1 Problem

The Detail page shows correct data but presents it as a vertical stream of
Streamlit widgets without visual grouping. Headers, status fields, date pickers,
risks, lifecycle, WD panel, tasks, QC button, and notes all flow one after
another with no containment boundaries. The result:

- The user cannot instantly see where "identity" ends and "tasks" begin
- Risks are hidden behind a collapsed `st.expander` — the user may miss CRITICAL flags
- The lifecycle strip is two plain `st.caption` lines — it does not feel like a
  panel or a visual representation of progress
- WD panel, Tasks, and Notes have `st.subheader` labels but no visual boundary;
  they merge into a continuous scroll
- Date pickers (Move-out, Move-in, Report Ready) are stacked vertically at full width,
  consuming excessive vertical space for three small date values

### 3.2 Refinements — Panel Architecture

The Detail page should feel like a **structured form with defined panels**,
matching the wireframe in Design Plan v2 §4.2. Each logical section gets its
own `st.container(border=True)` with a clear header.

**A. Unit Identity Panel (top)**

```
┌─────────────────────────────────────────────────────────────────┐
│  ██  5-101  ██                                          [← Back]│
│                                                                  │
│  Phase: SMI    MO: 02/12/2026    MI: 02/26/2026    DV: 12       │
│                                                                  │
│  Status: [▼ Vacant not ready]        Ready: N                    │
└─────────────────────────────────────────────────────────────────┘
```

- Unit code as `st.subheader` (large, bold) — this is the page title
- Back button on the same line (right-aligned via `st.columns`)
- Key dates and DV in a horizontal `st.columns` row — **not** stacked date pickers
- Status dropdown on a second row, alongside Ready indicator
- All inside one `st.container(border=True)`
- Remove the editable date pickers — dates are report-authoritative per the blueprint;
  they should display as read-only text, matching the DMRB Board

**B. Risks Panel — always visible, not collapsed**

```
┌─ RISKS ─────────────────────────────────────────────────────────┐
│  🔴 QC_RISK (CRITICAL) — QC not confirmed, 2 days to move-in   │
│  🟡 WD_RISK (WARNING) — WD not notified, 7 days to move-in     │
└─────────────────────────────────────────────────────────────────┘
```

- Replace `st.expander("RISKS")` with `st.container(border=True)`
- Add "RISKS" as a bold header inside the container
- Always visible — the user must never have to click to see CRITICAL alerts
- If no active risks, show `st.caption("No active risks")` inside the container
  so it doesn't disappear entirely

**C. Lifecycle Strip — visual phase indicator**

```
┌─ LIFECYCLE ─────────────────────────────────────────────────────┐
│  NOTICE  →  ██ VACANT ██  →  SMI  →  STABILIZATION  →  CLOSED  │
└─────────────────────────────────────────────────────────────────┘
```

- Inside `st.container(border=True)`
- Render the phase sequence as a single horizontal line
- Highlight the current phase with **bold** and a marker (e.g., `[ VACANT ]` or
  bold markdown), while inactive phases are plain/dimmed text
- Remove the second `st.caption("Current phase: ...")` — the highlighting makes it
  redundant

**D. Washer/Dryer Panel — contained with inline actions**

```
┌─ WASHER / DRYER ────────────────────────────────────────────────┐
│  Expected: Yes  │  Present: Yes  │  Notified: No  │  Installed: No  │
│                                                                  │
│  [Mark Notified]    [Mark Installed]                             │
└─────────────────────────────────────────────────────────────────┘
```

- Wrap in `st.container(border=True)`
- Status fields on one horizontal row (`st.columns`)
- Action buttons on a second row, also horizontal
- This is already close in the prototype — just needs the container boundary

**E. Tasks Panel — with header row**

```
┌─ TASKS ─────────────────────────────────────────────────────────┐
│  Task  │ Req │ Blk │  Due       │  Exec        │  Confirm      │
│  ───── │ ─── │ ─── │ ────────── │ ──────────── │ ───────────── │
│  Insp  │ Yes │ Yes │  02/14     │ [▼ Done    ] │ [▼ Pending  ] │
│  Paint │ Yes │ No  │  02/16     │ [▼ IP      ] │ [▼ Pending  ] │
│  MR    │ Yes │ Yes │  02/18     │ [▼ Sched   ] │ [▼ Pending  ] │
│  HK    │ Yes │ No  │  02/20     │ [▼ NS      ] │ [▼ Pending  ] │
│  CC    │ No  │ No  │  02/22     │ [▼ N/A     ] │ [▼ Pending  ] │
│  QC    │ Yes │ Yes │  02/25     │ [▼ NS      ] │ [▼ Pending  ] │
└─────────────────────────────────────────────────────────────────┘
```

- Wrap in `st.container(border=True)` with "TASKS" header
- Add a **header row** above the task rows using `st.columns` + bold labels —
  this is missing in the current prototype, making the columns hard to interpret
- Match Design Plan v2 §4.2: 6 columns (Task, Required, Blocking, Due, Exec, Confirm)
- Remove the extra Assign column per task — it adds width and is not in the spec
  wireframe; task-level assignment can be a future enhancement
- Add `st.divider()` between header and first task row

**F. Confirm QC — visual prominence**

Already uses `type="primary"` and `use_container_width=True`. This is correct.
Place it immediately after the Tasks container, visually attached.

**G. Notes Panel — contained**

```
┌─ NOTES ─────────────────────────────────────────────────────────┐
│  - Waiting on key delivery (blocking)              [Resolve]    │
│  - Expedited request (info)                                     │
│                                                                  │
│  [Add note: ___________________]                    [Add]        │
└─────────────────────────────────────────────────────────────────┘
```

- Wrap in `st.container(border=True)` with "NOTES" header
- Note text and Resolve button on the same row (already done via `st.columns`)
- Add note input and button at the bottom of the container
- Show note type/severity more clearly: `(blocking)` in bold or with ⛔ icon

---

## 4. Cross-Cutting Visual Refinements

### 4.1 Date Format

Change `_fmt_date` from `%m/%d/%y` (2-digit year) to `%m/%d/%Y` (4-digit year).
Design Plan v2 §9.1 specifies MM/DD/YYYY. This matches what the user sees in
Excel and avoids ambiguity.

### 4.2 Consistent Containment Pattern

Every visual section across all pages follows the same containment rule:

```python
with st.container(border=True):
    st.markdown("**SECTION TITLE**")
    # section content
```

This produces a consistent "panel" language throughout the application.
The user learns one visual pattern: bordered box = logical group.

### 4.3 Sidebar — Version Context

The sidebar currently shows "Prototype v2 (mock data)". Add a small active
unit count below the page radio to give the user context without navigating:

```
Turnover Cockpit
Prototype v2 (mock data)
──────────
◉ DMRB Board
○ Flag Bridge
○ Turnover Detail
○ Import
──────────
6 active turnovers
```

---

## 5. What This Refinement Does NOT Change

- **Page architecture** — still 4 pages, same sidebar navigation
- **Column set** — still 22 DMRB columns in exact Excel order
- **Data model** — still mock_data_v2 with 3-stage enrichment
- **Inline editing** — same selectbox-based editing on Status, tasks, QC
- **Session state** — same pattern, same keys
- **Enrichment pipeline** — compute_facts → compute_intelligence → compute_sla_breaches
- **Filter logic** — same 6 filters, same mapping
- **Sort order** — unchanged (fix for inverted sort is a separate bug fix)

Every refinement is a **rendering change** in `app_prototype_v2.py`. No changes
to `mock_data_v2.py`, no new dependencies, no architectural modifications.

---

## 6. Priority Order

| # | Refinement | Impact | Effort |
|---|-----------|--------|--------|
| 1 | Detail — panel containment (A–G) | High — scattered → structured | Medium |
| 2 | DMRB Board — three-zone containment | High — cramped → controlled | Low |
| 3 | Flag Bridge — inline ▶ buttons | High — disconnected → contextual | Medium |
| 4 | DMRB Board — column width rebalance | Medium — better scan density | Low |
| 5 | Assign column → read-only text | Medium — less noise, fewer widgets | Low |
| 6 | DV column — bold + color for breach | Medium — visual hierarchy | Low |
| 7 | Flag Bridge — breach icons (🔴/—) | Medium — scan speed | Low |
| 8 | Date format → MM/DD/YYYY | Low — correctness | Trivial |
| 9 | Header row visual distinction | Low — polish | Low |
| 10 | Detail — risks always visible | Low — safety | Trivial |

---

## 7. Closing — The Spreadsheet Standard

The DMRB raw Excel sheet is a high-density operational surface that the user has
refined over months of daily use. It is not beautiful — but it is *effective*.
Every column, every color, every filter serves the single question:
**"Which unit needs my attention right now?"**

The prototype v2 has the right data and the right intelligence engine behind it.
These refinements bring the *presentation* up to the standard the user already
has in Excel — then exceed it, because the database-powered enrichment pipeline
gives them DV, DTBR, breach flags, operational state, and attention badges
that their spreadsheet could never compute automatically.

The goal is not to look like an application. The goal is to feel like the
best spreadsheet they ever had — one that thinks for them.
