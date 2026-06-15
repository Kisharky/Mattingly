# Profit Lens — Phase 3 Working Prototype

**Warehouse Profit Intelligence · Monthly Management Operating System**

Mattingly AI & Operations Hackathon 2026 · Kishan Gowda

---

## What This Tool Does — In One Sentence

Profit Lens finds every dollar Mattingly is losing on warehouse operations, turns each loss into an owned action, and tracks delivery against a live target.

---

## How It Works — Four Steps

```
FIND  →  TICKET  →  ACT  →  RECOVER
```

| Step | What happens |
|------|-------------|
| **FIND** | Upload the warehouse Excel dataset. The ABC engine (Activity-Based Costing — a standard accounting method that assigns costs to the actual activities that caused them) calculates the true cost of each pick and compares it to what each customer is actually charged. |
| **TICKET** | Every gap — a customer charged below cost, unbilled work, a data quality gap — becomes a finding ticket with a dollar value, an owner, and a priority. |
| **ACT** | Each role (CEO, Commercial Lead, Site Manager) sees only their queue. The Commercial Lead reprices or rebills. The Site Manager closes data gaps. The CEO approves and tracks. |
| **TRACK** | Closing a ticket updates the live delivery bar. The tool shows which actions have converted to measurable profit improvement. |

---

## The Problem (Why This Exists)

Mattingly's standard reporting shows every customer at ~96% gross margin. That number is wrong — it ignores the true cost of picking.

The ABC engine calculates:

- **True pick cost: $0.265/pick** — conservative floor used for all negotiations. The engine-strict figure is $0.284/pick.
- **Charged rate: $0.12–$0.17/pick** — every customer is being served below cost.
- **$2.66M/year** total identified opportunity: $1.86M pricing leakage + $0.80M operational exposure (F014: exception-handling labour drain $0.45M + F015: urgent-order throughput penalty $0.35M).
- **$1.15M** is deliverable in 9 months through repricing and re-billing — without losing a single customer.

> **Why two pick-cost numbers?** The labour dataset has 4 days with missing time-and-attendance records. The conservative $0.265 treats those days as zero additional cost, producing the lower, safer negotiating floor. The strict $0.284 removes those incomplete days from the calculation. All commercial conversations use $0.265 — it is harder to dispute and still proves every customer is below cost.

---

## Quick Start

```bash
cd "Phase 3 Tool"
pip install -r requirements.txt

# Reset the database before presenting (puts Bravo ticket into "In Progress" for the demo)
python reload_db.py

streamlit run app.py
```

The app auto-loads 10 pre-built findings from `data/findings.json` on first run.

> **Note:** Run from the `Phase 3 Tool/` directory. SQLite cannot write to some network-mapped drives — if you get a disk I/O error, copy the folder to a local drive first.

**Optional AI (free):** Add `GROQ_API_KEY` to your environment to enable live Q&A. Without it, all pre-computed insights still display — the AI degrades gracefully and never goes blank.

---

## Pages

### 1. Dashboard
**Who it's for:** All roles — but the content changes based on who's logged in.

Switch the **Role** selector in the sidebar (CEO / Commercial Lead / Site Manager). The entire dashboard re-filters to show only what that role needs to act on today:

- **CEO** — recovery progress, portfolio health, decisions requiring sign-off, monthly cadence
- **Commercial Lead** — pricing action queue, customer re-billing priorities, weekly cadence
- **Site Manager** — data quality checklist, exception rates by customer, daily cadence

The **AI Next Action** card at the top of each view suggests the single most important thing that role should do today, based on live ticket state.

---

### 2. Customer Profitability
**Who it's for:** CEO and Commercial Lead.

30 customers ranked from most to least profitable — using true ABC margin (what's left after all real costs), not the reported figure.

Each customer card shows:
- **True margin** — the real number after labour, overhead, and unbilled work
- **Reported margin** — what the current system shows (~96% for almost everyone)
- **The gap** — where the loss is coming from (below-cost rate, unbilled picks, overhead)
- **Recommendation** — REPRICE / REBILL / MONITOR / REVIEW in plain language
- **Ask AI about [Customer]** — live Groq-powered per-account strategy brief

**Key accounts:**

| Customer | True Margin | Key Issue | Recommended Action |
|---|---|---|---|
| Bravo FMCG | 29% | Charged $0.12/pick vs $0.265 true cost | Reprice to $0.19 — Month 1 pilot |
| Delta Manufacturing | 19.5% | Below-cost rate + 14% exception rate (unbilled re