# Profit Lens — Phase 3 Working Prototype

**Monthly Management Operating System for Warehouse Profit Recovery**

Mattingly AI & Operations Hackathon 2026 · Kishan Gowda

---

## The Problem It Solves

Mattingly's current reporting shows every customer at ~96% gross margin. That number is wrong.

Activity-Based Costing (ABC) analysis of the actual warehouse data reveals:
- **True pick cost: $0.265/pick** (conservative floor, all-in labour; engine-strict $0.284/pick)
- **Charged rate: $0.12–$0.17/pick** — every customer is being served below cost
- **$1.86M/year** of identified exposure (conservative floor; engine-verified $2.09M)
- **$1.15M** is realistically recoverable in 9 months

The tool doesn't just surface the problem — it closes the loop. Findings become tickets. Tickets get assigned to the right person. Actions move money. The recovery bar proves it worked.

---

## What This App Is

A Streamlit management operating system that turns Profit Lens findings into live, role-specific action queues with full ticket tracking, customer intelligence, and a recovery tracker.

**One-sentence demo:** Upload findings → tickets auto-generated → each role works their queue → closing a ticket moves the recovery bar → Customer Intelligence shows WHY each account is unprofitable.

---

## Quick Start

```bash
cd "Phase 3 Tool"
pip install -r requirements.txt

# Reset DB before first run (sets Bravo to In Progress for demo)
python reload_db.py

streamlit run app.py
```

On first run, the app auto-loads 10 pre-built findings from `data/findings.json`.

> **Note:** Run from the `Phase 3 Tool/` directory. SQLite cannot write to some network-mapped paths — if you get a disk I/O error, copy the folder to a local drive first.

**Optional AI (free):** Set `GROQ_API_KEY` in your environment to enable live "Ask Profit Lens" Q&A. Without a key, all pre-computed insights still display — the AI degrades gracefully and never goes dark.

---

## Pages & What They Do

### 1. Dashboard
Role-specific home screen. Opens with a live KPI bar showing:
- **Recovery progress** ($ recovered vs $1.15M target)
- **Total exposure** ($1.86M identified)
- **Open tickets** count
- **Portfolio health** breakdown (Action Required / Watch / Healthy / Opportunity)

Switch roles in the sidebar — CEO, Commercial Lead, and Site Manager each see a distinct dashboard with role-relevant KPIs and AI-suggested next actions.

**AI Chat:** A floating chat button (bottom-right) opens "Ask Profit Lens" — a Groq-powered assistant pre-loaded with all warehouse data, pick costs, customer margins, and the recovery plan.

---

### 2. Customer Profitability
The deepest view. 30 customers ranked by true margin. Each card shows:

- **True vs Reported Margin** — the gap between ~96% reported and the ABC reality
- **Driver Breakdown** — donut chart splitting the loss by cause
- **Key metrics:** picks/year, rate charged, proposed rate, true cost, full annual exposure
- **Recommendation card** — REPRICE / REBILL / MONITOR / REVIEW with plain-English rationale
- **Ask AI about [Customer]** button — live Groq-powered account strategy

**Key accounts (engine-verified):**

| Customer | True Margin | Key Issue | Action |
|---|---|---|---|
| Bravo FMCG | 29.1% | Below-cost pick rate | REPRICE — Month 1 pilot |
| Delta Manufacturing | 19.5% | Pricing + unbilled exceptions | REPRICE + REBILL |
| Charlie Medical | 39.9% | 320K unbilled picks/year | REBILL — use their own logs |
| Medisupply Australia | ~65% | Minor rate gap | MONITOR — Wave 2 |
| Home & Living Products | ~53% | Underutilised capacity | SALES REVIEW — grow or redeploy |

---

### 3. Action Queue
The working view for Commercial Lead and Site Manager.

- **Role filter** (sidebar): queue shows only your tickets
- **Status filter:** To Do / In Progress / Done / Blocked
- **Confidence badges:** HIGH (green, engine-verified) / MED (amber, modelled)
- **Expand any ticket** → AI-generated root cause explanation + recommended action
- **Status dropdown** — change it here, recovery bar updates immediately

**Closing a ticket is the demo moment:** mark Bravo FMCG (F001) as Done → recovery bar jumps from $0 to **$144K / 12.5%**.

---

### 4. Recovery Tracker
The closed-loop proof.

**Recovery Bar:** Recovered dollars vs $1.15M target — updates in real time as tickets close.

**Reconciliation Panel:** How $2.09M total opportunity breaks down:
- $1.72M pricing leakage (below-cost rates × annual volume)
- $375K unbilled work (Delta $147K + Charlie $127K + others $101K)
- No double-count with F011 (structural) which is excluded from ticket aggregation

**Operating Cadence:** Daily (Site Manager) / Weekly (Commercial Lead) / Monthly (CEO).

---

### 5. Load Data
Upload a new findings.json or click **Reload Findings** to reset to the pre-loaded demo state. The Live Engine Analysis section lets you upload the raw xlsx and run the analysis engine in-app.

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

**Recovery target:** $1.15M · **Total exposure:** $1.86M (conservative floor)

---

## Role-Based Views

| Role | Ticket Queue | Strategic Focus |
|------|-------------|-----------------|
| CEO | All 10 tickets | Recovery progress, approve pilots, portfolio decisions |
| Commercial Lead | F001–F005, F011, F013 (pricing & billing) | Reprice, re-bill, sequencing |
| Site Manager | F006, F007, F010 (ops & hygiene) | Floor exceptions, data quality |

---

## Demo Flow (6 minutes)

| Step | Page | What to Show | What It Proves |
|------|------|-------------|----------------|
| 1 | Load Data | Upload xlsx → Live Engine Analysis runs | Raw data → live AI analysis |
| 2 | Dashboard (CEO) | Recovery target, exposure, AI Next Action | The problem at a glance |
| 3 | Dashboard (Commercial Lead) | Distinct view + different AI action | Role-based intelligence |
| 4 | Action Queue | Open F001 (Bravo) → HIGH confidence badge → "Explain with AI" | Evidence-backed findings |
| 5 | Customer Profitability | Expand Bravo → "Ask AI about Bravo" | Per-account intelligence |
| 6 | Recovery Tracker | Reconciliation panel → mark Bravo Done → bar jumps to $144K | Closed loop |
| 7 | Management Q&A | Ask "Which customer should I call first?" | AI layer on top |

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI | Streamlit |
| Analysis Engine | engine.py (pandas + Activity-Based Costing) |
| Data persistence | SQLite (swap to Postgres for production) |
| Charts | Plotly (recovery bar, driver donut, margin comparison) |
| AI layer | Groq API — Llama 3.3 70B (degrades gracefully without key) |
| Data | pandas + JSON findings format |

---

## File Structure

```
Phase 3 Tool/
├── app.py              # All UI: pages, layout, charts, AI chat
├── database.py         # SQLite layer — all DB operations isolated here
├── engine.py           # ABC analysis engine — run once per warehouse per month
├── reload_db.py        # Demo setup script — run before presenting
├── requirements.txt    # Dependencies
├── profit_lens.db      # Auto-created SQLite database
├── .streamlit/
│   └── config.toml     # Streamlit theme config
└── data/
    └── findings.json   # Pre-loaded 10 findings + 30 customer profiles
```

---

## Architecture Note

The separation of `engine.py` (analysis) → `findings.json` (output) → `app.py` (operating system) is intentional. The analysis engine runs once a month per warehouse and drops a JSON. The OS runs continuously. This is how it scales to 10+ sites without rebuilding the interface — point the engine at a new warehouse, drop the JSON, done.

---

*Profit Lens · Kishan Gowda · Mattingly AI & Operations Hackathon 2026*
#   M a t t i n g l y  
 