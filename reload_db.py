"""
reload_db.py — Run this from the Phase 3 Tool directory to reset the DB.
Usage (Windows): python reload_db.py
Sets Bravo FMCG ticket to "In Progress" so the demo close-ticket moment works.
"""
import os, sys

# Must run from the Phase 3 Tool directory so profit_lens.db resolves correctly
script_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_dir)
sys.path.insert(0, script_dir)

import database as db

print("Initialising DB …")
db.init_db()

conn = db.get_conn()
conn.execute("DELETE FROM tickets WHERE warehouse_id = 'WH001'")
conn.execute("DELETE FROM findings WHERE warehouse_id = 'WH001'")
conn.execute("DELETE FROM data_loaded WHERE warehouse_id = 'WH001'")
conn.commit()
conn.close()
print("Cleared stale data.")

db.load_findings_json("data/findings.json")

# Set Bravo FMCG (F001) to "In Progress" — enables live demo close-ticket moment
conn = db.get_conn()
conn.execute("""
    UPDATE tickets SET status = 'In Progress', updated_at = datetime('now')
    WHERE warehouse_id = 'WH001' AND finding_id = 'F001'
""")
conn.commit()
conn.close()
print("Set Bravo FMCG (F001) → In Progress for demo.")

tickets = db.get_tickets("WH001")
print(f"\nLoaded {len(tickets)} tickets:")
for t in sorted(tickets, key=lambda x: x["finding_id"] or ""):
    eps = " ← EPSILON?" if "Epsilon" in (t.get("customer") or "") else ""
    status_flag = " ★" if t.get("status") == "In Progress" else ""
    print(f"  {t['finding_id']:<6} ${t['dollar_impact']:>10,.0f}  status={t['status']:<12} {t['title'][:45]}{eps}{status_flag}")

total_excl_f011 = sum(t["dollar_impact"] for t in tickets if t["finding_id"] != "F011")
total_all = sum(t["dollar_impact"] for t in tickets)
print(f"\nTotal (all tickets):       ${total_all:>12,.0f}")
print(f"Total (excl F011):         ${total_excl_f011:>12,.0f}  ← donut/pipeline figure")
print(f"Expected excl F011:        $  1,056,245")
print(f"Expected F011 alone:       $  1,490,000")
print("\n✓ Done. Start Streamlit: streamlit run app.py")
