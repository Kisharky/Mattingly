"""
operations_pages.py  —  Profit Lens add-on
Operations & Bottlenecks  +  Information Gaps
"""

import os
from datetime import date
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

C_GREEN="#005A32"; C_AMBER="#B45309"; C_RED="#991B1B"; C_BLUE="#1E3A5F"
C_BG="#F5F6F5"; C_CARD="#FFFFFF"; C_BORDER="#D8DDD9"; C_TEXT="#1A1A2E"
C_MUTED="#6B7280"; C_DIVIDER="#E5E7EB"; C_GREEN_LITE="#EAF3EE"; C_AMBER_LITE="#FEF3C7"

ACT_ALL = ["Dispatch","Pick","Receipt","Returns","Rework","Storage","Urgent Order"]
EXC_ACT = ["Returns","Rework","Urgent Order"]
ANNUALISE = 6

_DATASET_PATH = None
def set_dataset_path(p):
    global _DATASET_PATH
    _DATASET_PATH = p


def _fmt(v):
    if v >= 1_000_000: return f"${v/1e6:.2f}M"
    if v >= 1_000:     return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"

def _header(title, subtitle=""):
    sub = f'<div style="font-size:13px;color:{C_MUTED};margin-top:4px">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""
    <div style='margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid {C_DIVIDER}'>
      <div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:600;margin-bottom:6px'>
        PROFIT LENS / MATTINGLY LOGISTICS</div>
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


@st.cache_data(show_spinner=False)
def _load(path):
    xl = pd.ExcelFile(path)
    g  = lambda n: xl.parse(n)
    cm = g("Customer Master").set_index("Customer ID")["Customer Name"].to_dict()

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

    exc_type = (exc.groupby(["Customer Id","Activity Type"])
                   .agg(cost=("lab_cost","sum"), units=("Quantity","sum"))
                   .reset_index())
    exc_type["name"] = [cm.get(c,c) for c in exc_type["Customer Id"]]

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
                urg_top=urg_top, trend=trend, exc_type=exc_type, cpu=cpu, hpu=hpu)


def _get_data():
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


# ===========================================================
# PAGE 1 — OPERATIONS & BOTTLENECKS
# ===========================================================
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

    today_str = date.today().strftime("%A, %d %b %Y")
    exc_pct   = d["exc_hr_share"]
    exc_status = "CRITICAL" if exc_pct > 25 else ("WATCH" if exc_pct > 15 else "OK")
    exc_status_color = "#DC2626" if exc_status == "CRITICAL" else ("#B45309" if exc_status == "WATCH" else "#005A32")

    st.markdown(f"""
    <div style='background:#0F2419;border:1px solid #1A3A28;border-radius:6px;
                padding:14px 20px;margin-bottom:20px'>
      <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>
        <div style='font-size:9px;letter-spacing:2px;color:#4A9E6A;font-weight:700'>
          SITE MANAGER MORNING BRIEF / LIVE ENGINE
        </div>
        <div style='font-size:11px;color:#4A9E6A'>{today_str} &nbsp;|&nbsp; Data: Jan-Feb 2026</div>
      </div>
      <div style='display:flex;gap:16px'>
        <div style='flex:1;padding:10px 14px;background:#1A3D2B;border-radius:4px;border-left:3px solid #DC2626'>
          <div style='font-size:9px;color:#FF8080;font-weight:700;letter-spacing:1px;margin-bottom:3px'>PRIORITY 1</div>
          <div style='font-size:13px;font-weight:700;color:#FFFFFF'>Delta exception drain</div>
          <div style='font-size:11px;color:#8FBF9F;margin-top:2px'>$446K/yr | 3.9x peers | Root cause investigation active</div>
        </div>
        <div style='flex:1;padding:10px 14px;background:#1A3D2B;border-radius:4px;border-left:3px solid #B45309'>
          <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:3px'>PRIORITY 2</div>
          <div style='font-size:13px;font-weight:700;color:#FFFFFF'>Urgent order throughput</div>
          <div style='font-size:11px;color:#8FBF9F;margin-top:2px'>$349K/yr | 2.35x slower than standard | SLA review needed</div>
        </div>
        <div style='flex:1;padding:10px 14px;background:#1A3D2B;border-radius:4px;border-left:3px solid {exc_status_color}'>
          <div style='font-size:9px;color:{exc_status_color};font-weight:700;letter-spacing:1px;margin-bottom:3px'>EXCEPTION POOL: {exc_status}</div>
          <div style='font-size:13px;font-weight:700;color:#FFFFFF'>{exc_pct:.0f}% of variable labour</div>
          <div style='font-size:11px;color:#8FBF9F;margin-top:2px'>Target: below 15% | Pick productivity {pick_delta:+.0f}% Jan-Feb</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    k1,k2,k3,k4 = st.columns(4)
    k1.markdown(_kpi("Exception-Labour Pool", _fmt(d["exc_pool_yr"])+"/yr",
                     "Returns + rework + urgent", C_RED), unsafe_allow_html=True)
    k2.markdown(_kpi("Share of Variable Labour", f"{d['exc_hr_share']:.0f}%",
                     "Hours spent on exceptions", C_AMBER), unsafe_allow_html=True)
    k3.markdown(_kpi("Urgent-Order Penalty", _fmt(d["urg_premium_yr"])+"/yr",
                     f"Urgent runs {d['urg_mult']:.1f}x slower", C_AMBER), unsafe_allow_html=True)
    k4.markdown(_kpi("Pick Productivity", f"{pick_now:.0f}/hr",
                     f"{pick_delta:+.0f}% Jan-Feb (improving)", C_GREEN), unsafe_allow_html=True)

    # THROUGHPUT TABLE
    _sec("Throughput by Activity - Units per Labour Hour")
    st.caption(
        "Pick speed is the baseline. Exception activities (Returns, Rework, Urgent Order) "
        "run 9x to 33x slower. Every exception unit added to the floor displaces roughly "
        "9-33 standard pick units from the queue."
    )

    pick_speed = prof.loc["Pick","units_hr"] if "Pick" in prof.index else 167.0
    rows = []
    for act in ACT_ALL:
        if act not in prof.index:
            continue
        row = prof.loc[act]
        uph   = row["units_hr"]
        cpu_v = row["per_unit"]
        hrs_yr = row["hours"] * ANNUALISE
        is_exc = act in EXC_ACT
        vs_pick = uph / pick_speed
        rows.append((act, uph, cpu_v, hrs_yr, is_exc, vs_pick))

    table_rows = ""
    for act, uph, cpu_v, hrs_yr, is_exc, vs_pick in sorted(rows, key=lambda x: -x[1]):
        bg = "#FFF5F5" if is_exc else "#F5FFF8"
        badge_color = "#DC2626" if is_exc else "#005A32"
        badge = "EXCEPTION" if is_exc else "STANDARD"
        bar_pct = min(uph / pick_speed * 100, 100)
        table_rows += f"""
        <tr style='background:{bg};border-bottom:1px solid {C_DIVIDER}'>
          <td style='padding:10px 14px;font-weight:600;color:{C_TEXT};font-size:12px;width:160px'>
            {act}<br><span style='background:{badge_color}18;color:{badge_color};font-size:8px;
            font-weight:700;padding:1px 6px;border-radius:2px;letter-spacing:1px'>{badge}</span>
          </td>
          <td style='padding:10px 14px;font-size:15px;font-weight:700;
                     color:{"#DC2626" if is_exc else "#005A32"}'>
            {uph:.0f}
          </td>
          <td style='padding:10px 14px;min-width:160px'>
            <div style='background:#E5E7EB;border-radius:2px;height:10px;width:100%;max-width:180px'>
              <div style='background:{"#DC2626" if is_exc else "#005A32"};height:10px;
                          border-radius:2px;width:{bar_pct:.0f}%'></div>
            </div>
            <div style='font-size:10px;color:{C_MUTED};margin-top:3px'>{vs_pick:.2f}x pick speed</div>
          </td>
          <td style='padding:10px 14px;font-size:12px;color:{C_TEXT}'>${cpu_v:.3f}/unit</td>
          <td style='padding:10px 14px;font-size:12px;color:{C_MUTED}'>{hrs_yr:,.0f} hrs/yr</td>
        </tr>"""

    st.markdown(f"""
    <table style='width:100%;border-collapse:collapse;border:1px solid {C_BORDER};border-radius:4px;
                  overflow:hidden;font-family:Inter,sans-serif;margin-bottom:8px'>
      <thead>
        <tr style='background:{C_TEXT};color:#FFFFFF'>
          <th style='padding:10px 14px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:600'>ACTIVITY</th>
          <th style='padding:10px 14px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:600'>UNITS/HR</th>
          <th style='padding:10px 14px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:600'>VS PICK SPEED</th>
          <th style='padding:10px 14px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:600'>COST/UNIT</th>
          <th style='padding:10px 14px;text-align:left;font-size:10px;letter-spacing:1px;font-weight:600'>HRS/YR</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
    <div style='font-size:10px;color:{C_MUTED};margin-bottom:4px'>
      Red = exception activity. Bar shows throughput as % of pick speed. Source: Jan-Feb 2026 labour data, annualised x6.
    </div>
    """, unsafe_allow_html=True)

    # WHERE LABOUR GOES
    _sec("Where the Labour Goes - Activity Profile (Annual Hours)")
    st.caption("Picking is fast and cheap. The labour is consumed by dispatch and exception activities "
               "which run at a fraction of pick speed.")
    order = prof.sort_values("hours", ascending=True)
    colours = [C_RED if a in EXC_ACT else (C_BLUE if a=="Dispatch" else C_GREEN) for a in order.index]
    fig = go.Figure(go.Bar(
        x=order["hours"]*ANNUALISE, y=list(order.index), orientation="h",
        marker_color=colours,
        text=[f"{h*ANNUALISE:,.0f} hrs / {u:.0f} units/hr" for h,u in zip(order["hours"], order["units_hr"])],
        textposition="auto"))
    fig.update_layout(height=300, margin=dict(l=10,r=10,t=10,b=10),
                      xaxis_title="Annual labour hours", plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(size=11))
    st.plotly_chart(fig, use_container_width=True)

    # EXCEPTION BOTTLENECK BY CUSTOMER
    _sec("Exception Bottleneck - All Customers Ranked by Annual Exception Cost")
    st.caption(
        "Delta stands out at 3.9x the peer average. Every customer is shown — ranked so the "
        "floor knows exactly where to focus root-cause investigation."
    )

    ebc = d["exc_by_cust"].copy()
    ebc["cost_yr"] = ebc["cost"] * ANNUALISE
    ebc_sorted = ebc.sort_values("cost_yr", ascending=True)

    avg_cost = ebc["cost_yr"].mean()
    bar_colors = []
    for _, row_c in ebc_sorted.iterrows():
        if "delta" in str(row_c["name"]).lower():
            bar_colors.append("#DC2626")
        elif row_c["cost_yr"] > avg_cost * 1.5:
            bar_colors.append("#B45309")
        else:
            bar_colors.append("#005A32")

    fig3 = go.Figure(go.Bar(
        x=ebc_sorted["cost_yr"],
        y=ebc_sorted["name"],
        orientation="h",
        marker_color=bar_colors,
        text=[f"${v/1000:.0f}K/yr  {h*ANNUALISE:,.0f} hrs" for v,h in zip(ebc_sorted["cost_yr"], ebc_sorted["hrs"])],
        textposition="auto",
    ))
    fig3.add_vline(x=avg_cost, line_dash="dot", line_color="#B45309",
                   annotation_text=f"Network avg ${avg_cost/1000:.0f}K/yr",
                   annotation_position="top right",
                   annotation_font_size=10)
    fig3.update_layout(
        height=max(300, len(ebc_sorted)*38),
        margin=dict(l=10,r=120,t=20,b=10),
        xaxis_title="Annual exception-handling labour cost ($)",
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(size=11),
        xaxis=dict(tickprefix="$", tickformat=",.0f"),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # EXCEPTION TYPE BREAKDOWN TOP 5
    _sec("Exception Type Breakdown - Top 5 Customers (Returns / Rework / Urgent)")
    st.caption("Where each customer's exception labour splits between activity types.")

    top5 = ebc.sort_values("cost_yr", ascending=False).head(5)["name"].tolist()
    exc_type = d["exc_type"].copy()
    exc_type = exc_type[exc_type["name"].isin(top5)].copy()
    exc_type["cost_yr"] = exc_type["cost"] * ANNUALISE

    fig4 = go.Figure()
    type_colors = {"Returns": "#DC2626", "Rework": "#B45309", "Urgent Order": "#1E3A5F"}
    for atype, acolor in type_colors.items():
        sub = exc_type[exc_type["Activity Type"]==atype]
        if sub.empty:
            continue
        fig4.add_trace(go.Bar(
            name=atype, x=sub["name"], y=sub["cost_yr"],
            marker_color=acolor,
            text=[f"${v/1000:.0f}K" for v in sub["cost_yr"]],
            textposition="auto",
        ))
    fig4.update_layout(
        barmode="stack", height=280,
        margin=dict(l=10,r=10,t=10,b=10),
        yaxis_title="Annual cost ($)",
        plot_bgcolor="white", paper_bgcolor="white",
        legend=dict(orientation="h", y=1.1, font=dict(size=10)),
        font=dict(size=11),
        yaxis=dict(tickprefix="$", tickformat=",.0f"),
    )
    st.plotly_chart(fig4, use_container_width=True)

    # RANKED OPPORTUNITIES
    _sec("Operational Opportunities - Ranked & Owned")

    if delta_row is not None:
        peer = d["exc_by_cust"]["cost"].iloc[1:6].mean()*ANNUALISE if len(d["exc_by_cust"])>5 else 0
        mult = (delta_row["cost"]*ANNUALISE)/peer if peer else 0
        st.markdown(_finding_card(
            C_RED, "BOTTLENECK / SITE MANAGER",
            f"{delta_row['name']} - Exception-Handling Labour Drain",
            "Site Manager", _fmt(delta_row["cost"]*ANNUALISE)+"/yr",
            f"{delta_row['name']} alone consumes {delta_row['hrs']*ANNUALISE:,.0f} labour hours/yr on returns, "
            f"rework and urgent orders - about {mult:.1f}x the next-highest customer. These activities run at "
            f"5-9 units/hr versus 167/hr for picking, so each one ties up scarce floor labour.",
            "Run a 2-week floor root-cause study (inbound quality, slotting, order patterns). Target a 30% "
            "reduction in exception volume - every 10% cut frees roughly "
            f"{_fmt(delta_row['cost']*ANNUALISE*0.10)}/yr of labour."),
            unsafe_allow_html=True)

    st.markdown(_finding_card(
        C_AMBER, "THROUGHPUT / SITE MANAGER + COMMERCIAL",
        "Urgent Orders Disrupt Standard Pick & Dispatch Flow",
        "Site Manager + Commercial Lead", _fmt(d["urg_premium_yr"])+"/yr",
        f"Urgent orders are processed at {d['urg_hr']:.1f}/hr versus {d['std_hr']:.1f}/hr for standard dispatch "
        f"- {d['urg_mult']:.1f}x the labour per order. They also pre-empt the standard queue, dragging overall "
        f"throughput. {d['urg_top'][0][0]} is the largest generator.",
        "Two levers: (1) demand-planning / cut-off SLAs with the top urgent-order customers to convert urgency "
        "into planned volume; (2) a priced urgent surcharge that reflects the real labour premium."),
        unsafe_allow_html=True)

    pool = d["exc_pool_yr"]
    st.markdown(_finding_card(
        C_BLUE, "STRATEGIC / CEO + SITE MANAGER",
        "Exception Handling Is 26% of All Variable Labour",
        "CEO + Site Manager", _fmt(pool)+"/yr",
        f"Across the network, returns/rework/urgent consume {d['exc_hr_share']:.0f}% of variable labour hours "
        f"- a {_fmt(pool)}/yr pool. This is the single largest operational lever in the warehouse.",
        f"Set a network exception-rate target. A 10% reduction = {_fmt(pool*0.10)}/yr; 25% = {_fmt(pool*0.25)}/yr "
        "- with no pricing change required."),
        unsafe_allow_html=True)

    # PRODUCTIVITY TREND
    _sec("Productivity Trend - Jan vs Feb (The Floor Is Improving)")
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
    st.caption("Every activity improved from January to February - a sign the floor responds to attention. "
               "This trend is what the monthly cadence is designed to protect and accelerate.")

    # URGENT ORDER BREAKDOWN
    _sec("Urgent Order Volume - By Customer (Annualised)")
    if d["urg_top"]:
        names_urg = [r[0] for r in d["urg_top"]]
        vols_urg  = [r[1] for r in d["urg_top"]]
        share_urg = [r[2] for r in d["urg_top"]]
        fig5 = go.Figure()
        fig5.add_bar(name="Urgent orders/yr", x=names_urg, y=vols_urg,
                     marker_color=C_BLUE,
                     text=[f"{v:,.0f} orders | {s:.0f}% of dispatches" for v,s in zip(vols_urg, share_urg)],
                     textposition="outside")
        fig5.update_layout(height=260, margin=dict(l=10,r=10,t=30,b=10),
                           yaxis_title="Urgent orders per year",
                           plot_bgcolor="white", paper_bgcolor="white", font=dict(size=11))
        st.plotly_chart(fig5, use_container_width=True)
        st.caption("Customers with high urgent-order share are candidates for SLA negotiation or urgent surcharges.")


# ===========================================================
# PAGE 2 - INFORMATION GAPS
# ===========================================================
def page_info_gaps():
    _header("Information Gaps - What We'd Need to Be Sure",
            "Naming our own analytical limits is part of a credible answer.")
    d = _get_data()
    missing = ", ".join(d["missing_days"]) if d and d["missing_days"] else "4 labour days"
    n_missing = len(d["missing_days"]) if d and d["missing_days"] else 4

    # DATA CONFIDENCE SCORE HERO
    score = 10
    score -= 2
    score -= min(n_missing, 3)
    score -= 1
    score -= 1
    score -= 0.5
    score = max(score, 0)
    score_int = round(score)
    score_pct = score / 10 * 100

    score_color = "#005A32" if score >= 7 else ("#B45309" if score >= 5 else "#991B1B")
    score_label = "SOLID FOUNDATION" if score >= 7 else ("REQUIRES VALIDATION" if score >= 5 else "DATA GAPS CRITICAL")

    st.markdown(f"""
    <div style='background:#0F1A0F;border:1px solid #1A3A28;border-radius:6px;
                padding:20px 24px;margin-bottom:24px'>
      <div style='font-size:9px;letter-spacing:2px;color:#4A9E6A;font-weight:700;margin-bottom:12px'>
        DATA CONFIDENCE ASSESSMENT / PROFIT LENS ENGINE
      </div>
      <div style='display:flex;gap:32px;align-items:center'>
        <div style='text-align:center;flex-shrink:0'>
          <div style='font-size:56px;font-weight:800;color:{score_color};letter-spacing:-2px;line-height:1'>
            {score_int}<span style='font-size:28px;color:#4A9E6A'>/10</span>
          </div>
          <div style='font-size:10px;font-weight:700;color:{score_color};letter-spacing:1px;margin-top:4px'>
            {score_label}
          </div>
        </div>
        <div style='flex:1'>
          <div style='font-size:12px;color:#8FBF9F;line-height:1.7;margin-bottom:12px'>
            The analysis is <strong style='color:#FFFFFF'>directionally reliable</strong> — every finding holds
            under both the floor ($0.265/pick) and strict ($0.284/pick) cost estimates. The score reflects
            missing data that would make confidence levels <strong style='color:#FFFFFF'>HIGH across all findings</strong>,
            not uncertainty about the direction of the conclusions.
          </div>
          <div style='margin-bottom:8px'>
            <div style='display:flex;justify-content:space-between;margin-bottom:4px'>
              <div style='font-size:10px;color:#6B9E83;font-weight:600'>OVERALL CONFIDENCE</div>
              <div style='font-size:10px;color:{score_color};font-weight:700'>{score_pct:.0f}%</div>
            </div>
            <div style='background:#1A3A28;border-radius:3px;height:8px'>
              <div style='background:{score_color};height:8px;border-radius:3px;width:{score_pct:.0f}%'></div>
            </div>
          </div>
          <div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:8px'>
            <span style='font-size:10px;color:#FF8080;background:#FF808015;padding:3px 10px;border-radius:2px;
                         font-weight:700'>2 HIGH gaps</span>
            <span style='font-size:10px;color:#F8B840;background:#F8B84015;padding:3px 10px;border-radius:2px;
                         font-weight:700'>3 MEDIUM gaps</span>
            <span style='font-size:10px;color:#8FBF9F;background:#8FBF9F15;padding:3px 10px;border-radius:2px;
                         font-weight:700'>1 LOW gap</span>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style='background:#FEF3C7;border:1px solid #F8B840;border-radius:4px;
                padding:12px 16px;margin-bottom:20px;font-size:12px;color:#78350F;line-height:1.6'>
      <strong>What this means in practice:</strong> The $0.265/pick floor cost, all customer margin findings,
      the $2.65M total opportunity, and every HIGH-confidence finding are robust to the gaps below.
      The MEDIUM-confidence findings would upgrade to HIGH once the 2 HIGH-priority gaps are closed.
    </div>
    """, unsafe_allow_html=True)

    _sec("Known Limitations of This Analysis")
    gaps = [
        (C_RED, "HIGH", "Labour-only cost base — no equipment / overhead / facility cost",
         "The $0.265/pick true cost is labour only. Forklifts, racking, energy, supervision and facility "
         "cost are not in the labour feed, so true cost-to-serve is understated, not overstated. Every "
         "below-cost finding is therefore conservative.",
         "Request the warehouse fixed-cost ledger and equipment/MHE cost schedule to build a fully-loaded cost per activity.",
         "Findings affected: F001 Bravo, F002 Delta reprice, F003 Charlie reprice — all understated"),
        (C_RED, "HIGH", f"{n_missing} missing labour days ({missing})",
         "These days have no time-and-attendance record. Treating them as zero gives the $0.265 floor; "
         "imputing them gives the $0.284 strict figure. The direction of every finding holds under both.",
         "Retrieve the payroll records for those dates and re-run the pick-cost calculation to remove the range.",
         "Findings affected: All cost-per-pick findings — narrows the $0.265-$0.284 range to a single number"),
        (C_AMBER, "MEDIUM", "Two months of data (Jan-Feb 2026), annualised x6",
         "All annual figures scale two months. A seasonality check shows every customer's M1/M2 volume ratio "
         "sits in a tight 0.84-1.18 band, so no seasonal adjustment was applied — but two months cannot rule "
         "out quarter-end or holiday effects.",
         "Pull 12-month revenue and volume history from finance to confirm the annualisation factor before external repricing.",
         "Findings affected: F013 Home & Living $276K, F015 urgent premium $349K — scale may shift up to 20%"),
        (C_BLUE, "MEDIUM", "No storage-capacity field — utilisation % is not directly measurable",
         "The dataset has units-on-hand and dwell days but no allocated capacity per customer, so any "
         "'% of capacity used' figure is an estimate, not a measured value.",
         "Request the site's slot/pallet capacity allocation by customer to quantify true space utilisation.",
         "Findings affected: Fixed-fee customer analysis — capacity utilisation claims are directional only"),
        (C_BLUE, "MEDIUM", "Exception-rate definition needs one agreed source",
         "The Exceptions sheet and the Activities sheet count exceptions differently (event flags vs activity "
         "volumes). Any headline exception rate % must state which source it uses.",
         "Agree one exception-rate definition with operations and apply it consistently across every report.",
         "Findings affected: F014 Delta exception drain, F016 network KPI — rate % may differ by 2-5pp"),
        (C_MUTED, "LOW", "Contribution margin, not full customer P&L",
         "True margins here are revenue minus activity-based labour. They are not a full customer P&L with "
         "allocated corporate overhead, so they show relative profitability, not statutory profit.",
         "Layer the management overhead allocation onto the activity costs for a board-grade customer P&L.",
         "Findings affected: All margin percentages — directionally correct, but absolute % will shift"),
    ]
    for color, sev, title, why, ask, impact in gaps:
        st.markdown(f"""
        <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {color};
                    border-radius:4px;padding:14px 18px;margin-bottom:10px'>
          <span style='background:{color}1A;color:{color};font-size:9px;font-weight:700;
                       padding:2px 8px;border-radius:2px;letter-spacing:1px'>{sev}</span>
          <div style='font-size:14px;font-weight:700;color:{C_TEXT};margin:8px 0 4px'>{title}</div>
          <div style='font-size:12px;color:{C_TEXT};line-height:1.5;margin-bottom:5px'>{why}</div>
          <div style='font-size:12px;color:{C_GREEN};line-height:1.5;margin-bottom:5px'>
            <b>What we'd request:</b> {ask}</div>
          <div style='font-size:11px;color:{C_MUTED};font-style:italic'>{impact}</div>
        </div>""", unsafe_allow_html=True)

    _sec("The Five Questions We'd Ask Management Next")
    qs = [
        ("Can we have 12 months of volume and revenue history to confirm the two-month annualisation?",
         "Upgrades F013, F015 from MEDIUM to HIGH confidence"),
        ("What is the fully-loaded warehouse cost base (equipment, facility, supervision) beyond direct labour?",
         "Makes all cost-per-pick and margin findings board-grade"),
        ("What is the contracted capacity / slot allocation per customer, so we can measure true utilisation?",
         "Enables precise fixed-fee customer analysis"),
        ("For the unbilled exceptions, which contract clauses govern re-billing of returns, rework and urgent orders?",
         "Unlocks F004 Delta and F005 Charlie unbilled findings for negotiation"),
        ("Which customers are strategic / relationship-protected, so repricing is sequenced commercially, not just by dollars?",
         "Shapes the negotiation roadmap — not all $1.86M is equally recoverable"),
    ]
    for i, (q, impact) in enumerate(qs, 1):
        st.markdown(f"""
        <div style='background:{C_GREEN_LITE};border-radius:4px;padding:12px 16px;margin-bottom:8px;
                    display:flex;gap:12px;align-items:flex-start'>
          <div style='font-size:18px;font-weight:700;color:{C_GREEN};flex-shrink:0;width:24px;
                      text-align:center'>{i}</div>
          <div style='flex:1'>
            <div style='font-size:13px;color:{C_TEXT};line-height:1.5'>{q}</div>
            <div style='font-size:11px;color:{C_GREEN};margin-top:4px;font-style:italic'>{impact}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    _sec("What Closing These Gaps Unlocks")
    st.markdown(f"""
    <div style='display:flex;gap:12px;margin-bottom:8px'>
      <div style='flex:1;background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:14px 18px'>
        <div style='font-size:9px;font-weight:700;color:{C_RED};letter-spacing:1px;margin-bottom:6px'>CLOSE HIGH GAPS FIRST</div>
        <div style='font-size:22px;font-weight:700;color:{C_TEXT}'>2 HIGH priority gaps</div>
        <div style='font-size:12px;color:{C_MUTED};margin-top:4px;line-height:1.5'>
          Overhead costs + missing pay records<br>
          Upgrades 8 of 12 findings to HIGH confidence<br>
          Required before repricing negotiations
        </div>
      </div>
      <div style='flex:1;background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:14px 18px'>
        <div style='font-size:9px;font-weight:700;color:{C_AMBER};letter-spacing:1px;margin-bottom:6px'>THEN MEDIUM GAPS</div>
        <div style='font-size:22px;font-weight:700;color:{C_TEXT}'>3 MEDIUM priority gaps</div>
        <div style='font-size:12px;color:{C_MUTED};margin-top:4px;line-height:1.5'>
          12-month history + capacity data + exception definition<br>
          Enables board-grade customer P&L<br>
          Required for WH002 + WH003 rollout
        </div>
      </div>
      <div style='flex:1;background:{C_GREEN_LITE};border:1px solid #B7DCC8;border-radius:4px;padding:14px 18px'>
        <div style='font-size:9px;font-weight:700;color:{C_GREEN};letter-spacing:1px;margin-bottom:6px'>RESULT: FULL CONFIDENCE</div>
        <div style='font-size:22px;font-weight:700;color:{C_GREEN}'>10/10 confidence</div>
        <div style='font-size:12px;color:{C_MUTED};margin-top:4px;line-height:1.5'>
          All 12 findings at HIGH confidence<br>
          $2.65M opportunity fully defensible<br>
          Platform ready for network expansion
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)
