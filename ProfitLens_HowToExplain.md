# Profit Lens — How to Explain the Tool

**Talking points, page walk-through, and demo script for judges, evaluators, or anyone who asks**

Mattingly AI & Operations Hackathon 2026 · Kishan Gowda

---

## The One-Paragraph Pitch

Mattingly currently shows every customer at ~96% gross margin. That number is wrong — it's calculated by allocating cost by revenue share, not by actual activity. When you run Activity-Based Costing on the real data, every single customer is being served below the true cost of a pick. The business is profitable on paper and bleeding in reality. Profit Lens surfaces that $2.66M opportunity ($1.86M pricing leakage + $0.80M operational), turns each finding into a ticket owned by the right person, and tracks recovery against a $1.15M target — with a live bar that proves the closed loop is working. It's not a dashboard you check once. It's a monthly management operating system.

---

## The Problem, in Plain Terms

**What Mattingly does:** Third-party logistics warehouse. Pick, pack, store, value-add services for ~30 customers. Revenue comes from per-pick fees and fixed contracts.

**What the current system shows:** Every customer at ~96% margin. Looks fine. CEO sees no problem.

**What's actually happening:**
- True all-in labour cost to perform one pick: **$0.265**
- What Mattingly charges: **$0.12–$0.17 per pick**
- Net result: every pick loses money. More volume = more losses.
- Example: Bravo FMCG has 2 million picks/year at $0.12 each. Revenue: $240K. True cost: $530K. Annual subsidy: **$298K.**
- The reporting system doesn't even allocate $25.5K of utilities — it just disappears

**Why it's invisible:** The current method calculates gross margin as (revenue minus direct labour per customer). It never measures what a pick actually costs end-to-end. It's not fraud — it's a broken accounting method that the whole industry uses.

**The $1.86M breakdown:**
- $1.49M from below-cost pick rates (all customers, structural)
- $275K from work performed but never invoiced ($147K Delta, $127K Charlie)
- ~$60K from productivity losses (Delta bottleneck / exception volume)

---

## What the Tool Does — Step by Step

### Step 1: Analysis (Phase 1 Engine)
The `engine.py` ingests the raw warehouse data (`.xlsx`), cleans it, assigns labour hours to each customer via activity-based costing, and calculates the true cost per pick. It outputs a `findings.json` — a structured list of dollar-valued problems, each with a customer, a priority, a recommended action, and a named owner.

This is the intelligence layer. It runs once a month per warehouse and can be pointed at any site.

### Step 2: Operating System (Phase 3 App)
`app.py` consumes the findings JSON and turns it into a live management operating system. Each finding becomes a ticket. Each ticket is assigned to a role. Each role gets a filtered queue. When a ticket is marked Done, the recovery bar moves.

This is the execution layer. It runs continuously. The CEO, Commercial Lead, and Site Manager all log in, see only their queue, and work through it on a cadence: daily, weekly, monthly.

### Step 3: The Closed Loop
The Recovery Tracker page shows recovered dollars vs $1.15M target — in real time, updated every time a ticket closes. This is the proof. Not a projection. Not a promise. Actual recovered dollars, visible on a single screen.

---

## Page-by-Page Walk-Through

### Dashboard — "The CEO View"

**What it shows:**
- 4 KPI cards: Recovery Progress / Total Exposure / Open Tickets / Portfolio Health
- Role-filtered action queue (switch roles in sidebar — queue re-filters instantly)
- Management insights panel: pre-computed strategic callouts
- Floating "Ask Profit Lens" chat button (bottom-right)

**What it solves:**
The CEO currently has no single view of where profit is leaking and what's being done about it. This page gives them: the size of the opportunity ($2.66M), the recovery target ($1.15M), what's open, and a color-coded health view of the whole customer portfolio — in 30 seconds.

**The key moment:** Switch from CEO → Commercial Lead → Site Manager in the sidebar. The queue changes instantly. Each role sees only their work. No noise, no overwhelm, clear ownership.

---

### Customer Intelligence — "The WHY Screen"

**What it shows:**
- True vs Reported Margin (side-by-side bar chart — the gap is the story)
- Driver Breakdown donut (what's causing the loss: pricing / unbilled / exceptions / productivity)
- Key metrics: picks/year, rate charged vs proposed vs true cost
- Projected margin post-fix
- Recommendation card: REPRICE / REBILL / MONITOR / SALES REVIEW
- All tickets linked to this customer

**What it solves:**
You can't go into a repricing negotiation without knowing WHY the customer is unprofitable. "Your rate is too low" is not a business conversation. "Your 2 million picks/year at $0.12 costs us $0.265 per pick — we lose $298K/year serving you at that rate" is. This page builds the evidence package for every commercial conversation.

**The demo moment — Delta Manufacturing:**
- Reported margin: ~96%
- True margin: **19.5%**
- Projected margin after repricing + rebilling: **61%**
- Two separate problems: below-cost rate ($198K/yr) AND $147K/yr of unbilled exceptions
- The donut shows both — side by side. The conversation with Delta is different from the conversation with Bravo, and this screen explains why.

**All 5 customers at a glance:**

| Customer | True Margin | The Problem | The Ask |
|---|---|---|---|
| Bravo FMCG | 29.1% | 2M picks/yr at $0.12 — every pick loses $0.145 | Reprice to $0.19 |
| Delta Manufacturing | 19.5% | Below-cost rate + $147K unbilled exceptions | Reprice + rebill |
| Charlie Medical | 38.9% | 320K picks performed, never invoiced | Rebill — use their own logs |
| Pacific Healthcare | 65.2% | Minor rate gap, low exceptions | Monitor — Wave 2 |
| Epsilon Wholesale | 53% | Fixed fee, 47% capacity utilisation | Grow account or redeploy |

---

### Action Queue — "The Work Queue"

**What it shows:**
- Tickets filtered by your role (Commercial Lead or Site Manager)
- Status filter: To Do / In Progress / Done / Blocked
- Each ticket: ID, type badge, customer, priority badge, dollar impact, AI explanation, action, status dropdown
- Change status here — recovery bar updates in real time

**What it solves:**
Most ops tools show you everything. This one shows you only what you own. The Commercial Lead doesn't need to see the data hygiene tickets. The Site Manager doesn't need to see the repricing queue. Role-based filtering is the mechanism that makes this a management operating system rather than a reporting tool.

**The demo moment:** As Commercial Lead, open F001 (Bravo FMCG). Read the AI explanation: *"Bravo is the most actionable opportunity in the building. 2 million picks at 12 cents — every pick costs 26.5 cents. Move to 19 cents, recover $144K. At 19 cents, Bravo still earns 33% margin. Win-either-way."* Mark it Done. Go to Recovery Tracker. Watch the bar jump.

---

### Tickets — "The Operational Layer"

**What it shows:**
- All tickets with full detail — expandable cards
- Filters: role / status / priority / customer / finding type
- Comment thread per ticket (timestamped, role-tagged)
- Create manual ticket (findings the JSON didn't catch)
- Edit any ticket field inline

**What it solves:**
Real work isn't clean. The Site Manager finds something on the floor that the analysis didn't catch. The Commercial Lead needs to note what the customer said in the repricing call. A ticket needs to be escalated. This page handles all of that — it's the living record of what's happening on the ground, not just what the data said at month-end.

**The comment thread is underrated:** "Customer pushed back on $0.19 — counter-proposed $0.17 for 6-month lock-in. Recommend accept." That note lives on the ticket. The CEO can see it. That's institutional memory.

---

### Recovery Tracker — "The Proof"

**What it shows:**
- Large visual recovery bar: dollars recovered vs $1.15M target (% + $ remaining)
- **Recovered (Done):** closed tickets with dollar value, date, customer, type
- **Open Pipeline:** remaining tickets ranked by dollar impact
- **Operating Cadence:** the management rhythm the tool runs on

**What it solves:**
Every initiative says "we'll recover X dollars." Almost none of them can prove it. The Recovery Tracker is the proof mechanism — not projected recovery, not modelled recovery, actual tickets closed, each worth a dollar amount, visible on one screen. When Bravo signs the repricing, F001 goes Done. $144K moves from pipeline to recovered. The bar moves. That's the closed loop.

**The cadence section matters:** It tells the organisation what to do and when:
- **Daily:** Site Manager closes data hygiene tickets and reviews exception volumes
- **Weekly:** Commercial Lead works the pricing/billing queue, ranked by dollar impact
- **Monthly:** CEO reviews the recovery bar vs target, approves next phase

---

### Load Data — "The Handoff Point"

**What it shows:**
- Upload a new `findings.json` (from a fresh monthly analysis)
- Reset to demo data
- Preview of what's loaded

**What it solves:**
In production, the analysis engine runs at month-end, outputs a new findings JSON, and someone drops it here. The operating system picks it up, generates new tickets, and the cycle starts again. This is how the tool stays live month after month without anyone rebuilding anything. It's also how you onboard a new warehouse — run the engine on their data, drop the JSON, done.

---

## The AI Layer — "Ask Profit Lens"

**What it is:** A Groq-powered assistant (Llama 3.3 70B) pre-loaded with every number from the analysis: true pick cost, customer margins, recovery plan, ticket status, operating cadences.

**What you can ask it:**
- "Which customer should we approach first?"
- "What happens if Bravo walks?"
- "What's the ROI on the Month 1 pilot?"
- "Why is Delta's margin so much worse than Charlie's?"
- "What should the Site Manager do this week?"

**Why it degrades gracefully:** If there's no Groq API key, all the pre-computed AI explanations on each ticket still display. The system never goes dark — the insights are baked in, the live Q&A is the bonus layer.

**The key design principle:** The AI assistant can only tell you things that are in the data. It doesn't speculate. If you give it a wrong number ("the pick cost is $0.20"), it corrects you and gives you the right one. This is intentional — in a financial context, hallucination is worse than silence.

---

## How to Demo It in 7 Minutes

**Minute 1 — The Problem:**
Open Dashboard as CEO. "This is what Mattingly sees today: $2.66M of opportunity, 12 open findings, and a portfolio where most customers are flagged Action Required or Watch. None of this was visible before."

**Minute 2 — The Gap:**
Click Customer Intelligence. Select Delta Manufacturing. "Reported margin: 96%. True margin: 19.5%. That's a 79-point gap — invisible in their current system. And it's not one problem, it's two." Show the donut.

**Minute 3 — All Customers:**
Cycle through the 5 customers quickly. "Every customer is below cost. The business is structurally upside-down on pick pricing. Profit Lens found this in two months of data."

**Minute 4 — The Work Queue:**
Switch to Commercial Lead. Open Action Queue. "Six tickets. All owned by Commercial Lead. Ranked by dollar impact. Each one has an AI explanation of why it matters and exactly what to do. No ambiguity."

**Minute 5 — The Closed Loop:**
Open F001 (Bravo FMCG). Read the AI explanation aloud. Mark it Done. Go to Recovery Tracker. "$144K recovered. 12.5% of target. One ticket closed, one negotiation won."

**Minute 6 — The Ops Side:**
Switch to Site Manager. Show their queue: data hygiene, exception volume, bottleneck. "The Site Manager doesn't see the repricing queue. The Commercial Lead doesn't see the ops tickets. Each person has exactly what they own."

**Minute 7 — The Ask:**
Recovery Tracker. "The target is $1.15M. Month 1 is one conversation with Bravo. The system scales to all 10 warehouses with the same interface — you point the engine at a new site, drop a JSON, and it's live. $50–60K to production-harden. Pays for itself in Month 1."

---

## Anticipate These Questions

**"How is $0.265/pick calculated?"**
Total allocated labour cost divided by total picks, Jan–Feb 2026. Conservative floor — the strict calculation puts it at $0.284. The $0.265 is the number we defend. Every finding is directionally identical under both; the range is disclosed.

**"What if a customer walks when you reprice?"**
That's the win-either-way design. Bravo's full exposure is $298K/yr. At the proposed $0.19 rate, they earn 33% margin — they have no incentive to leave. If they do walk, we stop a $298K annual subsidy. There is no bad outcome.

**"Why Bravo first?"**
Cleanest case: one problem (pricing only), largest volume (2M picks), most straightforward negotiation. Delta has two problems. Charlie needs physical log reconciliation first. Bravo is the proof point that makes every subsequent conversation easier.

**"What's the data quality caveat?"**
4 days of labour data is missing (F007 ticket). The analysis covers Jan–Feb only — seasonal variance possible. Delta and Charlie's unbilled gaps need physical log validation before the re-billing conversation. All of this is disclosed in the findings. The direction of every conclusion is stable even under the conservative assumptions.

**"How does it scale?"**
The analysis engine (engine.py) is decoupled from the operating system (app.py). Point the engine at any warehouse file, run it, drop the output JSON into Load Data, and the OS picks it up. 10 sites, one interface, one recovery tracker. Sites 2–3 are estimated at one dedicated onboarding sprint each (~4–6 weeks), based on the complexity of the Phase 1 site.

---

*Profit Lens · Kishan Gowda · Mattingly AI & Operations Hackathon 2026*
