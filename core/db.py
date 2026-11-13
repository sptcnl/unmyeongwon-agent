"""SQLite 저장소 + 운영 규칙 강제 (영상당 댓글 1개, 하루 상한)."""
import json
import sqlite3
from datetime import datetime, timedelta

from .config import ROOT

DB_PATH = ROOT / "data" / "agent.db"

IN_PROGRESS = ("opening", "typing", "submitting")

SCHEMA = """
CREATE TABLE IF NOT EXISTS videos(
  video_id TEXT PRIMARY KEY, title TEXT, channel TEXT, published_at TEXT,
  thumbnail TEXT, description TEXT, views INTEGER, views_per_hour REAL, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS drafts(
  video_id TEXT PRIMARY KEY, worry TEXT, evidence TEXT, keywords TEXT, persona TEXT,
  comment TEXT, source TEXT, attempts INTEGER, created_at TEXT);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, profile TEXT NOT NULL,
  comment TEXT NOT NULL, status TEXT NOT NULL, reason TEXT, screenshot TEXT,
  comment_url TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
-- 규칙: 한 영상에는 (실패를 뺀) 댓글이 딱 하나만 존재할 수 있음 → DB가 직접 막음
CREATE UNIQUE INDEX IF NOT EXISTS one_comment_per_video ON posts(video_id) WHERE status != 'failed';
"""


class RuleError(Exception):
    """운영 규칙 위반."""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


# ---------- videos ----------
def upsert_videos(videos: list[dict]) -> None:
    with connect() as c:
        for v in videos:
            c.execute(
                """INSERT INTO videos VALUES(:video_id,:title,:channel,:published_at,:thumbnail,
                   :description,:views,:views_per_hour,:fetched_at)
                   ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, channel=excluded.channel,
                   thumbnail=excluded.thumbnail, description=excluded.description, views=excluded.views,
                   views_per_hour=excluded.views_per_hour, fetched_at=excluded.fetched_at""",
                {**v, "fetched_at": now()},
            )


def get_video(video_id: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM videos WHERE video_id=?", (video_id,)).fetchone()
        return dict(r) if r else None


# ---------- drafts ----------
def save_draft(video_id: str, d: dict) -> None:
    with connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO drafts VALUES(?,?,?,?,?,?,?,?,?)",
            (video_id, d["worry"], d["evidence"], json.dumps(d["keywords"], ensure_ascii=False),
             d.get("persona", ""), d["comment"], d["source"], d.get("attempts", 1), now()),
        )


def get_draft(video_id: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM drafts WHERE video_id=?", (video_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["keywords"] = json.loads(d["keywords"] or "[]")
    return d


def recent_comments(exclude_video: str | None = None, n: int = 10) -> list[str]:
    """새 초안이 기존 댓글과 겹치지 않게 비교할 대상."""
    with connect() as c:
        rows = c.execute(
            """SELECT comment FROM (
                 SELECT video_id, comment, created_at FROM posts WHERE status='posted'
                 UNION ALL SELECT video_id, comment, created_at FROM drafts)
               WHERE video_id != ? ORDER BY created_at DESC LIMIT ?""",
            (exclude_video or "", n),
        ).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["comment"] not in seen:
            seen.add(r["comment"])
            out.append(r["comment"])
    return out


# ---------- posts (규칙 강제) ----------
def today_count(c: sqlite3.Connection | None = None) -> int:
    """오늘 게시했거나 게시 중인 댓글 수 (실패 제외)."""
    today = datetime.now().date().isoformat()
    q = "SELECT COUNT(*) FROM posts WHERE status != 'failed' AND substr(created_at,1,10)=?"
    if c:
        return c.execute(q, (today,)).fetchone()[0]
    with connect() as c2:
        return c2.execute(q, (today,)).fetchone()[0]


def profile_today_counts() -> dict[str, int]:
    today = datetime.now().date().isoformat()
    with connect() as c:
        rows = c.execute(
            """SELECT profile, COUNT(*) n FROM posts WHERE status != 'failed'
               AND substr(created_at,1,10)=? GROUP BY profile""", (today,)).fetchall()
    return {r["profile"]: r["n"] for r in rows}


def active_post_for_video(video_id: str) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM posts WHERE video_id=? AND status != 'failed'", (video_id,)).fetchone()
        return dict(r) if r else None


def create_post(video_id: str, profile: str, comment: str, daily_max: int) -> int:
    """규칙을 확인하고 게시 기록을 만든다. 위반이면 RuleError."""
    c = connect()
    try:
        c.execute("BEGIN IMMEDIATE")  # 동시에 두 번 눌러도 하나만 통과
        if c.execute("SELECT 1 FROM posts WHERE status IN ('opening','typing','submitting')").fetchone():
            raise RuleError("다른 댓글을 게시하는 중이에요. 끝난 뒤 다시 눌러 주세요.")
        if c.execute("SELECT 1 FROM posts WHERE video_id=? AND status != 'failed'", (video_id,)).fetchone():
            raise RuleError("이 영상에는 이미 댓글을 달았어요. (영상당 댓글 1개)")
        n = today_count(c)
        if n >= daily_max:
            raise RuleError(f"오늘 게시 상한({daily_max}개)에 도달했어요. 내일 다시 시도해 주세요.")
        t = now()
        cur = c.execute(
            "INSERT INTO posts(video_id,profile,comment,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (video_id, profile, comment, "opening", t, t),
        )
        c.execute("COMMIT")
        return cur.lastrowid
    except sqlite3.IntegrityError:
        c.execute("ROLLBACK")
        raise RuleError("이 영상에는 이미 댓글을 달았어요. (영상당 댓글 1개)")
    except Exception:
        if c.in_transaction:
            c.execute("ROLLBACK")
        raise
    finally:
        c.close()


def update_post(post_id: int, **fields) -> None:
    fields["updated_at"] = now()
    cols = ", ".join(f"{k}=?" for k in fields)
    with connect() as c:
        c.execute(f"UPDATE posts SET {cols} WHERE id=?", (*fields.values(), post_id))


def get_post(post_id: int) -> dict | None:
    with connect() as c:
        r = c.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        return dict(r) if r else None


def list_posts(limit: int = 200) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            """SELECT p.*, v.title FROM posts p LEFT JOIN videos v ON v.video_id=p.video_id
               ORDER BY p.id DESC LIMIT ?""", (limit,)).fetchall()
        return [dict(r) for r in rows]


def fail_stale_posts(minutes: int = 10) -> None:
    """프로그램이 중간에 꺼져서 '진행 중'으로 남은 기록을 실패 처리 (영상이 영원히 막히지 않게)."""
    cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with connect() as c:
        c.execute(
            "UPDATE posts SET status='failed', reason='중간에 중단됨', updated_at=? "
            "WHERE status IN ('opening','typing','submitting') AND updated_at < ?",
            (now(), cutoff),
        )
