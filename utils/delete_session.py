import shutil
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("/app/data/reelagent.sqlite")
MEDIA_DIR = Path("/app/media/sessions")


def main(sid: str) -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        for table, col in (("events", "session_id"), ("step_results", "session_id"), ("sessions", "id")):
            n = con.execute(f"DELETE FROM {table} WHERE {col}=?", (sid,)).rowcount
            print(f"{table}: {n}")
        con.commit()
    finally:
        con.close()

    session_dir = MEDIA_DIR / sid
    if session_dir.exists():
        shutil.rmtree(session_dir)
        print(f"removed {session_dir}")
    else:
        print(f"no media dir at {session_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python delete_session.py <session_id>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])
