"""크롬 프로필 처음 설정: 창이 열리면 구글 계정으로 로그인하고 창을 닫으세요.
사용법:  python setup_profile.py 유튜브1"""
import sys

from playwright.sync_api import sync_playwright

from core.browser import launch
from core.config import load_config


def main():
    cfg = load_config()
    names = [p["name"] for p in cfg["profiles"]]
    name = sys.argv[1] if len(sys.argv) > 1 else names[0]
    profile = next((p for p in cfg["profiles"] if p["name"] == name), None)
    if not profile:
        sys.exit(f"프로필 이름을 확인해 주세요: {', '.join(names)}")

    print(f"[{name}] 크롬 창이 열립니다.")
    print(" 1) 오른쪽 위 '로그인'을 눌러 이 프로필에 쓸 구글 계정으로 로그인")
    print(" 2) 유튜브 화면이 한국어인지 확인 (아니면 프로필 사진 > 언어 > 한국어)")
    print(" 3) 끝나면 크롬 창을 닫으세요. 로그인 상태가 저장됩니다.")
    with sync_playwright() as p:
        ctx = launch(p, profile, cfg)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.youtube.com/?hl=ko")
        ctx.wait_for_event("close", timeout=0)
    print(f"[{name}] 저장 완료.")


if __name__ == "__main__":
    main()
