import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = Path("/app/data/reelagent.sqlite")


def main(sid: str, title: str) -> None:
    con = sqlite3.connect(DB_PATH)
    try:
        n = con.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
            (title, int(time.time()), sid),
        ).rowcount
        con.commit()
        print(f"sessions: {n}")
    finally:
        con.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python update_title.py <session_id> <title>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
