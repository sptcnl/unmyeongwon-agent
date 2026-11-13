import json
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


PROFILE_NAME = re.compile(r"[0-9A-Za-z가-힣 _-]{1,20}")


def _profiles_block(lines: list[str]) -> tuple[int, int]:
    """config.yaml 줄 목록에서 profiles: 블록의 (시작 줄, 마지막 항목 줄) 위치."""
    start = next((i for i, l in enumerate(lines) if l.startswith("profiles:")), None)
    if start is None:
        raise ValueError("config.yaml에서 profiles: 를 찾지 못했어요.")
    end = start
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == "" or lines[i].lstrip().startswith("#"):
            continue
        if not lines[i].startswith((" ", "\t")):
            break
        end = i
    return start, end


def _save_config_text(text: str, check) -> None:
    """바꾼 내용이 YAML로 제대로 읽히는지 확인한 뒤에만 저장 (주석은 그대로 유지됨)."""
    if not check(yaml.safe_load(text)):
        raise ValueError("config.yaml 수정 결과가 예상과 달라 저장하지 않았어요.")
    (ROOT / "config.yaml").write_text(text, encoding="utf-8")


def add_profile(name: str) -> dict:
    """config.yaml의 profiles 끝에 새 프로필 추가. 폴더는 아직 안 쓴 chrome_profiles/ytN."""
    name = (name or "").strip()
    if not PROFILE_NAME.fullmatch(name):
        raise ValueError("이름은 한글·영문·숫자·공백·-·_ 로 20자 이내로 지어 주세요.")
    cfg = load_config()
    if any(p["name"] == name for p in cfg["profiles"]):
        raise ValueError(f"'{name}' 프로필이 이미 있어요.")
    used = {str(profile_dir(p)) for p in cfg["profiles"]}
    n = 1
    while str((ROOT / f"chrome_profiles/yt{n}").resolve()) in used or (ROOT / f"chrome_profiles/yt{n}").exists():
        n += 1  # 예전에 지운 프로필 폴더(옛 로그인 정보)는 재사용하지 않음
    new = {"name": name, "dir": f"chrome_profiles/yt{n}"}
    lines = (ROOT / "config.yaml").read_text(encoding="utf-8").split("\n")
    _, end = _profiles_block(lines)
    lines[end + 1:end + 1] = [f"  - name: {name}", f"    dir: {new['dir']}"]
    _save_config_text("\n".join(lines), lambda c: c["profiles"] == cfg["profiles"] + [new])
    return new


def remove_profile(name: str) -> None:
    """config.yaml에서 프로필 삭제. 로그인 정보 폴더는 지우지 않고 남겨 둠."""
    cfg = load_config()
    if len(cfg["profiles"]) <= 1:
        raise ValueError("프로필은 최소 1개는 있어야 해요.")
    target = next((p for p in cfg["profiles"] if p["name"] == name), None)
    if not target:
        raise ValueError(f"'{name}' 프로필이 없어요.")
    lines = (ROOT / "config.yaml").read_text(encoding="utf-8").split("\n")
    start, end = _profiles_block(lines)
    i = next((i for i in range(start + 1, end + 1)
              if re.fullmatch(r"\s*-\s*name:\s*['\"]?" + re.escape(name) + r"['\"]?\s*(#.*)?", lines[i])), None)
    if i is None:
        raise ValueError("config.yaml에서 이 프로필 줄을 찾지 못했어요. 직접 지워 주세요.")
    j = i + 1  # 같은 항목의 나머지 줄(dir 등)까지
    while j <= end and lines[j].strip() and not lines[j].lstrip().startswith("-"):
        j += 1
    del lines[i:j]
    rest = [p for p in cfg["profiles"] if p["name"] != name]
    _save_config_text("\n".join(lines), lambda c: c["profiles"] == rest)


def profile_dir(profile: dict) -> Path:
    return (ROOT / profile["dir"]).resolve()


def profile_open(profile: dict) -> bool:
    """이 프로필로 크롬 창이 열려 있는지. 크롬은 실행 중에 lockfile을 잠가 둠 (꺼지면 지우거나 잠금 해제)."""
    lock = profile_dir(profile) / "lockfile"
    if not lock.exists():
        return False
    try:
        with open(lock, "a"):
            return False  # 파일만 남은 것 (크롬이 비정상 종료됨)
    except OSError:
        return True


def _has_login_cookie(d: Path) -> bool | None:
    """유튜브 로그인 쿠키(LOGIN_INFO)가 있는지. 값은 암호화돼 있지만 이름·만료시각은 평문. 못 읽으면 None."""
    src = next((p for p in (d / "Default" / "Network" / "Cookies", d / "Default" / "Cookies") if p.exists()), None)
    if not src:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:  # 크롬이 쓰는 중일 수 있어서 복사본을 읽음
            dst = Path(tmp) / "Cookies"
            shutil.copy(src, dst)
            con = sqlite3.connect(dst)
            try:
                now_chrome = int((time.time() + 11644473600) * 1_000_000)  # 크롬 시각 = 1601년 기준 마이크로초
                n = con.execute(
                    "SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%youtube.com' AND name='LOGIN_INFO'"
                    " AND (expires_utc = 0 OR expires_utc > ?)", (now_chrome,)).fetchone()[0]
            finally:
                con.close()
        return n > 0
    except (OSError, sqlite3.Error):
        return None


def profile_account(profile: dict) -> str:
    """크롬에 로그인한 구글 계정 (이메일). 크롬 자체 로그인 없이 유튜브만 로그인했으면 빈 문자열."""
    try:
        prefs = json.loads((profile_dir(profile) / "Default" / "Preferences").read_text(encoding="utf-8"))
        return next((a.get("email", "") for a in prefs.get("account_info", []) if a.get("email")), "")
    except (OSError, ValueError):
        return ""


def profile_ready(profile: dict) -> bool:
    """유튜브에 로그인된 프로필인지 (쿠키로 확인). 쿠키를 못 읽으면 예전처럼 폴더가 있는지로 판단."""
    d = profile_dir(profile)
    if not d.exists():
        return False
    ok = _has_login_cookie(d)
    return any(d.iterdir()) if ok is None else ok
