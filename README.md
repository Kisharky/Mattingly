# Profit Lens — AI-Powered Warehouse Profit Intelligence
### Mattingly AI & Operations Hackathon 2026 · Kishan Gowda

---

## One-Line Summary

Profit Lens finds every dollar Mattingly is losing on warehouse operations, turns each loss into a role-owned action ticket, and tracks live delivery against a recovery target — powered by a hybrid AI architecture that routes reasoning tasks to NVIDIA Nemotron and conversation to Groq LLaMA 3.3 70B.

---

## The Problem

Mattingly's standard reporting shows every customer at ~96% gross margin. That number is structurally misleading — it ignores the true cost of picking.

The ABC (Activity-Based Costing) engine calculates:

| Metric | Value | What It Means |
|---|---|---|
| True pick cost | **$0.265/pick** | Conservative floor (4 days missing T&A data treated as zero cost) |
| True pick cost (strict) | **$0.284/pick** | Removes the 4 incomplete days from calculation |
| Charged rate range | **$0.12–$0.17/pick** | Every customer is being served below true cost |
| Total identified opportunity | **$2.66M/year** | $1.86M engine-derived pricing leakage + $0.80M qualitative ops exposure (F014/F015) |
| 9-month recovery target | **$1.15M** | Achievable through repricing and re-billing — no customer exits |

**Operational exposure breakdown:**
- F014 Delta exception-handling labour drain: **$446K/year** — premium labour absorbed without billing recovery
- F015 Urgent-order throughput penalty: **$349K/year** — disruption cost from non-standard fulfilment patterns

> **Why two pick costs?** The conservative $0.265 is the negotiating floor — it's harder to dispute and still proves every customer is below cost. The strict $0.284 is used for internal modelling. All commercial conversations use $0.265.

---

## How It Works

```
UPLOAD → ANALYSE → TICKET → ACT → RECOVER
```

| Stage | What Happens |
|---|---|
| **UPLOAD** | Drop the warehouse Excel file. The engine resolves sheet names dynamically — handles renamed or reordered tabs, concatenates monthly variants (M1/M2/M3...), and derives the annualisation factor from the months actually present. |
| **ANALYSE** | ABC engine calculates true pick cost, compares to each customer's contracted rate, identifies exception volumes, and flags data gaps — all from the raw dataset. |
| **TICKET** | Every gap becomes a finding ticket with a dollar value, priority, assigned role, and status. 10 pre-built findings load from `data/findings.json` on first run. Live upload regenerates the engine KPIs from the actual dataset; ticket templating from uploaded files is v2 (the Action Queue continues to show the findings.json tickets after upload). |
| **ACT** | Role-filtered queues: CEO approves and tracks, Commercial Lead reprices and rebills, Site Manager closes data gaps. AI suggests the single highest-impact action for each role based on live ticket state. |
| **RECOVER** | Closing a ticket moves the live recovery bar. The Impact Tracker shows which actions have converted to measurable profit improvement — closing the loop from finding to value. |

---

## AI Architecture

Profit Lens uses a hybrid LLM setup with deliberate model routing:

| Task | Model | Why |
|---|---|---|
| **AI Suggested Next Action** (Dashboard) | NVIDIA Nemotron | Multi-step reasoning over ranked tickets + role context |
| **Ticket Enhancement** (ROOT CAUSE / NEXT STEP) | NVIDIA Nemotron | Structural diagnosis — reasoning model outperforms chat model here |
| **Notifications Situational Brief** | NVIDIA Nemotron | Cross-ticket dependency reasoning |
| **Management Q&A chatbot** | Groq LLaMA 3.3 70B | Fast, conversational, pre-computed numbers in system prompt |
| **Inline role Q&A** (Dashboard) | Groq LLaMA 3.3 70B | Sub-second response for quick queries |

**Graceful degradation:** NVIDIA unavailable → falls back to Groq. Both unavailable → static pre-computed fallback. The app never goes blank.

**Security constraints hard-coded in architecture:**
- LLMs never analyse raw Excel data
- LLMs never generate financial findings
- LLMs never send external reports or trigger actions outside the app
- All dollar figures flow from `engine.get_headline_figures()` → `_HF` dict → system prompt

---

## Quick Start

```bash
cd "Phase 3 Tool"
pip install -r requirements.txt

# Reset DB before a demo (puts Bravo ticket into "In Progress" — the live demo state)
python reload_db.py

streamlit run app.py
```

The app auto-loads 10 pre-built findings from `data/findings.json` on first run.

> **Note:** Run from the `Phase 3 Tool/` directory. SQLite cannot write to some network-mapped drives — if you get a disk I/O error, copy the folder to a local drive first.

### API Keys (optional — AI degrades gracefully without them)

Create `.streamlit/secrets.toml` (already gitignored):

```toml
GROQ_API_KEY   = "your-groq-key"       # free at console.groq.com
NVIDIA_API_KEY = "your-nvidia-key"     # free at build.nvidia.com
```

Without keys: all pre-computed insights still display. AI cards fall back to role-specific static text. Nothing goes blank.

---

## Pages

### 1. Dashboard
Role-filtered view — the entire page changes based on the sidebar Role selector:

- **CEO** — recovery progress bar, portfolio health heatmap, decisions requiring sign-off, monthly cadence checklist, Best/Likely/Worst recovery scenarios, tiered pricing worked example
- **Commercial Lead** — pricing action queue ranked by dollar impact, weekly cadence, evidence-gathering workflow
- **Site Manager** — data quality checklist with today's date, exception rates by customer, daily ops cadence, F007 labour gap status

**AI Suggested Next Action** at the top of each view: Nemotron reads the live ticket queue and surfaces one ACTION / WHY / NEXT STEP tailored to that role's decision authority.

### 2. Customer Profitability
30 customers ranked by true ABC margin. Each card shows true margin, reported margin, root cause, and a recommendation (REPRICE / REBILL / MONITOR / REVIEW).

**Key accounts:**

| Customer | True Margin | Key Issue | Action |
|---|---|---|---|
| Bravo FMCG | 29% | $0.12/pick vs $0.265 true cost | Reprice to $0.19 — Month 1 pilot |
| Delta Manufacturing | 19.5% | Below-cost rate + 14% exception rate | Reprice + rebill exceptions — Month 2 |
| Charlie Medical | 22% | $127K unbilled pick exceptions | Issue credit note and rebill — immediate |

**Methodology caveat:** Margins are a pricing-and-billing view, not a measured-per-customer P&L. Missing input: Product ID join key on transaction records (top data quality priority).

### 3. Action Queue
Every finding as a prioritised ticket. Expandable — shows description, dollar impact, owner, status dropdown, and an AI Enhance button (Nemotron: ROOT CAUSE + NEXT STEP). Filtered by role.

### 4. Impact Tracker
Live recovery progress against the $1.15M target. Cumulative value by month across the 9-month roadmap.

### 5. Operations
Picks-per-hour productivity, exception volume by customer, bottleneck analysis.

### 6. Information Gaps
Data quality scorecard — confidence ratings for each finding, what's blocking full quantification, who owns resolution.

**CEO Monthly Data Quality Priorities:**
1. 🔴 OPEN — Product ID join key on transaction records (IT / Data Engineering)
2. 🟡 OPEN — F007 4-day labour gap in timesheet data (Site Manager)
3. 🟡 OPEN — Seasonality stable on available data (M1/M2 volume ratio 0.84–1.18 across all 30 customers); 12-month WMS history validation pending before repricing

### 7. AI Assistant (Management Q&A)
Full conversational chatbot on Groq LLaMA 3.3 70B. System prompt built from live `_HF` headline figures — cites actual engine output, never hardcoded numbers. Role-specific context loads on entry.

### 8. Load Data (Live Upload)
Upload the warehouse Excel file to regenerate the engine KPIs from the actual dataset. Sheet resolver handles renamed or reordered tabs. Ticket templating from uploaded files is planned for v2 — the Action Queue continues to show the findings.json tickets after upload, and an upload guard alerts if pre-baked tickets are still loaded after a fresh upload.

### 9. Tickets (Admin)
Database view — all tickets, raw status, dollar impact. Reset to default or reload from findings.json.

---

## File Structure

```
Phase 3 Tool/
├── app.py                  # Main Streamlit app (~3,376 lines)
├── engine.py               # ABC costing engine — all financial calculations
├── llm.py                  # Hybrid LLM routing layer (Nemotron + Groq)
├── database.py             # SQLite ticket store
├── operations_pages.py     # Operations + Information Gaps pages
├── requirements.txt        # streamlit, pandas, plotly, groq, openai
├── reload_db.py            # Demo reset script
├── data/
│   └── findings.json       # 10 pre-built findings (auto-loads on first run)
├── .streamlit/
│   ├── config.toml         # Dark theme, wide layout
│   └── secrets.toml        # API keys — gitignored, never committed
└── README.md
```

---

## Engine Design

- **Priority-ordered keyword resolver** — "customer pric" beats "pric" so "Customer Pricing" wins over "Standard Pricing" without ambiguity
- **Dynamic annualisation** — `annualise_factor = 12.0 / months_in_data` derived from actual sheet count
- **Multi-month concatenation** — M1/M2/M3 activity sheets stacked and treated as one dataset
- **Clear error messages** — missing sheets surface a human-readable error naming exactly what was expected
- **Named constants** — `OPS_EXPOSURE_F014_F015 = 446_000 + 349_000` with comments; no bare magic numbers
- **Single source of truth** — `get_headline_figures()` returns `_HF` dict; every dollar figure in the UI, AI system prompt, and fallback KB reads from `_HF`, never from a hardcoded literal

---

## Recovery Roadmap

| Month | Milestone | Cumulative Recovery |
|---|---|---|
| 1 | Bravo FMCG repricing pilot ($144K/yr) | $144K |
| 2 | Delta Manufacturing evidence + exception rebilling | $272K |
| 3 | Delta repricing + Charlie Medical rebill ($127K) | $416K |
| 6 | Sites 2–3 onboarding | $850K |
| 9 | Full portfolio — all 30 customers on corrected rates | $1.15M |

| Scenario | Recovery | Assumption |
|---|---|---|
| 🟢 Best | $1.4M | All customers accept new rates; no churn |
| 🟡 Likely | $1.15M | 80% acceptance; 2 customers negotiate down |
| 🔴 Worst | $0.75M | 50% acceptance; 3-month delay on Delta |

---

## Why This Wins

Most hackathon submissions find the problem. Profit Lens closes the loop:

1. **Finding → specific dollar amount**, not a directional observation
2. **Ticket → owned by a named role** with a status and a deadline
3. **AI action → Nemotron reasons over live ticket state**, not a generic recommendation
4. **Recovery tracking �