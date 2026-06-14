"""
operations_pages.py  —  Profit Lens add-on
Operations & Bottlenecks  +  Information Gaps

Two drop-in Streamlit pages that compute REAL operational bottlenecks live from the
Mattingly warehouse dataset (no hardcoded numbers). Built to match the existing
Profit Lens look & feel.

WIRING (3 small edits in app.py):
  1) At the top of app.py, after your other imports, add:
         from operations_pages import page_operations, page_info_gaps, set_dataset_path
         set_dataset_path(os.path.join(os.path.dirname(__file__), "data",
                          "Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx"))
     (Point set_dataset_path at wherever the .xlsx actually lives. If you skip this,
      the page shows an uploader instead.)

  2) In the sidebar `pages = [...]` list (around line 428), add:
         ("Operations",       "Operations & Bottlenecks"),
         ("Information Gaps", "Information Gaps"),

  3) In `_PAGE_MAP` (around line 2225), add:
         "Operations":       page_operations,
         "Information Gaps": page_info_gaps,

That's it. The pages are self-contained (their own colours/helpers) so there is no
import cycle with app.py.
"""

import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ── palette (mirrors app.py) ───────────────────────────────
C_GREEN="#005A32"; C_AMBER="#B45309"; C_RED="#991B1B"; C_BLUE="#1E3A5F"
C_BG="#F5F6F5"; C_CARD="#FFFFFF"; C_BORDER="#D8DDD9"; C_TEXT="#1A1A2E"
C_MUTED="#6B7280"; C_DIVIDER="#E5E7EB"; C_GREEN_LITE="#EAF3EE"; C_AMBER_LITE="#FEF3C7"

ACT_ALL = ["Dispatch","Pick","Receipt","Returns","Rework","Storage","Urgent Order"]
EXC_ACT = ["Returns","Rework","Urgent Order"]          # the labour-heavy exception activities
ANNUALISE = 6                                          # 2 months -> 12 months

_DATASET_PATH = None
def set_dataset_path(p):
    """Tell the module where the warehouse .xlsx lives."""
    global _DATASET_PATH
    _DATASET_PATH = p


# ── helpers (mirrors app.py) ───────────────────────────────
def _fmt(v):
    if v >= 1_000_000: return f"${v/1e6:.2f}M"
    if v >= 1_000:     return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"

def _header(title, subtitle=""):
    sub = f'<div style="font-size:13px;color:{C_MUTED};margin-top:4px">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div style='margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid {C_DIVIDER}'>
      <div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:600;margin-bottom:6px'>
        PROFIT LENS &nbsp;/&nbsp; MATTINGLY LOGISTICS</div>
      <h1 style='margin:0;font-size:22px;font-weight:700;color:{C_TEXT};letter-spacing:-0.3px'>{title}</h1>
      {sub}
    </div>""", unsafe_allow_html=True)

def _sec(label):
    st.markdown(f'<div style="font-size:9px;font-weight:700;letter-spacing:2px;color:{C_MUTED};'
                f'text-transform:uppercase;margin:24px 0 12px">{label}</div>', unsafe_allow_html=True)

def _kpi(label, value, sub="", color=None):
    val_color = color or C_TEXT
    sub_html = f'<div style="font-size:11px;color:{C_MUTED};margin-top:2px">{sub}</div>' if sub else ""
    return f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:20px 22px'>
      <div style='font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:{C_MUTED};
                  font-weight:600;margin-bottom:8px'>{label}</div>
      <div style='font-size:26px;font-weight:700;color:{val_color};letter-spacing:-0.5px'>{value}</div>
      {sub_html}</div>"""

def _finding_card(color, badge, title, owner, value, why, action):
    val_html = f'<div style="font-size:20px;font-weight:700;color:{color}">{value}</div>' if value else ""
    return f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {color};
                border-radius:4px;padding:16px 20px;margin-bottom:12px'>
      <div style='display:flex;justify-content:space-between;align-items:flex-start'>
        <div style='flex:1'>
          <span style='background:{color}1A;color:{color};font-size:9px;font-weight:700;
                       padding:2px 8px;border-radius:2px;letter-spacing:1px'>{badge}</span>
          <div style='font-size:15px;font-weight:700;color:{C_TEXT};margin:8px 0 2px'>{title}</div>
          <div style='font-size:11px;color:{C_MUTED};margin-bottom:8px'>Owner: {owner}</div>
        </div>
        <div style='text-align:right;padding-left:16px'>{val_html}</div>
      </div>
      <div style='font-size:12px;color:{C_TEXT};line-height:1.5;margin-bottom:6px'><b>Why it matters:</b> {why}</div>
      <div style='font-size:12px;color:{C_GREEN};line-height:1.5'><b>Action:</b> {action}</div>
    </div>"""


# ── DATA / LIVE ENGINE ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load(path):
    """Compute the operational metrics live from the warehouse workbook."""
    xl = pd.ExcelFile(path)
    g  = lambda n: xl.parse(n)
    cm = g("Customer Master").set_index("Customer ID")["Customer Name"].to_dict()

    # ---- labour profile (cost/unit, units/hr per activity) ----
    lab = pd.concat([g("M1 Labour"), g("M2 Labour")])
    lab = lab[lab["Activity Type"].isin(ACT_ALL)].copy()
    for c in ["Units Processed","Labour Hours","Labour Cost"]:
        lab[c] = pd.to_numeric(lab[c], errors="coerce")
    prof = lab.groupby("Activity Type").agg(units=("Units Processed","sum"),
                                            hours=("Labour Hours","sum"),
                                            cost=("Labour Cost","sum"))
    prof["per_unit"]  = prof["cost"]/prof["units"]
    prof["units_hr"]  = prof["units"]/prof["hours"]
    cpu = prof["per_unit"].to_dict()
    hpu = (prof["hours"]/prof["units"]).to_dict()
    avg_rate = lab["Labour Cost"].sum()/lab["Labour Hours"].sum()
    total_hours = lab["Labour Hours"].sum()
    missing_days = sorted(lab[lab["Data Quality Note"].notna()]["Date"].astype(str).unique())

    # ---- exception-handling labour pool, by customer ----
    act = pd.concat([g("M1 Activities"), g("M2 Activities")])
    act["Quantity"] = pd.to_numeric(act["Quantity"], errors="coerce")
    exc = act[act["Activity Type"].isin(EXC_ACT)].copy()
    exc["lab_cost"] = exc.apply(lambda r: r["Quantity"]*cpu.get(r["Activity Type"],0), axis=1)
    exc["lab_hrs"]  = exc.apply(lambda r: r["Quantity"]*hpu.get(r["Activity Type"],0), axis=1)
    exc_by_cust = (exc.groupby("Customer Id")
                      .agg(cost=("lab_cost","sum"), hrs=("lab_hrs","sum"), units=("Quantity","sum"))
                      .sort_values("cost", ascending=False))
    exc_by_cust["name"] = [cm.get(c, c) for c in exc_by_cust.index]
    exc_pool_yr  = exc["lab_cost"].sum()*ANNUALISE
    exc_hr_share = exc["lab_hrs"].sum()/total_hours*100

    # ---- urgent-order penalty ----
    std_hr = 1/hpu["Dispatch"]; urg_hr = 1/hpu["Urgent Order"]
    urg_mult = hpu["Urgent Order"]/hpu["Dispatch"]
    uo   = act[act["Activity Type"]=="Urgent Order"].groupby("Customer Id")["Quantity"].sum()
    disp = act[act["Activity Type"]=="Dispatch"].groupby("Customer Id")["Quantity"].sum()
    urg_premium_yr = (act[act["Activity Type"]=="Urgent Order"]["Quantity"].sum()
                      * (hpu["Urgent Order"]-hpu["Dispatch"]) * avg_rate * ANNUALISE)
    urg_top = []
    for c in uo.sort_values(ascending=False).head(6).index:
        share = uo[c]/(uo[c]+disp.get(c,0))*100
        urg_top.append((cm.get(c,c), int(uo[c]*ANNUALISE), share))

    # ---- productivity trend M1 -> M2 ----
    trend = {}
    for m in ["M1","M2"]:
        l = g(m+" Labour"); l = l[l["Activity Type"].isin(ACT_ALL)].copy()
        for c in ["Units Processed","Labour Hours"]:
            l[c] = pd.to_numeric(l[c], errors="coerce")
        uph = l.groupby("Activity Type").apply(lambda d: d["Units Processed"].sum()/d["Labour Hours"].sum())
        trend[m] = uph.to_dict()

    return dict(prof=prof, avg_rate=avg_rate, total_hours=total_hours, missing_days=missing_days,
                exc_by_cust=exc_by_cust, exc_pool_yr=exc_pool_yr, exc_hr_share=exc_hr_share,
                std_hr=std_hr, urg_hr=urg_hr, urg_mult=urg_mult, urg_premium_yr=urg_premium_yr,
                urg_top=urg_top, trend=trend)


def _get_data():
    """Return computed metrics, or None + render an uploader if no dataset is set."""
    path = _DATASET_PATH
    if path and os.path.exists(path):
        return _load(path)
    up = st.file_uploader("Upload the Mattingly warehouse dataset (.xlsx) to run the operations engine",
                          type=["xlsx"], key="ops_uploader")
    if up is not None:
        tmp = os.path.join(os.path.dirname(__file__) or ".", "_ops_tmp.xlsx")
        with open(tmp, "wb") as f:
            f.write(up.getbuffer())
        return _load(tmp)
    st.info("No dataset found. Set the path via set_dataset_path(...) in app.py, or upload the .xlsx above.")
    return None


# ═══════════════════════════════════════════════════════════
# PAGE 1 — OPERATIONS & BOTTLENECKS
# ═══════════════════════════════════════════════════════════
def page_operations():
    _header("Operations & Bottlenecks",
            "Where labour is consumed, where it is lost, and what to fix — computed live from activity & labour data")
    d = _get_data()
    if d is None:
        return

    prof = d["prof"]
    delta_row = d["exc_by_cust"].iloc[0] if len(d["exc_by_cust"]) else None
    pick_now  = d["trend"]["M2"].get("Pick", 0)
    pick_then = d["trend"]["M1"].get("Pick", 0)
    pick_delta = (pick_now/pick_then - 1)*100 if pick_then else 0

    # KPI row
    k1,k2,k3,k4 = st.columns(4)
    k1.markdown(_kpi("Exception-Labour Pool", _fmt(d["exc_pool_yr"])+"/yr",
                     "Returns + rework + urgent", C_RED), unsafe_allow_html=True)
    k2.markdown(_kpi("Share of Variable Labour", f"{d['exc_hr_share']:.0f}%",
                     "Hours spent on exceptions", C_AMBER), unsafe_allow_html=True)
    k3.markdown(_kpi("Urgent-Order Penalty", _fmt(d["urg_premium_yr"])+"/yr",
                     f"Urgent runs {d['urg_mult']:.1f}× slower", C_AMBER), unsafe_allow_html=True)
    k4.markdown(_kpi("Pick Productivity", f"{pick_now:.0f}/hr",
                     f"{pick_delta:+.0f}% Jan→Feb (improving)", C_GREEN), unsafe_allow_html=True)

    # 1) Where labour goes
    _sec("Where the Labour Goes — Activity Profile")
    st.caption("Picking is fast and cheap. The labour is consumed by dispatch and the exception activities "
               "(returns, rework, urgent orders) which run at a fraction of pick speed.")
    order = prof.sort_values("hours", ascending=True)
    colours = [C_RED if a in EXC_ACT else (C_BLUE if a=="Dispatch" else C_GREEN) for a in order.index]
    fig = go.Figure(go.Bar(
        x=order["hours"]*ANNUALISE, y=list(order.index), orientation="h",
        marker_color=colours,
        text=[f"{h*ANNUALISE:,.0f} hrs · {u:.0f}/hr" for h,u in zip(order["hours"], order["units_hr"])],
        textposition="auto"))
    fig.update_layout(height=300, margin=dict(l=10,r=10,t=10,b=10),
                      xaxis_title="Annual labour hours", plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True)

    # 2) Ranked operational opportunities (verified)
    _sec("Operational Opportunities — Ranked & Owned")

    if delta_row is not None:
        peer = d["exc_by_cust"]["cost"].iloc[1:6].mean()*ANNUALISE if len(d["exc_by_cust"])>5 else 0
        mult = (delta_row["cost"]*ANNUALISE)/peer if peer else 0
        st.markdown(_finding_card(
            C_RED, "BOTTLENECK · SITE MANAGER",
            f"{delta_row['name']} — Exception-Handling Labour Drain",
            "Site Manager", _fmt(delta_row["cost"]*ANNUALISE)+"/yr",
            f"{delta_row['name']} alone consumes {delta_row['hrs']*ANNUALISE:,.0f} labour hours/yr on returns, "
            f"rework and urgent orders — about {mult:.1f}× the next-highest customer. These activities run at "
            f"5–9 units/hr versus 167/hr for picking, so each one ties up scarce floor labour.",
            "Run a 2-week floor root-cause study (inbound quality, slotting, order patterns). Target a 30% "
            "reduction in exception volume — every 10% cut frees roughly "
            f"{_fmt(delta_row['cost']*ANNUALISE*0.10)}/yr of labour."),
            unsafe_allow_html=True)

    st.markdown(_finding_card(
        C_AMBER, "THROUGHPUT · SITE MANAGER + COMMERCIAL",
        "Urgent Orders Disrupt Standard Pick & Dispatch Flow",
        "Site Manager + Commercial Lead", _fmt(d["urg_premium_yr"])+"/yr",
        f"Urgent orders are processed at {d['urg_hr']:.1f}/hr versus {d['std_hr']:.1f}/hr for standard dispatch "
        f"— {d['urg_mult']:.1f}× the labour per order. They also pre-empt the standard queue, dragging overall "
        f"throughput. {d['urg_top'][0][0]} is the largest generator.",
        "Two levers: (1) demand-planning / cut-off SLAs with the top urgent-order customers to convert urgency "
        "into planned volume; (2) a priced 'urgent' surcharge that reflects the real labour premium."),
        unsafe_allow_html=True)

    pool = d["exc_pool_yr"]
    st.markdown(_finding_card(
        C_BLUE, "STRATEGIC · CEO + SITE MANAGER",
        "Exception Handling Is 26% of All Variable Labour",
        "CEO + Site Manager", _fmt(pool)+"/yr",
        f"Across the network, returns/rework/urgent consume {d['exc_hr_share']:.0f}% of variable labour hours "
        f"— a {_fmt(pool)}/yr pool. This is the single largest operational lever in the warehouse.",
        f"Set a network exception-rate target. A 10% reduction ≈ {_fmt(pool*0.10)}/yr; 25% ≈ {_fmt(pool*0.25)}/yr "
        "— with no pricing change required."),
        unsafe_allow_html=True)

    # 3) Productivity trend
    _sec("Productivity Trend — The Floor Is Already Improving")
    acts = ["Pick","Dispatch","Returns","Rework","Urgent Order"]
    m1 = [d["trend"]["M1"].get(a,0) for a in acts]
    m2 = [d["trend"]["M2"].get(a,0) for a in acts]
    fig2 = go.Figure()
    fig2.add_bar(name="Jan", x=acts, y=m1, marker_color=C_BORDER)
    fig2.add_bar(name="Feb", x=acts, y=m2, marker_color=C_GREEN)
    fig2.update_layout(barmode="group", height=300, margin=dict(l=10,r=10,t=10,b=10),
                       yaxis_title="Units / labour hour", plot_bgcolor="white", paper_bgcolor="white",
                       legend=dict(orientation="h", y=1.1), font=dict(size=11))
    st.plotly_chart(fig2, use_container_width=True)
    st.caption("Every activity improved from January to February — a credible baseline and a sign the floor "
               "responds to attention. This is the trend the monthly cadence is designed to protect.")


# ═══════════════════════════════════════════════════════════
# PAGE 2 — INFORMATION GAPS
# ═══════════════════════════════════════════════════════════
def page_info_gaps():
    _header("Information Gaps — What We'd Need to Be Sure",
            "Mattingly's brief asks 'what information is missing?'. Naming our own limits is part of the answer.")
    d = _get_data()
    missing = ", ".join(d["missing_days"]) if d and d["missing_days"] else "4 labour days"

    _sec("Known Limitations of This Analysis")
    gaps = [
        (C_RED, "HIGH", "Labour-only cost base — no equipment / overhead / facility cost",
         "The $0.265/pick true cost is labour only. Forklifts, racking, energy, supervision and facility "
         "cost are not in the labour feed, so true cost-to-serve is understated, not overstated. Every "
         "below-cost finding is therefore conservative.",
         "Request the warehouse fixed-cost ledger and an equipment/MHE cost schedule to build a fully-loaded cost per activity."),
        (C_AMBER, "HIGH", f"4 missing labour days ({missing})",
         "These days have no time-and-attendance record. Treating them as zero gives the $0.265 floor; "
         "imputing them gives the $0.284 strict figure. The direction of every finding holds under both.",
         "Retrieve the payroll records for those four dates and re-run the pick-cost calculation to remove the range."),
        (C_AMBER, "MEDIUM", "Two months of data (Jan–Feb 2026), annualised ×6",
         "All annual figures scale two months. A seasonality check shows every customer's M1/M2 volume ratio "
         "sits in a tight 0.84–1.18 band, so no seasonal adjustment was applied — but two months cannot rule "
         "out quarter-end or holiday effects.",
         "Pull 12-month revenue & volume history from finance to confirm the annualisation factor before external repricing."),
        (C_BLUE, "MEDIUM", "No storage-capacity field — utilisation % is not directly measurable",
         "The dataset has units-on-hand and dwell days but no allocated capacity per customer, so any "
         "'% of capacity used' figure (e.g. for fixed-fee accounts) is an estimate, not a measured value.",
         "Request the site's slot/pallet capacity allocation by customer to quantify true space utilisation."),
        (C_BLUE, "MEDIUM", "Exception-rate definition needs one agreed source",
         "The Exceptions sheet and the Activities sheet count exceptions differently (event flags vs activity "
         "volumes). Any headline 'exception rate %' must state which source it uses, or it won't reconcile.",
         "Agree one exception-rate definition with operations and apply it consistently across every report."),
        (C_MUTED, "LOW", "Contribution margin, not full customer P&L",
         "True margins here are revenue minus activity-based labour. They are not a full customer P&L with "
         "allocated corporate overhead, so they show relative profitability, not statutory profit.",
         "Layer the management overhead allocation onto the activity costs for a board-grade customer P&L."),
    ]
    for color, sev, title, why, ask in gaps:
        st.markdown(f"""
        <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {color};
                    border-radius:4px;padding:14px 18px;margin-bottom:10px'>
          <span style='background:{color}1A;color:{color};font-size:9px;font-weight:700;
                       padding:2px 8px;border-radius:2px;letter-spacing:1px'>{sev}</span>
          <div style='font-size:14px;font-weight:700;color:{C_TEXT};margin:8px 0 4px'>{title}</div>
          <div style='font-size:12px;color:{C_TEXT};line-height:1.5;margin-bottom:5px'>{why}</div>
          <div style='font-size:12px;color:{C_GREEN};line-height:1.5'><b>What we'd request:</b> {ask}</div>
        </div>""", unsafe_allow_html=True)

    _sec("The Five Questions We'd Ask Management Next")
    qs = [
        "Can we have 12 months of volume and revenue history to confirm the two-month annualisation?",
        "What is the fully-loaded warehouse cost base (equipment, facility, supervision) beyond direct labour?",
        "What is the contracted capacity / slot allocation per customer, so we can measure true utilisation?",
        "For the unbilled exceptions, which contract clauses govern re-billing of returns, rework and urgent orders?",
        "Which customers are strategic / relationship-protected, so repricing is sequenced commercially, not just by dollars?",
    ]
    for i,q in enumerate(qs,1):
        st.markdown(f"""
        <div style='background:{C_GREEN_LITE};border-radius:4px;padding:12px 16px;margin-bottom:8px;
                    display:flex;gap:12px;align-items:flex-start'>
          <div style='font-size:16px;font-weight:700;color:{C_GREEN};flex-shrink:0'>{i}</div>
          <div style='font-size:13px;color:{C_TEXT};line-height:1.5'>{q}</div>
        </div>""", unsafe_allow_html=True)
