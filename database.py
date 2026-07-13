"""
database.py
------------
All persistence for the bot lives here (SQLite).

Why SQLite + a JSON backup file?
- SQLite (`bot_data.db`) is the source of truth. It survives the bot
  crashing or being restarted by Render, because the file stays on disk
  for the life of that running instance.
- On every write we also refresh `backup.json`. If `bot_data.db` is ever
  missing or corrupted when the bot boots (e.g. a fresh container after
  a redeploy on a plan without a persistent disk), we auto-restore from
  `backup.json` so you don't start from zero.
- If you upgrade to Render's persistent disk or a hosted Postgres later,
  only this file needs to change — the rest of the bot calls these
  functions and doesn't care how storage works underneath.
"""

import sqlite3
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_data.db")
BACKUP_PATH = os.path.join(os.path.dirname(__file__), "backup.json")

_lock = threading.Lock()


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist, then restore from backup.json
    if the database is empty (fresh container / first boot after crash)."""
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT,
                is_banned INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'open',
                admin_reply TEXT,
                replied_at TEXT
            );
            """
        )
        # Safe migration for anyone with an older bot_data.db already on disk
        # (a fresh CREATE TABLE above won't retroactively add columns).
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(feedback)").fetchall()}
        if "admin_reply" not in existing_cols:
            conn.execute("ALTER TABLE feedback ADD COLUMN admin_reply TEXT")
        if "replied_at" not in existing_cols:
            conn.execute("ALTER TABLE feedback ADD COLUMN replied_at TEXT")

    _maybe_restore_from_backup()


def _maybe_restore_from_backup():
    """If users table is empty but a backup.json exists, restore it."""
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count > 0 or not os.path.exists(BACKUP_PATH):
        return

    try:
        with open(BACKUP_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    with _conn() as conn:
        for u in data.get("users", []):
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, username, first_name, joined_at, is_banned) "
                "VALUES (?, ?, ?, ?, ?)",
                (u["user_id"], u.get("username"), u.get("first_name"), u.get("joined_at"), u.get("is_banned", 0)),
            )
        for a in data.get("admins", []):
            conn.execute("INSERT OR REPLACE INTO admins (user_id) VALUES (?)", (a,))
        for k, v in data.get("settings", {}).items():
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
        for fb in data.get("feedback", []):
            conn.execute(
                "INSERT OR REPLACE INTO feedback (id, user_id, message, created_at, status, admin_reply, replied_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    fb["id"],
                    fb["user_id"],
                    fb["message"],
                    fb["created_at"],
                    fb.get("status", "open"),
                    fb.get("admin_reply"),
                    fb.get("replied_at"),
                ),
            )
    print("[database] Restored data from backup.json")


def backup_to_json():
    """Dump the whole DB to backup.json. Called after every write."""
    with _lock:
        with _conn() as conn:
            users = [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]
            admins = [r["user_id"] for r in conn.execute("SELECT user_id FROM admins").fetchall()]
            settings = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings").fetchall()}
            feedback = [dict(r) for r in conn.execute("SELECT * FROM feedback").fetchall()]

        tmp_path = BACKUP_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(
                {"users": users, "admins": admins, "settings": settings, "feedback": feedback},
                f,
                ensure_ascii=False,
                indent=2,
            )
        os.replace(tmp_path, BACKUP_PATH)  # atomic, avoids a half-written backup


# ---------- users ----------

def upsert_user(user_id: int, username: str | None, first_name: str | None):
    with _conn() as conn:
        existing = conn.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                (username, first_name, user_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?, ?, ?, ?)",
                (user_id, username, first_name, datetime.utcnow().isoformat()),
            )
    backup_to_json()


def get_all_user_ids() -> list[int]:
    with _conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM users WHERE is_banned = 0").fetchall()]


def get_stats() -> dict:
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        banned = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1").fetchone()[0]
        admins = conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
    return {"active_users": total - banned, "banned_users": banned, "administrators": admins}


def ban_user(user_id: int):
    with _conn() as conn:
        conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    backup_to_json()


def unban_user(user_id: int):
    with _conn() as conn:
        conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    backup_to_json()


def is_banned(user_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return bool(row and row["is_banned"])


# ---------- admins ----------

def add_admin(user_id: int):
    with _conn() as conn:
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    backup_to_json()


def remove_admin(user_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    backup_to_json()


def is_admin(user_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    return row is not None


def list_admins() -> list[int]:
    with _conn() as conn:
        return [r["user_id"] for r in conn.execute("SELECT user_id FROM admins").fetchall()]


# ---------- settings (welcome text, links, force-join channel, etc.) ----------

def set_setting(key: str, value: str):
    with _conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    backup_to_json()


def get_setting(key: str, default: str | None = None) -> str | None:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


# ---------- feedback / support tickets ----------

def add_feedback(user_id: int, message: str) -> int:
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO feedback (user_id, message, created_at) VALUES (?, ?, ?)",
            (user_id, message, datetime.utcnow().isoformat()),
        )
        fid = cur.lastrowid
    backup_to_json()
    return fid


def close_feedback(feedback_id: int):
    with _conn() as conn:
        conn.execute("UPDATE feedback SET status = 'closed' WHERE id = ?", (feedback_id,))
    backup_to_json()


def set_feedback_reply(feedback_id: int, reply_text: str):
    """Attach the admin's reply to a ticket and mark it as replied."""
    with _conn() as conn:
        conn.execute(
            "UPDATE feedback SET status = 'replied', admin_reply = ?, replied_at = ? WHERE id = ?",
            (reply_text, datetime.utcnow().isoformat(), feedback_id),
        )
    backup_to_json()


def get_feedback_by_user(user_id: int) -> list[dict]:
    """All tickets a user has ever raised, most recent first."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_feedback(feedback_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    return dict(row) if row else None
