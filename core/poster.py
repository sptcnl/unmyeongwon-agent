"""댓글 게시기. 대시보드가 별도 프로세스로 실행: python -m core.poster <post_id>
진행 상태(opening → typing → submitting → posted / failed)를 DB에 기록하고 대시보드가 읽어 표시."""
import random
import sys
import traceback
from datetime import datetime

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from . import db
from .browser import launch
from .config import ROOT, load_config

SHOT_DIR = ROOT / "logs" / "screens"


class PostError(Exception):
    pass


def _shot(page, post_id: int, tag: str) -> str | None:
    try:
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_post{post_id}_{tag}.png"
        page.screenshot(path=str(path))
        return str(path)
    except Exception:
        return None


def _open_comment_box(page):
    """댓글 영역이 나올 때까지 스크롤 → '댓글 추가...' 클릭."""
    page.evaluate("() => { const v = document.querySelector('video'); if (v) { v.pause(); v.muted = true; } }")
    placeholder = page.locator("#simplebox-placeholder").first
    for _ in range(20):
        if page.get_by_text("댓글이 사용 중지", exact=False).count() or \
           page.get_by_text("댓글 사용이 중지", exact=False).count():
            raise PostError("이 영상은 댓글이 사용 중지되어 있어요.")
        if placeholder.count() and placeholder.is_visible():
            break
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(800)
    else:
        raise PostError("댓글 입력창을 찾지 못했어요. (유튜브 화면 구조가 바뀌었거나 로딩 실패)")
    placeholder.scroll_into_view_if_needed()
    page.wait_for_timeout(500)
    placeholder.click()
    box = page.locator("#contenteditable-root").first
    box.wait_for(state="visible", timeout=10000)
    box.click()
    return box


def _type_like_human(page, text: str, delay_range: list[int]):
    lo, hi = delay_range
    for ch in text:
        page.keyboard.type(ch)  # 한글도 한 글자씩 입력됨
        page.wait_for_timeout(random.randint(lo, hi))


def _verify(page, comment: str) -> str | None:
    """내 댓글이 목록에 보이는지 확인하고, 댓글 고유 링크를 돌려준다."""
    snippet = comment.strip()[:14]
    mine = page.locator("#comments #content-text", has_text=snippet).first
    mine.wait_for(state="visible", timeout=20000)
    mine.scroll_into_view_if_needed()
    mine.evaluate("el => { el.style.outline = '3px solid #ff3b6b'; el.style.borderRadius = '6px'; }")
    try:
        thread = mine.locator("xpath=ancestor::ytd-comment-thread-renderer[1]")
        href = thread.locator("#published-time-text a").first.get_attribute("href", timeout=3000)
        if href:
            return href if href.startswith("http") else "https://www.youtube.com" + href
    except Exception:
        pass
    return None


def run(post_id: int) -> None:
    cfg = load_config()
    post = db.get_post(post_id)
    profile = next(p for p in cfg["profiles"] if p["name"] == post["profile"])
    video_url = f"https://www.youtube.com/watch?v={post['video_id']}&hl=ko"
    page = None
    with sync_playwright() as p:
        try:
            ctx = launch(p, profile, cfg)
        except Exception as e:
            db.update_post(post_id, status="failed",
                           reason=f"크롬 프로필을 열지 못했어요. 같은 프로필 창이 열려 있으면 닫아 주세요. ({str(e)[:150]})")
            return
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(video_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            if page.locator("ytd-masthead a[href*='accounts.google.com/ServiceLogin']").count():
                raise PostError(f"{post['profile']} 프로필이 로그인되어 있지 않아요. setup_profile.py로 로그인해 주세요.")

            box = _open_comment_box(page)
            db.update_post(post_id, status="typing")
            _type_like_human(page, post["comment"], cfg["chrome"].get("typing_delay_ms", [60, 160]))
            page.wait_for_timeout(800)

            if cfg["chrome"].get("dry_run"):
                shot = _shot(page, post_id, "dryrun")
                db.update_post(post_id, status="failed", reason="리허설 모드 — 게시 버튼은 누르지 않음", screenshot=shot)
                page.wait_for_timeout(3000)
                return

            db.update_post(post_id, status="submitting")
            page.locator("ytd-commentbox #submit-button").first.click()
            url = _verify(page, post["comment"]) or video_url
            shot = _shot(page, post_id, "posted")
            db.update_post(post_id, status="posted", comment_url=url, screenshot=shot, reason=None)
            try:
                page.wait_for_timeout(4000)  # 시연 영상에서 게시된 댓글이 보이게 잠깐 유지
            except Exception:
                pass  # 이미 게시 완료 — 이 사이에 창이 닫혀도 결과는 그대로 '게시 완료'
        except PostError as e:
            db.update_post(post_id, status="failed", reason=str(e), screenshot=_shot(page, post_id, "fail") if page else None)
        except PWTimeout:
            db.update_post(post_id, status="failed",
                           reason="시간 초과 — 게시 후 내 댓글이 목록에 보이지 않았거나 페이지 로딩이 느렸어요.",
                           screenshot=_shot(page, post_id, "fail") if page else None)
        except Exception as e:
            traceback.print_exc()
            if db.get_post(post_id)["status"] == "posted":
                return  # 게시 완료 기록을 실패로 덮어쓰지 않음 (영상당 1개 규칙이 풀리는 것 방지)
            if "has been closed" in str(e):
                reason = "크롬 창이 중간에 닫혔어요. 게시가 끝날 때까지 창을 닫지 말아 주세요."
            else:
                reason = f"예상 못 한 오류: {str(e)[:200]}"
            db.update_post(post_id, status="failed", reason=reason,
                           screenshot=_shot(page, post_id, "fail") if page else None)
        finally:
            try:
                ctx.close()
            except Exception:
                pass


if __name__ == "__main__":
    run(int(sys.argv[1]))
