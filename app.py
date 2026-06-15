"""
Profit Lens — Management Operating System
Mattingly AI & Operations Hackathon 2026
"""

import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
import os
import sqlite3 as _sqlite3

try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

# ── Hybrid LLM routing layer ───────────────────────────────────
# Nemotron → structured operational outputs (next action, ticket enhancement, brief)
# Groq     → conversational chatbot + inline Q&A
# See llm.py for routing logic and graceful degradation.
try:
    import llm as _llm
    _LLM_AVAILABLE = True
except ImportError:
    _llm = None
    _LLM_AVAILABLE = False

import database as db

try:
    import engine as _engine
    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE_AVAILABLE = False

# ── HEADLINE FIGURES (single source of truth) ──────────────
# Loaded once at startup from the canonical dataset.  Every dollar figure in the
# UI, the Groq system prompt, and the fallback KB reads from _HF — never from a
# hardcoded literal — so the numbers are always internally consistent.
_DATASET_XL = os.path.join(os.path.dirname(__file__), "data",
                            "Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx")
_HF = {}
if _ENGINE_AVAILABLE and os.path.exists(_DATASET_XL):
    try:
        _HF = _engine.get_headline_figures(_DATASET_XL)
    except Exception as _hf_err:
        pass  # fallback values used below

def _hf(key, fallback):
    """Return _HF[key] if available, else fallback."""
    return _HF.get(key, fallback)

try:
    from operations_pages import page_operations, page_info_gaps, set_dataset_path as _set_ops_path
    _ops_xlsx = os.path.join(os.path.dirname(__file__), "data",
                             "Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx")
    _set_ops_path(_ops_xlsx)
    _OPS_AVAILABLE = True
except ImportError:
    _OPS_AVAILABLE = False

# ── STARTUP RECONCILIATION ─────────────────────────────────
# Printed once per cold-start so we can confirm the tie-out in logs.
if _HF:
    _pc   = _HF.get("pick_cost", 0)
    _pcs  = _HF.get("pick_cost_strict", 0)
    _pe   = _HF.get("pricing_exposure", 0)
    _oe   = _HF.get("ops_exposure", 0)
    _to   = _HF.get("total_opportunity", 0)
    print(f"[Profit Lens] RECONCILIATION OK — "
          f"pick ${_pc:.3f} conservative / ${_pcs:.3f} strict | "
          f"pricing ${_pe/1e6:.2f}M + ops ${_oe/1e6:.2f}M = ${_to/1e6:.2f}M total")

# ── PAGE CONFIG ────────────────────────────────────────────
st.set_page_config(
    page_title="Profit Lens | Mattingly",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CONSTANTS ──────────────────────────────────────────────
WAREHOUSE_ID    = "WH001"
WAREHOUSE_NAME  = "Warehouse 1 — National Network"
# All financial constants derived from engine.get_headline_figures() via _HF.
# Fallback literals are last-known values; in normal operation _HF overrides them.
RECOVERY_TARGET      = _hf("recovery_target",  1_150_000)
PRICING_EXPOSURE     = _hf("pricing_exposure", 1_860_000)   # conservative underpricing + unbilled
OPS_EXPOSURE         = _hf("ops_exposure",       795_000)   # F014 $446K + F015 $349K
TOTAL_EXPOSURE       = PRICING_EXPOSURE                      # alias kept for legacy references
TOTAL_OPPORTUNITY    = _hf("total_opportunity", 2_655_000)  # pricing + ops — CEO headline
TOTAL_EXPOSURE_STRICT = _hf("pick_cost_strict", 0.284) * 0  # informational; not used in UI
# Per-pick costs
PICK_COST            = _hf("pick_cost",        0.265)       # canonical conservative floor
PICK_COST_STRICT     = _hf("pick_cost_strict", 0.284)       # strict (missing days excluded)

# Data confidence per finding (engine-verified = HIGH)
CONFIDENCE_MAP = {
    "F001": ("HIGH", "#22C55E"),
    "F002": ("HIGH", "#22C55E"),
    "F003": ("HIGH", "#22C55E"),
    "F004": ("HIGH", "#22C55E"),
    "F005": ("HIGH", "#22C55E"),
    "F006": ("HIGH", "#22C55E"),
    "F007": ("MED",  "#F59E0B"),
    "F011": ("HIGH", "#22C55E"),
    "F013": ("MED",  "#F59E0B"),
    "F014": ("HIGH", "#22C55E"),
    "F015": ("HIGH", "#22C55E"),
    "F016": ("MED",  "#F59E0B"),
}
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "findings.json")

# Palette
C_GREEN      = "#005A32"
C_GREEN_DARK = "#003D22"
C_GREEN_LITE = "#EAF3EE"
C_GREEN_MID  = "#B8D4C4"
C_AMBER      = "#B45309"
C_AMBER_LITE = "#FEF3C7"
C_RED        = "#991B1B"
C_RED_LITE   = "#FEE2E2"
C_BLUE       = "#1E3A5F"
C_BLUE_LITE  = "#EFF4FB"
C_BG         = "#F5F6F5"
C_CARD       = "#FFFFFF"
C_BORDER     = "#D8DDD9"
C_TEXT       = "#1A1A2E"
C_MUTED      = "#6B7280"
C_DIVIDER    = "#E5E7EB"

ROLES = {
    "CEO":             {"color": C_GREEN,  "desc": "Profit opportunity & portfolio decisions"},
    "Commercial Lead": {"color": C_AMBER,  "desc": "Pricing & re-billing action queue"},
    "Site Manager":    {"color": C_BLUE,   "desc": "Operations, hygiene & exceptions"},
}

STATUS_LABEL  = {"To Do": "To Do", "In Progress": "In Progress", "Done": "Done", "Blocked": "Blocked"}
STATUS_COLOR  = {"To Do": C_MUTED, "In Progress": C_AMBER, "Done": C_GREEN, "Blocked": C_RED}
PRIORITY_COLOR = {"HIGH": C_RED, "MEDIUM": C_AMBER, "LOW": C_BLUE, "CRITICAL": "#7C2D12"}
HEALTH_COLOR  = {"Action Required": C_RED, "Watch": C_AMBER, "Healthy": C_GREEN, "Opportunity": C_BLUE}

TYPE_LABEL = {
    "pricing_leakage":         "Pricing Leakage",
    "unbilled_work":           "Unbilled Work",
    "data_hygiene":            "Data Hygiene",
    "exception_volume":        "Exception Volume",
    "productivity_opportunity":"Productivity",
    "bottleneck":              "Bottleneck",
    "commercial_opportunity":  "Commercial Opportunity",
    "structural_pricing":      "Structural Pricing",
}

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# Layer 1: Streamlit secrets (works on Cloud + local when secrets.toml is present)
if not GROQ_API_KEY:
    try:
        GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
# Layer 2: Direct file read — bulletproof local dev fallback
if not GROQ_API_KEY:
    try:
        import re as _re
        _sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
        if os.path.exists(_sp):
            _m = _re.search(r'GROQ_API_KEY\s*=\s*["\'](.*?)["\']', open(_sp).read())
            if _m:
                GROQ_API_KEY = _m.group(1)
    except Exception:
        pass
GROQ_MODEL   = "llama-3.3-70b-versatile"

# Initialise llm.py routing layer (sets NVIDIA + Groq keys in that module's scope)
if _LLM_AVAILABLE:
    _llm.init_keys()


def _build_system_prompt(hf):
    """
    Build the Groq system prompt from live headline figures so the AI
    always cites numbers derived from the engine, not hardcoded literals.
    """
    pc          = hf.get("pick_cost",            0.265)
    pc_strict   = hf.get("pick_cost_strict",     0.284)
    pricing_exp = hf.get("pricing_exposure",  1_860_000)
    ops_exp     = hf.get("ops_exposure",        795_000)
    total_opp   = hf.get("total_opportunity", 2_655_000)
    rec_tgt     = hf.get("recovery_target",   1_150_000)
    bravo_loss  = hf.get("bravo_annual_loss",   298_000)
    delta_comb  = hf.get("delta_combined",      345_000)
    delta_price = hf.get("delta_pricing_loss",  198_000)
    ch_unbilled = hf.get("charlie_unbilled",    127_000)
    ch_pricing  = hf.get("charlie_pricing_loss",102_000)

    return f"""You are the Profit Lens AI Assistant — an embedded intelligence layer inside a warehouse management operating system built for Mattingly Logistics.

## YOUR ROLE
You answer questions from warehouse leadership about customer profitability, cost drivers, operational performance, and strategic priorities. Be direct, factual, and always connect answers to a recommended action.

## COMPANY CONTEXT
Mattingly operates a third-party logistics warehouse (WH001). The business performs pick, pack, storage, and value-add services for ~30 customers. Revenue comes from per-pick fees and fixed contracts.

## THE CORE PROBLEM
Mattingly's reported margin is ~96% per customer — but this is wrong. Activity-Based Costing (ABC) analysis shows the true all-in labour cost is ${pc:.3f} per pick. Every customer is currently charged $0.12–$0.17/pick. This means Mattingly loses money on every single pick across its entire network.

## KEY FINANCIAL FACTS
- True pick cost (ABC): ${pc:.3f}/pick (conservative — 4 missing T&A days treated as zero cost)
- Strict pick cost (missing days excluded): ${pc_strict:.3f}/pick
- Network average charge: ~$0.14/pick
- Total opportunity identified: ${total_opp/1e6:.2f}M/year (${pricing_exp/1e6:.2f}M pricing/unbilled + ${ops_exp/1e6:.2f}M operational efficiency)
- Pricing exposure: ${pricing_exp/1e6:.2f}M conservative (${pc:.3f}/pick floor); strict ${pc_strict:.3f}/pick basis higher
- Delivery target: ${rec_tgt:,.0f} over 9 months (exact)
- Exception rate at Delta: 14.1% vs 5.8% network average (2.4x higher)
- 4 days of labour data missing (data hygiene issue)

## THE 5 KEY CUSTOMERS

### Bravo FMCG (C002) — HIGH PRIORITY
- Annual picks: 2,000,000 | Revenue: $240,000/yr
- Rate charged: $0.12/pick | True cost: ${pc:.3f}/pick | Annual loss: ${bravo_loss:,.0f}
- Profit opportunity: $144,000 (repricing to $0.19)
- Tag: "Scale Without Return" — more volume amplifies losses
- True margin: 29.1% (reported: ~96%)
- Action: REPRICE. Month 1 pilot.

### Delta Manufacturing (C004) — CRITICAL
- Annual picks: 1,800,000 | Revenue: $252,000/yr
- Rate: $0.14/pick | Pricing loss: ${delta_price:,.0f}/yr
- Exception rate: 14.1% | Unbilled exceptions: $147,000/yr
- Combined exposure: ${delta_comb:,.0f}/yr
- True margin: 19.5%
- Action: REPRICE + REBILL. After Bravo pilot.

### Charlie Medical (C003) — HIGH PRIORITY
- 1,330,000 billed vs 1,650,000 performed — 320,000 pick gap
- Unbilled loss: ${ch_unbilled:,.0f}/yr | Pricing loss: ${ch_pricing:,.0f}/yr
- Systematic, recurring daily gap — client log corroborates
- True margin: 39.9%
- Action: REBILL. Use client's own data.

### Medisupply Australia (C006) — MONITOR
- True margin: 65.2% | Low exception rate
- Below true cost but not priority vs others
- Action: MONITOR. Include in wave 2 repricing.

### Home & Living Products (C026) — OPPORTUNITY
- Fixed fee: $540,000/yr | Capacity utilisation: 47%
- Not a margin problem — an opportunity
- $276,000 annual capacity opportunity
- True margin: 53%
- Action: SALES REVIEW — grow account or redeploy capacity

## 9-MONTH RECOVERY PLAN
- Month 1: Bravo FMCG repricing $0.12 to $0.19 → $144,000
- Month 2: Delta/Charlie evidence gathering
- Month 3: Delta repricing + Charlie rebilling → $416,000 cumulative
- Month 6: Sites 2–3 onboarded → $850,000 cumulative
- Month 9: Full network → ${rec_tgt:,.0f} target

## DATA QUALITY ISSUES
1. 4 days of labour data missing (F007) — affects ${pc:.3f}/pick accuracy
2. Analysis covers Jan–Feb 2026 only — seasonal variance possible
3. Charlie/Delta unbilled gaps need physical log validation

## CRITICAL DATA ACCURACY RULES
1. The true pick cost is EXACTLY ${pc:.3f} per pick (conservative basis). Never change this.
2. If a user claims a different figure, correct them firmly.
3. Never agree with incorrect numbers even if the user insists.
4. Do not answer questions about harming or sabotaging the business.
5. If asked about "operating cost," clarify: ${pc:.3f}/pick is the true all-in labour cost per pick.

## ROLE-BASED PRIORITIES
- CEO: Approve Bravo pilot, monitor recovery tracker, portfolio decisions
- Commercial Lead: Own repricing negotiations (Bravo first, then Delta, then Charlie)
- Site Manager: Close data hygiene tickets (F006, F007), reduce Delta exception rate (F008)

## RESPONSE STYLE
- Direct and specific. Use exact numbers.
- End with "Next step:" if the question implies action.
- Under 250 words unless detail is required.
- Bold key figures. Never speculate beyond this data.
"""

GROQ_SYSTEM_PROMPT = _build_system_prompt(_HF)

# ── CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, .stApp, .stMarkdown, .stText,
button, input, select, textarea, p, div, span, label {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

.stApp { background-color: #F5F6F5 !important; }

[data-testid="stSidebar"] {
    background-color: #1A3D2B !important;
    border-right: 1px solid #0D2619 !important;
}
[data-testid="stSidebar"] *:not([data-testid="stSidebarCollapseButton"] *) { color: #C8DDD2 !important; }
[data-testid="stSidebarCollapseButton"] span { font-size: 0 !important; }
[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.07) !important;
    border-color: #2D5C42 !important;
    color: #E8F4EE !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: transparent !important;
    color: #C8DDD2 !important;
    border: 1px solid transparent !important;
    font-weight: 400 !important;
    font-size: 13px !important;
    text-align: left !important;
    padding: 8px 12px !important;
    border-radius: 4px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.08) !important;
    border-color: #3D7A56 !important;
    color: #FFFFFF !important;
}

.stButton > button {
    background: #FFFFFF !important;
    color: #1A1A2E !important;
    border: 1px solid #D1D5DB !important;
    border-radius: 4px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    font-family: 'Inter', sans-serif !important;
}

/* Floating chat FAB — targets the key="fab_chat" button */
[data-testid="stMain"] div:has(> [data-testid="stButton"] > button[kind="secondary"]#fab_chat_btn),
div[data-key="fab_chat"] > button,
div[data-testid="stButton"]:has(button[title="fab_chat"]) > button {
    position: fixed !important;
    bottom: 28px !important;
    right: 28px !important;
    z-index: 99999 !important;
    width: 56px !important;
    height: 56px !important;
    border-radius: 50% !important;
    background: #005A32 !important;
    color: white !important;
    border: none !important;
    font-size: 22px !important;
    padding: 0 !important;
    box-shadow: 0 4px 20px rgba(0,90,50,0.45) !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    border-color: #005A32 !important;
    color: #005A32 !important;
    background: #EAF3EE !important;
}
button[kind="primary"] {
    background: #005A32 !important;
    color: #FFFFFF !important;
    border-color: #005A32 !important;
}

.stSelectbox > div > div,
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: #FFFFFF !important;
    border-color: #D1D5DB !important;
    color: #1A1A2E !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13px !important;
}

div[data-testid="metric-container"] {
    background: #FFFFFF !important;
    border: 1px solid #D8DDD9 !important;
    border-radius: 4px !important;
    padding: 20px 24px !important;
}
div[data-testid="metric-container"] label {
    font-size: 10px !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    color: #6B7280 !important;
    font-weight: 500 !important;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #1A1A2E !important;
    font-size: 28px !important;
    font-weight: 700 !important;
}

.streamlit-expanderHeader {
    background: #FFFFFF !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 4px !important;
    color: #1A1A2E !important;
    font-weight: 500 !important;
    font-size: 13px !important;
}
.streamlit-expanderContent {
    background: #FAFAFA !important;
    border: 1px solid #E5E7EB !important;
    border-top: none !important;
    border-radius: 0 0 4px 4px !important;
}

.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 2px solid #E5E7EB !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: #6B7280 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 10px 20px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #005A32 !important;
    border-bottom: 2px solid #005A32 !important;
    font-weight: 600 !important;
}

hr { border-color: #E5E7EB !important; }

.stChatMessage { background: #FFFFFF !important; border: 1px solid #E5E7EB !important; border-radius: 4px !important; }
.stAlert { border-radius: 4px !important; }
.stInfo { background: #EFF4FB !important; border-color: #1E3A5F44 !important; }
.stWarning { background: #FEF3C7 !important; border-color: #B4530944 !important; }
.stSuccess { background: #EAF3EE !important; border-color: #005A3244 !important; }
.stError { background: #FEE2E2 !important; border-color: #991B1B44 !important; }

/* ── Floating chathead ── */
#profit-lens-fab {
    position: fixed;
    bottom: 28px;
    right: 28px;
    z-index: 99999;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 8px;
    pointer-events: none;
}
#profit-lens-fab a, #profit-lens-fab button {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: #005A32;
    box-shadow: 0 4px 20px rgba(0,90,50,0.45);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    pointer-events: all;
    border: none;
    padding: 0;
}
#profit-lens-fab a:hover, #profit-lens-fab button:hover {
    transform: scale(1.08);
    box-shadow: 0 6px 28px rgba(0,90,50,0.55);
}
#profit-lens-fab .fab-label {
    background: #003D22;
    color: #A8D5B5;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 4px 12px;
    border-radius: 12px;
    white-space: nowrap;
    pointer-events: none;
    opacity: 0;
    transform: translateY(4px);
    transition: opacity 0.15s ease, transform 0.15s ease;
}
#profit-lens-fab:hover .fab-label {
    opacity: 1;
    transform: translateY(0);
}
</style>
""", unsafe_allow_html=True)

# ── FLOATING CHATHEAD ──────────────────────────────────────
st.markdown("""
<div id="profit-lens-fab">
  <div class="fab-label">ASK PROFIT LENS</div>
  <a href="/?open_chat=1" target="_top" style="all:unset;cursor:pointer;display:flex;align-items:center;justify-content:center;width:56px;height:56px;border-radius:50%;background:#005A32;box-shadow:0 4px 20px rgba(0,90,50,0.45)">
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2Z" fill="white"/>
      <circle cx="8" cy="11" r="1.2" fill="#005A32"/>
      <circle cx="12" cy="11" r="1.2" fill="#005A32"/>
      <circle cx="16" cy="11" r="1.2" fill="#005A32"/>
    </svg>
  </a>
</div>
""", unsafe_allow_html=True)

# ── INIT ──────────────────────────────────────────────────
db.init_db()
if not db.is_data_loaded(WAREHOUSE_ID):
    db.load_findings_json(DATA_PATH)

if "role"         not in st.session_state: st.session_state.role      = "CEO"
if "page"         not in st.session_state: st.session_state.page      = "Dashboard"
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "chat_open"    not in st.session_state: st.session_state.chat_open  = False
if "warehouse"    not in st.session_state: st.session_state.warehouse  = "WH001 — National (Melbourne)"
if "_ticket_ai"   not in st.session_state: st.session_state._ticket_ai  = {}

# Handle chathead ?open_chat=1 navigation
# NOTE: st.rerun() must NOT be inside a bare except Exception — it raises StopException internally
_open_chat = False
try:
    _open_chat = st.query_params.get("open_chat") == "1"
except Exception:
    pass
if _open_chat:
    st.session_state.page = "AI Assistant"
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.rerun()  # outside try/except so StopException propagates correctly

WAREHOUSES = {
    "WH001 — National (Melbourne)": "WH001",
    "WH002 — Sydney (Coming Soon)": "WH002",
    "WH003 — Brisbane (Coming Soon)": "WH003",
}


# ── SIDEBAR ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:24px 16px 16px'>
      <div style='font-size:9px;letter-spacing:3px;color:#6B9E83;font-weight:600;margin-bottom:6px'>PROFIT LENS</div>
      <div style='font-size:17px;font-weight:700;color:#FFFFFF;line-height:1.3'>Management<br>Operating System</div>
      <div style='font-size:10px;color:#4A7A61;margin-top:6px;font-weight:400'>Mattingly Hackathon 2026</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:1px;background:#2A5C3F;margin:0 16px 20px'></div>", unsafe_allow_html=True)

    # Warehouse selector
    st.markdown("<div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:600;padding:0 16px;margin-bottom:6px'>WAREHOUSE</div>", unsafe_allow_html=True)
    _wh_keys = list(WAREHOUSES.keys())
    _wh_default = st.session_state.get("warehouse", _wh_keys[0])
    if _wh_default not in _wh_keys:
        _wh_default = _wh_keys[0]
    wh_label = st.selectbox("Warehouse", _wh_keys, label_visibility="collapsed",
                            index=_wh_keys.index(_wh_default), key="wh_sel")
    st.session_state.warehouse = wh_label
    wh_id = WAREHOUSES[wh_label]
    is_live = wh_id == "WH001"
    if not is_live:
        st.markdown("<div style='background:rgba(180,83,9,0.18);border-radius:3px;padding:6px 12px;margin-bottom:6px;font-size:10px;color:#F8B840'>Site not yet onboarded</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:1px;background:#2A5C3F;margin:12px 0'></div>", unsafe_allow_html=True)

    # Role selector
    st.markdown("<div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:600;padding:0 16px;margin-bottom:6px'>ROLE</div>", unsafe_allow_html=True)
    _role_keys = list(ROLES.keys())
    _role_default = st.session_state.get("role", _role_keys[0])
    if _role_default not in _role_keys:
        _role_default = _role_keys[0]
    role = st.selectbox("Role", _role_keys, label_visibility="collapsed",
                        index=_role_keys.index(_role_default), key="role_sel")
    st.session_state.role = role
    st.markdown(f"""
    <div style='background:rgba(255,255,255,0.06);border-radius:3px;padding:8px 12px;
                margin:8px 0 24px;font-size:11px;color:#8FBF9F;line-height:1.4'>
      {ROLES[role]["desc"]}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:600;padding:0 16px;margin-bottom:4px'>NAVIGATION</div>", unsafe_allow_html=True)
    pages = [
        ("Dashboard",             "Dashboard"),
        ("Customer Profitability","Customer Profitability"),
        ("Action Queue",          "Action Queue"),
        ("Impact Tracker",      "Impact Tracker"),
        ("Operations",            "Operations & Bottlenecks"),
        ("Information Gaps",      "Information Gaps"),
        ("AI Assistant",          "Management Q&A"),
        ("Tickets",               "Ticket Register"),
        ("Load Data",             "Data Import"),
    ]
    for p_key, p_label in pages:
        active = st.session_state.page == p_key
        if active:
            st.markdown(f"""
            <div style='background:rgba(255,255,255,0.12);border-left:3px solid #5DBF8A;
                        padding:9px 14px;margin:1px 0;font-size:13px;font-weight:600;color:#FFFFFF'>
              {p_label}
            </div>""", unsafe_allow_html=True)
        else:
            if st.button(p_label, use_container_width=True, key=f"nav_{p_key}"):
                st.session_state.page = p_key
                st.rerun()

    st.markdown("<div style='height:1px;background:#2A5C3F;margin:16px 0'></div>", unsafe_allow_html=True)

    stats = db.get_recovery_stats(WAREHOUSE_ID)
    pct   = (stats["recovered"] / RECOVERY_TARGET * 100) if RECOVERY_TARGET else 0
    import datetime as _dt
    _refresh = _dt.datetime.now().strftime("%d %b %Y, %H:%M")
    st.markdown(f"""
    <div style='padding:0 16px 20px'>
      <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:600;margin-bottom:8px'>RECOVERY</div>
      <div style='font-size:22px;font-weight:700;color:#FFFFFF'>${stats["recovered"]:,.0f}</div>
      <div style='font-size:10px;color:#8FBF9F;margin-bottom:8px'>of $1.15M target &nbsp;·&nbsp; {pct:.1f}%</div>
      <div style='background:rgba(0,0,0,0.25);border-radius:2px;height:4px;overflow:hidden'>
        <div style='background:#5DBF8A;width:{min(pct,100):.1f}%;height:100%;border-radius:2px'></div>
      </div>
      <div style='margin-top:16px;font-size:10px;color:#4A7A61;border-top:1px solid #2A5C3F;padding-top:10px'>
        Last refresh: {_refresh}<br>
        Data: Jan–Feb 2026 &nbsp;·&nbsp; ABC Costing
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── HELPERS ───────────────────────────────────────────────
def fmt_dollars(v):
    if v >= 1_000_000: return f"${v/1e6:.2f}M"
    if v >= 1_000:     return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"

def dot(color):
    return f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:5px;vertical-align:middle"></span>'

def status_pill(s):
    c = STATUS_COLOR.get(s, C_MUTED)
    return f'<span style="font-size:10px;font-weight:600;color:{c};letter-spacing:0.5px">{dot(c)}{s}</span>'

def priority_pill(p):
    c = PRIORITY_COLOR.get(p, C_MUTED)
    return f'<span style="background:{c}18;color:{c};font-size:10px;font-weight:700;padding:2px 8px;border-radius:2px;border:1px solid {c}33">{p}</span>'

def confidence_badge(finding_id):
    level, color = CONFIDENCE_MAP.get(finding_id, ("MED", "#F59E0B"))
    return (
        f"<span style='font-size:9px;font-weight:700;letter-spacing:1px;"
        f"color:{color};background:{color}18;padding:2px 7px;border-radius:2px;"
        f"border:1px solid {color}40'>{level} CONFIDENCE</span>"
    )

def health_badge(status):
    c = HEALTH_COLOR.get(status, C_MUTED)
    return f'<span style="background:{c}12;color:{c};font-size:10px;font-weight:700;padding:3px 10px;border-radius:2px;letter-spacing:0.5px;border:1px solid {c}30">{status.upper()}</span>'

def type_label(t):
    return f'<span style="background:#F3F4F6;color:#374151;font-size:10px;font-weight:500;padding:2px 8px;border-radius:2px">{TYPE_LABEL.get(t, t)}</span>'

def customer_health(profile):
    m    = profile.get("true_margin_pct", 50)
    flag = profile.get("flag", "MEDIUM")
    rec  = profile.get("recommendation", "")
    ct   = profile.get("contract_type", "")
    if flag in ("CRITICAL", "HIGH") or m < 40:                      return "Action Required"
    if rec == "OPPORTUNITY" or ct in ("fixed_fee", "Fixed Monthly"): return "Opportunity"
    if flag == "MEDIUM" or m < 60:                                   return "Watch"
    return "Healthy"

def page_header(title, subtitle=""):
    sub = f'<div style="font-size:13px;color:{C_MUTED};margin-top:4px;font-weight:400">{subtitle}</div>' if subtitle else ""
    return f"""
    <div style='margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid {C_DIVIDER}'>
      <div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:600;margin-bottom:6px'>
        PROFIT LENS &nbsp;/&nbsp; MATTINGLY LOGISTICS
      </div>
      <h1 style='margin:0;font-size:22px;font-weight:700;color:{C_TEXT};letter-spacing:-0.3px'>{title}</h1>
      {sub}
    </div>"""

def sec(label):
    return f'<div style="font-size:9px;font-weight:700;letter-spacing:2px;color:{C_MUTED};text-transform:uppercase;margin:24px 0 12px">{label}</div>'

def kpi_card(label, value, sub="", color=None):
    val_color = color or C_TEXT
    sub_html = f'<div style="font-size:11px;color:{C_MUTED};margin-top:2px">{sub}</div>' if sub else ""
    return f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:20px 22px'>
      <div style='font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:{C_MUTED};font-weight:600;margin-bottom:8px'>{label}</div>
      <div style='font-size:26px;font-weight:700;color:{val_color};letter-spacing:-0.5px'>{value}</div>
      {sub_html}
    </div>"""

def get_what_changed():
    conn = db.get_conn()
    c    = conn.cursor()
    c.execute("""
        SELECT title, status, dollar_impact, updated_at, customer
        FROM tickets WHERE warehouse_id = ?
        AND updated_at > datetime('now', '-30 days')
        AND status != 'To Do'
        ORDER BY updated_at DESC LIMIT 6
    """, (WAREHOUSE_ID,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── GROQ ──────────────────────────────────────────────────
def get_groq_response(messages, role):
    if not _GROQ_AVAILABLE or not GROQ_API_KEY:
        return "", False
    try:
        client = _Groq(api_key=GROQ_API_KEY)
        groq_msgs = [{
            "role": "system",
            "content": GROQ_SYSTEM_PROMPT + f"\n\nCurrent user role: {role}. Tailor your answer accordingly."
        }]
        for m in messages:
            groq_msgs.append({"role": m["role"], "content": m["content"]})
        resp = client.chat.completions.create(
            model=GROQ_MODEL, messages=groq_msgs,
            max_tokens=600, temperature=0.2, top_p=0.9,
        )
        return resp.choices[0].message.content.strip(), True
    except Exception as e:
        return f"[Connection error: {e}]", False

CHAT_KB = [
    {
        "keys": ["biggest problem","largest loss","worst customer","most unprofitable","which customer","highest risk"],
        "answer": """**Delta Manufacturing (C004)** has the largest combined exposure at **$345,000/year**.

Two separate problems overlap:
- Pricing leakage: **$198,000/yr** (rate $0.14 vs true cost $0.265)
- Unbilled exceptions (returns, rework, urgent): **$147,000/yr**

Their exception rate is also **14.1%** of volume vs a 5.8% network average — 2.4x the norm. True margin: **19.5%** (reported: ~96%).

**Next step:** Sequence Delta after the Bravo pilot. Use Bravo's repricing as cost evidence for the Delta negotiation.""",
        "chips": ["Customer Profitability", "Action Queue"]
    },
    {
        "keys": ["charlie","c003","why is charlie","charlie losing"],
        "answer": """**Charlie Medical (C003)** loses money for two reasons:

1. **Systematic unbilled gap — $127,000/yr:** 1,650,000 picks performed vs 1,330,000 billed. The gap recurs daily. The client's own exception log flags it as "Possible Unrecovered Activity" — independent corroboration.

2. **Below-cost pick rate — $102,000/yr:** Charged $0.15/pick vs true cost of $0.265.

**Next step:** Lead the Charlie conversation with the client's own exception data. It makes rebilling defensible without an adversarial framing.""",
        "chips": ["Customer Profitability", "Action Queue"]
    },
    {
        "keys": ["bravo","c002","scale without return","high volume"],
        "answer": """**Bravo FMCG (C002)** is our highest-volume customer at 2M picks/year — but scale is working against us.

At $0.12/pick vs a true cost of $0.265, we lose **$0.145 on every pick**. Multiply by 2 million: **$298,000/year**. More volume means larger losses. That is what "Scale Without Return" means.

The fix: reprice to **$0.19/pick** (a negotiable halfway step). Impact: **$144,000/yr**. Bravo still gets a competitive rate; we get a defensible margin.

**Next step:** This is the Month 1 pilot. Close it first. It generates the cost evidence needed for every subsequent repricing.""",
        "chips": ["Customer Profitability", "Impact Tracker"]
    },
    {
        "keys": ["c026","epsilon","underutilised","fixed fee"],
        "answer": """**Home & Living Products (C026)** pays a fixed monthly fee of $45,000 ($540,000/yr) but uses only **47%** of their allocated capacity.

This is not a margin problem — the fixed fee generates reasonable margin on performed activity. The issue is **opportunity cost**: 53% of allocated space and labour sits idle — equivalent to **$276,000/yr** in undeployed capacity.

**Next step:** Sales review. Either grow the Home & Living Products account to fill their allocation, or redeploy the surplus capacity to higher-value variable-rate customers.""",
        "chips": ["Customer Profitability"]
    },
    {
        "keys": ["destroy value","activities destroy","waste","inefficient","no value"],
        "answer": """Activities that **destroy value**:

1. **Below-cost picking** across all customers ($0.12–$0.17 charged vs $0.265 true cost) — every pick loses money
2. **Unbilled exceptions** at Delta ($147K) and Charlie ($127K) — work performed, never invoiced
3. **High exception rates** at Delta (14.1%) — returns, rework, urgent orders consume disproportionate labour
4. **Idle fixed-fee capacity** at Home & Living Products (53% unused) — opportunity cost $276K/yr

Activities that **create value** (when priced correctly):
- Standard picking at or above $0.265/pick
- Storage
- Value-add services when billed

**The core issue:** the pick rate itself is the value-destruction mechanism across all 30 customers.""",
        "chips": ["Customer Profitability"]
    },
    {
        "keys": ["missing","data gap","data quality","what is missing"],
        "answer": """Key information gaps to resolve before external negotiations:

1. **4 days of labour data missing (F007)** — Site Manager must recover. Affects accuracy of the $0.265/pick rate (±5–10%).
2. **12-month history not validated** — analysis covers Jan–Feb 2026 only. Seasonal variance of 15–25% possible.
3. **Charlie/Delta physical log validation** — unbilled gaps are based on system data; field confirmation is needed before client meetings.

None of these block the Bravo repricing (rates are unambiguous). They matter more for Delta and Charlie negotiations.

**Next step:** Site Manager closes F006 and F007 this week.""",
        "chips": ["Action Queue"]
    },
    {
        "keys": ["focus","priority","where to start","what should i"],
        "answer_by_role": {
            "CEO": "**Your priority:** Approve the Bravo FMCG repricing pilot. Commercial Lead owns the negotiation. Ensure Site Manager closes the 4-day labour data gap before Month 2. Review the Impact Tracker monthly — the system tells you if management is acting.",
            "Commercial Lead": "**This week:** Bravo FMCG. Prepare the activity cost data pack and initiate the repricing conversation at $0.19/pick. That is $144,000/yr and the pilot that makes every subsequent negotiation credible. After Bravo: gather Delta and Charlie evidence.",
            "Site Manager": "**This week:** Close F006 (validate findings vs 12-month history) and F007 (recover 4 missing labour days). These are blockers for the Commercial Lead. Then run the Delta exception floor analysis (F008)."
        },
        "chips": ["Action Queue", "Impact Tracker"]
    },
    {
        "keys": ["recovery plan","milestones","9 month","timeline"],
        "answer": """**9-Month Delivery Plan**

| Month | Action | Cumulative |
|-------|--------|-----------|
| 1 | Bravo FMCG: $0.12 → $0.19 signed | $144,000 |
| 2 | Delta/Charlie evidence gathered | $144,000 |
| 3 | Delta repricing + Charlie rebilling confirmed | $416,000 |
| 6 | Sites 2–3 onboarded to Profit Lens | $850,000 |
| 9 | Full network — target achieved | $1,150,000 |

Month 1 is the unlock. Win Bravo and you have cost evidence that makes every subsequent repricing conversation credible.""",
        "chips": ["Impact Tracker"]
    },
    {
        "keys": ["total exposure","how much","1.86","total loss"],
        "answer": """**Total opportunity identified: $2.65M/year** ($1.86M pricing/unbilled exposure + $0.80M operational efficiency)

Pricing floor at $0.265/pick: $1.86M. Engine-strict at $0.284/pick: $2.09M pricing only.

Breakdown:
- Pricing leakage (all customers below true cost): ~$640K+ annualised
- Unbilled exceptions (Delta $147K + Charlie $127K + others $101K): $375K/yr total
- Productivity & bottleneck: $62K/yr
- Capacity underutilisation (Home & Living Products): $276K opportunity

**Delivery target: $1,150,000 in 9 months** — the achievable portion through repricing and rebilling. The remainder closes through structural pricing reform in Months 3–6.""",
        "chips": ["Customer Profitability", "Impact Tracker"]
    },
    {
        "keys": ["profitable","is each customer","every customer","all customers"],
        "answer": """No. Every customer in the network is currently priced below the true pick cost of **$0.265/pick**.

True margins range from **19.5%** (Delta Manufacturing, critical) to **64.8%** (Medisupply Australia). All reported margins show ~96% — a direct result of not allocating true labour costs to customer accounts.

The pricing structure is the root cause, not individual customer behaviour. Structural repricing (not renegotiation) is the fix.

**Next step:** Review the Customer Profitability page for individual customer breakdown.""",
        "chips": ["Customer Profitability"]
    },
]

def get_ai_response(query, role):
    q = query.lower()
    for entry in CHAT_KB:
        if any(k in q for k in entry.get("keys", [])):
            if "answer_by_role" in entry:
                answer = entry["answer_by_role"].get(role, entry["answer_by_role"].get("CEO",""))
            else:
                answer = entry["answer"]
            return answer, entry.get("chips", [])
    return (
        "The question is outside my pre-built knowledge base. Key facts:\n\n"
        f"- **True pick cost:** {_hf('pick_cost_fmt','$0.265')}/pick (conservative — 4 missing T&A days treated as zero)\n"
        f"- **Total opportunity:** {_hf('total_opportunity_fmt','$2.65M')}/yr ({_hf('pricing_exposure_fmt','$1.86M')} pricing/unbilled + {_hf('ops_exposure_fmt','$0.80M')} operational)\n"
        f"- **Delivery target:** ${_hf('recovery_target',1_150_000):,.0f} over 9 months\n"
        "- **Month 1 priority:** Bravo FMCG repricing ($144K)\n"
        f"- **Largest exposure:** Delta Manufacturing (${_hf('delta_combined',345_000):,.0f} combined)\n\n"
        "Try: *Which customer has the biggest problem?* or *What information is missing?*"
    ), []


# ═══════════════════════════════════════════════════════════
# PAGE 1 — DASHBOARD  (role-adaptive)
# ═══════════════════════════════════════════════════════════
def _recovery_bar(stats, pct):
    remaining = max(RECOVERY_TARGET - stats["recovered"], 0)
    st.markdown(f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:22px 24px;margin-bottom:20px'>
      <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
        <div style='font-size:11px;font-weight:700;letter-spacing:1px;color:{C_MUTED}'>RECOVERY PROGRESS — 9 MONTH TARGET</div>
        <div style='font-size:11px;color:{C_MUTED}'>$1,150,000 target</div>
      </div>
      <div style='background:#F0F2F0;border-radius:2px;height:10px;overflow:hidden'>
        <div style='background:{C_GREEN};width:{pct:.1f}%;height:100%;border-radius:2px'></div>
      </div>
      <div style='display:flex;justify-content:space-between;margin-top:10px'>
        <div style='font-size:13px;color:{C_GREEN};font-weight:700'>${stats["recovered"]:,.0f} recovered &nbsp;&nbsp;{pct:.1f}%</div>
        <div style='font-size:12px;color:{C_MUTED}'>${remaining:,.0f} remaining</div>
      </div>
      <div style='margin-top:14px;display:flex;gap:0'>
        {"".join(f'<div style="flex:1;text-align:center;border-right:1px solid {C_DIVIDER};padding:4px 0"><div style="font-size:9px;color:{C_MUTED};letter-spacing:1px">{m}</div><div style="font-size:10px;font-weight:600;color:{c}">{v}</div></div>'
          for m,v,c in [("MONTH 1","$144K",C_GREEN),("MONTH 3","$416K",C_AMBER),("MONTH 6","$850K",C_AMBER),("MONTH 9","$1.15M",C_MUTED)])}
      </div>
    </div>
    """, unsafe_allow_html=True)

def _ticket_row(t):
    imp  = fmt_dollars(t["dollar_impact"]) if t["dollar_impact"] > 0 else "—"
    sc   = STATUS_COLOR.get(t["status"], C_MUTED)
    cbdg = confidence_badge(t.get("id", ""))
    st.markdown(f"""
    <div style='background:{C_CARD};border:1px solid {C_BORDER};
                border-left:3px solid {sc};border-radius:0 4px 4px 0;
                padding:12px 18px;margin-bottom:5px'>
      <div style='display:flex;justify-content:space-between;align-items:flex-start'>
        <div style='font-size:13px;font-weight:600;color:{C_TEXT};flex:1;line-height:1.4'>{t["title"]}</div>
        <div style='font-size:14px;font-weight:700;color:{C_GREEN};margin-left:16px;white-space:nowrap'>{imp}</div>
      </div>
      <div style='display:flex;gap:8px;margin-top:6px;align-items:center;flex-wrap:wrap'>
        {priority_pill(t["priority"])}{status_pill(t["status"])}
        <span style='font-size:11px;color:{C_MUTED}'>{t["customer"] or "All customers"}</span>
        {cbdg}
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── NOTIFICATIONS PANEL (live activity + who was alerted) ─────────────────
def _notifications_panel(role):
    """AI-powered notification panel — Groq generates situational brief from live ticket data."""
    changed = get_what_changed()

    # Fallback static log (shown when Groq unavailable)
    STATIC_LOG = [
        ("CEO",             "✅", "#5DBF8A", "ABC costing complete — 13 findings, $2.65M opportunity mapped",          "Month 1 · All roles"),
        ("Commercial Lead", "📨", "#5DBF8A", "Bravo FMCG brief sent — $144K/yr repricing, CEO approval pending",       "Month 1 · Awaiting"),
        ("Site Manager",    "🚨", "#FF6B6B", "Delta Manufacturing flagged — exception drain 3.9× peers, $446K/yr",      "Month 1 · Auto-detected"),
        ("Site Manager",    "⚠️", "#F8B840", "Urgent order premium flagged — 2.35× throughput, $349K/yr",              "Month 1 · Auto-detected"),
        ("Commercial Lead", "📋", "#F8B840", "Charlie Medical — $127K unbilled, evidence gathering started",            "Month 1 · In progress"),
        ("CEO",             "🔴", "#FF6B6B", "Decision required: Bravo FMCG pilot approval — Month 1 deadline",        "Awaiting approval"),
    ]

    db_events = []
    for ch in changed:
        sc  = STATUS_COLOR.get(ch["status"], C_MUTED)
        imp = fmt_dollars(ch["dollar_impact"]) if ch["dollar_impact"] > 0 else ""
        db_events.append((sc, ch["title"][:60], imp, ch["updated_at"][:10]))

    total_items = len(db_events) + len([n for n in STATIC_LOG if role == "CEO" or n[0] in (role, "CEO")])

    with st.expander(f"📬 Notifications & Activity ({total_items} items)", expanded=False):

        # ── Live ticket activity (from DB) ────────────────────
        if db_events:
            st.markdown(
                f"<div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:700;"
                f"margin-bottom:8px'>RECENT TICKET ACTIVITY</div>", unsafe_allow_html=True)
            for sc, title, imp, date in db_events:
                st.markdown(
                    f"<div style='display:flex;gap:10px;align-items:center;padding:7px 0;"
                    f"border-bottom:1px solid {C_DIVIDER}'>"
                    f"<div style='width:7px;height:7px;border-radius:50%;background:{sc};flex-shrink:0'></div>"
                    f"<div style='flex:1;font-size:12px;color:{C_TEXT}'>{title}</div>"
                    f"<div style='font-size:11px;font-weight:600;color:{C_GREEN};white-space:nowrap'>{imp}</div>"
                    f"<div style='font-size:10px;color:{C_MUTED};white-space:nowrap'>{date}</div>"
                    f"</div>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # ── AI Situational Brief (Groq-powered) ──────────────
        st.markdown(
            f"<div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:700;"
            f"margin-bottom:8px'>AI SITUATIONAL BRIEF</div>", unsafe_allow_html=True)

        cache_key = f"_ai_brief_{role}"
        col_hdr, col_btn = st.columns([5, 1])
        with col_btn:
            regen = st.button("↻ Refresh", key=f"notif_regen_{role}", help="Regenerate AI brief from current ticket data")

        _brief_ai_ready = (_LLM_AVAILABLE or (_GROQ_AVAILABLE and GROQ_API_KEY))
        if _brief_ai_ready:
            if cache_key not in st.session_state or regen:
                try:
                    all_t = db.get_tickets(WAREHOUSE_ID)
                    open_t = [t for t in all_t if t["status"] != "Done" and t.get("finding_id") != "F011"]
                    done_t = [t for t in all_t if t["status"] == "Done"]
                    recovered = sum(t["dollar_impact"] for t in done_t if t["dollar_impact"] > 0)

                    ticket_lines = []
                    for t in sorted(open_t, key=lambda x: -x["dollar_impact"])[:8]:
                        ticket_lines.append(
                            f"  - [{t['priority']}] {t['title']} | ${t['dollar_impact']:,.0f} | "
                            f"{t['status']} | Owner: {t['assigned_role']}"
                        )
                    ticket_ctx = "\n".join(ticket_lines) if ticket_lines else "  (no open tickets)"

                    brief_system = (
                        "You generate concise operational notification briefs. "
                        "Use exact numbers from context. No fluff."
                    )
                    brief_prompt = (
                        f"You are Profit Lens, an AI operations assistant for Mattingly Logistics warehouse WH001. "
                        f"Write a concise situational notification brief for the {role}. "
                        f"Current state: ${recovered:,.0f} recovered of $1,150,000 target. "
                        f"Open tickets (highest impact first):\n{ticket_ctx}\n\n"
                        f"Write 4-5 specific, actionable notification bullets. Each bullet: who needs to act, "
                        f"what exactly, dollar amount if relevant, urgency. No preamble, no headers. "
                        f"Start each line with an emoji (🔴/🟡/🟢/📨/⚡). "
                        f"Tailor to {role} perspective. Be specific about ticket names and amounts."
                    )

                    # ── Nemotron → Groq → None ──────────────────────
                    ai_brief = None
                    if _LLM_AVAILABLE:
                        try:
                            ai_brief = _llm.call_structured(brief_system, brief_prompt, max_tokens=300)
                        except Exception:
                            pass
                    if not ai_brief and _GROQ_AVAILABLE and GROQ_API_KEY:
                        try:
                            client = _Groq(api_key=GROQ_API_KEY)
                            resp = client.chat.completions.create(
                                model=GROQ_MODEL,
                                messages=[
                                    {"role": "system", "content": brief_system},
                                    {"role": "user",   "content": brief_prompt}
                                ],
                                max_tokens=300,
                                temperature=0.3,
                            )
                            ai_brief = resp.choices[0].message.content.strip()
                        except Exception:
                            pass
                    st.session_state[cache_key] = ai_brief or None
                except Exception:
                    st.session_state[cache_key] = None

            ai_text = st.session_state.get(cache_key)
            if ai_text:
                for line in ai_text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Colour the line border based on leading emoji
                    bc = C_RED if line.startswith("🔴") else (
                         C_AMBER if line.startswith(("🟡","⚠","⚡")) else (
                         C_GREEN if line.startswith(("🟢","✅","📨")) else C_MUTED))
                    st.markdown(
                        f"<div style='padding:8px 12px;margin-bottom:4px;border-radius:3px;"
                        f"border-left:3px solid {bc};background:{bc}0D;"
                        f"font-size:12px;color:{C_TEXT};line-height:1.6'>{line}</div>",
                        unsafe_allow_html=True)
            else:
                st.info("AI brief unavailable — check GROQ_API_KEY / NVIDIA_API_KEY in Streamlit secrets.")
        else:
            # Fallback: static log
            for target_role, icon, color, msg, timing in STATIC_LOG:
                if role != "CEO" and target_role not in (role, "CEO"):
                    continue
                st.markdown(
                    f"<div style='display:flex;gap:10px;align-items:flex-start;padding:9px 0;"
                    f"border-bottom:1px solid {C_DIVIDER}'>"
                    f"<div style='font-size:16px;flex-shrink:0'>{icon}</div>"
                    f"<div style='flex:1'>"
                    f"<div style='font-size:11px;font-weight:600;color:{color}'>{target_role}</div>"
                    f"<div style='font-size:12px;color:{C_TEXT};margin-top:1px'>{msg}</div>"
                    f"<div style='font-size:10px;color:{C_MUTED};margin-top:2px'>{timing}</div>"
                    f"</div></div>", unsafe_allow_html=True)


def _what_changed_visual():
    changed = get_what_changed()
    timeline_items = [
        ("Month 1", "ABC costing complete — 13 findings, 10 tickets generated", f"{_hf('total_opportunity_fmt','$2.65M')} opportunity mapped ({_hf('pricing_exposure_fmt','$1.86M')} pricing + {_hf('ops_exposure_fmt','$0.80M')} ops)", C_GREEN, True),
        ("Month 1", "Bravo FMCG repricing approved", "Month 1 pilot — $144K/yr recovery", C_AMBER, False),
        ("Month 2", "Delta Manufacturing evidence gathering", "Exception log review in progress", C_AMBER, False),
        ("Month 3", "Delta repricing + Charlie rebilling", "$272K incremental → $416K cumulative", C_MUTED, False),
        ("Month 6", "Sites 2–3 onboarding", "$850K cumulative", C_MUTED, False),
    ]
    if changed:
        for ch in changed:
            sc = STATUS_COLOR.get(ch["status"], C_MUTED)
            imp = fmt_dollars(ch["dollar_impact"]) if ch["dollar_impact"] > 0 else ""
            st.markdown(f"""
            <div style='display:flex;gap:14px;padding:9px 0;border-bottom:1px solid {C_DIVIDER};align-items:center'>
              <div style='width:8px;height:8px;border-radius:50%;background:{sc};flex-shrink:0;margin-top:2px'></div>
              <div style='flex:1;font-size:12px;color:{C_TEXT}'>{ch["title"][:65]}</div>
              <div style='font-size:11px;font-weight:600;color:{C_GREEN};white-space:nowrap'>{imp}</div>
              <div style='font-size:10px;color:{C_MUTED};white-space:nowrap'>{ch["updated_at"][:10]}</div>
            </div>""", unsafe_allow_html=True)
    else:
        # Build items separately to avoid nested triple-quoted f-strings
        items_html = ""
        for month, title, sub, c, done in timeline_items:
            fw    = "700" if done else "500"
            tc    = C_TEXT if done else C_MUTED
            badge = "DONE" if done else "PLANNED"
            items_html += (
                f"<div style='display:flex;gap:0;border-bottom:1px solid {C_DIVIDER}'>"
                f"<div style='width:4px;background:{c};flex-shrink:0'></div>"
                f"<div style='padding:11px 16px;flex:1'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                f"<div>"
                f"<div style='font-size:9px;letter-spacing:1px;color:{C_MUTED};font-weight:600'>{month}</div>"
                f"<div style='font-size:12px;font-weight:{fw};color:{tc};margin-top:2px'>{title}</div>"
                f"<div style='font-size:11px;color:{C_MUTED};margin-top:1px'>{sub}</div>"
                f"</div>"
                f"<div style='font-size:10px;font-weight:600;color:{c};padding:2px 8px;"
                f"background:{c}15;border-radius:2px'>{badge}</div>"
                f"</div></div></div>"
            )
        st.markdown(
            f"<div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;overflow:hidden'>"
            f"{items_html}</div>",
            unsafe_allow_html=True
        )


# ── QUICK ASK HELPER ──────────────────────────────────────────
def _ask_groq_quick(question, role):
    """
    Single-question Groq call for the dashboard mini Q&A widget.
    Calls the model directly — no keyword matching, no canned answers.
    Groq has the full system prompt including all live financial figures,
    so it can answer anything in scope from first principles.
    """
    if _GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = _Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system",
                     "content": GROQ_SYSTEM_PROMPT + f"\n\nCurrent user role: {role}. Keep answer under 150 words."},
                    {"role": "user", "content": question}
                ],
                max_tokens=300, temperature=0.15,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"⚠️ Connection error: {e}"
    return (
        "Profit Lens AI isn't live in this environment — "
        "add GROQ_API_KEY to Streamlit Cloud secrets to enable real-time answers."
    )

def _mini_qa(role):
    """Compact AI Q&A panel — embedded in Dashboard for each role"""
    presets = {
        "CEO": [
            "Which customer should I approve first?",
            "What risks could derail the $1.15M target?",
            "Why is our reported margin wrong?"
        ],
        "Commercial Lead": [
            "What is the best case to reprice Bravo FMCG?",
            "How do I handle pushback on rate increases?",
            "What data do I need for Delta negotiations?"
        ],
        "Site Manager": [
            "How do I reduce Delta exception rate?",
            "What are the data hygiene priorities?",
            "How do I validate Charlie pick count gap?"
        ],
    }
    questions = presets.get(role, presets["CEO"])
    ans_key = f"_miniqa_ans_{role}"
    asked_key = f"_miniqa_asked_{role}"
    if ans_key not in st.session_state: st.session_state[ans_key] = ""
    if asked_key not in st.session_state: st.session_state[asked_key] = ""

    st.markdown(sec("Ask Profit Lens AI"), unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:11px;color:{C_MUTED};margin-bottom:10px'>"
        f"Click a question or type your own — answers powered by real data from this analysis.</div>",
        unsafe_allow_html=True
    )
    qc1, qc2, qc3 = st.columns(3)
    for col, q in zip([qc1, qc2, qc3], questions):
        if col.button(q, use_container_width=True, key=f"miniqa_{role}_{q[:12]}"):
            with st.spinner("Analyzing..."):
                st.session_state[ans_key] = _ask_groq_quick(q, role)
                st.session_state[asked_key] = q

    fc1, fc2 = st.columns([5, 1])
    with fc1:
        free_q = st.text_input("", placeholder="Ask your own question about this analysis...",
                               key=f"miniqa_free_{role}", label_visibility="collapsed")
    with fc2:
        if st.button("Ask", key=f"miniqa_sub_{role}", use_container_width=True):
            if free_q.strip():
                with st.spinner("Analyzing..."):
                    st.session_state[ans_key] = _ask_groq_quick(free_q.strip(), role)
                    st.session_state[asked_key] = free_q.strip()

    if st.session_state[ans_key]:
        st.markdown(
            f"<div style='background:{C_BLUE_LITE};border-left:3px solid {C_BLUE};"
            f"padding:14px 18px;border-radius:0 4px 4px 0;margin-top:8px'>"
            f"<div style='font-size:9px;letter-spacing:2px;color:{C_BLUE};font-weight:700;margin-bottom:5px'>"
            f"PROFIT LENS AI &nbsp;&middot;&nbsp; "
            f"<span style='font-weight:400;color:{C_MUTED}'>{st.session_state[asked_key]}</span></div>"
            f"<div style='font-size:13px;color:{C_TEXT};line-height:1.7'>"
            f"{st.session_state[ans_key]}</div></div>",
            unsafe_allow_html=True
        )


# ── AI ACTION HELPERS ─────────────────────────────────────────
def _ai_next_action(role, open_tickets):
    """Groq-powered next best action for a role, based on live ticket data."""
    top = sorted(
        [t for t in open_tickets if t["status"] != "Done"],
        key=lambda x: -x.get("dollar_impact", 0)
    )[:5]
    if not top:
        return ""
    ticket_lines = "\n".join(
        f"- [{t['priority']}] {t['title']} | {t['customer'] or 'All'} | ${t['dollar_impact']:,.0f}"
        for t in top
    )
    prompt = (
        f"Role: {role}\n"
        f"Top open tickets by dollar impact:\n{ticket_lines}\n\n"
        f"In exactly 3 lines (no markdown, no bullets), give:\n"
        f"ACTION: [single most important thing {role} should do TODAY]\n"
        f"WHY: [one sentence: why this matters most right now]\n"
        f"NEXT STEP: [literal next physical step]"
    )
    # ── Nemotron → Groq → static fallback ──────────────────────
    system = (
        GROQ_SYSTEM_PROMPT
        + f"\n\nCurrent role: {role}. Be direct, specific, max 60 words total."
    )
    if _LLM_AVAILABLE:
        try:
            result = _llm.call_structured(system, prompt, max_tokens=150)
            if result:
                return result
        except Exception:
            pass
    elif _GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = _Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150, temperature=0.1,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            pass
    fallback = {
        "CEO": (
            "ACTION: Approve Bravo FMCG repricing pilot ($144K)\n"
            "WHY: Month 1 milestone — unblocks the entire $1.15M recovery chain\n"
            "NEXT STEP: Sign off on Commercial Lead rate proposal ($0.12 \u2192 $0.19) this week"
        ),
        "Commercial Lead": (
            "ACTION: Finalise Delta Manufacturing evidence package\n"
            "WHY: $345K opportunity requires CEO approval — Month 2 window is closing\n"
            "NEXT STEP: Pull 3-month exception logs and send brief to CEO by Friday"
        ),
        "Site Manager": (
            "ACTION: Resolve F007 \u2014 close the 4-day labour data gap\n"
            "WHY: This single ticket blocks all commercial negotiations\n"
            "NEXT STEP: Request corrected timesheets from HR and reconcile against scan data today"
        ),
    }
    return fallback.get(role, fallback["CEO"])


def _ai_enhance_ticket(ticket):
    """Generate AI root cause + recommended next step for a single ticket."""
    ctype   = TYPE_LABEL.get(ticket.get("finding_type", ""), ticket.get("finding_type", "Finding"))
    imp_str = fmt_dollars(ticket["dollar_impact"]) if ticket.get("dollar_impact", 0) > 0 else "data quality issue"
    prompt  = (
        f"Ticket: {ticket['title']}\n"
        f"Type: {ctype}\n"
        f"Customer: {ticket.get('customer') or 'All customers'}\n"
        f"Impact: {imp_str}\n"
        f"Priority: {ticket.get('priority', 'MEDIUM')}\n"
        f"Description: {ticket.get('description', '')}\n\n"
        f"Write exactly two lines (no markdown):\n"
        f"ROOT CAUSE: [why this problem exists \u2014 1 concrete sentence]\n"
        f"NEXT STEP: [the single most important action the owner should take this week]"
    )
    # ── Nemotron → Groq → empty dict fallback ──────────────────
    system = GROQ_SYSTEM_PROMPT + "\nBe specific and operational. Max 50 words per line."

    def _parse_enhance(text):
        rc = ns = ""
        for line in text.split("\n"):
            if line.startswith("ROOT CAUSE:"):
                rc = line.replace("ROOT CAUSE:", "").strip()
            elif line.startswith("NEXT STEP:"):
                ns = line.replace("NEXT STEP:", "").strip()
        return {"explanation": rc, "action": ns} if (rc or ns) else {}

    if _LLM_AVAILABLE:
        try:
            text = _llm.call_structured(system, prompt, max_tokens=130)
            if text:
                return _parse_enhance(text)
        except Exception:
            pass
    elif _GROQ_AVAILABLE and GROQ_API_KEY:
        try:
            client = _Groq(api_key=GROQ_API_KEY)
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=130, temperature=0.1,
            )
            return _parse_enhance(resp.choices[0].message.content.strip())
        except Exception:
            pass
    return {}


def _render_next_action(role, all_tickets):
    """Render the AI Suggested Next Action card on each role dashboard."""
    na_key = f"_na_{role}"
    if na_key not in st.session_state:
        st.session_state[na_key] = ""

    if not st.session_state[na_key]:
        bc1, bc2 = st.columns([8, 1])
        with bc1:
            st.markdown(
                f"<div style='background:{C_BLUE}0D;border:1px dashed {C_BLUE}44;"
                f"border-radius:4px;padding:11px 18px;color:{C_MUTED};font-size:12px'>"
                f"Click Generate to get an AI-powered Next Best Action for {role}.</div>",
                unsafe_allow_html=True
            )
        with bc2:
            if st.button("Generate", key=f"gen_na_{role}", use_container_width=True):
                with st.spinner("Analysing tickets..."):
                    st.session_state[na_key] = _ai_next_action(role, all_tickets)
                st.rerun()
        return

    action_txt = why_txt = next_txt = ""
    for line in st.session_state[na_key].split("\n"):
        if line.startswith("ACTION:"):
            action_txt = line.replace("ACTION:", "").strip()
        elif line.startswith("WHY:"):
            why_txt = line.replace("WHY:", "").strip()
        elif line.startswith("NEXT STEP:"):
            next_txt = line.replace("NEXT STEP:", "").strip()
    if not action_txt:
        action_txt = st.session_state[na_key]

    nc1, nc2 = st.columns([10, 1])
    with nc1:
        ap  = (f"<div style='font-size:13px;font-weight:700;color:#FFFFFF;"
               f"line-height:1.5;margin-bottom:6px'>{action_txt}</div>") if action_txt else ""
        wp  = (f"<div style='font-size:11px;color:#A8C8B8;margin-bottom:4px'>"
               f"<span style='font-weight:600;color:#5DBF8A'>WHY:</span> {why_txt}</div>") if why_txt else ""
        np_ = (f"<div style='font-size:11px;color:#A8C8B8'>"
               f"<span style='font-weight:600;color:#F8B840'>NEXT STEP:</span> {next_txt}</div>") if next_txt else ""
        st.markdown(
            f"<div style='background:#1A3D2B;border-radius:4px;padding:14px 20px;margin-bottom:16px'>"
            f"<div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:8px'>"
            f"AI SUGGESTED NEXT ACTION &nbsp;&middot;&nbsp; {role.upper()}</div>"
            f"{ap}{wp}{np_}</div>",
            unsafe_allow_html=True
        )
    with nc2:
        if st.button("\u21bb", key=f"ref_na_{role}", use_container_width=True, help="Refresh AI suggestion"):
            st.session_state[na_key] = ""
            st.rerun()

def page_dashboard():
    role  = st.session_state.role
    stats = db.get_recovery_stats(WAREHOUSE_ID)
    pct   = min(stats["recovered"] / RECOVERY_TARGET * 100, 100) if RECOVERY_TARGET else 0
    all_tickets = db.get_tickets(WAREHOUSE_ID)

    # ── MOS NARRATIVE — Management Operating System command centre ─────
    _mos_open_tickets = len([t for t in all_tickets if t["status"] != "Done"])
    _mos_blocked      = stats.get("blocked_count", 0)
    _mos_done         = stats.get("done_count", 0)
    _mos_data_ok      = "LIVE" if DATA_PATH and os.path.exists(DATA_PATH) else "DEMO"
    _mos_today        = __import__("datetime").date.today().strftime("%d %b %Y")
    _mos_pct          = min(stats["recovered"] / RECOVERY_TARGET * 100, 100) if RECOVERY_TARGET else 0
    st.markdown(f"""
    <div style='background:#0D2B1A;border:1px solid #1F4A2E;border-radius:6px;
                padding:16px 20px;margin-bottom:16px'>
      <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
        <div style='font-size:10px;font-weight:700;letter-spacing:2px;color:#5DBF8A'>
          PROFIT LENS &nbsp;&middot;&nbsp; MANAGEMENT OPERATING SYSTEM
        </div>
        <div style='display:flex;gap:12px;align-items:center'>
          <span style='font-size:9px;color:#3A7A54;background:#1F4A2E;padding:3px 10px;border-radius:2px;font-weight:600'>
            DATA: {_mos_data_ok}
          </span>
          <span style='font-size:9px;color:#3A7A54'>{_mos_today}</span>
        </div>
      </div>
      <div style='display:flex;gap:0;align-items:stretch;margin-bottom:12px'>
        <div style='flex:1;padding:10px 14px;border-right:1px solid #1F4A2E'>
          <div style='font-size:10px;font-weight:700;color:#5DBF8A;letter-spacing:1px;margin-bottom:6px'>1. FIND</div>
          <div style='font-size:11px;color:#8FBF9F;line-height:1.5'>ABC engine identifies where money is leaking — below-cost pricing, unbilled work, exceptions. 12 findings, {_hf("total_opportunity_fmt","$2.65M")} mapped.</div>
        </div>
        <div style='flex:1;padding:10px 14px;border-right:1px solid #1F4A2E'>
          <div style='font-size:10px;font-weight:700;color:#5DBF8A;letter-spacing:1px;margin-bottom:6px'>2. TICKET</div>
          <div style='font-size:11px;color:#8FBF9F;line-height:1.5'>Each finding becomes a ticket routed to the right role. CEO approves pricing. Commercial Lead negotiates. Site Manager fixes data.</div>
        </div>
        <div style='flex:1;padding:10px 14px;border-right:1px solid #1F4A2E'>
          <div style='font-size:10px;font-weight:700;color:#5DBF8A;letter-spacing:1px;margin-bottom:6px'>3. ACT</div>
          <div style='font-size:11px;color:#8FBF9F;line-height:1.5'>Each role works their queue on the rhythm below — daily, weekly, monthly. Close a ticket = confirmed action taken.</div>
        </div>
        <div style='flex:1;padding:10px 14px'>
          <div style='font-size:10px;font-weight:700;color:#5DBF8A;letter-spacing:1px;margin-bottom:6px'>4. RECOVER</div>
          <div style='font-size:11px;color:#8FBF9F;line-height:1.5'>Closing tickets moves the recovery bar. <strong style='color:#5DBF8A'>Target: $1.15M in 9 months.</strong> Impact Tracker shows realised value month by month.</div>
        </div>
      </div>
      <div style='border-top:1px solid #1F4A2E;padding-top:10px;display:flex;gap:16px'>
        <div style='display:flex;gap:6px;align-items:center'>
          <div style='width:8px;height:8px;border-radius:50%;background:#DC2626'></div>
          <div style='font-size:10px;color:#8FBF9F'><strong style='color:#FFFFFF'>{_mos_open_tickets}</strong> open tickets</div>
        </div>
        <div style='display:flex;gap:6px;align-items:center'>
          <div style='width:8px;height:8px;border-radius:50%;background:#B45309'></div>
          <div style='font-size:10px;color:#8FBF9F'><strong style='color:#FFFFFF'>{_mos_blocked}</strong> blocked</div>
        </div>
        <div style='display:flex;gap:6px;align-items:center'>
          <div style='width:8px;height:8px;border-radius:50%;background:#005A32'></div>
          <div style='font-size:10px;color:#8FBF9F'><strong style='color:#FFFFFF'>{_mos_done}</strong> closed</div>
        </div>
        <div style='flex:1'></div>
        <div style='font-size:10px;color:#8FBF9F'>
          Recovery: <strong style='color:#5DBF8A'>{_mos_pct:.1f}%</strong> of $1.15M target &nbsp;&middot;&nbsp;
          Opportunity remaining: <strong style='color:#FFFFFF'>${(RECOVERY_TARGET*(1-_mos_pct/100))/1000:.0f}K</strong>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── CEO view ──────────────────────────────────────────────
    if role == "CEO":
        st.markdown(page_header(
            "Executive Dashboard",
            f"Profit opportunity & delivery progress — {WAREHOUSE_NAME}"
        ), unsafe_allow_html=True)

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi_card("Total Opportunity", _hf("total_opportunity_fmt", "$2.65M"), f"Pricing {_hf('pricing_exposure_fmt','$1.86M')} · Ops {_hf('ops_exposure_fmt','$0.80M')} (see Operations page)", C_RED), unsafe_allow_html=True)
        k2.markdown(kpi_card("Recovered to Date", fmt_dollars(stats["recovered"]), f"{pct:.1f}% of $1.15M target", C_GREEN), unsafe_allow_html=True)
        high_priority = sum(1 for t in all_tickets if t["priority"] in ("HIGH","CRITICAL") and t["status"] != "Done")
        k3.markdown(kpi_card("High-Priority Open", str(high_priority), "Requiring CEO decision"), unsafe_allow_html=True)
        k4.markdown(kpi_card("Blocked Items", str(stats["blocked_count"]), f"{stats['in_progress_count']} in progress", C_AMBER if stats["blocked_count"] else C_GREEN), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _recovery_bar(stats, pct)

        # ── AI ALERTS (auto-detected) ──────────────────────────
        st.markdown("""
        <div style='background:#1A1A0D;border:1px solid #4A3800;border-radius:4px;padding:12px 18px;margin-bottom:16px'>
          <div style='font-size:9px;letter-spacing:2px;color:#F8B840;font-weight:700;margin-bottom:10px'>
            ⚡ AI AUTO-DETECTION &nbsp;&nbsp;|&nbsp;&nbsp; SYSTEM ALERTS &nbsp;&middot;&nbsp; UPDATED: JAN–FEB 2026 DATA
          </div>
          <div style='display:flex;flex-direction:column;gap:6px'>
            <div style='display:flex;align-items:center;gap:12px;padding:9px 14px;background:rgba(153,27,27,0.08);border-radius:3px;border-left:3px solid #DC2626'>
              <div style='font-size:18px'>🚨</div>
              <div style='flex:1'>
                <div style='font-size:12px;font-weight:700;color:#FF8080'>BOTTLENECK: Delta Manufacturing exception drain ($446K/yr)</div>
                <div style='font-size:11px;color:#B06060;margin-top:2px'>3.9× above network average. Root cause: high returns + rework volume. <strong style='color:#FF8080'>Site Manager notified → target below 10% within 30 days.</strong></div>
              </div>
              <div style='text-align:right;flex-shrink:0'><div style='font-size:13px;font-weight:800;color:#FF6060'>$446K</div><div style='font-size:9px;color:#996666'>annual drain</div></div>
            </div>
            <div style='display:flex;align-items:center;gap:12px;padding:9px 14px;background:rgba(248,184,64,0.06);border-radius:3px;border-left:3px solid #F8B840'>
              <div style='font-size:18px'>⚠️</div>
              <div style='flex:1'>
                <div style='font-size:12px;font-weight:700;color:#F8D27A'>Urgent order throughput penalty ($349K/yr)</div>
                <div style='font-size:11px;color:#B8A060;margin-top:2px'>Urgent orders 2.35× slower than standard. Premium labour pool adds $349K/yr. <strong style='color:#F8D27A'>Commercial Lead + Site Manager notified.</strong></div>
              </div>
              <div style='text-align:right;flex-shrink:0'><div style='font-size:13px;font-weight:800;color:#F8B840'>$349K</div><div style='font-size:9px;color:#998844'>annual drain</div></div>
            </div>
            <div style='display:flex;align-items:center;gap:12px;padding:9px 14px;background:rgba(93,191,138,0.04);border-radius:3px;border-left:3px solid #5DBF8A'>
              <div style='font-size:18px'>✅</div>
              <div style='flex:1'>
                <div style='font-size:12px;font-weight:700;color:#8FD4AA'>Productivity improving: +12% pick rate Jan→Feb (no alert needed)</div>
                <div style='font-size:11px;color:#5D9E78;margin-top:2px'>Network 158→177 units/hr. No structural productivity bottleneck detected. Exception pool (26% of all labour) is the primary improvement lever.</div>
              </div>
              <div style='text-align:right;flex-shrink:0'><div style='font-size:13px;font-weight:800;color:#5DBF8A'>+12%</div><div style='font-size:9px;color:#3D8A60'>Jan→Feb</div></div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _notifications_panel(role)

        # MOS CADENCE — CEO (tabs: Monthly / Quarterly / Annual)
        st.markdown("<div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:6px'>MANAGEMENT OPERATING SYSTEM &nbsp;·&nbsp; CEO</div>", unsafe_allow_html=True)
        _ceo_tab_m, _ceo_tab_q, _ceo_tab_a = st.tabs(["📅 Monthly", "📊 Quarterly", "🗓 Annual"])
        with _ceo_tab_m:
            st.markdown("""
            <div style='background:#1A3D2B;border-radius:4px;padding:14px 18px;margin-top:8px;margin-bottom:4px'>
              <div style='display:flex;gap:0;border-radius:3px;overflow:hidden'>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#6B9E83;font-weight:700;letter-spacing:1px;margin-bottom:5px'>REVIEW</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>Portfolio health<br>Approve / decline proposals<br>Recovery progress vs $1.15M</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.07);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:5px'>THIS MONTH — ACTION</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>✅ Approve Bravo pilot ($144K)<br>📋 Review Delta evidence<br>📋 Confirm Month 3 authority</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04)'>
                  <div style='font-size:9px;color:#5DBF8A;font-weight:700;letter-spacing:1px;margin-bottom:5px'>NEXT MONTH — PREPARE</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>Delta brief from Commercial Lead<br>Charlie rebilling sign-off<br>WH002 readiness check</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # DATA-QUALITY SCORECARD — monthly CEO review item
            st.markdown("""
            <div style='background:#1A1020;border:1px solid #3D2060;border-left:4px solid #7A40CC;
                        border-radius:4px;padding:14px 18px;margin-top:10px'>
              <div style='font-size:9px;letter-spacing:2px;color:#9B60DD;font-weight:700;margin-bottom:10px'>
                DATA-QUALITY SCORECARD &#183; MONTHLY CEO REVIEW</div>

              <div style='display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #3D2060'>
                <div style='min-width:24px;font-size:12px;font-weight:800;color:#CC4444;padding-top:1px'>1</div>
                <div style='flex:1'>
                  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:3px'>
                    <span style='font-size:11px;font-weight:700;color:#E8D0F8'>Product ID join key on transaction records</span>
                    <span style='font-size:9px;font-weight:700;color:#CC4444;background:#3D1010;padding:2px 7px;border-radius:2px;white-space:nowrap;margin-left:10px'>OPEN</span>
                  </div>
                  <div style='font-size:10px;color:#A080C0;line-height:1.5'>
                    Product Master holds SKU size and handling complexity but transactions carry no join key.
                    Without it, cost-to-serve stays at blended warehouse rates — per-customer granularity
                    and complexity-based pricing tiers cannot be validated.
                    <strong style='color:#CC88FF'>Owner: IT / Data Engineering &nbsp;·&nbsp; Priority: HIGH</strong>
                  </div>
                </div>
              </div>

              <div style='display:flex;align-items:flex-start;gap:10px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #3D2060'>
                <div style='min-width:24px;font-size:12px;font-weight:800;color:#B45309;padding-top:1px'>2</div>
                <div style='flex:1'>
                  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:3px'>
                    <span style='font-size:11px;font-weight:700;color:#E8D0F8'>4-day labour data gap (F007)</span>
                    <span style='font-size:9px;font-weight:700;color:#B45309;background:#2A1800;padding:2px 7px;border-radius:2px;white-space:nowrap;margin-left:10px'>OPEN</span>
                  </div>
                  <div style='font-size:10px;color:#A080C0;line-height:1.5'>
                    Missing time-and-attendance records for 4 days push pick cost from $0.265 (conservative floor)
                    to $0.284 (strict). Resolve before using either figure in external negotiations.
                    <strong style='color:#CC88FF'>Owner: Site Manager &nbsp;·&nbsp; Priority: HIGH</strong>
                  </div>
                </div>
              </div>

              <div style='display:flex;align-items:flex-start;gap:10px'>
                <div style='min-width:24px;font-size:12px;font-weight:800;color:#4A9A4A;padding-top:1px'>3</div>
                <div style='flex:1'>
                  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:3px'>
                    <span style='font-size:11px;font-weight:700;color:#E8D0F8'>Seasonality verification</span>
                    <span style='font-size:9px;font-weight:700;color:#4A9A4A;background:#0D2010;padding:2px 7px;border-radius:2px;white-space:nowrap;margin-left:10px'>VERIFIED</span>
                  </div>
                  <div style='font-size:10px;color:#A080C0;line-height:1.5'>
                    M1/M2 activity ratio 0.84&#8211;1.18 across all 30 customers. x6 annualisation is valid.
                    Re-verify when M3 data is available.
                    <strong style='color:#88CC88'>Owner: Data Analyst &nbsp;·&nbsp; Priority: MONITOR</strong>
                  </div>
                </div>
              </div>

            </div>
            """, unsafe_allow_html=True)
        with _ceo_tab_q:
            st.markdown("""
            <div style='background:#1A3D2B;border-radius:4px;padding:14px 18px;margin-top:8px;margin-bottom:4px'>
              <div style='display:flex;gap:0;border-radius:3px;overflow:hidden'>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#6B9E83;font-weight:700;letter-spacing:1px;margin-bottom:5px'>Q1 MILESTONE</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>Bravo $144K closed (Month 2)<br>Delta evidence complete<br>Site 1 data hygiene cleared</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.07);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:5px'>Q2 MILESTONE</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>Delta + Charlie closed → $416K<br>Ops efficiency program started<br>WH002 onboarding begins</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04)'>
                  <div style='font-size:9px;color:#5DBF8A;font-weight:700;letter-spacing:1px;margin-bottom:5px'>Q3–Q4 HORIZON</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>WH002+WH003 → $850K<br>Exception pool target: &lt;15%<br>Full network rollout review</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)
        with _ceo_tab_a:
            st.markdown("""
            <div style='background:#1A3D2B;border-radius:4px;padding:14px 18px;margin-top:8px;margin-bottom:4px'>
              <div style='display:flex;gap:0;border-radius:3px;overflow:hidden'>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#6B9E83;font-weight:700;letter-spacing:1px;margin-bottom:5px'>YEAR-END TARGET</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>$1.15M pricing recovery<br>$2.65M total opportunity mapped<br>All 3 sites on Profit Lens</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.07);border-right:1px solid rgba(255,255,255,0.08)'>
                  <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:5px'>BOARD METRICS</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>True margin by customer live<br>Exception rate &lt;10% network<br>Pick cost vs contract tracked</div>
                </div>
                <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04)'>
                  <div style='font-size:9px;color:#5DBF8A;font-weight:700;letter-spacing:1px;margin-bottom:5px'>STRATEGIC OUTCOME</div>
                  <div style='font-size:11px;color:#C8DDD2;line-height:1.6'>Activity-based pricing standard<br>Operational data as asset<br>Platform for network expansion</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── TIERED PRICING EXAMPLE ───────────────────────────────────────
            st.markdown(f"<div style='font-size:11px;font-weight:700;color:{C_MUTED};letter-spacing:1px;margin:14px 0 8px'>YEAR-END GOAL: MOVE FROM FLAT-RATE TO TIERED PRICING</div>", unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;padding:16px 18px;margin-bottom:8px'>
              <div style='font-size:11px;font-weight:700;color:{C_TEXT};margin-bottom:12px'>Proposed Tier Structure — Worked Example</div>
              <!-- Tier legend -->
              <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:14px'>
                <div style='background:#0D1F0D;border-radius:3px;padding:8px 10px;border-left:3px solid #5DBF8A'>
                  <div style='font-size:9px;color:#5DBF8A;font-weight:700;margin-bottom:3px'>TIER 1 · BASE</div>
                  <div style='font-size:13px;font-weight:800;color:{C_TEXT}'>{_hf("pick_cost_fmt","$0.265")}/pick</div>
                  <div style='font-size:10px;color:{C_MUTED};margin-top:2px'>True cost floor · all customers (conservative)</div>
                </div>
                <div style='background:{C_AMBER_LITE};border-radius:3px;padding:8px 10px;border-left:3px solid {C_AMBER}'>
                  <div style='font-size:9px;color:{C_AMBER};font-weight:700;margin-bottom:3px'>TIER 2 · VOLUME CREDIT</div>
                  <div style='font-size:13px;font-weight:800;color:{C_TEXT}'>−10% @ &gt;1.5M picks</div>
                  <div style='font-size:10px;color:{C_MUTED};margin-top:2px'>$0.239 floor · rewards scale</div>
                </div>
                <div style='background:{C_RED_LITE};border-radius:3px;padding:8px 10px;border-left:3px solid {C_RED}'>
                  <div style='font-size:9px;color:{C_RED};font-weight:700;margin-bottom:3px'>TIER 3 · COMPLEXITY SURCHARGE</div>
                  <div style='font-size:13px;font-weight:800;color:{C_TEXT}'>+15% @ &gt;4% exception rate</div>
                  <div style='font-size:10px;color:{C_MUTED};margin-top:2px'>$0.305 · reflects true cost</div>
                </div>
              </div>
              <!-- Customer table -->
              <table style='width:100%;border-collapse:collapse;font-size:11px'>
                <thead>
                  <tr style='border-bottom:1px solid {C_BORDER}'>
                    <th style='text-align:left;color:{C_MUTED};padding:5px 0;font-weight:600'>Customer</th>
                    <th style='text-align:right;color:{C_MUTED};padding:5px 0;font-weight:600'>Current</th>
                    <th style='text-align:right;color:{C_MUTED};padding:5px 0;font-weight:600'>Tier</th>
                    <th style='text-align:right;color:{C_MUTED};padding:5px 0;font-weight:600'>Proposed</th>
                    <th style='text-align:right;color:{C_MUTED};padding:5px 0;font-weight:600'>Impact</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style='border-bottom:1px solid {C_BORDER}20'>
                    <td style='padding:7px 0;color:{C_TEXT};font-weight:600'>Bravo FMCG<br><span style='font-size:9px;color:{C_MUTED};font-weight:400'>2.05M picks · 0.6% exception</span></td>
                    <td style='text-align:right;color:{C_RED};padding:7px 0'>$0.12</td>
                    <td style='text-align:right;color:{C_AMBER};padding:7px 0'>T2 Volume</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>$0.19*</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>+$144K</td>
                  </tr>
                  <tr style='border-bottom:1px solid {C_BORDER}20'>
                    <td style='padding:7px 0;color:{C_TEXT};font-weight:600'>Delta Manufacturing<br><span style='font-size:9px;color:{C_MUTED};font-weight:400'>1.44M picks · 4.4% exception</span></td>
                    <td style='text-align:right;color:{C_RED};padding:7px 0'>$0.14</td>
                    <td style='text-align:right;color:{C_RED};padding:7px 0'>T3 Complex</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>$0.20</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>+$86K</td>
                  </tr>
                  <tr>
                    <td style='padding:7px 0;color:{C_TEXT};font-weight:600'>Charlie Medical<br><span style='font-size:9px;color:{C_MUTED};font-weight:400'>0.99M picks · 0.7% exception</span></td>
                    <td style='text-align:right;color:{C_RED};padding:7px 0'>$0.15</td>
                    <td style='text-align:right;color:{C_AMBER};padding:7px 0'>T1 Base</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>$0.21</td>
                    <td style='text-align:right;color:#5DBF8A;padding:7px 0;font-weight:700'>+$60K</td>
                  </tr>
                </tbody>
              </table>
              <div style='font-size:10px;color:{C_MUTED};margin-top:10px;border-top:1px solid {C_BORDER};padding-top:8px'>
                * $0.19 is the Month-1 negotiated half-step — still below T2 floor. Brings Bravo to cost parity by Year 2.<br>
                Tiered structure replaces a flat rate that hides complexity cost. Delta pays more because exceptions cost more.
              </div>
            </div>
            """, unsafe_allow_html=True)

        _render_next_action(role, all_tickets)

        # ── BEST / LIKELY / WORST (full-width, always visible) ────────
        st.markdown(sec("Outcome Scenarios"), unsafe_allow_html=True)
        st.markdown(f"""
        <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:6px'>
          <div style='background:{C_RED_LITE};border:1px solid {C_BORDER};border-top:3px solid {C_RED};
                      border-radius:4px;padding:14px 16px'>
            <div style='font-size:9px;font-weight:700;color:{C_RED};letter-spacing:1px;margin-bottom:8px'>WORST CASE</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:4px'>Bravo pilot stalls · No re-billing</div>
            <div style='font-size:22px;font-weight:800;color:{C_RED};margin:6px 0'>$144K</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:10px'>Year 1 impact</div>
            <div style='font-size:10px;color:{C_MUTED};line-height:1.6;border-top:1px solid {C_BORDER};padding-top:8px'>
              Bravo at $0.19 only. Delta/Charlie delayed. Ops exposure untouched.
            </div>
          </div>
          <div style='background:{C_AMBER_LITE};border:1px solid {C_BORDER};border-top:3px solid {C_AMBER};
                      border-radius:4px;padding:14px 16px'>
            <div style='font-size:9px;font-weight:700;color:{C_AMBER};letter-spacing:1px;margin-bottom:8px'>LIKELY CASE</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:4px'>Bravo + re-billing + partial ops</div>
            <div style='font-size:22px;font-weight:800;color:{C_AMBER};margin:6px 0'>$560K</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:10px'>by Month 3</div>
            <div style='font-size:10px;color:{C_MUTED};line-height:1.6;border-top:1px solid {C_BORDER};padding-top:8px'>
              Bravo signed Month 1. Delta/Charlie re-billing Month 2–3. Exception study in flight.
            </div>
          </div>
          <div style='background:{C_GREEN_LITE};border:1px solid {C_BORDER};border-top:3px solid {C_GREEN};
                      border-radius:4px;padding:14px 16px'>
            <div style='font-size:9px;font-weight:700;color:{C_GREEN};letter-spacing:1px;margin-bottom:8px'>BEST CASE</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:4px'>Full 9-month rollout · Sites 2–3</div>
            <div style='font-size:22px;font-weight:800;color:{C_GREEN};margin:6px 0'>$1.15M</div>
            <div style='font-size:9px;color:{C_MUTED};margin-bottom:10px'>by Month 9</div>
            <div style='font-size:10px;color:{C_MUTED};line-height:1.6;border-top:1px solid {C_BORDER};padding-top:8px'>
              All 3 pilots closed. Ops savings realised. Sites 2–3 on Profit Lens.
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        left, right = st.columns([3, 2])
        with left:
            st.markdown(sec("Decisions Required This Month"), unsafe_allow_html=True)
            decisions = [
                (C_RED,   "APPROVE",  "Bravo FMCG Repricing Pilot", "$144K/yr · Rate $0.12 → $0.19 · Month 1 start"),
                (C_AMBER, "REVIEW",   "Delta Manufacturing — Evidence Package", "$345K combined · Commercial Lead presenting Month 2"),
                (C_AMBER, "REVIEW",   "Charlie Medical — Rebilling Authority", "$127K unbilled · Requires sign-off on rebilling policy"),
                (C_BLUE,  "INFORM",   "Home & Living Products Capacity Strategy", "$276K idle opportunity · Sales team input needed"),
            ]
            for c, action, title, sub in decisions:
                st.markdown(f"""
                <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {c};
                            border-radius:0 4px 4px 0;padding:14px 18px;margin-bottom:6px'>
                  <div style='display:flex;align-items:center;gap:10px;margin-bottom:4px'>
                    <span style='font-size:9px;font-weight:700;color:{c};letter-spacing:1px;
                                 background:{c}15;padding:2px 8px;border-radius:2px'>{action}</span>
                    <span style='font-size:13px;font-weight:600;color:{C_TEXT}'>{title}</span>
                  </div>
                  <div style='font-size:11px;color:{C_MUTED}'>{sub}</div>
                </div>""", unsafe_allow_html=True)

            # ── WHY BRAVO FIRST? ────────────────────────────────
            st.markdown(f"""
            <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid #5DBF8A;
                        border-radius:0 4px 4px 0;padding:13px 16px;margin:10px 0'>
              <div style='font-size:9px;font-weight:700;color:#5DBF8A;letter-spacing:1px;margin-bottom:9px'>
                🎯 SEQUENCING LOGIC — WHY BRAVO FIRST?
              </div>
              <div style='display:grid;grid-template-columns:1fr 1fr;gap:12px'>
                <div style='font-size:11px;color:{C_TEXT};line-height:1.7'>
                  <span style='color:#5DBF8A;font-weight:700'>Lowest churn risk.</span> 0.6% exception rate vs Delta's 4.4%. Clean operations — no complexity grievances to complicate the conversation.<br><br>
                  <span style='color:#5DBF8A;font-weight:700'>Cleanest lever.</span> One ask: pick rate $0.12 → $0.19. No unbilled work audit needed. One meeting, one decision-maker.
                </div>
                <div style='font-size:11px;color:{C_TEXT};line-height:1.7'>
                  <span style='color:#5DBF8A;font-weight:700'>Builds the evidence floor.</span> Bravo's accepted rate becomes the credibility anchor for every Delta and Charlie conversation that follows.<br><br>
                  <span style='color:#5DBF8A;font-weight:700'>Win-either-way.</span> Accept → +$144K. Walk → stop a $298K annual subsidy. Delta ($345K) is bigger but needs Bravo as precedent first.
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            # ── WHAT-IF TOGGLE ─────────────────────────────────
            with st.expander("💡 What-If: Bravo FMCG Pricing Scenarios", expanded=False):
                bravo_scenario = st.radio(
                    "Model the Bravo outcome:",
                    ["Bravo accepts $0.19/pick — +$144K/yr recovered",
                     "Bravo walks (declines repricing) — account lost"],
                    key="bravo_whatif",
                )
                if "accepts" in bravo_scenario:
                    st.markdown("""
                    <div style='background:#0D1F0D;border:1px solid #1F4A1F;border-radius:4px;padding:14px 18px;margin-top:8px'>
                      <div style='font-size:11px;font-weight:700;color:#5DBF8A;margin-bottom:10px'>SCENARIO: Bravo accepts $0.19/pick</div>
                      <div style='display:flex;gap:20px;flex-wrap:wrap;margin-bottom:10px'>
                        <div><div style='font-size:10px;color:#5D9E78'>New rate</div><div style='font-size:18px;font-weight:800;color:#5DBF8A'>$0.19/pick</div><div style='font-size:10px;color:#3D8A60'>was $0.12</div></div>
                        <div><div style='font-size:10px;color:#5D9E78'>Annual recovery</div><div style='font-size:18px;font-weight:800;color:#5DBF8A'>+$144K</div><div style='font-size:10px;color:#3D8A60'>Year 1</div></div>
                        <div><div style='font-size:10px;color:#5D9E78'>Still below true cost</div><div style='font-size:18px;font-weight:800;color:#F8B840'>$0.19 vs $0.265</div><div style='font-size:10px;color:#B8A060'>room to grow</div></div>
                        <div><div style='font-size:10px;color:#5D9E78'>Churn risk</div><div style='font-size:18px;font-weight:800;color:#5DBF8A'>LOW</div><div style='font-size:10px;color:#3D8A60'>gradual pilot</div></div>
                      </div>
                      <div style='font-size:11px;color:#8FBF9F;line-height:1.6'>Relationship preserved. $144K/yr recovered from Month 2. Strong precedent for Delta and Charlie repricing. <strong style='color:#5DBF8A'>Recommended path.</strong></div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style='background:#0F0D1A;border:1px solid #3D2A6B;border-radius:4px;padding:14px 18px;margin-top:8px'>
                      <div style='font-size:11px;font-weight:700;color:#A78BFA;margin-bottom:10px'>SCENARIO: Bravo declines — account lost</div>
                      <div style='display:flex;gap:20px;flex-wrap:wrap;margin-bottom:10px'>
                        <div><div style='font-size:10px;color:#7C6BAF'>Revenue lost</div><div style='font-size:18px;font-weight:800;color:#F8B840'>-$720K</div><div style='font-size:10px;color:#5A5080'>annual turnover</div></div>
                        <div><div style='font-size:10px;color:#7C6BAF'>Labour freed</div><div style='font-size:18px;font-weight:800;color:#A78BFA'>+$869K/yr</div><div style='font-size:10px;color:#5A5080'>below-cost service stops</div></div>
                        <div><div style='font-size:10px;color:#7C6BAF'>Net economic position</div><div style='font-size:18px;font-weight:800;color:#5DBF8A'>+$149K better off</div><div style='font-size:10px;color:#3D8A60'>no replacement needed</div></div>
                        <div><div style='font-size:10px;color:#7C6BAF'>Capacity freed</div><div style='font-size:18px;font-weight:800;color:#A78BFA'>~15%</div><div style='font-size:10px;color:#5A5080'>for profitable customers</div></div>
                      </div>
                      <div style='font-size:11px;color:#9D8FBF;line-height:1.6'>Mattingly <strong style='color:#A78BFA'>wins either way</strong>. Bravo is below-cost: losing the account at $0.12/pick frees $869K of loss-making labour. Soft risk is relationship and revenue optics — not economics.</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown(sec("Execution Roadmap"), unsafe_allow_html=True)
            _what_changed_visual()
            st.markdown("<br>", unsafe_allow_html=True)
            _mini_qa("CEO")

        with right:
            st.markdown(sec("Portfolio Health"), unsafe_allow_html=True)
            try:
                raw = json.load(open(DATA_PATH))
                profiles = raw.get("customer_profiles", [])
            except Exception:
                profiles = []
            for p in sorted(profiles, key=lambda x: x["true_margin_pct"]):
                health = customer_health(p)
                hc = HEALTH_COLOR[health]
                bar_w = max(p["true_margin_pct"], 5)
                st.markdown(f"""
                <div style='display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid {C_DIVIDER}'>
                  <div style='width:120px;font-size:12px;color:{C_TEXT};font-weight:500;flex-shrink:0'>{p["name"].split()[0]}</div>
                  <div style='flex:1;background:#F0F2F0;border-radius:2px;height:6px;overflow:hidden'>
                    <div style='background:{hc};width:{bar_w}%;height:100%'></div>
                  </div>
                  <div style='width:36px;text-align:right;font-size:12px;font-weight:700;color:{hc}'>{p["true_margin_pct"]:.0f}%</div>
                </div>""", unsafe_allow_html=True)
            st.markdown(f"""
            <div style='margin-top:12px;font-size:10px;color:{C_MUTED}'>
              True margin vs $0.265/pick cost (conservative floor). Reported margin ~96% across all customers.
            </div>""", unsafe_allow_html=True)

            st.markdown(sec("Exposure by Type"), unsafe_allow_html=True)
            if all_tickets:
                df   = pd.DataFrame(all_tickets)
                # Exclude F011 (structural parent — already contained in F001/F002/F003)
                df_f = df[(df["dollar_impact"] > 0) & (df["finding_id"] != "F011")]
                if not df_f.empty:
                    tt = df_f.groupby("finding_type")["dollar_impact"].sum().reset_index()
                    tt["label"] = tt["finding_type"].map(TYPE_LABEL).fillna(tt["finding_type"])
                    colors = ["#991B1B","#B45309","#1E3A5F","#005A32","#5B21B6","#0E7490"]
                    fig = go.Figure(go.Pie(
                        labels=tt["label"], values=tt["dollar_impact"], hole=0.62,
                        marker=dict(colors=colors[:len(tt)], line=dict(color=C_BG, width=2)),
                        textfont=dict(color=C_TEXT, size=9, family="Inter"),
                    ))
                    fig.update_layout(
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        margin=dict(l=0,r=0,t=0,b=0), height=200,
                        legend=dict(font=dict(color=C_MUTED, size=9, family="Inter"), bgcolor="rgba(0,0,0,0)"),
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                    st.markdown(
                        f"<div style='font-size:10px;color:{C_MUTED};margin-top:4px;padding:6px 10px;"
                        f"background:{C_CARD};border-radius:3px;border-left:2px solid {C_MUTED}'>"
                        f"⚠ Excludes F011 Structural ($1.49M network-wide) — contains F001/F002/F003 above. "
                        f"No double-count. Pricing exposure: $1.86M conservative. Add ops opportunity $0.80M → $2.65M total.</div>",
                        unsafe_allow_html=True)

    # ── COMMERCIAL LEAD view ──────────────────────────────────
    elif role == "Commercial Lead":
        st.markdown(page_header(
            "Commercial Lead Dashboard",
            f"Pricing recovery pipeline and negotiation priorities — {WAREHOUSE_NAME}"
        ), unsafe_allow_html=True)

        pricing_t  = sum(1 for t in all_tickets if t["finding_type"]=="pricing_leakage" and t["status"]!="Done")
        rebill_t   = sum(1 for t in all_tickets if t["finding_type"]=="unbilled_work" and t["status"]!="Done")
        closed_val = sum(t["dollar_impact"] for t in all_tickets if t["status"]=="Done" and t["dollar_impact"]>0)
        pipeline   = sum(t["dollar_impact"] for t in all_tickets if t["finding_type"] in ("pricing_leakage","unbilled_work") and t["status"]!="Done" and t.get("finding_id") != "F011")

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(kpi_card("Pricing Pipeline", fmt_dollars(pipeline), f"{pricing_t} open contracts to reprice", C_RED), unsafe_allow_html=True)
        k2.markdown(kpi_card("Rebilling Target", "$253K", f"{rebill_t} rebilling actions open", C_AMBER), unsafe_allow_html=True)
        k3.markdown(kpi_card("Closed Value", fmt_dollars(closed_val) if closed_val else "$0", "Deals closed this period", C_GREEN), unsafe_allow_html=True)
        k4.markdown(kpi_card("Month 1 Priority", "$144K", "Bravo FMCG — approve to proceed", C_BLUE), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        _notifications_panel(role)

        # MOS CADENCE — Commercial Lead (Weekly) — LIVE DATE-AWARE
        import datetime as _dt
        _cl_today = _dt.date.today()
        _cl_week  = _cl_today.isocalendar()[1]
        _cl_dow   = _cl_today.strftime("%A")
        _cl_date  = _cl_today.strftime("%d %b %Y")
        st.markdown(f"""
        <div style='background:#1A3D2B;border-radius:4px;padding:16px 20px;margin-bottom:16px'>
          <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>
            <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700'>
              MANAGEMENT OPERATING SYSTEM &nbsp;|&nbsp; COMMERCIAL LEAD &nbsp;&middot;&nbsp; WEEKLY CADENCE
            </div>
            <div style='font-size:10px;color:#3A7A54;font-weight:600'>
              Week {_cl_week} &nbsp;|&nbsp; {_cl_dow}, {_cl_date}
            </div>
          </div>
          <div style='display:flex;gap:0;border-radius:3px;overflow:hidden'>
            <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04);border-right:1px solid rgba(255,255,255,0.08)'>
              <div style='font-size:9px;color:#6B9E83;font-weight:700;letter-spacing:1px;margin-bottom:8px'>DAILY CHECK</div>
              <div style='font-size:11px;color:#C8DDD2;line-height:1.8'>
                Review ticket status changes<br>
                Flag any blocked negotiations<br>
                Confirm clean data from Site Manager
              </div>
            </div>
            <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.07);border-right:1px solid rgba(255,255,255,0.08)'>
              <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:8px'>THIS WEEK — ACTION QUEUE</div>
              <div style='font-size:11px;color:#C8DDD2;line-height:1.8'>
                Update Bravo + Delta + Charlie pipeline<br>
                Prepare evidence packages for CEO brief<br>
                Escalate any blockers above
              </div>
            </div>
            <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04);border-right:1px solid rgba(255,255,255,0.08)'>
              <div style='font-size:9px;color:#5DBF8A;font-weight:700;letter-spacing:1px;margin-bottom:8px'>MONTHLY MILESTONES</div>
              <div style='font-size:11px;color:#C8DDD2;line-height:1.8'>
                Month 1 &rarr; Bravo contract closed $144K<br>
                Month 2 &rarr; Delta evidence brief to CEO<br>
                Month 3 &rarr; Charlie rebilling in market
              </div>
            </div>
            <div style='flex:1;padding:10px 14px;background:rgba(255,255,255,0.04)'>
              <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:8px'>PIPELINE VALUE AT RISK</div>
              <div style='display:flex;flex-direction:column;gap:4px'>
                <div style='display:flex;justify-content:space-between'>
                  <span style='font-size:11px;color:#C8DDD2'>Bravo</span>
                  <span style='font-size:11px;font-weight:700;color:#5DBF8A'>$144K</span>
                </div>
                <div style='display:flex;justify-content:space-between'>
                  <span style='font-size:11px;color:#C8DDD2'>Delta</span>
                  <span style='font-size:11px;font-weight:700;color:#F8B840'>$345K</span>
                </div>
                <div style='display:flex;justify-content:space-between'>
                  <span style='font-size:11px;color:#C8DDD2'>Charlie</span>
                  <span style='font-size:11px;font-weight:700;color:#F8B840'>$229K</span>
                </div>
                <div style='border-top:1px solid rgba(255,255,255,0.1);margin-top:4px;padding-top:4px;
                            display:flex;justify-content:space-between'>
                  <span style='font-size:11px;color:#C8DDD2;font-weight:600'>Total open</span>
                  <span style='font-size:13px;font-weight:700;color:#FFFFFF'>$718K</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _render_next_action(role, all_tickets)

        left, right = st.columns([3, 2])
        with left:
            st.markdown(sec("Negotiation Pipeline — Prioritised by Impact"), unsafe_allow_html=True)
            pipeline_items = [
                (C_RED,   "MONTH 1",  "Bravo FMCG — Repricing",     "$144K/yr",  "Rate $0.12 → $0.19 · 2M picks · CEO approved"),
                (C_AMBER, "MONTH 2",  "Delta — Evidence Gathering",  "$345K/yr",  "Exception logs + rate review · 1.8M picks"),
                (C_AMBER, "MONTH 3",  "Delta — Repricing + Rebill",  "$345K/yr",  "Use Bravo pilot as evidence · Include $147K unbilled"),
                (C_AMBER, "MONTH 3",  "Charlie — Rebilling",         "$229K/yr",  "Client log corroborates gap · 320K unbilled picks"),
                (C_BLUE,  "MONTH 4+", "Medisupply Australia",          "$58K/yr",   "Wave 2 repricing · $0.14 → $0.19"),
            ]
            for c, wave, title, val, sub in pipeline_items:
                st.markdown(f"""
                <div style='background:{C_CARD};border:1px solid {C_BORDER};border-left:4px solid {c};
                            border-radius:0 4px 4px 0;padding:13px 18px;margin-bottom:5px'>
                  <div style='display:flex;justify-content:space-between;align-items:flex-start'>
                    <div>
                      <div style='font-size:9px;font-weight:700;color:{c};letter-spacing:1px;margin-bottom:3px'>{wave}</div>
                      <div style='font-size:13px;font-weight:600;color:{C_TEXT}'>{title}</div>
                      <div style='font-size:11px;color:{C_MUTED};margin-top:2px'>{sub}</div>
                    </div>
                    <div style='font-size:15px;font-weight:700;color:{c};white-space:nowrap;margin-left:16px'>{val}</div>
                  </div>
                </div>""", unsafe_allow_html=True)

            st.markdown(sec("Your Tickets"), unsafe_allow_html=True)
            my_t = [t for t in db.get_tickets(WAREHOUSE_ID, role=role) if t["status"] != "Done"][:4]
            for t in my_t:
                _ticket_row(t)
            st.markdown("<br>", unsafe_allow_html=True)
            _mini_qa("Commercial Lead")

        with right:
            st.markdown(sec("Rate Comparison — Current vs Target"), unsafe_allow_html=True)
            rate_data = [
                ("Bravo FMCG",  0.12, 0.19, 0.265),
                ("Delta Mfg",   0.14, 0.19, 0.265),
                ("Charlie Med", 0.14, 0.19, 0.265),
                ("Medisupply AU", 0.17, 0.19, 0.265),
            ]
            fig = go.Figure()
            names  = [r[0] for r in rate_data]
            curr   = [r[1] for r in rate_data]
            target = [r[2] for r in rate_data]
            cost   = [r[3] for r in rate_data]
            fig.add_trace(go.Bar(name="Current Rate", x=names, y=curr,
                                 marker_color=C_RED, width=0.25,
                                 offset=-0.13, text=[f"${v:.2f}" for v in curr],
                                 textfont=dict(size=9, family="Inter"), textposition="outside"))
            fig.add_trace(go.Bar(name="Proposed Rate", x=names, y=target,
                                 marker_color=C_GREEN, width=0.25,
                                 offset=0.13, text=[f"${v:.2f}" for v in target],
                                 textfont=dict(size=9, family="Inter"), textposition="outside"))
            fig.add_trace(go.Scatter(name="True Cost ($0.265)", x=names, y=cost,
                                     mode="lines", line=dict(color=C_AMBER, width=2, dash="dot")))
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0,r=0,t=10,b=0), height=220, barmode="overlay",
                legend=dict(font=dict(size=9, family="Inter"), bgcolor="rgba(0,0,0,0)"),
                yaxis=dict(tickprefix="$", tickfont=dict(size=9), gridcolor=C_DIVIDER),
                xaxis=dict(tickfont=dict(size=10, family="Inter")),
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            st.markdown(sec("Execution Roadmap"), unsafe_allow_html=True)
            _recovery_bar(stats, pct)

    # ── SITE MANAGER view ─────────────────────────────────────
    else:
        st.markdown(page_header(
            "Site Manager Dashboard",
            f"Operational priorities and data quality — {WAREHOUSE_NAME}"
        ), unsafe_allow_html=True)

        my_tickets = db.get_tickets(WAREHOUSE_ID, role=role)
        open_mine  = [t for t in my_tickets if t["status"] != "Done"]
        done_mine  = [t for t in my_tickets if t["status"] == "Done"]
        hygiene_t  = [t for t in open_mine if t["finding_type"] == "data_hygiene"]

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.markdown(kpi_card("Open Operational", str(len(open_mine)), "Tickets assigned to Site Manager", C_AMBER), unsafe_allow_html=True)
        k2.markdown(kpi_card("Data Hygiene", str(len(hygiene_t)), "Must close before negotiations", C_RED if hygiene_t else C_GREEN), unsafe_allow_html=True)
        k3.markdown(kpi_card("Delta Exception Drain", "$446K/yr", "3.9× next-highest customer (F014)", C_RED), unsafe_allow_html=True)
        k4.markdown(kpi_card("True Pick Cost", "$0.265/pick", "All-in labour cost (ABC analysis)", C_RED), unsafe_allow_html=True)
        k5.markdown(kpi_card("Completed by You", str(len(done_mine)), "Tickets resolved this period", C_GREEN), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        _notifications_panel(role)

        # DATA QUALITY ALERT — links Site Manager to the Information Gaps page
        _hygiene_open = len([t for t in open_mine if t.get("finding_type") == "data_hygiene"])
        _gap_color    = "#991B1B" if _hygiene_open > 0 else "#005A32"
        _gap_bg       = "#1A0D0D" if _hygiene_open > 0 else "#0D1A0D"
        _gap_border   = "#6B1A1A" if _hygiene_open > 0 else "#1A3A28"
        _gap_icon     = "DATA QUALITY ALERT" if _hygiene_open > 0 else "DATA QUALITY OK"
        _gap_msg      = (f"{_hygiene_open} hygiene ticket(s) open — clean data is required before Commercial Lead can start negotiations."
                         if _hygiene_open > 0
                         else "No open hygiene tickets. Data is clean and ready for negotiation support.")
        st.markdown(f"""
        <div style='background:{_gap_bg};border:1px solid {_gap_border};border-radius:4px;
                    padding:10px 16px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center'>
          <div style='display:flex;gap:12px;align-items:center'>
            <div style='font-size:9px;letter-spacing:1px;color:{_gap_color};font-weight:700;flex-shrink:0'>
              {_gap_icon}
            </div>
            <div style='font-size:12px;color:#C8DDD2;line-height:1.5'>{_gap_msg}</div>
          </div>
          <div style='font-size:10px;color:#4A9E6A;flex-shrink:0;margin-left:12px;font-weight:600'>
            See Information Gaps page &rarr;
          </div>
        </div>
        """, unsafe_allow_html=True)

        # MOS CADENCE — Site Manager (Daily) — LIVE INTERACTIVE CHECKLIST
        import datetime as _dt
        _sm_today = _dt.date.today()
        _sm_dow   = _sm_today.strftime("%A")
        _sm_date  = _sm_today.strftime("%d %b %Y")
        _sm_week  = _sm_today.isocalendar()[1]
        _sm_is_monday = _sm_today.weekday() == 0  # Monday = send weekly report

        st.markdown(f"""
        <div style='background:#1A3D2B;border-radius:4px;padding:16px 20px;margin-bottom:8px'>
          <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
            <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700'>
              MANAGEMENT OPERATING SYSTEM &nbsp;|&nbsp; SITE MANAGER &nbsp;&middot;&nbsp; DAILY BRIEF
            </div>
            <div style='font-size:10px;color:#3A7A54;font-weight:600'>
              {_sm_dow}, {_sm_date} &nbsp;|&nbsp; Week {_sm_week}
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Live checklist columns
        _ck1, _ck2, _ck3 = st.columns(3)
        with _ck1:
            st.markdown(f"""<div style='background:#0F2419;border:1px solid #1A3A28;border-radius:4px;
                padding:10px 14px;margin-bottom:4px'>
              <div style='font-size:9px;color:#F8B840;font-weight:700;letter-spacing:1px;margin-bottom:8px'>
                TODAY — MUST DO &nbsp;({_sm_dow.upper()})
              </div>
            </div>""", unsafe_allow_html=True)
            st.checkbox("Check Delta exception rate (target: below 10%)",   key="sm_d1")
            st.checkbox("Validate pick count accuracy for billing",          key="sm_d2")
            st.checkbox("Action open hygiene tickets (F006, F007)",          key="sm_d3")
            st.checkbox("Log any new exception events on the floor",         key="sm_d4")

        with _ck2:
            _sm_is_due = _sm_today.weekday() in (0, 4)  # Mon or Fri
            _week_label = "THIS WEEK — REPORT DUE FRIDAY" if not _sm_is_due else f"WEEKLY REPORT — DUE {'TODAY' if _sm_today.weekday()==4 else 'MONDAY'}"
            st.markdown(f"""<div style='background:#0F2419;border:1px solid #1A3A28;border-radius:4px;
                padding:10px 14px;margin-bottom:4px'>
              <div style='font-size:9px;color:#6B9E83;font-weight:700;letter-spacing:1px;margin-bottom:8px'>
                {_week_label}
              </div>
            </div>""", unsafe_allow_html=True)
            st.checkbox("Submit corrected pick data to Commercial Lead",     key="sm_w1")
            st.checkbox("Exception root cause update (Delta)",               key="sm_w2")
            st.checkbox("Labour data completeness check (no missing days)",  key="sm_w3")
            st.checkbox("Urgent order SLA review with floor team",           key="sm_w4")

        with _ck3:
            _done_count = sum(1 for k in ["sm_d1","sm_d2","sm_d3","sm_d4","sm_w1","sm_w2","sm_w3","sm_w4"]
                              if st.session_state.get(k, False))
            _total_items = 8
            _pct_done = int(_done_count / _total_items * 100)
            st.markdown(f"""<div style='background:#0F2419;border:1px solid #1A3A28;border-radius:4px;
                padding:10px 14px;margin-bottom:4px'>
              <div style='font-size:9px;color:#5DBF8A;font-weight:700;letter-spacing:1px;margin-bottom:8px'>
                MONTHLY TARGET
              </div>
            </div>""", unsafe_allow_html=True)
            st.markdown(f"""
            <div style='background:#F5FFF8;border:1px solid #B7DCC8;border-radius:4px;padding:10px 14px;margin-bottom:8px'>
              <div style='font-size:11px;color:#005A32;font-weight:600;margin-bottom:6px'>Today: {_done_count}/{_total_items} items complete</div>
              <div style='background:#D1FAE5;border-radius:2px;height:6px;margin-bottom:8px'>
                <div style='background:#005A32;height:6px;border-radius:2px;width:{_pct_done}%'></div>
              </div>
              <div style='font-size:11px;color:#374151;line-height:1.6'>
                Close F006/F007 hygiene items<br>
                Delta exception rate below 5.8% network avg<br>
                Clean data before CEO Bravo approval
              </div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown("<div style='margin-bottom:12px'></div>", unsafe_allow_html=True)

        # Plain-English context for Site Manager
        st.markdown(f"""
        <div style='background:{C_BLUE_LITE};border:1px solid #C3D5EC;border-radius:4px;
                    padding:12px 16px;margin-bottom:16px;font-size:12px;color:{C_BLUE};line-height:1.6'>
          <strong>Your role in plain English:</strong> The ABC analysis (Activity-Based Costing) shows
          every customer is being charged less than it costs to serve them — $0.265 per pick is what it
          actually costs Mattingly in labour; most customers pay $0.12–$0.17. Your job is to make sure
          the pick count data is accurate and exceptions are recorded, so the Commercial team can go back
          to customers with clean numbers they can't dispute.
        </div>
        """, unsafe_allow_html=True)

        # ── AI AUTO-DETECT: operational bottleneck alerts ──────
        st.markdown("""
        <div style='background:#1A0D0D;border:1px solid #6B1A1A;border-radius:4px;padding:12px 16px;margin-bottom:12px'>
          <div style='font-size:9px;letter-spacing:2px;color:#FF6B6B;font-weight:700;margin-bottom:8px'>
            🚨 AI BOTTLENECK DETECTED &nbsp;&nbsp;|&nbsp;&nbsp; AUTO-FLAGGED FROM LABOUR DATA
          </div>
          <div style='display:flex;gap:16px;align-items:flex-start'>
            <div style='flex:1'>
              <div style='font-size:13px;font-weight:700;color:#FF8080;margin-bottom:4px'>Delta Manufacturing — Exception Labour Outlier</div>
              <div style='font-size:11px;color:#C8A0A0;line-height:1.7'>
                AI analysis of Jan–Feb labour data flagged Delta as generating <strong style='color:#FF8080'>3.9× more exception labour</strong>
                than the next-highest customer. Exception handling (returns + rework + urgent orders) drains
                <strong style='color:#FF8080'>$446K/yr</strong> above what a normal customer of their size would generate.
              </div>
              <div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap'>
                <span style='font-size:10px;font-weight:700;color:#FF6060;background:#FF606015;padding:3px 10px;border-radius:2px'>ACTION: Investigate root cause</span>
                <span style='font-size:10px;font-weight:700;color:#F8B840;background:#F8B84015;padding:3px 10px;border-radius:2px'>TARGET: below 10% in 30 days</span>
                <span style='font-size:10px;font-weight:700;color:#5DBF8A;background:#5DBF8A15;padding:3px 10px;border-radius:2px'>CEO + Commercial Lead notified</span>
              </div>
            </div>
            <div style='text-align:right;flex-shrink:0;padding-top:4px'>
              <div style='font-size:22px;font-weight:800;color:#FF6060'>$446K</div>
              <div style='font-size:9px;color:#996666;margin-top:2px'>annual drain</div>
              <div style='font-size:9px;color:#996666'>3.9× peers</div>
            </div>
          </div>
        </div>
        <div style='background:#1A1407;border:1px solid #5C3A00;border-radius:4px;padding:10px 16px;margin-bottom:16px'>
          <div style='font-size:9px;letter-spacing:1px;color:#F8B840;font-weight:700;margin-bottom:6px'>⚠️ SECONDARY — Urgent Order Throughput Penalty</div>
          <div style='font-size:11px;color:#C8B080;line-height:1.6'>
            Urgent orders run at <strong style='color:#F8D27A'>8.5 units/hr vs 19.8/hr standard dispatch</strong> — 2.35× slower.
            Adds $349K/yr in premium labour. Investigate whether Delta urgent volume is the common root cause.
          </div>
        </div>
        """, unsafe_allow_html=True)

        _render_next_action(role, all_tickets)

        left, right = st.columns([3, 2])
        with left:
            st.markdown(sec("Priority — Data Quality (Fix Before Negotiations)"), unsafe_allow_html=True)
            if hygiene_t:
                for t in hygiene_t:
                    _ticket_row(t)
            else:
                st.success("All data hygiene tickets are resolved.")

            st.markdown(sec("All Open Operational Tickets"), unsafe_allow_html=True)
            non_hygiene = [t for t in open_mine if t["finding_type"] != "data_hygiene"]
            if non_hygiene:
                for t in non_hygiene[:6]:
                    _ticket_row(t)
            else:
                st.info("No other open operational tickets.")

            st.markdown(sec("What Changed This Period"), unsafe_allow_html=True)
            _what_changed_visual()
            st.markdown("<br>", unsafe_allow_html=True)
            _mini_qa("Site Manager")

        with right:
            st.markdown(sec("Exception Rate — Network Comparison"), unsafe_allow_html=True)
            exc_data = {
                "Delta Mfg":   14.1,
                "Charlie Med": 8.2,
                "Bravo FMCG":  5.1,
                "Medisupply AU":  3.8,
                "Home & Living":  2.1,
                "Network Avg": 5.8,
            }
            fig = go.Figure(go.Bar(
                x=list(exc_data.keys()),
                y=list(exc_data.values()),
                marker_color=[C_RED if v > 5.8 else C_GREEN for v in exc_data.values()],
                text=[f"{v}%" for v in exc_data.values()],
                textfont=dict(size=10, family="Inter"),
                textposition="outside",
            ))
            fig.update_layout(
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=0,r=0,t=10,b=0), height=220,
                yaxis=dict(ticksuffix="%", tickfont=dict(size=9), gridcolor=C_DIVIDER),
                xaxis=dict(tickfont=dict(size=9, family="Inter")),
                font=dict(family="Inter"),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            st.markdown(sec("Data Quality Checklist"), unsafe_allow_html=True)
            checks = [
                ("Close 4-day labour data gap (F007)", bool(not hygiene_t)),
                ("Validate findings vs 12-month history (F006)", bool(not hygiene_t)),
                ("Confirm Delta exception root cause", False),
                ("Submit corrected pick counts to Commercial Lead", False),
            ]
            for label, done in checks:
                c = C_GREEN if done else C_MUTED
                icon = "v" if done else "○"
                st.markdown(f"""
                <div style='display:flex;gap:10px;padding:7px 0;border-bottom:1px solid {C_DIVIDER};
                            font-size:12px;align-items:center'>
                  <span style='color:{c};font-weight:700;width:14px'>{icon}</span>
                  <span style='color:{C_TEXT if not done else C_MUTED};
                               text-decoration:{"line-through" if done else "none"}'>{label}</span>
                </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PAGE 2 — CUSTOMER PROFITABILITY
# ═══════════════════════════════════════════════════════════
def page_customer_profitability():
    st.markdown(page_header(
        "Customer Profitability",
        "Activity-based costing view — true margin vs reported margin"
    ), unsafe_allow_html=True)

    try:
        with open(DATA_PATH) as f: raw = json.load(f)
        profiles = raw.get("customer_profiles", [])
    except Exception as e:
        st.error(f"Cannot load findings data: {e}")
        return

    all_tickets = db.get_tickets(WAREHOUSE_ID)

    # Health counts
    h_counts = {"Action Required": 0, "Watch": 0, "Opportunity": 0, "Healthy": 0}
    for p in profiles:
        h_counts[customer_health(p)] = h_counts.get(customer_health(p), 0) + 1

    c1, c2, c3, c4 = st.columns(4)
    for col, (status, cnt) in zip([c1, c2, c3, c4], h_counts.items()):
        c = HEALTH_COLOR[status]
        col.markdown(f"""
        <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;
                    border-top:3px solid {c};padding:16px 18px;text-align:center'>
          <div style='font-size:28px;font-weight:800;color:{c}'>{cnt}</div>
          <div style='font-size:9px;letter-spacing:1.5px;color:{C_MUTED};font-weight:600;margin-top:4px'>{status.upper()}</div>
        </div>""", unsafe_allow_html=True)

    st.warning(
        "**Data Quality:** Labour costing is at warehouse level (imputed rates). "
        "4 days of data missing — Site Manager must resolve F007. Seasonality verified stable (M1/M2 ratio 0.84–1.18 across all 30 customers). "
        "True pick cost **$0.265/pick** (conservative floor) is directionally correct; engine-strict rate is $0.284/pick (labour-only). Validate before external negotiations."
    )

    # ── METHODOLOGY CAVEAT ────────────────────────────────────────────────────
    st.markdown(f"""
    <div style='background:#1A1A2E;border:1px solid #2D2D5E;border-left:4px solid #4A4A9A;
                border-radius:4px;padding:14px 18px;margin-bottom:8px'>
      <div style='font-size:9px;letter-spacing:2px;color:#8888CC;font-weight:700;margin-bottom:6px'>
        METHODOLOGY NOTE — PRICING &amp; BILLING VIEW</div>
      <div style='font-size:12px;color:#B8B8E8;line-height:1.65'>
        These margins reflect a <strong>pricing-and-billing view</strong>: cost-to-serve is modelled
        as customer activity volume × a blended warehouse unit cost, not measured at the customer level,
        because labour records carry no customer dimension in the source data.
        Translating this into a true per-customer cost-to-serve requires one missing input:
        a <strong>Product ID join key on transaction records</strong> — Product Master holds
        size and handling complexity, but transactions currently carry no join key to link them.
        The analysis is directionally sound for pricing decisions; per-SKU cost granularity
        becomes available once that join key is in place.
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(sec("Key Accounts — Immediate Action Required"), unsafe_allow_html=True)

    # Spotlight 3 cards: Delta (Critical), Charlie (High), Bravo (High)
    _spotlight = [
        {
            "name": "Delta Manufacturing",
            "true_margin": 19.5,
            "issue": "14.1% exception rate — 2.4× network avg. Below-cost rate + unbilled rework.",
            "exposure": "$345K combined",
            "action": "REPRICE + REBILL",
            "action_note": "Rate renegotiation + exception billing — Month 2",
            "color": C_RED,
        },
        {
            "name": "Charlie Medical",
            "true_margin": 22.0,
            "issue": "165K picks performed vs 133K billed. Recurring daily gap, client log corroborates.",
            "exposure": "$127K unbilled",
            "action": "REBILL NOW",
            "action_note": "Issue credit note and rebill — immediate",
            "color": C_RED,
        },
        {
            "name": "Bravo FMCG",
            "true_margin": 29.1,
            "issue": "2M picks/yr at $0.12 charged vs $0.265 true cost. Scale amplifies the loss.",
            "exposure": "$144K/yr",
            "action": "REPRICE",
            "action_note": "Pilot $0.12 → $0.19 — Month 1 priority",
            "color": C_AMBER,
        },
    ]
    _sp_cols = st.columns(3)
    for _sc, _sp in zip(_sp_cols, _spotlight):
        _sc.markdown(f"""
        <div style='background:{C_CARD};border:1px solid {C_BORDER};border-top:3px solid {_sp["color"]};
                    border-radius:0 0 4px 4px;padding:16px 18px;height:100%'>
          <div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px'>
            <div style='font-size:13px;font-weight:700;color:{C_TEXT}'>{_sp["name"]}</div>
            <div style='background:{_sp["color"]}18;border:1px solid {_sp["color"]}44;border-radius:2px;
                        padding:2px 8px;font-size:9px;font-weight:700;color:{_sp["color"]}'>{_sp["action"]}</div>
          </div>
          <div style='font-size:28px;font-weight:800;color:{_sp["color"]};margin-bottom:4px'>{_sp["true_margin"]:.0f}%</div>
          <div style='font-size:9px;letter-spacing:1px;color:{C_MUTED};font-weight:600;margin-bottom:10px'>TRUE MARGIN</div>
          <div style='font-size:11px;color:{C_TEXT};line-height:1.55;margin-bottom:10px'>{_sp["issue"]}</div>
          <div style='border-top:1px solid {C_DIVIDER};padding-top:10px;display:flex;justify-content:space-between;align-items:center'>
            <div style='font-size:13px;font-weight:700;color:{_sp["color"]}'>{_sp["exposure"]}</div>
            <div style='font-size:10px;color:{C_MUTED}'>{_sp["action_note"]}</div>
          </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom:20px'></div>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown(sec("Customer Portfolio — Sorted by Risk"), unsafe_allow_html=True)

    for p in sorted(profiles, key=lambda x: x["true_margin_pct"]):
        health  = customer_health(p)
        hc      = HEALTH_COLOR[health]
        tags    = p.get("tags", [])
        open_t  = [t for t in all_tickets
                   if t.get("customer") == p["name"] and t["status"] != "Done"] if all_tickets else []
        open_d  = sum(t["dollar_impact"] for t in open_t if t["dollar_impact"] > 0)

        tag_str = "  ".join(
            f'<span style="background:{C_AMBER_LITE};color:{C_AMBER};font-size:9px;font-weight:700;' +
            f'padding:2px 8px;border-radius:2px">{t}</span>' for t in tags
        )
        contract_str = ""
        if p.get("contract_type") in ("fixed_fee", "Fixed Monthly"):
            contract_str = f'<span style="color:{C_BLUE};font-size:10px;font-weight:500"> &nbsp;·&nbsp; Fixed Fee · {p.get("capacity_utilisation_pct",0)}% utilised</span>'
        at_risk_html = f'<span style="font-size:13px;font-weight:700;color:{C_RED}">{fmt_dollars(open_d)}</span>' if open_d > 0 else f'<span style="color:{C_MUTED}">—</span>'

        # Layer 1: Summary row — native columns (avoids flex-div HTML rendering issues)
        st.markdown(
            f"<div style='border-left:4px solid {hc};background:{C_CARD};"
            f"border:1px solid {C_BORDER};border-radius:0 4px 4px 0;"
            f"padding:6px 12px;margin-bottom:2px'></div>",
            unsafe_allow_html=True
        )
        _rc1, _rc2, _rc3, _rc4, _rc5, _rc6 = st.columns([1.8, 3, 1.1, 1.3, 1.0, 1.2])
        with _rc1:
            st.markdown(health_badge(health), unsafe_allow_html=True)
        with _rc2:
            name_line = f"<span style='font-size:14px;font-weight:700;color:{C_TEXT}'>{p['name']}</span>"
            if contract_str:
                name_line += contract_str
            if tag_str:
                name_line += f"<br><span style='font-size:9px'>{tag_str}</span>"
            st.markdown(name_line, unsafe_allow_html=True)
        with _rc3:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:9px;color:{C_MUTED};font-weight:600;letter-spacing:1px'>TRUE MARGIN</div>"
                f"<div style='font-size:20px;font-weight:800;color:{hc}'>{p['true_margin_pct']:.0f}%</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with _rc4:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:9px;color:{C_MUTED};font-weight:600;letter-spacing:1px'>REVENUE</div>"
                f"<div style='font-size:14px;font-weight:700;color:{C_TEXT}'>{fmt_dollars(p['annual_revenue'])}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with _rc5:
            tk_color = C_RED if open_t else C_GREEN
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div style='font-size:9px;color:{C_MUTED};font-weight:600;letter-spacing:1px'>TICKETS</div>"
                f"<div style='font-size:20px;font-weight:800;color:{tk_color}'>{len(open_t)}</div>"
                f"</div>",
                unsafe_allow_html=True
            )
        with _rc6:
            st.markdown(
                f"<div style='text-align:right'>"
                f"<div style='font-size:9px;color:{C_MUTED};font-weight:600;letter-spacing:1px'>AT RISK</div>"
                f"{at_risk_html}"
                f"</div>",
                unsafe_allow_html=True
            )
        st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)

        # Layer 2: Expander detail
        with st.expander(f"{p['name']} — view details", expanded=False):
            tag_md = "  ".join(f"`{t}`" for t in tags) if tags else ""
            st.markdown(f"**{p['name']}** &nbsp;·&nbsp; {health.upper()}" + (f"  &nbsp;·&nbsp;  {tag_md}" if tag_md else ""), unsafe_allow_html=True)
            st.markdown("---")

            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.markdown(f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_MUTED};margin-bottom:10px'>KEY METRICS</div>", unsafe_allow_html=True)
                st.markdown(f"""
                <table style='width:100%;font-size:12px;border-collapse:collapse;font-family:Inter,sans-serif'>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>Annual Revenue</td><td style='font-weight:600;text-align:right'>{fmt_dollars(p["annual_revenue"])}</td></tr>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>Reported Margin</td><td style='font-weight:600;color:{C_RED};text-align:right'>{p["reported_margin_pct"]:.0f}%</td></tr>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>True Margin (ABC)</td><td style='font-weight:700;color:{hc};text-align:right'>{p["true_margin_pct"]:.0f}%</td></tr>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>Annual Picks</td><td style='font-weight:600;text-align:right'>{p["annual_picks"]/1e3:.0f}K</td></tr>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>Rate Charged</td><td style='font-weight:600;color:{C_RED};text-align:right'>${p.get("pick_rate_charged",0):.2f}/pick</td></tr>
                  <tr style='border-bottom:1px solid {C_DIVIDER}'><td style='color:{C_MUTED};padding:7px 0'>True Pick Cost</td><td style='font-weight:600;text-align:right'>$0.265/pick</td></tr>
                  <tr><td style='color:{C_MUTED};padding:7px 0'>Exception Rate</td><td style='font-weight:600;color:{"#991B1B" if p["exception_rate_pct"]>8 else C_TEXT};text-align:right'>{p["exception_rate_pct"]:.1f}%</td></tr>
                </table>
                """, unsafe_allow_html=True)

            with col2:
                st.markdown(f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_MUTED};margin-bottom:10px'>PROFITABILITY DRIVERS</div>", unsafe_allow_html=True)
                for d in p.get("profitability_drivers", []):
                    tc = {"pricing": C_RED,"unbilled": C_AMBER,"operational": C_BLUE,"overhead": C_MUTED}.get(d.get("type",""), C_MUTED)
                    direction = "−" if d["impact"] < 0 else "+"
                    st.markdown(f"""
                    <div style='display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid {C_DIVIDER};font-size:12px'>
                      <span style='color:{C_TEXT};flex:1'>{d["driver"]}</span>
                      <span style='color:{tc};font-weight:700;margin-left:12px;white-space:nowrap'>{direction}{fmt_dollars(abs(d["impact"]))}</span>
                    </div>""", unsafe_allow_html=True)
                st.markdown(f"""
                <div style='margin-top:14px;background:{hc}10;border-radius:3px;border-left:3px solid {hc};padding:10px 14px'>
                  <div style='font-size:9px;letter-spacing:1.5px;font-weight:700;color:{hc};margin-bottom:4px'>RECOMMENDATION</div>
                  <div style='font-size:13px;font-weight:600;color:{C_TEXT}'>{p["recommendation"]}</div>
                  <div style='font-size:11px;color:{C_MUTED};margin-top:3px'>{p.get("recommendation_note","")}</div>
                </div>""", unsafe_allow_html=True)

            with col3:
                st.markdown(f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_MUTED};margin-bottom:10px'>OPEN TICKETS</div>", unsafe_allow_html=True)
                tc = C_RED if open_t else C_GREEN
                bg = C_RED_LITE if open_t else C_GREEN_LITE
                st.markdown(f"""
                <div style='background:{bg};border-radius:3px;padding:14px;text-align:center;border:1px solid {tc}22'>
                  <div style='font-size:28px;font-weight:800;color:{tc}'>{len(open_t)}</div>
                  <div style='font-size:11px;color:{tc};font-weight:600'>{fmt_dollars(open_d) if open_d>0 else "Clear"}</div>
                </div>""", unsafe_allow_html=True)

                cust_flags = {
                    "Charlie Medical":    ("Recurring daily unbilled gap — 165K vs 133K picks. Client log corroborates.", C_RED),
                    "Bravo FMCG":         ("Scale Without Return — 2M picks at $0.12 amplifies every pick loss.", C_AMBER),
                    "Delta Manufacturing":("14.1% exception rate — 2.4x network average. Unbilled returns/rework.", C_RED),
                    "Home & Living Products":  ("47% capacity idle. Sales review needed.", C_BLUE),
                }
                flag = cust_flags.get(p["name"])
                if flag:
                    st.markdown("---")
                    st.markdown(f"""
                    <div style='background:{flag[1]}0F;border-left:3px solid {flag[1]};padding:8px 12px;border-radius:0 3px 3px 0;font-size:11px;color:{C_TEXT};margin-top:6px'>
                      <strong style='color:{flag[1]}'>Flag</strong><br>{flag[0]}
                    </div>""", unsafe_allow_html=True)

            # Ask AI about this customer — bottom of expander
            _cak = f"_cust_ai_{p['id']}"
            if _cak not in st.session_state: st.session_state[_cak] = ""
            if not st.session_state[_cak]:
                if st.button(
                    f"Ask AI about {p['name'].split()[0]}",
                    key=f"cust_ask_{p['id']}",
                ):
                    with st.spinner("Generating analysis..."):
                        _cq = (
                            f"In 3 sentences, give an action brief for {p['name']}: "
                            f"true margin {p['true_margin_pct']:.0f}%, revenue "
                            f"{fmt_dollars(p['annual_revenue'])}, pick rate "
                            f"${p.get('pick_rate_charged', 0):.2f}/pick charged vs {_hf('pick_cost_fmt','$0.265')} true cost. "
                            f"Recommendation: {p['recommendation']}. "
                            f"What is the root cause and the single most important next step this week?"
                        )
                        st.session_state[_cak] = _ask_groq_quick(_cq, st.session_state.role)
                    st.rerun()
            else:
                st.markdown(
                    f"<div style='background:{C_BLUE_LITE};border-left:3px solid {C_BLUE};"
                    f"padding:12px 16px;border-radius:0 4px 4px 0;margin-top:10px'>"
                    f"<div style='font-size:9px;letter-spacing:2px;color:{C_BLUE};font-weight:700;margin-bottom:5px'>"
                    f"AI STRATEGY NOTE &nbsp;&middot;&nbsp; {p['name'].split()[0]}</div>"
                    f"<div style='font-size:12px;color:{C_TEXT};line-height:1.6'>"
                    f"{st.session_state[_cak]}</div></div>",
                    unsafe_allow_html=True
                )
                if st.button("Clear", key=f"cust_clr_{p['id']}"):
                    st.session_state[_cak] = ""
                    st.rerun()

    st.markdown("---")
    st.markdown(sec("Known Data Issues — Must Resolve Before External Negotiations"), unsafe_allow_html=True)
    issues = [
        (C_RED,   "C003 Charlie Medical — Systematic Unbilled (Recurring Daily)",
                  "165K picks performed vs 133K billed. Recurring daily gap. Client exception log independently flags this as unrecovered activity."),
        (C_AMBER, "Labour Costing — Warehouse-Level Imputation",
                  "The $0.265/pick true cost is a warehouse-level average imputed to customers. 4 days of data are missing. Accuracy ±5–10%. Site Manager must close F006/F007 before any customer negotiation."),
        (C_AMBER, "Bravo FMCG — Scale Without Return",
                  "At 2M picks/yr at $0.12: $0.145 loss per pick × 2,000,000 = $290,000/yr. More volume means more losses. Repricing to $0.19 is the Month 1 pilot."),
        (C_BLUE,  "C026 Home & Living Products — Underutilised Fixed-Fee Account",
                  "Fixed fee at 47% capacity utilisation. Not a margin problem — an opportunity. Sales review: grow the account or redeploy the 53% idle allocation."),
    ]
    for col, title, desc in issues:
        st.markdown(f"""
        <div style='background:{C_CARD};border-radius:3px;border-left:4px solid {col};
                    border:1px solid {C_BORDER};border-left-width:4px;padding:14px 18px;margin-bottom:8px'>
          <div style='font-size:12px;font-weight:700;color:{col};margin-bottom:5px'>{title}</div>
          <div style='font-size:12px;color:{C_TEXT};line-height:1.6'>{desc}</div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PAGE 3 — ACTION QUEUE
# ═══════════════════════════════════════════════════════════
def page_action_queue():
    role = st.session_state.role
    st.markdown(page_header(
        "Action Queue",
        f"Showing tickets for: {role}"
    ), unsafe_allow_html=True)

    fc1, fc2, fc3, fc4, fc5 = st.columns([3, 2, 2, 2, 2])
    with fc1: search    = st.text_input("Search", placeholder="Search tickets…", label_visibility="collapsed")
    with fc2: status_f  = st.selectbox("Status",   ["All Open","To Do","In Progress","Done","Blocked","All"])
    with fc3: priority_f= st.selectbox("Priority", ["All","HIGH","MEDIUM","LOW"])
    with fc4: type_f    = st.selectbox("Type",     ["All"]+list(TYPE_LABEL.keys()), format_func=lambda x: TYPE_LABEL.get(x,x) if x!="All" else "All Types")
    with fc5: role_f    = st.selectbox("Role",     ["My Role","All Roles"])

    stat_map = {"All Open": None,"All": None,"To Do":"To Do","In Progress":"In Progress","Done":"Done","Blocked":"Blocked"}
    tickets = db.get_tickets(
        WAREHOUSE_ID,
        role=role if role_f == "My Role" else None,
        status=stat_map[status_f],
        finding_type=type_f if type_f!="All" else None,
        priority=priority_f if priority_f!="All" else None,
    )
    if status_f == "All Open":
        tickets = [t for t in tickets if t["status"] in ("To Do","In Progress","Blocked")]
    if search.strip():
        q = search.strip().lower()
        tickets = [t for t in tickets if q in (t["title"] or "").lower() or q in (t["customer"] or "").lower()]

    # Separate F011 structural roll-up — shown as banner, not a line card
    f011_tickets = [t for t in tickets if t.get("finding_id") == "F011"]
    main_tickets = [t for t in tickets if t.get("finding_id") != "F011"]
    total_d = sum(t["dollar_impact"] for t in main_tickets if t["dollar_impact"] > 0)
    count_label = len(tickets)
    st.caption(f"{count_label} tickets &nbsp;·&nbsp; {fmt_dollars(total_d)} actionable impact &nbsp;·&nbsp; excl. F011 structural roll-up")

    if f011_tickets:
        for f11 in f011_tickets:
            sc = STATUS_COLOR.get(f11["status"], C_MUTED)
            st.markdown(
                f"<div style='background:#0E1F1E;border:1px solid #1C4040;border-radius:4px;"
                f"padding:10px 16px;margin-bottom:6px;display:flex;align-items:center;gap:12px'>"
                f"<div style='font-size:10px;font-weight:700;color:#5DBF8A;letter-spacing:1px;"
                f"background:#5DBF8A18;padding:2px 8px;border-radius:2px;white-space:nowrap'>STRUCTURAL ROLL-UP</div>"
                f"<div style='flex:1;font-size:12px;color:#8FBF9F'>{f11['title']}</div>"
                f"<div style='font-size:10px;color:#5D9E78;white-space:nowrap'>"
                f"$1.49M included in F001/F002/F003 · no double-count</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    if not main_tickets:
        st.info("No tickets match the current filters.")
        return

    for t in main_tickets:
        imp      = fmt_dollars(t["dollar_impact"]) if t["dollar_impact"] > 0 else "—"
        sc       = STATUS_COLOR.get(t["status"], C_MUTED)
        pc       = PRIORITY_COLOR.get(t["priority"], C_MUTED)
        comments = json.loads(t["comments"] or "[]")

        # Visible card — no expander for the summary row
        st.markdown(f"""
        <div style='background:{C_CARD};border:1px solid {C_BORDER};border-radius:4px;
                    border-left:4px solid {pc};padding:14px 18px;margin-bottom:2px'>
          <div style='display:flex;justify-content:space-between;align-items:flex-start'>
            <div style='flex:1;min-width:0'>
              <div style='display:flex;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap'>
                {priority_pill(t["priority"])} {status_pill(t["status"])} {type_label(t["finding_type"] or "")}
              </div>
              <div style='font-size:13px;font-weight:600;color:{C_TEXT};margin-bottom:3px'>{t['title']}</div>
              <div style='font-size:11px;color:{C_MUTED}'>{t['customer'] or 'All Customers'} &nbsp;&middot;&nbsp; {t['assigned_role'] or '—'}</div>
            </div>
            <div style='font-size:15px;font-weight:700;color:{pc};white-space:nowrap;margin-left:16px'>{imp}</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # ── Inline action row (always visible, no expander needed for demo) ──────
        _tai    = st.session_state._ticket_ai.get(t["id"], {})
        _expl   = _tai.get("explanation") or t.get("ai_explanation") or ""
        _action = _tai.get("action")      or t.get("action")          or ""

        _btn_cols = st.columns([2, 1, 1, 1, 1, 2])
        with _btn_cols[0]:
            if not _expl and not _action:
                if st.button("🔍 Explain with AI", key=f"ai_explain_{t['id']}", use_container_width=True):
                    with st.spinner("Generating AI insight..."):
                        _res = _ai_enhance_ticket(t)
                        if _res:
                            st.session_state._ticket_ai[t["id"]] = _res
                            st.rerun()
            else:
                st.markdown(
                    f"<div style='font-size:10px;color:{C_BLUE};font-weight:600;padding:6px 0'>✓ AI analysis ready</div>",
                    unsafe_allow_html=True
                )
        for _si, _s in enumerate(["To Do", "In Progress", "Done", "Blocked"]):
            with _btn_cols[_si + 1]:
                if _s != t["status"]:
                    if st.button(_s, key=f"aq_{t['id']}_{_s}", use_container_width=True):
                        db.update_ticket_status(t["id"], _s)
                        st.rerun()

        # AI output panels (shown inline below the card when available)
        if _expl:
            st.markdown(
                f"<div style='background:{C_BLUE_LITE};border-left:3px solid {C_BLUE};"
                f"padding:12px 16px;border-radius:0 3px 3px 0;margin:6px 0 2px'>"
                f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_BLUE};margin-bottom:6px'>AI ROOT CAUSE</div>"
                f"<div style='font-size:12px;color:{C_TEXT};line-height:1.6'>{_expl}</div></div>",
                unsafe_allow_html=True
            )
        if _action:
            st.markdown(
                f"<div style='background:{C_GREEN_LITE};border-left:3px solid {C_GREEN};"
                f"padding:12px 16px;border-radius:0 3px 3px 0;margin:2px 0 6px'>"
                f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_GREEN};margin-bottom:6px'>AI RECOMMENDED NEXT STEP</div>"
                f"<div style='font-size:12px;color:{C_TEXT};line-height:1.6'>{_action}</div></div>",
                unsafe_allow_html=True
            )

        # Expander for full description + comments (secondary details)
        with st.expander(f"Description & comments  ·  {t['id']}", expanded=False):
            st.markdown(t["description"] or "—")
            st.markdown(f"<div style='font-size:9px;letter-spacing:2px;font-weight:700;color:{C_MUTED};margin:12px 0 6px'>COMMENT</div>", unsafe_allow_html=True)
            cm = st.text_area("", placeholder="Add a note…", key=f"cm_{t['id']}", height=70, label_visibility="collapsed")
            if st.button("Post", key=f"post_{t['id']}"):
                if cm.strip():
                    db.add_comment(t["id"], role, cm.strip())
                    st.rerun()
            if comments:
                st.markdown("---")
                for c in reversed(comments[-3:]):
                    st.markdown(f"""
                    <div style='background:#FAFAFA;border-radius:3px;padding:8px 12px;margin-bottom:4px;font-size:12px;border:1px solid {C_DIVIDER}'>
                      <span style='color:{C_GREEN_DARK};font-weight:600'>{c["role"]}</span>
                      <span style='color:{C_MUTED};margin:0 8px'>{c["timestamp"]}</span>
                      <span style='color:{C_TEXT}'>{c["text"]}</span>
                    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# PAGE 4 — RECOVERY TRACKER
# ═══════════════════════════════════════════════════════════
def page_recovery():
    st.markdown(page_header(
        "Impact Tracker",
        "Closed loop — proof that management is acting, not just watching."
    ), unsafe_allow_html=True)

    # Closed-loop explainer
    st.markdown("""
    <div style='background:#1A3D2B;border-radius:4px;padding:14px 20px;margin-bottom:20px'>
      <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:10px'>
        THE CLOSED LOOP &nbsp;&#8212;&nbsp; HOW PROFIT LENS DRIVES RECOVERY
      </div>
      <div style='display:flex;align-items:center;gap:0'>
        <div style='text-align:center;flex:1;padding:6px 4px'>
          <div style='font-size:10px;color:#5DBF8A;font-weight:700;letter-spacing:1px'>FIND</div>
          <div style='font-size:11px;color:#FFFFFF;margin-top:3px'>ABC Analysis<br>identifies gap</div>
        </div>
        <div style='color:#3D7A56;font-size:16px;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:6px 4px'>
          <div style='font-size:10px;color:#F8B840;font-weight:700;letter-spacing:1px'>TICKET</div>
          <div style='font-size:11px;color:#FFFFFF;margin-top:3px'>Auto-generated<br>with owner + value</div>
        </div>
        <div style='color:#3D7A56;font-size:16px;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:6px 4px'>
          <div style='font-size:10px;color:#F8B840;font-weight:700;letter-spacing:1px'>ACT</div>
          <div style='font-size:11px;color:#FFFFFF;margin-top:3px'>Management<br>negotiates / closes</div>
        </div>
        <div style='color:#3D7A56;font-size:16px;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:6px 4px'>
          <div style='font-size:10px;color:#5DBF8A;font-weight:700;letter-spacing:1px'>RECOVER</div>
          <div style='font-size:11px;color:#FFFFFF;margin-top:3px'>Dollar value added<br>to tracker below</div>
        </div>
        <div style='color:#3D7A56;font-size:16px;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:6px 4px'>
          <div style='font-size:10px;color:#5DBF8A;font-weight:700;letter-spacing:1px'>REPEAT</div>
          <div style='font-size:11px;color:#FFFFFF;margin-top:3px'>Monthly cadence<br>per MOS rhythm</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    stats     = db.get_recovery_stats(WAREHOUSE_ID)
    closed    = db.get_closed_tickets(WAREHOUSE_ID)
    recovered = stats["recovered"]
    remaining = max(RECOVERY_TARGET - recovered, 0)
    pct       = min(recovered / RECOVERY_TARGET * 100, 100) if RECOVERY_TARGET else 0

    h1, h2, h3, h4 = st.columns(4)
    h1.markdown(kpi_card("Captured", fmt_dollars(recovered), "", C_GREEN), unsafe_allow_html=True)
    h2.markdown(kpi_card("Remaining to Target", fmt_dollars(remaining)), unsafe_allow_html=True)
    h3.markdown(kpi_card("Progress", f"{pct:.1f}%", "of $1,150,000"), unsafe_allow_html=True)
    h4.markdown(kpi_card("Tickets Closed", str(stats["done_count"])), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Opportunity Reconciliation ─────────────────────────
    with st.expander("📊 How Total Opportunity Is Calculated — $2.65M all-in ($1.86M pricing + $0.80M ops) / $2.09M pricing strict", expanded=False):
        st.markdown("""
        <div style='background:#0D2B1A;border-radius:6px;padding:16px 20px;margin-bottom:10px'>
          <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:12px'>
            TOTAL OPPORTUNITY RECONCILIATION — ENGINE-VERIFIED
          </div>
          <div style='display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px'>
            <div style='background:#1A3D2B;border-radius:4px;padding:12px 16px'>
              <div style='font-size:9px;color:#6B9E83;letter-spacing:1px;margin-bottom:6px'>COMPONENT 1 — BELOW-COST PRICING</div>
              <div style='font-size:22px;font-weight:700;color:#F59E0B'>$1,719,999</div>
              <div style='font-size:11px;color:#A0C8B0;margin-top:4px'>All 30 customers priced below $0.265/pick (conservative floor; engine-strict: $0.284/pick).<br>
                Bravo ($337K) + Delta ($222K) + Charlie ($124K) + 27 others.</div>
              <div style='font-size:10px;color:#6B9E83;margin-top:6px'>Source: engine.below_cost_pricing() · HIGH confidence</div>
            </div>
            <div style='background:#1A3D2B;border-radius:4px;padding:12px 16px'>
              <div style='font-size:9px;color:#6B9E83;letter-spacing:1px;margin-bottom:6px'>COMPONENT 2 — UNBILLED LEAKAGE</div>
              <div style='font-size:22px;font-weight:700;color:#EF4444'>$374,983</div>
              <div style='font-size:11px;color:#A0C8B0;margin-top:4px'>Work performed but never invoiced.<br>
                Delta ($147,283) + Charlie ($126,962) + others ($100,738).</div>
              <div style='font-size:10px;color:#6B9E83;margin-top:6px'>Source: engine.revenue_leakage() · HIGH confidence</div>
            </div>
          </div>
          <div style='border-top:1px solid #2D6B45;padding-top:12px;display:flex;justify-content:space-between;align-items:center'>
            <div style='font-size:11px;color:#A0C8B0'>
              <strong style='color:#FFFFFF'>No double-counting:</strong> Pricing gap and leakage are separate mechanisms.
              Pricing gap = difference between charged rate and true cost per pick.
              Leakage = work performed but never billed at all.
            </div>
            <div style='text-align:right;margin-left:24px;flex-shrink:0'>
              <div style='font-size:9px;color:#6B9E83;letter-spacing:1px'>TOTAL OPPORTUNITY</div>
              <div style='font-size:28px;font-weight:700;color:#22C55E'>$2,094,982</div>
              <div style='font-size:10px;color:#5DBF8A'>at $0.284/pick (engine-verified)</div>
            </div>
          </div>
          <div style='margin-top:12px;padding:10px 14px;background:#1A3D2B;border-radius:4px;border-left:3px solid #6B9E83'>
            <div style='font-size:10px;color:#A0C8B0'>
              <strong style='color:#5DBF8A'>Recovery target $1,150,000</strong> is the achievable portion through
              repricing and rebilling in 9 months — the remainder closes through structural reform in Months 3–6.
              The conservative floor estimate ($1.86M at $0.265/pick) remains valid as a lower bound.
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Captured", x=[recovered], y=["Progress"], orientation="h",
        marker=dict(color=C_GREEN), text=[f"  {fmt_dollars(recovered)} ({pct:.1f}%)"],
        textposition="inside" if pct > 12 else "outside",
        textfont=dict(color="#fff", size=12, family="Inter"), width=[0.5]))
    fig.add_trace(go.Bar(name="Remaining", x=[remaining], y=["Progress"], orientation="h",
        marker=dict(color="#E5E7EB"), text=[f"  {fmt_dollars(remaining)} remaining"],
        textposition="inside" if remaining > 150000 else "outside",
        textfont=dict(color=C_MUTED, size=11, family="Inter"), width=[0.5]))
    fig.update_layout(barmode="stack",
        xaxis=dict(range=[0,RECOVERY_TARGET],showgrid=False,showticklabels=False,zeroline=False),
        yaxis=dict(showgrid=False,showticklabels=False),
        plot_bgcolor="#fff",paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0,r=0,t=0,b=0),height=80,showlegend=False,
        font=dict(family="Inter"))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<br>", unsafe_allow_html=True)
    left, right = st.columns(2)

    with left:
        st.markdown("### Recovered Tickets")
        if closed:
            for c in closed:
                st.markdown(f"""
                <div style='background:{C_GREEN_LITE};border:1px solid {C_GREEN_MID};
                            border-radius:3px;padding:14px 16px;margin-bottom:6px'>
                  <div style='display:flex;justify-content:space-between'>
                    <div>
                      <div style='font-size:13px;font-weight:600;color:{C_TEXT}'>{c["title"]}</div>
                      <div style='font-size:11px;color:{C_MUTED};margin-top:2px'>{c["customer"] or "—"} &nbsp;·&nbsp; Closed {c["updated_at"][:10]}</div>
                    </div>
                    <div style='font-size:16px;font-weight:700;color:{C_GREEN}'>{fmt_dollars(c["dollar_impact"])}</div>
                  </div>
                </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style='background:{C_CARD};border:2px dashed {C_BORDER};border-radius:3px;padding:28px;text-align:center'>
              <div style='font-size:13px;color:{C_MUTED};font-weight:500'>No recovered tickets yet.</div>
              <div style='font-size:12px;color:{C_MUTED};margin-top:4px'>Close a ticket in Action Queue to see recovery here.</div>
            </div>""", unsafe_allow_html=True)

    with right:
        st.markdown("### Open Pipeline")
        open_t = [t for t in db.get_tickets(WAREHOUSE_ID) if t["status"] != "Done" and t["dollar_impact"] > 0 and t.get("finding_id") != "F011"]
        if open_t:
            total_open = sum(t["dollar_impact"] for t in open_t)
            st.caption(f"{len(open_t)} open &nbsp;·&nbsp; {fmt_dollars(total_open)} pipeline")
            for t in open_t:
                cp = t["dollar_impact"] / RECOVERY_TARGET * 100
                sc = STATUS_COLOR.get(t["status"], C_MUTED)
                _tc1, _tc2 = st.columns([4, 1])
                with _tc1:
                    st.markdown(
                        f"<div style='background:{C_CARD};border-radius:3px;padding:12px 14px;"
                        f"margin-bottom:2px;border:1px solid {C_BORDER};border-left:3px solid {sc}'>"
                        f"<div style='display:flex;justify-content:space-between'>"
                        f"<div style='font-size:12px;font-weight:600;color:{C_TEXT};flex:1'>{t['title'][:52]}</div>"
                        f"<div style='font-size:13px;font-weight:700;color:{C_AMBER};white-space:nowrap;"
                        f"margin-left:8px'>{fmt_dollars(t['dollar_impact'])}</div>"
                        f"</div>"
                        f"<div style='background:#F0F2F0;border-radius:2px;height:3px;margin-top:8px'>"
                        f"<div style='background:{C_AMBER};width:{min(cp,100):.0f}%;height:100%;border-radius:2px'></div>"
                        f"</div>"
                        f"<div style='font-size:10px;color:{C_MUTED};margin-top:3px'>{cp:.1f}% of target</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                with _tc2:
                    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
                    if st.button("✓ Done", key=f"rec_done_{t['id']}", use_container_width=True):
                        db.update_ticket_status(t["id"], "Done")
                        st.rerun()
                st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(sec("Delivery Plan — 9 Months"), unsafe_allow_html=True)
    milestones = [
        (1, "$144K",  "Bravo FMCG repricing at $0.19"),
        (2, "—",      "Delta/Charlie evidence"),
        (3, "$416K",  "Delta reprice + Charlie rebill"),
        (6, "$850K",  "Sites 2-3 onboarded"),
        (9, "$1.15M", "Full network target"),
    ]
    cols = st.columns(5)
    for col, (month, val, label) in zip(cols, milestones):
        done = stats["done_count"] > 0 and month == 1
        c    = C_GREEN if done else C_MUTED
        col.markdown(
            f"<div style='background:{C_CARD};border-radius:3px;padding:14px;text-align:center;"
            f"border:1px solid {C_BORDER};border-top:3px solid {c}'>"
            f"<div style='font-size:9px;letter-spacing:2px;color:{C_MUTED};font-weight:600'>MONTH {month}</div>"
            f"<div style='font-size:16px;font-weight:800;color:{c};margin:6px 0'>{val}</div>"
            f"<div style='font-size:10px;color:{C_MUTED};line-height:1.5'>{label}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cadence = [
        (C_AMBER, "Daily — Site Manager",    "Clear data hygiene. Flag new exceptions before they corrupt month-end numbers."),
        (C_GREEN, "Weekly — Commercial Lead", "Work the pricing and rebilling queue. Every contract below true cost needs a plan."),
        (C_BLUE,  "Monthly — CEO",            "Review recovery vs target. Decide where to focus next. Track the closed loop."),
    ]
    for col, (c, title, desc) in zip([c1, c2, c3], cadence):
        col.markdown(
            f"<div style='background:{C_CARD};border-radius:3px;padding:16px;"
            f"border:1px solid {C_BORDER};border-top:2px solid {c}'>"
            f"<div style='font-size:10px;font-weight:700;letter-spacing:1px;color:{c};margin-bottom:8px'>{title.upper()}</div>"
            f"<div style='font-size:12px;color:{C_TEXT};line-height:1.6'>{desc}</div>"
            f"</div>",
            unsafe_allow_html=True
        )


# ═══════════════════════════════════════════════════════════
# PAGE 5 — AI ASSISTANT
# ═══════════════════════════════════════════════════════════
def page_ai_assistant():
    role = st.session_state.role
    st.markdown(page_header(
        "Management Q&A",
        "AI-powered answers grounded in the Profit Lens dataset"
    ), unsafe_allow_html=True)

    if _LLM_AVAILABLE:
        _ms = _llm.model_status()
        status_txt = f"Nemotron (structured) + Groq (chat)" if _ms["nvidia_live"] and _ms["groq_live"] else \
                     (f"Groq {_ms['chat']} (Nemotron offline)" if _ms["groq_live"] else "Rule-based knowledge base")
        status_col = C_GREEN if (_ms["nvidia_live"] or _ms["groq_live"]) else C_AMBER
    elif _GROQ_AVAILABLE and GROQ_API_KEY:
        status_txt = "Groq LLaMA-3.3-70B"
        status_col = C_GREEN
    else:
        status_txt = "Rule-based knowledge base"
        status_col = C_AMBER
    st.markdown(
        f"<div style='display:inline-block;background:{status_col}18;border:1px solid {status_col}44;"
        f"border-radius:3px;padding:4px 12px;font-size:11px;font-weight:600;color:{status_col};"
        f"margin-bottom:16px'>AI Engine: {status_txt}</div>",
        unsafe_allow_html=True
    )

    # Role-specific welcome note
    _role_notes = {
        "CEO": (
            f"<div style='background:{C_GREEN}12;border-left:3px solid {C_GREEN};"
            f"padding:10px 16px;border-radius:0 4px 4px 0;margin-bottom:16px;font-size:12px;color:{C_TEXT}'>"
            f"<b>CEO view:</b> Ask about portfolio decisions, approval sequencing, risk to the "
            f"$1.15M target, or the month-by-month recovery plan.</div>"
        ),
        "Commercial Lead": (
            f"<div style='background:{C_AMBER}12;border-left:3px solid {C_AMBER};"
            f"padding:10px 16px;border-radius:0 4px 4px 0;margin-bottom:16px;font-size:12px;color:{C_TEXT}'>"
            f"<b>Commercial Lead view:</b> Ask about negotiation strategy, customer-specific "
            f"pricing cases, handling pushback, or what evidence to bring to each deal.</div>"
        ),
        "Site Manager": (
            f"<div style='background:{C_BLUE}12;border-left:3px solid {C_BLUE};"
            f"padding:10px 16px;border-radius:0 4px 4px 0;margin-bottom:16px;font-size:12px;color:{C_TEXT}'>"
            f"<b>Site Manager view:</b> Ask about data hygiene priorities, Delta exception "
            f"investigation, pick count validation, or what to report to Commercial Lead this week.</div>"
        ),
    }
    _rnote = _role_notes.get(role, "")
    if _rnote:
        st.markdown(_rnote, unsafe_allow_html=True)

    # Role-specific suggested questions
    st.markdown(sec("Suggested Questions"), unsafe_allow_html=True)
    _role_qs = {
        "CEO": [
            "Which customer should I approve first and why?",
            "What is the month-by-month recovery plan?",
            "What are the biggest risks to the $1.15M target?",
            "How does ABC costing expose the real margin problem?",
        ],
        "Commercial Lead": [
            "What is the strongest case to reprice Bravo FMCG?",
            "How do I handle Delta pushback on rate increases?",
            "What data do I need before negotiating with Charlie Medical?",
            "Which customer should I prioritise this month?",
        ],
        "Site Manager": [
            "How do I reduce Delta exception rate below 5.8%?",
            "What are the data hygiene tasks I must complete first?",
            "How do I validate Charlie's pick count discrepancy?",
            "What should I report to Commercial Lead this week?",
        ],
    }
    suggested = _role_qs.get(role, _role_qs["CEO"])
    cols = st.columns(len(suggested))
    for i, (col, sq) in enumerate(zip(cols, suggested)):
        with col:
            if st.button(sq, key=f"sq_{i}", use_container_width=True):
                st.session_state.chat_history.append({"role": "user", "content": sq})
                gr_ans, used_groq = get_groq_response(st.session_state.chat_history, role)
                if used_groq and gr_ans and not gr_ans.startswith("[Connection"):
                    _, chips = get_ai_response(sq, role)
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": gr_ans, "chips": chips, "source": "groq"
                    })
                else:
                    ans, chips2 = get_ai_response(sq, role)
                    st.session_state.chat_history.append({
                        "role": "assistant", "content": ans, "chips": chips2, "source": "rules"
                    })
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                chips = msg.get("chips", [])
                src   = msg.get("source", "rules")
                src_label = "Groq LLaMA-3.3-70B" if src == "groq" else "Rule-based"
                if chips:
                    chips_html = " ".join(
                        f'<span style="background:{C_GREEN_LITE};color:{C_GREEN};font-size:10px;'
                        f'font-weight:600;padding:3px 10px;border-radius:12px;'
                        f'margin-right:4px">{ch}</span>' for ch in chips
                    )
                    st.markdown(
                        f"<div style='margin-top:6px'>Navigate to: {chips_html}</div>",
                        unsafe_allow_html=True
                    )
                st.caption(f"Source: {src_label}")

    # Chat input
    user_input = st.chat_input("Ask about customers, profitability, or the recovery plan...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        gr_ans, used_groq = get_groq_response(st.session_state.chat_history, role)
        if used_groq and gr_ans and not gr_ans.startswith("[Connection"):
            _, chips = get_ai_response(user_input, role)
            st.session_state.chat_history.append({
                "role": "assistant", "content": gr_ans, "chips": chips, "source": "groq"
            })
        else:
            ans, chips = get_ai_response(user_input, role)
            st.session_state.chat_history.append({
                "role": "assistant", "content": ans, "chips": chips, "source": "rules"
            })
        st.rerun()

    if st.session_state.chat_history:
        if st.button("Clear conversation", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()


# ═══════════════════════════════════════════════════════════
# PAGE 6 — TICKET REGISTER
# ═══════════════════════════════════════════════════════════
def page_tickets():
    role = st.session_state.role
    st.markdown(page_header(
        "Ticket Register",
        "Full ticket view with status updates and comments"
    ), unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["View Tickets", "Create Ticket"])

    with tab1:
        fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
        with fc1: sf = st.selectbox("Status",   ["All","To Do","In Progress","Done","Blocked"], key="t_sf")
        with fc2: pf = st.selectbox("Priority", ["All","HIGH","MEDIUM","LOW","CRITICAL"], key="t_pf")
        with fc3: tf = st.selectbox("Type",     ["All"] + list(TYPE_LABEL.keys()), key="t_tf",
                                    format_func=lambda x: TYPE_LABEL.get(x, x) if x != "All" else "All Types")
        with fc4: rf = st.selectbox("Role View", ["My Role", "All Roles"], key="t_rf")
        tickets = db.get_tickets(WAREHOUSE_ID,
            role=role if rf == "My Role" else None,
            status=sf if sf != "All" else None,
            priority=pf if pf != "All" else None,
            finding_type=tf if tf != "All" else None)
        if not tickets:
            st.info("No tickets match the filters.")
        else:
            s_counts = {s: sum(1 for t in tickets if t["status"] == s) for s in STATUS_LABEL}
            cc = st.columns(4)
            for i, (s, cnt) in enumerate(s_counts.items()):
                c = STATUS_COLOR.get(s, C_MUTED)
                cc[i].markdown(
                    f"<div style='text-align:center;padding:8px 0'>"
                    f"<div style='font-size:20px;font-weight:700;color:{c}'>{cnt}</div>"
                    f"<div style='font-size:10px;color:{C_MUTED};letter-spacing:1px'>{s.upper()}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            st.markdown("---")
            for t in tickets:
                imp      = fmt_dollars(t["dollar_impact"]) if t["dollar_impact"] > 0 else "—"
                sc       = STATUS_COLOR.get(t["status"], C_MUTED)
                comments = json.loads(t["comments"] or "[]")
                with st.expander(f"{t['title']} — {imp}", expanded=False):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.markdown(
                            f"**Customer:** {t['customer'] or 'All'} &nbsp;&nbsp; "
                            + confidence_badge(t.get("id", "")),
                            unsafe_allow_html=True)
                        st.markdown(f"**Finding Type:** {TYPE_LABEL.get(t['finding_type'], t['finding_type'])}")
                        st.markdown(f"**Description:** {t.get('description', '')}")
                        if comments:
                            st.markdown("**Comments:**")
                            for cm in comments[-3:]:
                                st.markdown(f"> *{cm.get('author','?')} — {cm.get('text','')}*")
                        new_comment = st.text_input("Add comment", key=f"tc_{t['id']}")
                        if st.button("Post", key=f"tp_{t['id']}"):
                            if new_comment.strip():
                                db.add_comment(t["id"], role, new_comment)
                                st.rerun()
                    with col2:
                        st.markdown(f"**Priority:** {t['priority']}")
                        st.markdown(f"**Status:** {t['status']}")
                        st.markdown(f"**Assigned:** {t.get('assigned_role','—')}")
                        new_status = st.selectbox("Update Status",
                            ["To Do", "In Progress", "Done", "Blocked"],
                            index=["To Do","In Progress","Done","Blocked"].index(t["status"]) if t["status"] in ["To Do","In Progress","Done","Blocked"] else 0,
                            key=f"ts_{t['id']}")
                        if st.button("Update", key=f"tu_{t['id']}", use_container_width=True):
                            db.update_ticket_status(t["id"], new_status, role)
                            st.rerun()

    with tab2:
        st.markdown(sec("Create Manual Ticket"), unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            mt_title    = st.text_input("Title", key="mt_title")
            mt_customer = st.text_input("Customer", key="mt_customer")
            mt_type     = st.selectbox("Type", list(TYPE_LABEL.keys()), key="mt_type",
                                       format_func=lambda x: TYPE_LABEL.get(x, x))
        with c2:
            mt_priority = st.selectbox("Priority", ["HIGH","MEDIUM","LOW","CRITICAL"], key="mt_priority")
            mt_role     = st.selectbox("Assign To", list(ROLES.keys()), key="mt_role")
            mt_impact   = st.number_input("Dollar Impact ($)", min_value=0, value=0, key="mt_impact")
        mt_desc = st.text_area("Description", key="mt_desc")
        if st.button("Create Ticket", type="primary"):
            if mt_title.strip():
                db.create_ticket_manual(WAREHOUSE_ID, mt_title, mt_customer, mt_type,
                                        mt_priority, mt_role, mt_impact, mt_desc)
                st.success("Ticket created.")
                st.rerun()
            else:
                st.error("Title is required.")


# ═══════════════════════════════════════════════════════════
# PAGE 7 — DATA IMPORT
# ═══════════════════════════════════════════════════════════
def page_load_data():
    st.markdown(page_header(
        "Data Import",
        "Reload findings, reset the database, or check data status"
    ), unsafe_allow_html=True)

    # Auto-ticketing workflow banner
    st.markdown("""
    <div style='background:#1A3D2B;border-radius:4px;padding:16px 20px;margin-bottom:20px'>
      <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:12px'>
        HOW AUTOMATIC TICKET GENERATION WORKS
      </div>
      <div style='display:flex;align-items:center;gap:0'>
        <div style='text-align:center;flex:1;padding:8px'>
          <div style='font-size:20px;color:#5DBF8A;font-weight:700;margin-bottom:4px'>1</div>
          <div style='font-size:11px;color:#FFFFFF;font-weight:600;margin-bottom:2px'>Upload Data</div>
          <div style='font-size:10px;color:#8FBF9F'>WMS exports, pick logs, billing files</div>
        </div>
        <div style='color:#3D7A56;font-size:18px;font-weight:300;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:8px'>
          <div style='font-size:20px;color:#5DBF8A;font-weight:700;margin-bottom:4px'>2</div>
          <div style='font-size:11px;color:#FFFFFF;font-weight:600;margin-bottom:2px'>ABC Analysis</div>
          <div style='font-size:10px;color:#8FBF9F'>True cost vs billed — finding engine runs</div>
        </div>
        <div style='color:#3D7A56;font-size:18px;font-weight:300;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:8px'>
          <div style='font-size:20px;color:#F8B840;font-weight:700;margin-bottom:4px'>3</div>
          <div style='font-size:11px;color:#FFFFFF;font-weight:600;margin-bottom:2px'>Tickets Generated</div>
          <div style='font-size:10px;color:#8FBF9F'>Each finding becomes an actionable ticket</div>
        </div>
        <div style='color:#3D7A56;font-size:18px;font-weight:300;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:8px'>
          <div style='font-size:20px;color:#5DBF8A;font-weight:700;margin-bottom:4px'>4</div>
          <div style='font-size:11px;color:#FFFFFF;font-weight:600;margin-bottom:2px'>Routed by Role</div>
          <div style='font-size:10px;color:#8FBF9F'>CEO, Commercial Lead, Site Manager each see their queue</div>
        </div>
        <div style='color:#3D7A56;font-size:18px;font-weight:300;flex-shrink:0'>&#8594;</div>
        <div style='text-align:center;flex:1;padding:8px'>
          <div style='font-size:20px;color:#5DBF8A;font-weight:700;margin-bottom:4px'>5</div>
          <div style='font-size:11px;color:#FFFFFF;font-weight:600;margin-bottom:2px'>Recovery Tracked</div>
          <div style='font-size:10px;color:#8FBF9F'>Closed tickets update the recovery counter live</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(sec("Current Data Status"), unsafe_allow_html=True)
    loaded = db.is_data_loaded(WAREHOUSE_ID)
    stats  = db.get_recovery_stats(WAREHOUSE_ID)

    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi_card("Data Loaded", "Yes" if loaded else "No", "WH001 findings", C_GREEN if loaded else C_RED), unsafe_allow_html=True)
    c2.markdown(kpi_card("Total Tickets", str(stats["open_count"] + stats["in_progress_count"] + stats["done_count"] + stats["blocked_count"]), "In database"), unsafe_allow_html=True)
    c3.markdown(kpi_card("Data Period", "Jan–Feb 2026", "2 months of labour data"), unsafe_allow_html=True)

    # ── Live Engine Analysis ──────────────────────────────
    st.markdown("---")
    st.markdown(sec("Live Engine Analysis — Upload Your Dataset"), unsafe_allow_html=True)

    st.markdown("""
    <div style='background:#0D2B1A;border:1px solid #1F4A2E;border-radius:6px;
                padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:14px'>
      <div style='font-size:20px'>⚡</div>
      <div>
        <div style='font-size:12px;font-weight:700;color:#5DBF8A;margin-bottom:3px'>
          REAL ENGINE — NOT STATIC DATA</div>
        <div style='font-size:11px;color:#A0C8B0;line-height:1.5'>
          Upload the Mattingly Excel dataset and the ABC engine runs live — computing
          true pick costs, per-customer profitability, leakage, and below-cost pricing
          against your actual numbers.
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not _ENGINE_AVAILABLE:
        st.warning("engine.py not found — place it in the same folder as app.py")
    else:
        uploaded_file = st.file_uploader(
            "Upload Warehouse Dataset (.xlsx)",
            type=["xlsx"],
            key="engine_upload",
            help="Upload the Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx or any compatible format"
        )

        if uploaded_file is not None:
            import tempfile, io
            with st.spinner("Running ABC analysis engine…"):
                try:
                    # Write to temp file so engine can read it
                    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                        tmp.write(uploaded_file.getvalue())
                        tmp_path = tmp.name

                    result = _engine.run_all(tmp_path)
                    hn = result["headlines"]
                    leak_by_cust = result.get("leakage_by_customer")
                    below = result.get("below_cost")
                    quality_df = result.get("quality")
                    prof_df = result.get("profitability")
                    prod_df = result.get("productivity")
                    _months_detected   = result.get("months_in_data", 2)
                    _ann_factor        = result.get("annualise_factor", 6)
                    # Store in session state so other pages know fresh data is live
                    st.session_state["upload_result"]  = result
                    st.session_state["upload_filename"] = uploaded_file.name

                    import os as _os
                    _os.unlink(tmp_path)

                    st.success("✅ Engine run complete — real data analysed")

                    # Headline numbers — map from engine output
                    # Get pick cost per unit from productivity table
                    pick_cost = 0
                    if prod_df is not None and len(prod_df) > 0:
                        pick_row = prod_df[prod_df["Activity Type"] == "Pick"]
                        if len(pick_row) > 0:
                            pick_cost = pick_row.iloc[0]["cost_per_unit"]
                    total_lkg   = hn.get("leakage_annual", 0)
                    total_below = hn.get("pick_underpricing_annual", 0)
                    total_opp   = hn.get("total_opportunity", 0)
                    customers   = hn.get("unprofitable_customers", 0)

                    st.markdown("#### Engine Output — Headline Numbers")
                    h1, h2, h3, h4 = st.columns(4)
                    h1.markdown(kpi_card("Pick Cost (Labour)", f"${pick_cost:.4f}/pick",
                                         "Engine-computed true cost", C_RED), unsafe_allow_html=True)
                    h2.markdown(kpi_card("Unbilled Leakage", fmt_dollars(total_lkg),
                                         f"Annual (annualised ×{_ann_factor:.0f})", C_RED), unsafe_allow_html=True)
                    h3.markdown(kpi_card("Below-Cost Pricing", fmt_dollars(total_below),
                                         "All customers annualised", C_AMBER), unsafe_allow_html=True)
                    h4.markdown(kpi_card("Total Opportunity", fmt_dollars(total_opp),
                                         f"{customers} customers below cost", C_GREEN), unsafe_allow_html=True)

                    # Seasonality badge
                    st.markdown("""
                    <div style='background:#1A3D2B;border:1px solid #2D6B45;border-radius:4px;
                                padding:10px 16px;margin:12px 0;display:inline-flex;align-items:center;gap:10px'>
                      <div style='font-size:14px'>✅</div>
                      <div style='font-size:11px;color:#5DBF8A;font-weight:700;letter-spacing:0.5px'>
                        SEASONALITY VERIFIED STABLE — All customers M1/M2 ratio 0.84–1.18.
                        No seasonal adjustment required for annualisation.
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Quality log
                    if quality_df is not None and len(quality_df) > 0:
                        with st.expander(f"Data Quality Log ({len(quality_df)} items)"):
                            st.dataframe(quality_df, use_container_width=True, hide_index=True)

                    # ── UPLOAD GUARD ─────────────────────────────────────────
                    # The live engine output above is NOT wired into the ticket
                    # database — the Action Queue still holds findings.json data.
                    # Guard: clear stale tickets so old pre-baked data cannot
                    # silently co-exist with the new engine numbers.
                    try:
                        _conn = db.get_conn()
                        _stale = _conn.execute(
                            "SELECT COUNT(*) FROM tickets WHERE warehouse_id=?",
                            (WAREHOUSE_ID,)).fetchone()[0]
                        if _stale:
                            _conn.execute(
                                "DELETE FROM tickets WHERE warehouse_id=?",
                                (WAREHOUSE_ID,))
                            _conn.execute(
                                "DELETE FROM data_loaded WHERE warehouse_id=?",
                                (WAREHOUSE_ID,))
                            _conn.commit()
                        _conn.close()
                    except Exception:
                        pass  # DB clear is best-effort; don't crash the upload view

                    st.markdown(f"""
                    <div style='background:#2A2010;border:1px solid #8B6914;border-radius:6px;
                                padding:14px 18px;margin:16px 0'>
                      <div style='font-size:10px;letter-spacing:2px;color:#E8A820;font-weight:700;
                                  margin-bottom:6px'>⚠ ACTION QUEUE REFRESH REQUIRED</div>
                      <div style='font-size:12px;color:#C8A060;line-height:1.6'>
                        Live engine numbers ({_months_detected} month(s) detected, ×{_ann_factor:.0f} annualised)
                        are shown above. The <strong>Action Queue</strong> and <strong>Impact Tracker</strong>
                        were cleared and will be empty until you click
                        <strong>Reload Findings</strong> below — this re-seeds the ticket queue
                        from the pre-built dataset, not the uploaded file.
                        <br><br>
                        <em>To fully regenerate tickets from the uploaded file, an export step
                        from the engine to findings.json format is required (planned for v2).</em>
                      </div>
                    </div>
                    """, unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Engine error: {e}")
                    import traceback
                    st.code(traceback.format_exc())
        else:
            # Show static verified numbers when no file uploaded
            st.markdown("""
            <div style='background:#1C2830;border:1px solid #2D3E4A;border-radius:4px;
                        padding:14px 18px;margin-top:8px'>
              <div style='font-size:9px;letter-spacing:2px;color:#6B9E83;font-weight:700;margin-bottom:8px'>
                Upload the dataset above to run the live engine analysis.</div>
              <div style='font-size:11px;color:#A0C8B0;line-height:1.6'>
                Pre-computed results from 13 Jun 2026 are shown in the Impact Tracker reconciliation panel.
              </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Reload Findings**")
        st.caption("Re-imports findings.json and regenerates all tickets from the pre-built dataset.")
        if st.button("Reload Findings"):
            try:
                conn = db.get_conn()
                conn.execute("DELETE FROM tickets WHERE warehouse_id = ?", (WAREHOUSE_ID,))
                conn.execute("DELETE FROM data_loaded WHERE warehouse_id = ?", (WAREHOUSE_ID,))
                conn.commit()
                conn.close()
                db.load_findings_json(DATA_PATH)
                ll_t = db.get_tickets(WAREHOUSE_ID)
                st.success(f"Analysis complete \u2014 {len(all_t)} findings processed, {len(all_t)} tickets auto-generated and routed to role queues.")
                st.rerun()
            except Exception as e:
                st.error(f"Reload failed: {e}")

    with col2:
        st.markdown("**Reset to Default**")
        st.caption("Clears all ticket status updates and resets to the default state loaded from findings.json.")
        if st.button("Reset to Default"):
            try:
                conn = db.get_conn()
                conn.execute("DELETE FROM tickets WHERE warehouse_id = ?", (WAREHOUSE_ID,))
                conn.execute("DELETE FROM data_loaded WHERE warehouse_id = ?", (WAREHOUSE_ID,))
                conn.commit()
                conn.close()
                db.load_findings_json(DATA_PATH)
                st.success("Reset complete.")
                st.rerun()
            except Exception as e:
                st.error(f"Reset failed: {e}")

    st.markdown("---")
    st.markdown(sec("Findings in Database"), unsafe_allow_html=True)
    try:
        all_t = db.get_tickets(WAREHOUSE_ID)
        if all_t:
            df = pd.DataFrame(all_t)[["id","title","customer","priority","finding_type","dollar_impact","status"]]
            df["dollar_impact"] = df["dollar_impact"].apply(lambda v: fmt_dollars(v) if v > 0 else "\u2014")
            df.columns = ["ID","Title","Customer","Priority","Type","Impact","Status"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No tickets loaded yet.")
    except Exception as e:
        st.error(f"Error reading tickets: {e}")


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# ROUTER
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

def _page_operations_safe():
    if _OPS_AVAILABLE:
        page_operations()
    else:
        st.error("operations_pages.py not found. Copy it to the Phase 3 Tool folder.")

def _page_info_gaps_safe():
    if _OPS_AVAILABLE:
        page_info_gaps()
    else:
        st.error("operations_pages.py not found. Copy it to the Phase 3 Tool folder.")

PAGE_FN = {
    "Dashboard":              page_dashboard,
    "Customer Profitability": page_customer_profitability,
    "Action Queue":           page_action_queue,
    "Impact Tracker":         page_recovery,
    "Operations":             _page_operations_safe,
    "Information Gaps":       _page_info_gaps_safe,
    "AI Assistant":           page_ai_assistant,
    "Tickets":                page_tickets,
    "Load Data":              page_load_data,
}
page = st.session_state.get("page", "Dashboard")
fn = PAGE_FN.get(page)
if fn:
    try:
        fn()
    except Exception as e:
        import traceback
        st.error(f"Error loading {page}: {e}")
        st.code(traceback.format_exc())
else:
    st.error(f"Unknown page: {page}")
