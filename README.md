# Profit Lens — Phase 3 Working Prototype

**Warehouse Profit Recovery · Monthly Management Operating System**

Mattingly AI & Operations Hackathon 2026 · Kishan Gowda

---

## What This Tool Does — In One Sentence

Profit Lens finds every dollar Mattingly is losing on warehouse operations, turns each loss into an owned action, and tracks the money as it comes back.

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
| **RECOVER** | Closing a ticket moves real dollars onto the Recovery Bar. The tool proves the money came back. |

---

## The Problem (Why This Exists)

Mattingly's standard reporting shows every customer at ~96% gross margin. That number is wrong — it ignores the true cost of picking.

The ABC engine calculates:

- **True pick cost: $0.265/pick** — what it actually costs Mattingly to pick one item, all labour included. The more precise engine figure is $0.284/pick (labour only, no overhead allocation).
- **Charged rate: $0.12–$0.17/pick** — every customer is being served below cost.
- **$1.86M/year** in identified exposure (at the $0.265 conservative floor).
- **$1.15M** is realistically recoverable in 9 months without losing a single customer.

> **Why two pick-cost numbers?** $0.265/pick is the conservative, all-in floor used for all negotiations — it includes overhead. $0.284/pick is the engine's labour-only rate. The difference is intentional: always negotiate from the conservative number so there's no room to argue.

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
| Delta Manufacturing | 20% | Below-cost rate + 14% exception rate (unbilled rework) | Reprice + rebill exceptions |
| Charlie Medical | 40% | 320K picks/year billed as 133K | Rebill using client's own exception log |
| Home & Living Products | 53% | Fixed fee at 47% capacity — idle space | Sales review: grow the account or redeploy |

> **Jargon note — "true margin":** The percentage of revenue left over after paying all real costs. A margin of 29% means for every $100 Mattingly earns from that customer, $71 is spent on labour and overhead, leaving $29 profit.

---

### 3. Action Queue
**Who it's for:** Commercial Lead and Site Manager (their working view).

The queue filters automatically to the logged-in role's tickets. Each ticket shows:
- Dollar impact, priority, and confidence level (HIGH = engine-verified data; MED = modelled estimate)
- Status: To Do / In Progress / Done / Blocked
- **Explain with AI** button — root cause and recommended next step

**The demo moment:** Mark Bravo FMCG (F001) as Done → the recovery bar on the Recovery Tracker jumps from $0 to **$144K / 12.5% of target**. That's the closed loop.

---

### 4. Recovery Tracker
**Who it's for:** CEO — monthly review.

Shows the recovery target ($1.15M) vs dollars actually recovered as tickets close. The reconciliation panel breaks down the full $2.09M opportunity:

- **$1.72M** — pricing leakage (below-cost rates × annual volume across all customers)
- **$375K** — unbilled work (Delta $147K + Charlie $127K + others $101K)

> **Jargon note — "leakage":** Money Mattingly earned by doing the work but never invoiced. Not a future opportunity — it's revenue for services already delivered that was never collected.

---

### 5. AI Advisor
**Who it's for:** Any role, any question.

A full-page conversational AI pre-loaded with all warehouse data: pick costs, customer margins, ticket status, the recovery plan. Ask it anything:

- *"Which customer should we call first?"*
- *"What's the root cause of Delta's exception rate?"*
- *"How do we explain the rate increase to Bravo?"*

Also accessible via the floating chat button (bottom-right corner) on any page.

---

### 6. Load Data
Upload a new `findings.json` or raw `.xlsx` dataset. The Live Engine Analysis section runs the full ABC engine in-app and displays engine-computed pick costs, per-customer profitability, and leakage figures from the real data.

---

## Pre-Loaded Findings (10 Tickets)

| ID | Type | Customer | $ Impact | Owner | Priority |
|----|------|----------|----------|-------|----------|
| F001 | Pricing Leakage | Bravo FMCG | $144K/yr | Commercial Lead | HIGH |
| F002 | Pricing Leakage | Delta Manufacturing | $198K/yr | Commercial Lead | HIGH |
| F003 | Pricing Leakage | Charlie Medical | $102K/yr | Commercial Lead | HIGH |
| F004 | Unbilled Work | Delta Manufacturing | $147K/yr | Commercial Lead | CRITICAL |
| F005 | Unbilled Work | Charlie Medical | $127K/yr | Commercial Lead | HIGH |
| F006 | Data Hygiene | All | — | Site Manager | MEDIUM |
| F007 | Data Hygiene | All | — | Site Manager | MEDIUM |
| F010 | Productivity | Delta Manufacturing | $62K/yr | Site Manager | MEDIUM |
| F011 | Structural Pricing | All Customers | $1.49M/yr | Commercial Lead | CRITICAL |
| F013 | Fixed-Fee Capacity | Home & Living Products | $276K/yr | Commercial Lead | MEDIUM |

---

## Role Guide

| Role | Their Queue | What They're Solving |
|------|-------------|----------------------|
| **CEO** | All 10 tickets | Is the recovery on track? Which pilots to approve? |
| **Commercial Lead** | F001–F005, F011, F013 | Reprice below-cost contracts. Rebill unbilled work. |
| **Site Manager** | F006, F007, F010 | Close data gaps. Fix floor exception processes. |

---

## Demo Flow (6 Minutes)

| Step | Page | What to Show | What It Proves |
|------|------|-------------|----------------|
| 1 | Load Data | Upload xlsx → Engine runs → Live pick cost output | Real data, real engine — not static slides |
| 2 | Dashboard (CEO) | Recovery bar, portfolio health, AI Next Action | The problem in 10 seconds |
| 3 | Dashboard (Site Manager) | Switch role → completely different view | Role-based operating system |
| 4 | Customer Profitability | Expand Bravo → true margin 29% → Ask AI | Per-account intelligence, plain English |
| 5 | Action Queue | Open F001 → HIGH confidence → Explain with AI | Evidence-backed, not opinion |
| 6 | Recovery Tracker | Mark Bravo Done → bar jumps $144K / 12.5% | Closed loop — money tracked back |
| 7 | AI Advisor | "Which customer should I call first?" | Management Q&A layer |

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Analysis Engine | `engine.py` — pandas + Activity-Based Costing |
| Data Persistence | SQLite (production swap: Postgres) |
| Charts | Plotly |
| AI Layer | Groq API — Llama 3.3 70B (degrades gracefully without a key) |

---

## File Structure

```
Phase 3 Tool/
├── app.py              # All UI: pages, layout, charts, role views, AI chat
├── database.py         # SQLite layer — all DB operations isolated here
├── engine.py           # ABC analysis engine — runs once per warehouse per month
├── reload_db.py        # Demo reset script — run before presenting
├── requirements.txt    # Python dependencies
├── profit_lens.db      # Auto-created SQLite database
├── .streamlit/
│   └── config.toml     # Streamlit theme
└── data/
    └── findings.json   # 10 pre-loaded findings + 30 customer profiles
```

---

## Architecture Note

`engine.py` (analysis) → `findings.json` (output) → `app.py` (operating system) are deliberately separated. The engine runs once a month per warehouse and drops a JSON file. The operating system runs continuously on top of it. Scaling to 10 sites means pointing the engine at each new warehouse and dropping a new JSON — no UI changes required.

---

*Profit Lens · Kishan Gowda · Mattingly AI & Operations Hackathon 2026*