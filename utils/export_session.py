import json
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("/app/data/reelagent.sqlite")
MEDIA_DIR = Path("/app/media/sessions")


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}


def _maybe_json(s: str | None):
    if s is None:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return s


def main(sid: str, out_path: str | None = None) -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        session_row = con.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not session_row:
            print(f"no session {sid}", file=sys.stderr)
            sys.exit(1)
        session = _row_to_dict(session_row)

        events = [
            {**_row_to_dict(r), "payload": _maybe_json(r["payload"])}
            for r in con.execute(
                "SELECT * FROM events WHERE session_id=? ORDER BY seq ASC", (sid,)
            ).fetchall()
        ]

        step_results = [
            {**_row_to_dict(r), "result": _maybe_json(r["result"])}
            for r in con.execute(
                "SELECT * FROM step_results WHERE session_id=? ORDER BY created_at ASC",
                (sid,),
            ).fetchall()
        ]

        transcript = None
        transcript_row = con.execute(
            "SELECT transcript FROM transcript_cache WHERE youtube_url=? "
            "AND clip_start_sec=? AND clip_end_sec=?",
            (
                session["youtube_url"],
                session.get("clip_start_sec") if session.get("clip_start_sec") is not None else -1.0,
                session.get("clip_end_sec") if session.get("clip_end_sec") is not None else -1.0,
            ),
        ).fetchone()
        if transcript_row:
            transcript = _maybe_json(transcript_row["transcript"])
        if transcript is None:
            for sr in step_results:
                if sr["step_key"] == "transcribe":
                    transcript = sr["result"]
                    break
    finally:
        con.close()

    session_dir = MEDIA_DIR / sid
    plan = None
    plan_path = session_dir / "plan.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())

    media_files = []
    if session_dir.exists():
        for p in sorted(session_dir.rglob("*")):
            if p.is_file():
                media_files.append({
                    "path": str(p.relative_to(session_dir)),
                    "size": p.stat().st_size,
                })

    trajectory = {
        "session": session,
        "plan": plan,
        "transcript": transcript,
        "step_results": step_results,
        "events": events,
        "media_files": media_files,
    }

    out = Path(out_path) if out_path else Path(f"trajectory_{sid}.json")
    out.write_text(json.dumps(trajectory, indent=2, ensure_ascii=False))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    print(f"  events: {len(events)}  step_results: {len(step_results)}  "
          f"plan: {'yes' if plan else 'no'}  transcript: {'yes' if transcript else 'no'}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        print("usage: python export_session.py <session_id> [out.json]", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) == 3 else None)
