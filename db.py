"""
db.py — SQLite database layer for the lead follow-up app.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = "app.db"
REPS = ["Priya", "Rohit", "Anjali", "Sameer", "Vikram"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            lead_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            company TEXT NOT NULL,
            phone TEXT,
            source TEXT,
            last_contact_date TEXT,
            assigned_rep TEXT DEFAULT 'Priya'
        );

        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL,
            from_who TEXT NOT NULL,
            msg_date TEXT NOT NULL,
            text TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
        );

        CREATE TABLE IF NOT EXISTS agent_results (
            lead_id TEXT PRIMARY KEY,
            tag TEXT NOT NULL,
            reason TEXT,
            next_followup_date TEXT,
            draft_message TEXT,
            analyzed_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
        );

        CREATE TABLE IF NOT EXISTS sent_log (
            sent_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL,
            message_text TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
        );
    """)
    conn.commit()

    # Migration: add assigned_rep column to older DBs
    cur.execute("PRAGMA table_info(leads)")
    cols = [row[1] for row in cur.fetchall()]
    if "assigned_rep" not in cols:
        cur.execute("ALTER TABLE leads ADD COLUMN assigned_rep TEXT DEFAULT 'Priya'")
        conn.commit()

    conn.close()


def seed_if_empty():
    """Load leads.json + chats.json into DB. Also backfills missing reps for existing leads."""
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM leads")
    lead_count = cur.fetchone()[0]

    if lead_count == 0:
        # Fresh DB — seed from JSON
        with open("data/leads.json") as f:
            leads = json.load(f)
        with open("data/chats.json") as f:
            chats = json.load(f)

        for i, lead in enumerate(leads):
            assigned = REPS[i % len(REPS)]
            cur.execute(
                """INSERT INTO leads (lead_id, name, company, phone, source, last_contact_date, assigned_rep)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (lead["lead_id"], lead["name"], lead["company"],
                 lead["phone"], lead["source"], lead["last_contact_date"], assigned)
            )

        for chat in chats:
            for msg in chat["messages"]:
                cur.execute(
                    """INSERT INTO chats (lead_id, from_who, msg_date, text)
                       VALUES (?, ?, ?, ?)""",
                    (chat["lead_id"], msg["from"], msg["date"], msg["text"])
                )
    else:
        # Existing DB — backfill missing reps if migration left them NULL/default
        cur.execute("SELECT lead_id FROM leads WHERE assigned_rep IS NULL OR assigned_rep = '' ORDER BY lead_id")
        missing = [row[0] for row in cur.fetchall()]
        for i, lead_id in enumerate(missing):
            cur.execute(
                "UPDATE leads SET assigned_rep = ? WHERE lead_id = ?",
                (REPS[i % len(REPS)], lead_id)
            )

    conn.commit()
    conn.close()


def get_all_leads():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM leads ORDER BY lead_id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lead(lead_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_lead(name: str, company: str, phone: str, source: str,
             last_contact_date: str, assigned_rep: str = "Priya"):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT lead_id FROM leads ORDER BY lead_id DESC LIMIT 1")
    last = cur.fetchone()
    if last:
        last_num = int(last["lead_id"][1:])
        new_id = f"L{last_num + 1:03d}"
    else:
        new_id = "L001"

    cur.execute(
        """INSERT INTO leads (lead_id, name, company, phone, source, last_contact_date, assigned_rep)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (new_id, name, company, phone, source, last_contact_date, assigned_rep)
    )
    conn.commit()
    conn.close()
    return new_id


def get_chat(lead_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT from_who, msg_date, text FROM chats WHERE lead_id = ? ORDER BY msg_date ASC",
        (lead_id,)
    ).fetchall()
    conn.close()
    return [{"from": r["from_who"], "date": r["msg_date"], "text": r["text"]} for r in rows]


def add_chat_message(lead_id: str, from_who: str, text: str):
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "INSERT INTO chats (lead_id, from_who, msg_date, text) VALUES (?, ?, ?, ?)",
        (lead_id, from_who, now, text)
    )
    conn.execute(
        "UPDATE leads SET last_contact_date = ? WHERE lead_id = ?",
        (now[:10], lead_id)
    )
    conn.commit()
    conn.close()


def save_agent_result(lead_id: str, result: dict):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO agent_results
           (lead_id, tag, reason, next_followup_date, draft_message, analyzed_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (lead_id, result["tag"], result["reason"],
         result["next_followup_date"], result["draft_message"],
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_agent_result(lead_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM agent_results WHERE lead_id = ?", (lead_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_agent_results():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agent_results").fetchall()
    conn.close()
    return {r["lead_id"]: dict(r) for r in rows}


def update_draft(lead_id: str, new_draft: str):
    conn = get_conn()
    conn.execute(
        "UPDATE agent_results SET draft_message = ? WHERE lead_id = ?",
        (new_draft, lead_id)
    )
    conn.commit()
    conn.close()


def mark_sent(lead_id: str, message_text: str):
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "INSERT INTO sent_log (lead_id, message_text, sent_at) VALUES (?, ?, ?)",
        (lead_id, message_text, now)
    )
    conn.execute(
        "INSERT INTO chats (lead_id, from_who, msg_date, text) VALUES (?, ?, ?, ?)",
        (lead_id, "rep", now, message_text)
    )
    conn.execute(
        "UPDATE leads SET last_contact_date = ? WHERE lead_id = ?",
        (now[:10], lead_id)
    )
    conn.commit()
    conn.close()


def is_sent_today(lead_id: str):
    conn = get_conn()
    today = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT 1 FROM sent_log WHERE lead_id = ? AND sent_at LIKE ?",
        (lead_id, f"{today}%")
    ).fetchone()
    conn.close()
    return row is not None


def reset_db():
    Path(DB_PATH).unlink(missing_ok=True)


if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Seeding from JSON (if empty)...")
    seed_if_empty()

    leads = get_all_leads()
    print(f"\nLoaded {len(leads)} leads.")
    if leads:
        print(f"First lead: {leads[0]['name']} -> rep: {leads[0].get('assigned_rep')}")
    print("Database ready.")