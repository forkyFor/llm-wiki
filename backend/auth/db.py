"""SQLite user store — sync sqlite3 via run_in_executor."""
import asyncio
import sqlite3
from functools import partial
from pathlib import Path

from backend.config import settings

COOKIE_NAME = "llm_wiki_session"


def _db_path() -> Path:
    return settings.data_dir / "users.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db_sync() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT NOT NULL UNIQUE,
                hashed_pw  TEXT NOT NULL,
                is_admin   INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login TEXT
            )
        """)
        conn.commit()


def _get_user_by_username_sync(username: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def _get_user_by_id_sync(user_id: int) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


def _list_users_sync() -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM users ORDER BY created_at ASC"
        ).fetchall()


def _create_user_sync(username: str, hashed_pw: str, is_admin: bool) -> int:
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, hashed_pw, is_admin) VALUES (?, ?, ?)",
                (username, hashed_pw, 1 if is_admin else 0),
            )
            conn.commit()
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' already exists")


def _delete_user_sync(user_id: int) -> bool:
    with _connect() as conn:
        # Prevent deleting last admin
        admins = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_admin = 1"
        ).fetchone()[0]
        target = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target is None:
            return False
        if target["is_admin"] and admins <= 1:
            raise ValueError("Cannot delete the last admin account")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True


def _update_last_login_sync(user_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE users SET last_login = datetime('now') WHERE id = ?", (user_id,)
        )
        conn.commit()


async def _run(fn, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, *args))


async def init_db() -> None:
    await _run(_init_db_sync)


async def get_user_by_username(username: str) -> sqlite3.Row | None:
    return await _run(_get_user_by_username_sync, username)


async def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    return await _run(_get_user_by_id_sync, user_id)


async def list_users() -> list[sqlite3.Row]:
    return await _run(_list_users_sync)


async def create_user(username: str, hashed_pw: str, is_admin: bool) -> int:
    return await _run(_create_user_sync, username, hashed_pw, is_admin)


async def delete_user(user_id: int) -> bool:
    return await _run(_delete_user_sync, user_id)


async def update_last_login(user_id: int) -> None:
    await _run(_update_last_login_sync, user_id)
