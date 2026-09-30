"""เก็บโพสต์/ข้อความที่ดึงมาแล้วไว้ใน SQLite
ทำให้สั่ง /news ซ้ำไม่ต้องจ่ายค่า X API สำหรับโพสต์เดิมอีกรอบ"""
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS x_users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    user_id  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS x_posts (
    id         INTEGER PRIMARY KEY,
    user_id    TEXT NOT NULL,
    username   TEXT NOT NULL,
    created_ts INTEGER NOT NULL,
    text       TEXT NOT NULL,
    url        TEXT NOT NULL,
    likes      INTEGER DEFAULT 0,
    reposts    INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS discord_msgs (
    id           INTEGER PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    author       TEXT NOT NULL,
    created_ts   INTEGER NOT NULL,
    text         TEXT NOT NULL,
    url          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_x_user ON x_posts(user_id, created_ts);
CREATE INDEX IF NOT EXISTS idx_dc_ch ON discord_msgs(channel_id, created_ts);
"""


@contextmanager
def _db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- X ----------
def get_user_id(username: str) -> str | None:
    with _db() as c:
        row = c.execute("SELECT user_id FROM x_users WHERE username=?", (username,)).fetchone()
        return row["user_id"] if row else None


def save_user(username: str, user_id: str) -> None:
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO x_users VALUES (?,?)", (username, user_id))


def latest_post(user_id: str) -> tuple[int, int] | None:
    """คืน (post_id, created_ts) ของโพสต์ล่าสุดที่เคยเก็บไว้"""
    with _db() as c:
        row = c.execute(
            "SELECT id, created_ts FROM x_posts WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return (row["id"], row["created_ts"]) if row else None


def save_posts(posts: list[dict]) -> None:
    with _db() as c:
        c.executemany(
            "INSERT OR IGNORE INTO x_posts VALUES "
            "(:id,:user_id,:username,:created_ts,:text,:url,:likes,:reposts)",
            posts,
        )


def posts_since(user_ids: list[str], since_ts: int) -> list[dict]:
    if not user_ids:
        return []
    marks = ",".join("?" * len(user_ids))
    with _db() as c:
        rows = c.execute(
            f"SELECT * FROM x_posts WHERE user_id IN ({marks}) AND created_ts>=? "
            "ORDER BY created_ts",
            (*user_ids, since_ts),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Discord ----------
def latest_msg_id(channel_id: str) -> int | None:
    with _db() as c:
        row = c.execute(
            "SELECT MAX(id) AS m FROM discord_msgs WHERE channel_id=?", (channel_id,)
        ).fetchone()
        return row["m"] if row and row["m"] is not None else None


def save_msgs(msgs: list[dict]) -> None:
    with _db() as c:
        c.executemany(
            "INSERT OR IGNORE INTO discord_msgs VALUES "
            "(:id,:channel_id,:channel_name,:author,:created_ts,:text,:url)",
            msgs,
        )


def msgs_since(channel_ids: list[str], since_ts: int) -> list[dict]:
    if not channel_ids:
        return []
    marks = ",".join("?" * len(channel_ids))
    with _db() as c:
        rows = c.execute(
            f"SELECT * FROM discord_msgs WHERE channel_id IN ({marks}) AND created_ts>=? "
            "ORDER BY created_ts",
            (*channel_ids, since_ts),
        ).fetchall()
        return [dict(r) for r in rows]
