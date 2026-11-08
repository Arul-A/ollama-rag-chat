import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")


def get_connection():
    """Returns a SQLite connection with row_factory set for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initializes the threads and messages tables if they do not exist."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'rag',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def get_all_threads():
    """Returns all chat threads ordered by most recently updated."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, mode, created_at, updated_at FROM threads ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def create_thread(thread_id: str, title: str, mode: str = "rag"):
    """Creates a new conversation thread."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO threads (id, title, mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, title, mode, datetime.now(), datetime.now())
        )
        conn.commit()
    return {"id": thread_id, "title": title, "mode": mode}


def get_thread_messages(thread_id: str):
    """Retrieves all messages for a given thread in chronological order."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, role, content, sources, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC, id ASC",
            (thread_id,)
        )
        rows = cursor.fetchall()
        results = []
        for r in rows:
            msg = dict(r)
            if msg["sources"]:
                try:
                    msg["sources"] = json.loads(msg["sources"])
                except Exception:
                    msg["sources"] = []
            else:
                msg["sources"] = []
            results.append(msg)
        return results


def add_message(thread_id: str, role: str, content: str, sources=None):
    """Adds a message to a thread and updates the thread's updated_at timestamp."""
    sources_json = json.dumps(sources) if sources else None
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, sources, created_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, role, content, sources_json, datetime.now())
        )
        conn.execute(
            "UPDATE threads SET updated_at = ? WHERE id = ?",
            (datetime.now(), thread_id)
        )
        conn.commit()


def update_thread_title(thread_id: str, title: str):
    """Updates the title of a conversation thread."""
    with get_connection() as conn:
        conn.execute("UPDATE threads SET title = ? WHERE id = ?", (title, thread_id))
        conn.commit()


def delete_thread(thread_id: str):
    """Deletes a thread and its messages."""
    with get_connection() as conn:
        conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
        conn.commit()
    return True


# Initialize database upon import
init_db()

