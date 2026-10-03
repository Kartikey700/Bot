import sqlite3
import os
from config import DB_PATH

os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)


def _conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            escrower_id INTEGER,
            escrower_name TEXT,
            amount REAL,
            fee REAL,
            total REAL,
            reason TEXT DEFAULT '',
            trade_id TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS coowners (
            user_id INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS stats (
            chat_id INTEGER PRIMARY KEY,
            total_deals INTEGER DEFAULT 0,
            total_volume REAL DEFAULT 0,
            total_fees REAL DEFAULT 0
        );
        """)


# ---------- Admins ----------
def add_admin(uid, username=""):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)", (uid, username))


def remove_admin(uid):
    with _conn() as c:
        c.execute("DELETE FROM admins WHERE user_id=?", (uid,))


def list_admins():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM admins").fetchall()]


def is_admin(uid, owner_id):
    if uid == owner_id:
        return True
    with _conn() as c:
        return c.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,)).fetchone() is not None


# ---------- Co-owners ----------
def add_coowner(uid):
    with _conn() as c:
        c.execute("INSERT OR IGNORE INTO coowners (user_id) VALUES (?)", (uid,))


def remove_coowner(uid):
    with _conn() as c:
        c.execute("DELETE FROM coowners WHERE user_id=?", (uid,))


def list_coowners():
    with _conn() as c:
        return [r["user_id"] for r in c.execute("SELECT user_id FROM coowners").fetchall()]


def is_coowner(uid):
    with _conn() as c:
        return c.execute("SELECT 1 FROM coowners WHERE user_id=?", (uid,)).fetchone() is not None


def is_owner_or_coowner(uid, owner_id):
    return uid == owner_id or is_coowner(uid)


# ---------- Deals ----------
def create_deal(chat_id, escrower_id, escrower_name, amount, fee, total, reason=""):
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO deals (chat_id, escrower_id, escrower_name, amount, fee, total, reason) VALUES (?,?,?,?,?,?,?)",
            (chat_id, escrower_id, escrower_name, amount, fee, total, reason),
        )
        deal_id = cur.lastrowid
        c.execute(
            """INSERT INTO stats (chat_id, total_deals, total_volume, total_fees)
               VALUES (?,1,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
                  total_deals = total_deals + 1,
                  total_volume = total_volume + excluded.total_volume,
                  total_fees = total_fees + excluded.total_fees""",
            (chat_id, amount, fee),
        )
        return deal_id


def get_deal(deal_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone()
        return dict(row) if row else None


def latest_deal(chat_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM deals WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)).fetchone()
        return dict(row) if row else None


def update_deal(deal_id, **kwargs):
    if not kwargs:
        return
    keys = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [deal_id]
    with _conn() as c:
        c.execute(f"UPDATE deals SET {keys} WHERE id=?", vals)


def delete_latest(chat_id):
    with _conn() as c:
        row = c.execute("SELECT id FROM deals WHERE chat_id=? ORDER BY id DESC LIMIT 1", (chat_id,)).fetchone()
        if row:
            c.execute("DELETE FROM deals WHERE id=?", (row["id"],))
            return row["id"]
        return None


def chat_stats(chat_id):
    with _conn() as c:
        row = c.execute("SELECT * FROM stats WHERE chat_id=?", (chat_id,)).fetchone()
        return dict(row) if row else {"total_deals": 0, "total_volume": 0, "total_fees": 0}


def user_earnings(uid):
    with _conn() as c:
        rows = c.execute("SELECT fee FROM deals WHERE escrower_id=? AND status='closed'", (uid,)).fetchall()
        return sum(r["fee"] for r in rows)


def user_deals(uid, limit=10):
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM deals WHERE escrower_id=? ORDER BY id DESC LIMIT ?",
            (uid, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Settings ----------
def set_setting(key, value):
    with _conn() as c:
        c.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_setting(key, default=None):
    with _conn() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def all_settings():
    with _conn() as c:
        return {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings").fetchall()}
