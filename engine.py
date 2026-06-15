"""
Profit Lens - Analysis Engine
Mattingly AI & Operations Hackathon 2026 | Kishan Gowda

This module is the brain of Profit Lens. It is deliberately separated from the
user interface (app.py) so the same logic can be pointed at any warehouse's
data file - which is exactly how it scales across a 10+ warehouse network.

Pipeline:  INGEST -> CLEAN & VALIDATE -> COST ENGINE -> INTELLIGENCE
Everything downstream (dashboards, AI layer) reads from the objects this
module produces.
"""

import pandas as pd
import numpy as np

# The seven valid warehouse activities. Anything else in an "Activity Type"
# column is corrupted data (in the supplied file, customer IDs were dumped here).
VALID_ACTIVITIES = ["Storage", "Receipt", "Dispatch", "Pick",
                    "Returns", "Rework", "Urgent Order"]

# Annualisation factor: the dataset is 2 months of actuals. x6 = 12 months.
ANNUALISE = 6

# Conservative cost handling: treat missing T&A days as zero-cost (picks still happened,
# we just have no labour record for those 4 days). This uses the activities sheet as the
# volume denominator — larger than the labour sheet, giving a lower (more conservative)
# cost per unit. Flip to False for the strict "only counted days" figure.
CONSERVATIVE_DAYS_HANDLING = True


# ----------------------------------------------------------------------------
# 1. INGEST
# ----------------------------------------------------------------------------
def load_workbook(path_or_buffer):
    """Load every sheet we need from the warehouse Excel file."""
    xl = pd.ExcelFile(path_or_buffer)
    sheets = {}
    for name in xl.sheet_names:
        sheets[name] = pd.read_excel(xl, sheet_name=name)
    return sheets


# ----------------------------------------------------------------------------
# 2. CLEAN & VALIDATE  (transparency over silence)
# ----------------------------------------------------------------------------
def clean_data(sheets):
    """
    Repair the messy data and RECORD what we did, so the UI can show it.
    Returns (clean_dict, quality_log).
    """
    log = []

    # --- Activities: combine the two months, coerce quantity, drop junk ---
    acts = pd.concat([sheets["M1 Activities"], sheets["M2 Activities"]],
                     ignore_index=True)
    before = len(acts)
    acts["Quantity"] = pd.to_numeric(acts["Quantity"], errors="coerce")
    junk_act = acts[~acts["Activity Type"].isin(VALID_ACTIVITIES)]
    if len(junk_act):
        log.append(("Activities", f"{len(junk_act)} rows with an invalid activity type were removed"))
    missing_qty = acts["Quantity"].isna().sum()
    if missing_qty:
        log.append(("Activities", f"{missing_qty} rows had a missing quantity (flagged, excluded from volumes)"))
    dupe_flag = (acts.get("Data Quality Note") == "Possible duplicate").sum()
    if dupe_flag:
        log.append(("Activities", f"{dupe_flag} rows flagged 'Possible duplicate' by the source system"))
    acts = acts[acts["Activity Type"].isin(VALID_ACTIVITIES)].copy()
    acts = acts.dropna(subset=["Quantity"])

    # --- Labour: the worst sheet. Customer IDs leaked into Activity Type. ---
    lab_frames = []
    for m in ["M1 Labour", "M2 Labour"]:
        df = sheets[m].copy()
        raw = len(df)
        junk = df[~df["Activity Type"].isin(VALID_ACTIVITIES)]
        if len(junk):
            log.append((m, f"{len(junk)} corrupted rows (customer IDs in the activity column) removed"))
        df = df[df["Activity Type"].isin(VALID_ACTIVITIES)].copy()
        for col in ["Units Processed", "Labour Hours", "Labour Cost"]:
            bad = pd.to_numeric(df[col], errors="coerce").isna() & df[col].notna()
            if bad.sum():
                log.append((m, f"{bad.sum()} non-numeric values in '{col}' coerced"))
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # de-duplicate on date+activity (source contained repeats)
        d0 = len(df)
        df = df.drop_duplicates(subset=["Date", "Activity Type"], keep="first")
        if d0 - len(df):
            log.append((m, f"{d0 - len(df)} duplicate date/activity rows removed"))
        df = df.dropna(subset=["Labour Cost", "Units Processed"])
        lab_frames.append(df)
    labour = pd.concat(lab_frames, ignore_index=True)

    # --- Revenue ---
    rev = pd.concat([sheets["M1 Revenue"], sheets["M2 Revenue"]], ignore_index=True)
    rev["Revenue"] = pd.to_numeric(rev["Revenue"], errors="coerce").fillna(0)
    rev["Charged Quantity"] = pd.to_numeric(rev["Charged Quantity"], errors="coerce").fillna(0)

    # --- Pricing: flag customers with no contract rate ---
    pricing = sheets["Customer Pricing"].copy()
    pricing["Contract Rate"] = pd.to_numeric(pricing["Contract Rate"], errors="coerce")
    no_rate = pricing[pricing["Contract Rate"].isna()]
    if len(no_rate):
        custs = ", ".join(sorted(no_rate["Customer Id"].astype(str).unique()))
        log.append(("Customer Pricing", f"{len(no_rate)} price points missing a contract rate ({custs})"))

    # --- Exceptions (the client's own flags) ---
    exc = pd.concat([sheets["M1 Exceptions"], sheets["M2 Exceptions"]], ignore_index=True)
    exc["Count"] = pd.to_numeric(exc["Count"], errors="coerce").fillna(0)

    clean = {
        "activities": acts,
        "labour": labour,
        "revenue": rev,
        "pricing": pricing,
        "exceptions": exc,
        "customer_master": sheets["Customer Master"],
        "cost_allocation": sheets["Cost Allocation"],
        "mgmt_allocation": sheets["Management Allocation Cost"],
    }
    quality = pd.DataFrame(log, columns=["Sheet", "Issue handled"])
    return clean, quality


# ----------------------------------------------------------------------------
# 3. COST ENGINE  (activity-based costing)
# ----------------------------------------------------------------------------
def activity_unit_costs(clean):
    """
    True labour cost per unit of each activity.

    Returns two cost columns:
      cost_per_unit        — the canonical figure (conservative when CONSERVATIVE_DAYS_HANDLING
                             is True, strict otherwise).  Downstream functions use this column.
      cost_per_unit_strict — always the strict figure (labour-sheet units only), exposed so
                             headline_numbers() can report both in the same call.

    Conservative logic: some days have activities recorded but no matching labour rows
    (the 4 missing T&A days flagged in F007).  Under the strict method those days are excluded
    from both cost and units, artificially raising cost/unit.  The conservative method keeps the
    same total labour cost but uses the larger activity-sheet unit count as the denominator,
    correctly treating missing-day picks as zero incremental cost — a cautious floor.
    """
    lab = clean["labour"]
    grp = lab.groupby("Activity Type").agg(
        units=("Units Processed", "sum"),
        hours=("Labour Hours", "sum"),
        cost=("Labour Cost", "sum"),
    )
    # Strict: labour-sheet units only (current behaviour — excludes missing-data days)
    grp["cost_per_unit_strict"] = grp["cost"] / grp["units"]

    # Conservative: use activity volumes as denominator (includes days with no labour record)
    act_units = clean["activities"].groupby("Activity Type")["Quantity"].sum()
    conservative_denom = act_units.reindex(grp.index).fillna(grp["units"])
    grp["cost_per_unit_conservative"] = grp["cost"] / conservative_denom

    # Default column used by all downstream functions
    grp["cost_per_unit"] = (
        grp["cost_per_unit_conservative"] if CONSERVATIVE_DAYS_HANDLING
        else grp["cost_per_unit_strict"]
    )
    return grp


def customer_activity_matrix(clean):
    """Total quantity of each activity, per customer."""
    a = clean["activities"]
    return (a.groupby(["Customer Id", "Activity Type"])["Quantity"]
            .sum().unstack(fill_value=0))


def build_profitability(clean):
    """
    The core output: true profit per customer (activity-based), alongside
    management's current revenue-share view, so the gap is visible.
    """
    cpu = activity_unit_costs(clean)["cost_per_unit"]
    cust_act = customer_activity_matrix(clean)

    # Labour cost to serve each customer = their volumes x true unit costs
    labour_cost = (cust_act * cpu.reindex(cust_act.columns)).sum(axis=1)

    # Overhead: rent+equipment follow storage footprint; the rest follow labour
    ca = clean["cost_allocation"]
    overhead_total = ca["Monthly Cost"].sum()  # both months in the sheet
    rent_equip = ca[ca["Cost Category"].isin(["Rent", "Equipment"])]["Monthly Cost"].sum()
    other_oh = overhead_total - rent_equip
    storage = cust_act.get("Storage", pd.Series(0, index=cust_act.index))
    storage_share = storage / storage.sum() if storage.sum() else 0
    labour_share = labour_cost / labour_cost.sum() if labour_cost.sum() else 0
    overhead = storage_share * rent_equip + labour_share * other_oh

    # Revenue per customer
    revenue = clean["revenue"].groupby("Customer Id")["Revenue"].sum()

    # Management's current view (overhead by revenue share)
    mgmt = clean["mgmt_allocation"].groupby("Customer Id")["Management Allocated Cost"].sum()

    df = pd.DataFrame({
        "revenue": revenue,
        "labour_cost": labour_cost,
        "overhead": overhead,
    }).fillna(0)
    df["total_cost"] = df["labour_cost"] + df["overhead"]
    df["profit"] = df["revenue"] - df["total_cost"]
    df["margin_pct"] = np.where(df["revenue"] > 0,
                                df["profit"] / df["revenue"] * 100, 0)
    # management view of profit (their cost method)
    df["mgmt_cost"] = mgmt.reindex(df.index).fillna(df["total_cost"])
    df["mgmt_profit"] = df["revenue"] - df["mgmt_cost"]

    cm = clean["customer_master"].set_index("Customer ID")
    for col in ["Customer Name", "Industry", "Contract Type"]:
        if col in cm.columns:
            df[col] = cm[col].reindex(df.index)
    return df.sort_values("profit")


# ----------------------------------------------------------------------------
# 4. INTELLIGENCE  (leakage, mispricing, productivity)
# ----------------------------------------------------------------------------
def revenue_leakage(clean):
    """Activities performed but not charged, valued at the customer's own rate."""
    acts = clean["activities"].groupby(["Customer Id", "Activity Type"])["Quantity"].sum().reset_index()
    charged = (clean["revenue"].groupby(["Customer Id", "Charge Type"])["Charged Quantity"]
               .sum().reset_index())
    m = acts.merge(charged, left_on=["Customer Id", "Activity Type"],
                   right_on=["Customer Id", "Charge Type"], how="left")
    m["Charged Quantity"] = m["Charged Quantity"].fillna(0)
    m["gap_units"] = (m["Quantity"] - m["Charged Quantity"]).clip(lower=0)

    rates = clean["pricing"].set_index(["Customer Id", "Activity Type"])["Contract Rate"]
    m["rate"] = m.apply(lambda r: rates.get((r["Customer Id"], r["Activity Type"]), np.nan), axis=1)
    m["leakage_2mo"] = (m["gap_units"] * m["rate"]).fillna(0)
    m["leakage_annual"] = m["leakage_2mo"] * ANNUALISE
    by_cust = (m.groupby("Customer Id")
               .agg(leakage_annual=("leakage_annual", "sum"),
                    gap_units=("gap_units", "sum"))
               .sort_values("leakage_annual", ascending=False))
    return m, by_cust


def below_cost_pricing(clean):
    """Price points charged below the true cost of the activity."""
    cpu = activity_unit_costs(clean)["cost_per_unit"]
    p = clean["pricing"].copy()
    p["true_cost"] = p["Activity Type"].map(cpu)
    p["margin_per_unit"] = p["Contract Rate"] - p["true_cost"]
    p = p.dropna(subset=["margin_per_unit"])

    # value the loss using actual volumes
    vol = clean["activities"].groupby(["Customer Id", "Activity Type"])["Quantity"].sum()
    p["volume_2mo"] = p.apply(lambda r: vol.get((r["Customer Id"], r["Activity Type"]), 0), axis=1)
    p["annual_loss"] = np.where(p["margin_per_unit"] < 0,
                                -p["margin_per_unit"] * p["volume_2mo"] * ANNUALISE, 0)
    below = p[p["margin_per_unit"] < 0].sort_values("annual_loss", ascending=False)
    return below


def productivity(clean):
    """Cost per unit and throughput by activity - the ops view."""
    cpu = activity_unit_costs(clean).reset_index()
    cpu = cpu.rename(columns={"cost_per_unit": "cost_per_unit",
                              "units": "total_units", "cost": "total_cost"})
    return cpu[["Activity Type", "total_units", "total_cost", "cost_per_unit"]]


def headline_numbers(clean, prof, leak_by_cust, below):
    """
    The handful of numbers the CEO remembers.

    Conservative vs strict pick costs are both surfaced here so callers can
    report either without re-running the pipeline.  `pick_underpricing_annual`
    always uses the canonical (conservative) cost_per_unit; the strict figure
    is provided alongside for disclosure purposes.
    """
    auc = activity_unit_costs(clean)
    total_rev_annual = clean["revenue"]["Revenue"].sum() * ANNUALISE
    pick_loss = below[below["Activity Type"] == "Pick"]["annual_loss"].sum()
    total_leak = leak_by_cust["leakage_annual"].sum()
    margin_min = prof["margin_pct"].min()
    margin_max = prof["margin_pct"].max()
    unprofitable = int((prof["profit"] < 0).sum())

    # Per-pick unit costs (both methods)
    pick_cost_conservative = float(auc.loc["Pick", "cost_per_unit_conservative"]) if "Pick" in auc.index else 0.0
    pick_cost_strict       = float(auc.loc["Pick", "cost_per_unit_strict"])       if "Pick" in auc.index else 0.0

    # Strict pick underpricing: re-price below_cost against strict cpu (informational)
    bc_strict = below.copy()
    if "Pick" in auc.index:
        strict_cpu = auc["cost_per_unit_strict"]
        bc_strict["true_cost_strict"] = bc_strict["Activity Type"].map(strict_cpu)
        bc_strict["margin_strict"] = bc_strict["Contract Rate"] - bc_strict["true_cost_strict"]
        bc_strict["annual_loss_strict"] = bc_strict.apply(
            lambda r: -r["margin_strict"] * r["volume_2mo"] * ANNUALISE if r["margin_strict"] < 0 else 0,
            axis=1
        )
        pick_loss_strict = bc_strict[bc_strict["Activity Type"] == "Pick"]["annual_loss_strict"].sum()
    else:
        pick_loss_strict = pick_loss

    return {
        "annual_revenue": total_rev_annual,
        "pick_cost_conservative": pick_cost_conservative,
        "pick_cost_strict": pick_cost_strict,
        "pick_underpricing_annual": pick_loss,           # conservative basis
        "pick_underpricing_strict": pick_loss_strict,    # strict basis (disclosure)
        "leakage_annual": total_leak,
        "pricing_exposure": pick_loss + total_leak,      # conservative underpricing + unbilled
        "margin_min": margin_min,
        "margin_max": margin_max,
        "unprofitable_customers": unprofitable,
        "total_opportunity": pick_loss + total_leak,     # pricing/unbilled only (add ops_exposure separately)
    }


def run_all(path_or_buffer):
    """Convenience: run the entire pipeline and return everything the app needs."""
    sheets = load_workbook(path_or_buffer)
    clean, quality = clean_data(sheets)
    prof = build_profitability(clean)
    leak_detail, leak_by_cust = revenue_leakage(clean)
    below = below_cost_pricing(clean)
    prod = productivity(clean)
    heads = headline_numbers(clean, prof, leak_by_cust, below)
    return {
        "clean": clean, "quality": quality, "profitability": prof,
        "leakage_detail": leak_detail, "leakage_by_customer": leak_by_cust,
        "below_cost": below, "productivity": prod, "headlines": heads,
    }


def get_headline_figures(path_or_buffer, ops_exposure=795_000, recovery_target=1_150_000):
    """
    Single source of truth for all financial figures shown in the UI.

    Runs the full pipeline on the supplied dataset and returns a dict of
    canonical conservative numbers.  app.py imports this at startup and stores
    the result in _HF; every constant and string that references a dollar figure
    reads from _HF rather than hardcoding a value.

    Parameters
    ----------
    path_or_buffer : path or file-like object for the warehouse Excel workbook
    ops_exposure   : operational exposure from findings F014 + F015 (default $795K)
    recovery_target: 9-month delivery target (default $1.15M)

    Returns
    -------
    dict with keys:
        pick_cost, pick_cost_strict,
        pricing_exposure, ops_exposure, total_opportunity, recovery_target,
        bravo_annual_loss, delta_pricing_loss, delta_combined,
        charlie_unbilled, charlie_pricing_loss,
        *_fmt  -- pre-formatted string versions for embedding in prompts/UI
    """
    result = run_all(path_or_buffer)
    h = result["headlines"]
    bc = result["below_cost"]
    leak = result["leakage_by_customer"]

    # Per-customer figures
    def _pick_loss(cid):
        rows = bc[bc["Customer Id"] == cid] if "Customer Id" in bc.columns else pd.DataFrame()
        return float(rows["annual_loss"].sum()) if len(rows) else 0.0

    def _leak_annual(cid):
        return float(leak.loc[cid, "leakage_annual"]) if cid in leak.index else 0.0

    bravo_loss       = _pick_loss("C002")
    delta_pricing    = _pick_loss("C004")
    delta_unbilled   = _leak_annual("C004")
    charlie_unbilled = _leak_annual("C003")
    charlie_pricing  = _pick_loss("C003")

    pricing_exposure  = h["pricing_exposure"]          # conservative underpricing + unbilled
    total_opportunity = pricing_exposure + ops_exposure

    out = {
        "pick_cost":              h["pick_cost_conservative"],
        "pick_cost_strict":       h["pick_cost_strict"],
        "pricing_exposure":       pricing_exposure,
        "ops_exposure":           ops_exposure,
        "total_opportunity":      total_opportunity,
        "recovery_target":        recovery_target,
        "bravo_annual_loss":      bravo_loss,
        "delta_pricing_loss":     delta_pricing,
        "delta_combined":         delta_pricing + delta_unbilled,
        "charlie_unbilled":       charlie_unbilled,
        "charlie_pricing_loss":   charlie_pricing,
    }
    # Pre-formatted strings for prompt/UI embedding
    out["pick_cost_fmt"]         = f"${out['pick_cost']:.3f}"
    out["pick_cost_strict_fmt"]  = f"${out['pick_cost_strict']:.3f}"
    out["pricing_exposure_fmt"]  = f"${pricing_exposure/1e6:.2f}M"
    out["ops_exposure_fmt"]      = f"${ops_exposure/1e6:.2f}M"
    out["total_opportunity_fmt"] = f"${total_opportunity/1e6:.2f}M"
    out["recovery_target_fmt"]   = f"${recovery_target/1e6:.2f}M"
    return out


if __name__ == "__main__":
    import sys
    path = (sys.argv[1] if len(sys.argv) > 1 else
            "F:/Mattingly/Phase 3 Tool/data/Mattingly_Hackathon_Warehouse_Dataset_contestant.xlsx")
    res = run_all(path)
    h = res["headlines"]

    print("-" * 60)
    print("HEADLINE NUMBERS")
    for k, v in h.items():
        print(f"  {k}: {v:,.4f}" if isinstance(v, float) else f"  {k}: {v}")

    hf = get_headline_figures(path)
    print()
    print("-" * 60)
    print("CANONICAL RECONCILIATION (conservative basis)")
    print(f"  Pick cost (conservative): {hf['pick_cost_fmt']}/pick")
    print(f"  Pick cost (strict):       {hf['pick_cost_strict_fmt']}/pick")
    print(f"  Underpricing + unbilled:  {hf['pricing_exposure_fmt']}  <- PRICING_EXPOSURE")
    print(f"  Operational exposure:     {hf['ops_exposure_fmt']}  <- OPS_EXPOSURE")
    print(f"  Total opportunity:        {hf['total_opportunity_fmt']}  <- TOTAL_OPPORTUNITY")
    print(f"  Recovery target:          {hf['recovery_target_fmt']}")
    print(f"  Bravo annual loss:        ${hf['bravo_annual_loss']:,.0f}")
    print(f"  Delta combined:           ${hf['delta_combined']:,.0f}")
    print(f"  Charlie unbilled:         ${hf['charlie_unbilled']:,.0f}")
    print("-" * 60)
    tie_check = abs(hf["pricing_exposure"] + hf["ops_exposure"] - hf["total_opportunity"])
    if tie_check < 1:
        print("TIE-OUT OK -- pricing_exposure + ops_exposure = total_opportunity")
    else:
        print(f"TIE-OUT FAILED: delta = {tie_check:.2f}")

    print()
    print("WORST 5 CUSTOMERS")
    print(res["profitability"].head(5)[["Customer Name", "revenue", "profit", "margin_pct"]].round(0))
    print()
    print("QUALITY LOG")
    print(res["quality"].to_string(index=False))
