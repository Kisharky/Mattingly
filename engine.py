"""
Profit Lens - Analysis Engine
Mattingly AI & Operations Hackathon 2026 | Kishan Gowda

Pipeline:  INGEST -> CLEAN & VALIDATE -> COST ENGINE -> INTELLIGENCE
Everything downstream (dashboards, AI layer) reads from the objects this
module produces.
"""

import re
import pandas as pd
import numpy as np

VALID_ACTIVITIES = ["Storage", "Receipt", "Dispatch", "Pick",
                    "Returns", "Rework", "Urgent Order"]

# Default annualisation factor (2 months × 6 = 12 months).
# Overridden at runtime by run_all() from actual months_in_data.
ANNUALISE = 6

CONSERVATIVE_DAYS_HANDLING = True

# Operational exposure sourced from findings F014 + F015 — these represent
# inefficiency losses that are identified through qualitative assessment of the
# data, not purely engine-derivable from the labour/activity tables alone:
#   F014  Delta exception-handling labour drain   $446,000/yr
#   F015  Urgent-order throughput penalty          $349,000/yr
# This constant is the single named source so it never appears as a bare literal.
OPS_EXPOSURE_F014_F015 = 446_000 + 349_000   # $795,000

# ── Sheet keywords ────────────────────────────────────────────────────────────
# Each value is a priority-ordered list: earlier keyword = higher priority.
# When multiple sheets match the same canonical key the one whose FIRST
# matching keyword has the lowest index wins.
_SHEET_KEYWORDS = {
    "activities":      ["activit"],
    "labour":          ["labour", "labor"],
    "revenue":         ["revenue"],
    "exceptions":      ["exception"],
    # "customer pric" beats plain "pric" so Customer Pricing wins over Standard Pricing
    "pricing":         ["customer pric", "activity rate", "contract rate", "rate card", "pric"],
    "customer_master": ["customer master"],
    "cost_allocation": ["cost alloc"],
    "mgmt_allocation": ["management alloc", "mgmt alloc"],
}

_REQUIRED_MULTI  = {"activities", "labour"}
_REQUIRED_SINGLE = {"pricing", "customer_master", "cost_allocation", "mgmt_allocation"}


# ── 0. SHEET RESOLVER ────────────────────────────────────────────────────────
def _resolve_sheets(sheet_names):
    """
    Map workbook sheet names → canonical roles by priority-ordered keyword match.

    For multi-month keys (activities, labour, revenue, exceptions) returns a list
    sorted by the first integer in the sheet name (M1, M2, M3 …).
    For singleton keys returns a single sheet name.

    Raises ValueError naming every required sheet that could not be matched.
    """
    lower_to_orig = {n.lower(): n for n in sheet_names}

    # grouped: canon → list of (priority_index, orig_name)
    grouped = {k: [] for k in _SHEET_KEYWORDS}

    for lower_n, orig_n in lower_to_orig.items():
        for canon, kws in _SHEET_KEYWORDS.items():
            for i, kw in enumerate(kws):
                if kw in lower_n:
                    grouped[canon].append((i, orig_n))
                    break  # use first keyword match within this category

    def _month_key(name):
        m = re.search(r"(\d+)", name)
        return int(m.group(1)) if m else 0

    missing = []

    # Multi-month keys: sort by month number, keep all sheets
    for key in ("activities", "labour", "revenue", "exceptions"):
        names = [name for _, name in sorted(grouped[key], key=lambda x: _month_key(x[1]))]
        grouped[key] = names
        if key in _REQUIRED_MULTI and not names:
            grouped[key] = []
            missing.append(f"'{key}' (need a sheet whose name contains one of: "
                           f"{_SHEET_KEYWORDS[key]})")

    # Singleton keys: take the highest-priority (lowest index) match
    for key in _REQUIRED_SINGLE | (set(_SHEET_KEYWORDS) - _REQUIRED_MULTI - {"revenue", "exceptions"}):
        if key in ("revenue", "exceptions"):
            continue
        if grouped[key]:
            best = min(grouped[key], key=lambda x: x[0])[1]
            grouped[key] = best
        else:
            grouped[key] = None
            missing.append(f"'{key}' (need a sheet whose name contains one of: "
                           f"{_SHEET_KEYWORDS[key]})")

    if missing:
        raise ValueError(
            "Required sheet(s) not found in workbook:\n  • "
            + "\n  • ".join(missing)
            + f"\n\nSheets present: {', '.join(sheet_names)}"
        )

    months_in_data = max(len(grouped["activities"]), 1)
    return grouped, months_in_data


# ── 1. INGEST ────────────────────────────────────────────────────────────────
def load_workbook(path_or_buffer):
    """
    Load every sheet and resolve sheet roles.

    Returns
    -------
    sheets           : {sheet_name: DataFrame}
    mapping          : canonical role → sheet name(s)
    months_in_data   : int
    annualise_factor : float  (12 / months_in_data)
    """
    xl = pd.ExcelFile(path_or_buffer)
    sheets = {name: pd.read_excel(xl, sheet_name=name) for name in xl.sheet_names}
    mapping, months_in_data = _resolve_sheets(xl.sheet_names)
    annualise_factor = 12.0 / months_in_data
    return sheets, mapping, months_in_data, annualise_factor


# ── 2. CLEAN & VALIDATE ──────────────────────────────────────────────────────
def _require_cols(df, cols, sheet_label):
    """Raise a clear ValueError if any expected column is missing."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Sheet '{sheet_label}' is missing required column(s): "
            + ", ".join(f"'{c}'" for c in missing)
            + f"\n  Columns present: {', '.join(df.columns.tolist())}"
        )


def clean_data(sheets, mapping):
    """
    Repair the messy data and RECORD what we did.

    Parameters
    ----------
    sheets  : {sheet_name: DataFrame}
    mapping : canonical-role → sheet name(s)

    Returns (clean_dict, quality_log).
    """
    log = []

    # ── Activities ────────────────────────────────────────────────────────────
    act_frames = [sheets[n] for n in mapping["activities"]]
    acts = pd.concat(act_frames, ignore_index=True)
    _require_cols(acts, ["Activity Type", "Quantity"], "Activities")
    # Normalise Customer Id column name
    if "Customer ID" in acts.columns and "Customer Id" not in acts.columns:
        acts = acts.rename(columns={"Customer ID": "Customer Id"})

    acts["Quantity"] = pd.to_numeric(acts["Quantity"], errors="coerce")
    junk_act = acts[~acts["Activity Type"].isin(VALID_ACTIVITIES)]
    if len(junk_act):
        log.append(("Activities", f"{len(junk_act)} rows with an invalid activity type were removed"))
    missing_qty = acts["Quantity"].isna().sum()
    if missing_qty:
        log.append(("Activities", f"{missing_qty} rows had a missing quantity (excluded from volumes)"))
    dupe_flag = (acts.get("Data Quality Note") == "Possible duplicate").sum()
    if dupe_flag:
        log.append(("Activities", f"{dupe_flag} rows flagged 'Possible duplicate' by the source system"))
    acts = acts[acts["Activity Type"].isin(VALID_ACTIVITIES)].copy()
    acts = acts.dropna(subset=["Quantity"])

    # ── Labour ────────────────────────────────────────────────────────────────
    lab_frames = []
    for sheet_name in mapping["labour"]:
        df = sheets[sheet_name].copy()
        _require_cols(df, ["Activity Type", "Units Processed", "Labour Hours",
                            "Labour Cost"], sheet_name)
        junk = df[~df["Activity Type"].isin(VALID_ACTIVITIES)]
        if len(junk):
            log.append((sheet_name,
                        f"{len(junk)} corrupted rows (customer IDs in activity column) removed"))
        df = df[df["Activity Type"].isin(VALID_ACTIVITIES)].copy()
        for col in ["Units Processed", "Labour Hours", "Labour Cost"]:
            bad = pd.to_numeric(df[col], errors="coerce").isna() & df[col].notna()
            if bad.sum():
                log.append((sheet_name, f"{bad.sum()} non-numeric values in '{col}' coerced"))
            df[col] = pd.to_numeric(df[col], errors="coerce")
        d0 = len(df)
        df = df.drop_duplicates(subset=["Date", "Activity Type"], keep="first")
        if d0 - len(df):
            log.append((sheet_name, f"{d0 - len(df)} duplicate date/activity rows removed"))
        df = df.dropna(subset=["Labour Cost", "Units Processed"])
        lab_frames.append(df)
    labour = pd.concat(lab_frames, ignore_index=True)

    # ── Revenue ───────────────────────────────────────────────────────────────
    if mapping["revenue"]:
        rev = pd.concat([sheets[n] for n in mapping["revenue"]], ignore_index=True)
    else:
        log.append(("Revenue", "No revenue sheets found — revenue will be zero"))
        rev = pd.DataFrame(columns=["Customer Id", "Revenue", "Charged Quantity", "Charge Type"])
    rev["Revenue"] = pd.to_numeric(rev.get("Revenue", 0), errors="coerce").fillna(0)
    if "Charged Quantity" in rev.columns:
        rev["Charged Quantity"] = pd.to_numeric(rev["Charged Quantity"], errors="coerce").fillna(0)

    # ── Pricing ───────────────────────────────────────────────────────────────
    pricing = sheets[mapping["pricing"]].copy()
    _require_cols(pricing, ["Customer Id", "Activity Type", "Contract Rate"],
                  mapping["pricing"])
    pricing["Contract Rate"] = pd.to_numeric(pricing["Contract Rate"], errors="coerce")
    no_rate = pricing[pricing["Contract Rate"].isna()]
    if len(no_rate):
        custs = ", ".join(sorted(no_rate["Customer Id"].astype(str).unique()))
        log.append(("Customer Pricing",
                    f"{len(no_rate)} price points missing a contract rate ({custs})"))

    # ── Exceptions ────────────────────────────────────────────────────────────
    if mapping["exceptions"]:
        exc = pd.concat([sheets[n] for n in mapping["exceptions"]], ignore_index=True)
        if "Count" in exc.columns:
            exc["Count"] = pd.to_numeric(exc["Count"], errors="coerce").fillna(0)
    else:
        log.append(("Exceptions", "No exceptions sheets found — exceptions will be empty"))
        exc = pd.DataFrame(columns=["Customer Id", "Exception Type", "Count"])

    # ── Singleton sheets ──────────────────────────────────────────────────────
    customer_master = sheets[mapping["customer_master"]].copy()
    cost_allocation = sheets[mapping["cost_allocation"]].copy()
    mgmt_allocation = sheets[mapping["mgmt_allocation"]].copy()

    clean = {
        "activities":      acts,
        "labour":          labour,
        "revenue":         rev,
        "pricing":         pricing,
        "exceptions":      exc,
        "customer_master": customer_master,
        "cost_allocation": cost_allocation,
        "mgmt_allocation": mgmt_allocation,
    }
    quality = pd.DataFrame(log, columns=["Sheet", "Issue handled"])
    return clean, quality


# ── 3. COST ENGINE ───────────────────────────────────────────────────────────
def activity_unit_costs(clean):
    """
    True labour cost per unit of each activity.

    cost_per_unit        — canonical (conservative when CONSERVATIVE_DAYS_HANDLING=True)
    cost_per_unit_strict — strict figure (labour-sheet units only)
    """
    lab = clean["labour"]
    grp = lab.groupby("Activity Type").agg(
        units=("Units Processed", "sum"),
        hours=("Labour Hours", "sum"),
        cost=("Labour Cost", "sum"),
    )
    grp["cost_per_unit_strict"] = grp["cost"] / grp["units"]

    act_units = clean["activities"].groupby("Activity Type")["Quantity"].sum()
    conservative_denom = act_units.reindex(grp.index).fillna(grp["units"])
    grp["cost_per_unit_conservative"] = grp["cost"] / conservative_denom

    grp["cost_per_unit"] = (
        grp["cost_per_unit_conservative"] if CONSERVATIVE_DAYS_HANDLING
        else grp["cost_per_unit_strict"]
    )
    return grp


def customer_activity_matrix(clean):
    a = clean["activities"]
    return (a.groupby(["Customer Id", "Activity Type"])["Quantity"]
            .sum().unstack(fill_value=0))


def build_profitability(clean):
    cpu = activity_unit_costs(clean)["cost_per_unit"]
    cust_act = customer_activity_matrix(clean)

    labour_cost = (cust_act * cpu.reindex(cust_act.columns)).sum(axis=1)

    ca = clean["cost_allocation"]
    overhead_total = ca["Monthly Cost"].sum()
    rent_equip = ca[ca["Cost Category"].isin(["Rent", "Equipment"])]["Monthly Cost"].sum()
    other_oh = overhead_total - rent_equip
    storage = cust_act.get("Storage", pd.Series(0, index=cust_act.index))
    storage_share = storage / storage.sum() if storage.sum() else 0
    labour_share = labour_cost / labour_cost.sum() if labour_cost.sum() else 0
    overhead = storage_share * rent_equip + labour_share * other_oh

    revenue = clean["revenue"].groupby("Customer Id")["Revenue"].sum()
    mgmt = clean["mgmt_allocation"].groupby("Customer Id")["Management Allocated Cost"].sum()

    df = pd.DataFrame({
        "revenue":     revenue,
        "labour_cost": labour_cost,
        "overhead":    overhead,
    }).fillna(0)
    df["total_cost"] = df["labour_cost"] + df["overhead"]
    df["profit"]     = df["revenue"] - df["total_cost"]
    df["margin_pct"] = np.where(df["revenue"] > 0,
                                df["profit"] / df["revenue"] * 100, 0)
    df["mgmt_cost"]   = mgmt.reindex(df.index).fillna(df["total_cost"])
    df["mgmt_profit"] = df["revenue"] - df["mgmt_cost"]

    # Customer master — handle both "Customer ID" and "Customer Id"
    cm = clean["customer_master"]
    id_col = "Customer ID" if "Customer ID" in cm.columns else "Customer Id"
    cm = cm.set_index(id_col)
    for col in ["Customer Name", "Industry", "Contract Type"]:
        if col in cm.columns:
            df[col] = cm[col].reindex(df.index)
    return df.sort_values("profit")


# ── 4. INTELLIGENCE ──────────────────────────────────────────────────────────
def revenue_leakage(clean, annualise_factor=None):
    if annualise_factor is None:
        annualise_factor = ANNUALISE
    acts = (clean["activities"]
            .groupby(["Customer Id", "Activity Type"])["Quantity"].sum().reset_index())
    charged = (clean["revenue"]
               .groupby(["Customer Id", "Charge Type"])["Charged Quantity"]
               .sum().reset_index())
    m = acts.merge(charged, left_on=["Customer Id", "Activity Type"],
                   right_on=["Customer Id", "Charge Type"], how="left")
    m["Charged Quantity"] = m["Charged Quantity"].fillna(0)
    m["gap_units"] = (m["Quantity"] - m["Charged Quantity"]).clip(lower=0)
    rates = clean["pricing"].set_index(["Customer Id", "Activity Type"])["Contract Rate"]
    m["rate"] = m.apply(
        lambda r: rates.get((r["Customer Id"], r["Activity Type"]), np.nan), axis=1)
    m["leakage_2mo"]   = (m["gap_units"] * m["rate"]).fillna(0)
    m["leakage_annual"] = m["leakage_2mo"] * annualise_factor
    by_cust = (m.groupby("Customer Id")
               .agg(leakage_annual=("leakage_annual", "sum"),
                    gap_units=("gap_units", "sum"))
               .sort_values("leakage_annual", ascending=False))
    return m, by_cust


def below_cost_pricing(clean, annualise_factor=None):
    if annualise_factor is None:
        annualise_factor = ANNUALISE
    cpu = activity_unit_costs(clean)["cost_per_unit"]
    p = clean["pricing"].copy()
    p["true_cost"]      = p["Activity Type"].map(cpu)
    p["margin_per_unit"] = p["Contract Rate"] - p["true_cost"]
    p = p.dropna(subset=["margin_per_unit"])
    vol = clean["activities"].groupby(["Customer Id", "Activity Type"])["Quantity"].sum()
    p["volume_2mo"] = p.apply(
        lambda r: vol.get((r["Customer Id"], r["Activity Type"]), 0), axis=1)
    p["annual_loss"] = np.where(
        p["margin_per_unit"] < 0,
        -p["margin_per_unit"] * p["volume_2mo"] * annualise_factor, 0)
    return p[p["margin_per_unit"] < 0].sort_values("annual_loss", ascending=False)


def productivity(clean):
    cpu = activity_unit_costs(clean).reset_index()
    return cpu[["Activity Type", "units", "cost", "cost_per_unit"]].rename(
        columns={"units": "total_units", "cost": "total_cost"})


def headline_numbers(clean, prof, leak_by_cust, below, annualise_factor=None):
    if annualise_factor is None:
        annualise_factor = ANNUALISE
    auc = activity_unit_costs(clean)
    total_rev_annual = clean["revenue"]["Revenue"].sum() * annualise_factor
    pick_loss  = below[below["Activity Type"] == "Pick"]["annual_loss"].sum()
    total_leak = leak_by_cust["leakage_annual"].sum()

    pick_cost_conservative = float(auc.loc["Pick", "cost_per_unit_conservative"]) if "Pick" in auc.index else 0.0
    pick_cost_strict       = float(auc.loc["Pick", "cost_per_unit_strict"])       if "Pick" in auc.index else 0.0

    bc_strict = below.copy()
    if "Pick" in auc.index:
        strict_cpu = auc["cost_per_unit_strict"]
        bc_strict["true_cost_strict"]  = bc_strict["Activity Type"].map(strict_cpu)
        bc_strict["margin_strict"]     = bc_strict["Contract Rate"] - bc_strict["true_cost_strict"]
        bc_strict["annual_loss_strict"] = bc_strict.apply(
            lambda r: -r["margin_strict"] * r["volume_2mo"] * annualise_factor
            if r["margin_strict"] < 0 else 0, axis=1)
        pick_loss_strict = bc_strict[bc_strict["Activity Type"] == "Pick"]["annual_loss_strict"].sum()
    else:
        pick_loss_strict = pick_loss

    months = int(round(12 / annualise_factor)) if annualise_factor else 2

    return {
        "annual_revenue":           total_rev_annual,
        "pick_cost_conservative":   pick_cost_conservative,
        "pick_cost_strict":         pick_cost_strict,
        "pick_underpricing_annual": pick_loss,
        "pick_underpricing_strict": pick_loss_strict,
        "leakage_annual":           total_leak,
        "pricing_exposure":         pick_loss + total_leak,
        "margin_min":               prof["margin_pct"].min(),
        "margin_max":               prof["margin_pct"].max(),
        "unprofitable_customers":   int((prof["profit"] < 0).sum()),
        "total_opportunity":        pick_loss + total_leak,
        "months_in_data":           months,
        "annualise_factor":         annualise_factor,
    }


def run_all(path_or_buffer):
    """Run the entire pipeline; return everything the app needs."""
    sheets, mapping, months_in_data, annualise_factor = load_workbook(path_or_buffer)
    clean, quality = clean_data(sheets, mapping)
    prof            = build_profitability(clean)
    leak_detail, leak_by_cust = revenue_leakage(clean, annualise_factor)
    below           = below_cost_pricing(clean, annualise_factor)
    prod            = productivity(clean)
    heads           = headline_numbers(clean, prof, leak_by_cust, below, annualise_factor)
    return {
        "clean":              clean,
        "quality":            quality,
        "profitability":      prof,
        "leakage_detail":     leak_detail,
        "leakage_by_customer": leak_by_cust,
        "below_cost":         below,
        "productivity":       prod,
        "headlines":          heads,
        "months_in_data":     months_in_data,
        "annualise_factor":   annualise_factor,
    }


def get_headline_figures(path_or_buffer,
                        ops_exposure=OPS_EXPOSURE_F014_F015,
                        recovery_target=1_150_000):
    """
    Single source of truth for all financial figures shown in the UI.
    app.py loads this at startup into _HF; every dollar figure in the UI
    reads from _HF rather than hardcoding.

    Parameters
    ----------
    path_or_buffer : path or file-like object for the warehouse Excel workbook.
    ops_exposure   : operational efficiency losses from findings F014 + F015.
                     This is the ONLY parameter that is not purely engine-derived
                     from the Excel data — F014 and F015 require qualitative
                     assessment (exception-handling drain and urgent-order
                     throughput penalty) that goes beyond what labour/activity
                     tables alone can produce. Default = OPS_EXPOSURE_F014_F015
                     ($446K + $349K = $795K). Override for sensitivity analysis
                     or when re-assessed findings change the estimate.
    recovery_target: 9-month delivery target agreed with management ($1.15M).
    """
    result = run_all(path_or_buffer)
    h   = result["headlines"]
    bc  = result["below_cost"]
    leak = result["leakage_by_customer"]

    def _pick_loss(cid):
        rows = bc[bc["Customer Id"] == cid] if "Customer Id" in bc.columns else pd.DataFrame()
        return float(rows["annual_loss"].sum()) if len(rows) else 0.0

    def _leak_annual(cid):
        return float(leak.loc[cid, "leakage_annual"]) if cid in leak.index else 0.0

    pricing_exposure  = h["pricing_exposure"]
    total_opportunity = pricing_exposure + ops_exposure

    out = {
        "pick_cost":            h["pick_cost_conservative"],
        "pick_cost_strict":     h["pick_cost_strict"],
        "pricing_exposure":     pricing_exposure,
        "ops_exposure":         ops_exposure,
        "total_opportunity":    total_opportunity,
        "recovery_target":      recovery_target,
        "bravo_annual_loss":    _pick_loss("C002"),
        "delta_pricing_loss":   _pick_loss("C004"),
        "delta_combined":       _pick_loss("C004") + _leak_annual("C004"),
        "charlie_unbilled":     _leak_annual("C003"),
        "charlie_pricing_loss": _pick_loss("C003"),
        "months_in_data":       result["months_in_data"],
        "annualise_factor":     result["annualise_factor"],
    }
    out["pick_cost_fmt"]         = f"${out['pick_cost']:.3f}"
    out["pick_cost_strict_fmt"]  = f"${out['pick_cost_strict']:.3f}"
    out["pricing_exposure_fmt"]  = f"${pricing_exposure/1e6:.2f}M"
    out["ops_exposure_fmt"]      = f"${ops_exposure/1e6:.2f}M"
    out["total_opportunity_fmt"] = f"${total_opportunity/1e6:.2f}M"
    out["recovery_target_fmt"]   = f"${recovery_target/1e6:.2f}M"
    out["annualise_factor_fmt"]  = f"×{out['annualise_factor']:.1f}"
    return out


if __name__ == "__main__":
    import sys
    path = (sys.argv[1] if len(sys.argv) > 1 else
            "F:/Mattingly/Phase 3 Tool/data/Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx")

    print("Running engine on:", path)
    res = run_all(path)
    h   = res["headlines"]

    print("-" * 65)
    print(f"MONTHS IN DATA: {res['months_in_data']}  |  ANNUALISE: ×{res['annualise_factor']:.1f}")
    print("HEADLINE NUMBERS")
    for k, v in h.items():
        print(f"  {k}: {v:,.4f}" if isinstance(v, float) else f"  {k}: {v}")

    hf = get_headline_figures(path)
    print()
    print("-" * 65)
    print("CANONICAL RECONCILIATION (conservative basis)")
    print(f"  Pick cost (conservative):  {hf['pick_cost_fmt']}/pick")
    print(f"  Pick cost (strict):        {hf['pick_cost_strict_fmt']}/pick")
    print(f"  Annualise factor:          {hf['annualise_factor_fmt']}  ({hf['months_in_data']} months detected)")
    print(f"  Underpricing + unbilled:   {hf['pricing_exposure_fmt']}   <- PRICING_EXPOSURE")
    print(f"  Operational exposure:      {hf['ops_exposure_fmt']}   <- OPS_EXPOSURE")
    print(f"  Total opportunity:         {hf['total_opportunity_fmt']}   <- TOTAL_OPPORTUNITY")
    print(f"  Recovery target:           {hf['recovery_target_fmt']}")
    print(f"  Bravo annual loss:         ${hf['bravo_annual_loss']:,.0f}")
    print(f"  Delta combined:            ${hf['delta_combined']:,.0f}")
    