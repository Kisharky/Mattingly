"""
database.py — Profit Lens SQLite layer
All DB operations live here. Swap to Postgres later by changing the connection string.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "profit_lens.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS warehouses (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            location    TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS findings (
            id              TEXT PRIMARY KEY,
            warehouse_id    TEXT NOT NULL,
            type            TEXT NOT NULL,
            title           TEXT NOT NULL,
            customer        TEXT,
            customer_id     TEXT,
            priority        TEXT DEFAULT 'MEDIUM',
            suggested_owner TEXT,
            dollar_impact   REAL DEFAULT 0,
            full_exposure   REAL DEFAULT 0,
            current_rate    REAL,
            proposed_rate   REAL,
            true_cost       REAL,
            description     TEXT,
            ai_explanation  TEXT,
            action          TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            warehouse_id    TEXT NOT NULL DEFAULT 'WH001',
            finding_id      TEXT,
            title           TEXT NOT NULL,
            description     TEXT,
            dollar_impact   REAL DEFAULT 0,
            assigned_role   TEXT,
            priority        TEXT DEFAULT 'MEDIUM',
            status          TEXT DEFAULT 'To Do',
            customer        TEXT,
            finding_type    TEXT,
            ai_explanation  TEXT,
            action          TEXT,
            comments        TEXT DEFAULT '[]',
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
            FOREIGN KEY (finding_id)   REFERENCES findings(id)
        );
    """)
    conn.commit()
    conn.close()


def is_data_loaded(warehouse_id="WH001"):
    """Check if findings have already been imported for this warehouse."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM findings WHERE warehouse_id = ?", (warehouse_id,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def load_findings_json(filepath="data/findings.json"):
    """Import findings JSON into DB and auto-generate tickets."""
    with open(filepath, "r") as f:
        data = json.load(f)

    conn = get_conn()
    c = conn.cursor()
    wh = data["warehouse"]

    # Upsert warehouse
    c.execute("""
        INSERT OR REPLACE INTO warehouses (id, name, location)
        VALUES (?, ?, ?)
    """, (wh["id"], wh["name"], wh["location"]))

    # Insert findings + create tickets
    for finding in data["findings"]:
        c.execute("""
            INSERT OR REPLACE INTO findings
            (id, warehouse_id, type, title, customer, customer_id, priority,
             suggested_owner, dollar_impact, full_exposure, current_rate,
             proposed_rate, true_cost, description, ai_explanation, action)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            finding["id"], wh["id"], finding["type"], finding["title"],
            finding.get("customer"), finding.get("customer_id"),
            finding.get("priority", "MEDIUM"), finding.get("suggested_owner"),
            finding.get("dollar_impact", 0), finding.get("full_exposure", 0),
            finding.get("current_rate"), finding.get("proposed_rate"),
            finding.get("true_cost"), finding.get("description"),
            finding.get("ai_explanation"), finding.get("action")
        ))

        # Auto-generate ticket from finding
        c.execute("""
            INSERT OR IGNORE INTO tickets
            (warehouse_id, finding_id, title, description, dollar_impact,
             assigned_role, priority, status, customer, finding_type,
             ai_explanation, action)
            SELECT ?, id, title, description, dollar_impact,
                   suggested_owner, priority, 'To Do', customer, type,
                   ai_explanation, action
            FROM findings WHERE id = ?
        """, (wh["id"], finding["id"]))

    conn.commit()
    conn.close()


def get_tickets(warehouse_id="WH001", role=None, status=None,
                finding_type=None, priority=None):
    """Fetch tickets with optional filters."""
    conn = get_conn()
    c = conn.cursor()

    query = "SELECT * FROM tickets WHERE warehouse_id = ?"
    params = [warehouse_id]

    # Role-based filtering — filter by assigned_role so new types route automatically
    if role and role != "CEO":
        query += " AND assigned_role = ?"
        params.append(role)

    if status and status != "All":
        query += " AND status = ?"
        params.append(status)

    if finding_type and finding_type != "All":
        query += " AND finding_type = ?"
        params.append(finding_type)

    if priority and priority != "All":
        query += " AND priority = ?"
        params.append(priority)

    query += " ORDER BY dollar_impact DESC, priority ASC, created_at ASC"

    c.execute(query, params)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def update_ticket_status(ticket_id, new_status):
    """Update ticket status and timestamp."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE tickets SET status = ?, updated_at = datetime('now')
        WHERE id = ?
    """, (new_status, ticket_id))
    conn.commit()
    conn.close()


def add_comment(ticket_id, role, text):
    """Append a comment to a ticket's JSON comment list."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT comments FROM tickets WHERE id = ?", (ticket_id,))
    row = c.fetchone()
    comments = json.loads(row[0] or "[]")
    comments.append({
        "role": role,
        "text": text,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    c.execute("""
        UPDATE tickets SET comments = ?, updated_at = datetime('now')
        WHERE id = ?
    """, (json.dumps(comments), ticket_id))
    conn.commit()
    conn.close()


def create_ticket_manual(warehouse_id, title, description, dollar_impact,
                          assigned_role, priority, customer, finding_type):
    """Create a ticket manually (not from a finding)."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO tickets
        (warehouse_id, title, description, dollar_impact, assigned_role,
         priority, status, customer, finding_type)
        VALUES (?,?,?,?,?,?,'To Do',?,?)
    """, (warehouse_id, title, description, dollar_impact, assigned_role,
          priority, customer, finding_type))
    conn.commit()
    conn.close()


def get_recovery_stats(warehouse_id="WH001"):
    """Dashboard KPIs: exposure, recovered, open, blocked."""
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        SELECT
            SUM(CASE WHEN status = 'Done' AND dollar_impact > 0 THEN dollar_impact ELSE 0 END) as recovered,
            SUM(CASE WHEN status != 'Done' THEN 1 ELSE 0 END) as open_count,
            SUM(CASE WHEN status = 'Blocked' THEN 1 ELSE 0 END) as blocked_count,
            SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) as in_progress_count,
            SUM(CASE WHEN status = 'Done' THEN 1 ELSE 0 END) as done_count,
            COUNT(*) as total_count
        FROM tickets WHERE warehouse_id = ?
    """, (warehouse_id,))

    row = dict(c.fetchone())
    conn.close()
    return {
        "recovered": row["recovered"] or 0,
        "open_count": row["open_count"] or 0,
        "blocked_count": row["blocked_count"] or 0,
        "in_progress_count": row["in_progress_count"] or 0,
        "done_count": row["done_count"] or 0,
        "total_count": row["total_count"] or 0,
    }


def get_closed_tickets(warehouse_id="WH001"):
    """Return Done tickets with dollar_impact > 0 for recovery breakdown."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT title, customer, dollar_impact, finding_type, updated_at
        FROM tickets
        WHERE warehouse_id = ? AND status = 'Done' AND dollar_impact > 0
        ORDER BY updated_at DESC
    """, (warehouse_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
