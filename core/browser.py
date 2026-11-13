"""크롬 프로필 폴더를 지정해서 여는 공통 함수 (Playwright launch_persistent_context = --user-data-dir).
로그인(setup_profile.py)과 게시(poster.py)가 같은 방식으로 열어야 쿠키가 그대로 유지돼요."""
from .config import profile_dir


def launch(p, profile: dict, cfg: dict):
    d = profile_dir(profile)
    d.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(d),
        headless=False,                     # 화면에 보이게
        locale="ko-KR",
        no_viewport=True,
        args=["--lang=ko-KR", "--start-maximized", "--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],  # '자동화 제어 중' 표시 제거 → 구글 로그인 차단 완화
    )
    channel = (cfg.get("chrome") or {}).get("channel")
    if channel:
        kwargs["channel"] = channel
    return p.chromium.launch_persistent_context(**kwargs)
