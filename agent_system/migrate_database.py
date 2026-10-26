"""Offline migration into the configured SQLite/PostgreSQL database."""
import argparse
import sqlite3
from pathlib import Path
from urllib.parse import quote
from agent_system.core.database import get_database
from agent_system.core.storage import SupabaseStorage


def from_sqlite(source_path):
    target = get_database()
    with sqlite3.connect("file:" + quote(Path(source_path).resolve().as_posix(), safe="/:") + "?mode=ro", uri=True) as source:
        documents = source.execute("SELECT key,data FROM naml_documents").fetchall()
        sessions = source.execute("SELECT session_id,user_id,created_at,status,data FROM naml_sessions").fetchall()
    with target.connection(write=True) as conn:
        for key, data in documents:
            if key.startswith("legacy_import:"):
                continue
            target.lock(conn, key)
            if target._get(conn, key) is not None:
                raise ValueError("Target database already contains application data. Use an empty target; nothing was overwritten.")
            target.execute(conn, "INSERT INTO naml_documents (key,data) VALUES (?,?)", (key, data))
        for row in sessions:
            target.execute(conn, "INSERT INTO naml_sessions (session_id,user_id,created_at,status,data) VALUES (?,?,?,?,?)", row)
    return len(sessions)


def from_supabase():
    # Local settings/users are imported automatically from the old storage dir.
    source = SupabaseStorage()
    target = get_database()
    offset = 0
    imported = 0
    while True:
        response = source._requests.get(source.endpoint, headers=source.headers, params={"select": "data", "order": "session_id.asc", "offset": offset, "limit": 1000}, timeout=30)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break
        for row in rows:
            if row.get("data"):
                imported += int(target.import_session(row["data"]))
        offset += len(rows)
    return imported


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--from-sqlite", metavar="PATH")
    group.add_argument("--from-supabase", action="store_true")
    args = parser.parse_args()
    count = from_sqlite(args.from_sqlite) if args.from_sqlite else from_supabase()
    print(f"Migration complete: {count} analyses imported. Source data was not modified.")
