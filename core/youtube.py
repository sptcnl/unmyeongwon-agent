"""YouTube Data API v3 (무료 할당량) + 자막(youtube-transcript-api)."""
import os
import re
from datetime import datetime, timedelta, timezone

import requests

API = "https://www.googleapis.com/youtube/v3"
KST = timezone(timedelta(hours=9))


class YouTubeError(Exception):
    pass


def _get(path: str, **params) -> dict:
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise YouTubeError(".env 파일에 YOUTUBE_API_KEY가 없어요. README의 'API 키 받기'를 따라 넣어 주세요.")
    r = requests.get(f"{API}/{path}", params={**params, "key": key}, timeout=15)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = r.text[:200]
        raise YouTubeError(f"YouTube API 오류 ({r.status_code}): {msg}")
    return r.json()


def parse_video_id(text: str) -> str | None:
    text = (text or "").strip()
    if re.fullmatch(r"[\w-]{11}", text):
        return text
    m = re.search(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", text)
    return m.group(1) if m else None


def _hours_since(published_at: str) -> float:
    t = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    return max((datetime.now(timezone.utc) - t).total_seconds() / 3600, 0.1)


def video_details(ids: list[str]) -> list[dict]:
    """videos.list (1유닛) — 썸네일·제목·채널·날짜·조회수."""
    if not ids:
        return []
    data = _get("videos", part="snippet,statistics", id=",".join(ids[:50]), hl="ko")
    out = []
    for it in data.get("items", []):
        sn, st = it["snippet"], it.get("statistics", {})
        views = int(st.get("viewCount", 0))
        thumbs = sn.get("thumbnails", {})
        thumb = (thumbs.get("medium") or thumbs.get("high") or thumbs.get("default") or {}).get("url", "")
        out.append({
            "video_id": it["id"],
            "title": sn.get("title", ""),
            "channel": sn.get("channelTitle", ""),
            "published_at": sn.get("publishedAt", ""),
            "thumbnail": thumb,
            "description": sn.get("description", ""),
            "views": views,
            "views_per_hour": round(views / _hours_since(sn["publishedAt"]), 1),
        })
    order = {v: i for i, v in enumerate(ids)}
    return sorted(out, key=lambda v: order.get(v["video_id"], 0))


def search_latest(cfg: dict) -> list[dict]:
    """최신 '연애' 영상 (search.list 100유닛 + videos.list 1유닛)."""
    y = cfg["youtube"]
    data = _get("search", part="id", q=y["query"], type="video", order="date",
                regionCode=y["region"], relevanceLanguage=y["language"], maxResults=y["max_results"])
    ids = [it["id"]["videoId"] for it in data.get("items", [])]
    return video_details(ids)


def search_rising(cfg: dict) -> list[dict]:
    """뜨기 직전 영상: 최근 N시간 영상 중 조회수·시간당 조회수 조건은 config.yaml의 youtube.rising."""
    y, r = cfg["youtube"], cfg["youtube"]["rising"]
    after = (datetime.now(timezone.utc) - timedelta(hours=r["lookback_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = _get("search", part="id", q=y["query"], type="video", order="date",
                publishedAfter=after, regionCode=y["region"], relevanceLanguage=y["language"], maxResults=50)
    ids = [it["id"]["videoId"] for it in data.get("items", [])]
    vids = [v for v in video_details(ids)
            if r["min_views"] <= v["views"] <= r["max_views"] and v["views_per_hour"] >= r["min_views_per_hour"]]
    return sorted(vids, key=lambda v: v["views_per_hour"], reverse=True)


def top_comments(video_id: str, n: int = 15) -> list[str]:
    """인기 댓글 (commentThreads.list 1유닛). 댓글이 꺼진 영상이면 빈 목록."""
    try:
        data = _get("commentThreads", part="snippet", videoId=video_id, order="relevance",
                    maxResults=n, textFormat="plainText")
    except YouTubeError:
        return []
    out = []
    for it in data.get("items", []):
        s = it["snippet"]["topLevelComment"]["snippet"]
        out.append(f"{s.get('textDisplay', '').strip()[:150]} (좋아요 {s.get('likeCount', 0)})")
    return out


def transcript(video_id: str) -> str | None:
    """자막을 '[분:초] 문장' 형태로. 없으면 None."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):  # 1.x
            items = [(s.start, s.text) for s in api.fetch(video_id, languages=["ko", "en"])]
        else:  # 0.x
            items = [(d["start"], d["text"]) for d in YouTubeTranscriptApi.get_transcript(video_id, languages=["ko", "en"])]
    except Exception:
        return None
    lines = [f"[{int(t)//60}:{int(t)%60:02d}] {txt.strip()}" for t, txt in items if txt.strip()]
    return "\n".join(lines) or None


def excerpt(text: str, limit: int = 6000) -> str:
    """긴 자막은 앞·중간·끝만 잘라서 토큰(=구독 사용량) 절약."""
    if len(text) <= limit:
        return text
    a, b, c = int(limit * 0.45), int(limit * 0.3), int(limit * 0.25)
    mid = len(text) // 2
    return f"{text[:a]}\n…(중략)…\n{text[mid - b // 2: mid + b // 2]}\n…(중략)…\n{text[-c:]}"


def kst_date(published_at: str) -> str:
    if not published_at:
        return ""
    t = datetime.fromisoformat(published_at.replace("Z", "+00:00")).astimezone(KST)
    return t.strftime("%Y.%m.%d %H:%M")
