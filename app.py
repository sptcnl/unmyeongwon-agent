"""운명원 유튜브 댓글 에이전트 대시보드.  실행: streamlit run app.py"""
import subprocess
import sys
import time

import pandas as pd
import streamlit as st

from core import db, llm, validate, writer, youtube
from core.config import (ROOT, add_profile, load_config, profile_account, profile_open, profile_ready,
                         remove_profile)

st.set_page_config(page_title="운명원 댓글 에이전트", page_icon="💬", layout="wide")
st.markdown("""<style>
.block-container {padding-top: 1.6rem;}
.step {font-size: 1.15rem; font-weight: 700; margin-bottom: .3rem;}
.hint {color: #888; font-size: .85rem; margin-bottom: .6rem;}
.worry {background: #fff1f4; border-left: 4px solid #ff3b6b; padding: .6rem .8rem; border-radius: 6px; font-weight: 600; color: #222;}
</style>""", unsafe_allow_html=True)

cfg = load_config()
db.fail_stale_posts()
ss = st.session_state
ss.setdefault("video_ids", [])
ss.setdefault("selected", None)
ss.setdefault("last_post", None)

STATUS = {
    "opening": "🟡 프로필 여는 중", "typing": "⌨️ 입력 중", "submitting": "📨 게시 중",
    "posted": "✅ 게시 완료", "failed": "❌ 실패",
}
DAILY_MAX = cfg["limits"]["daily_max_comments"]
logged_in = {p["name"]: profile_ready(p) for p in cfg["profiles"]}
open_now = {p["name"]: profile_open(p) for p in cfg["profiles"]}
# 로그인돼 있고, 지금 다른 크롬 창(로그인 창 등)에서 쓰고 있지 않은 프로필만 게시에 사용
ready_profiles = [n for n in logged_in if logged_in[n] and not open_now[n]]

# ---------- 상단 ----------
h1, h2, h3 = st.columns([2.2, 1, 1])
h1.title("💬 운명원 유튜브 댓글 에이전트")
h1.caption("① 영상 불러오기 → ② 영상 고르기 → ③ 댓글 달기. 순서대로 누르기만 하면 돼요.")
h2.metric("오늘 게시", f"{db.today_count()} / {DAILY_MAX}")
h3.metric("사용 가능한 프로필", f"{len(ready_profiles)}개", help=", ".join(ready_profiles) or "아래 [유튜브 계정 연결]에서 로그인해 주세요")

# ---------- 유튜브 계정 연결 ----------
with st.expander(f"👤 유튜브 계정 연결 ({sum(logged_in.values())}/{len(logged_in)}개 로그인됨)",
                 expanded=not ready_profiles):
    st.caption("[로그인 창 열기] → 열린 크롬에서 구글 로그인 → 유튜브가 한국어인지 확인 → **크롬 창 닫기** → [상태 새로고침]. "
               "계정마다 한 번만 하면 돼요. 평소 쓰는 크롬과는 따로 저장돼요.")
    for p in cfg["profiles"]:
        name = p["name"]
        a, b, c, d = st.columns([1, 2.4, 1.2, 0.5], vertical_alignment="center")
        a.markdown(f"**{name}**")
        if open_now[name]:
            b.markdown("🟢 크롬 창 열려 있음 — 로그인 끝나면 창을 닫아 주세요")
        elif logged_in[name]:
            acct = profile_account(p)
            b.markdown("✅ 로그인됨" + (f" · {acct}" if acct else ""))
        else:
            b.markdown("⚠️ 로그인 필요")
        label = "다른 계정으로 다시 로그인" if logged_in[name] else "로그인 창 열기"
        if c.button(label, key=f"login_{name}", use_container_width=True, disabled=open_now[name]):
            log_dir = ROOT / "logs"
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / f"login_{p['dir'].replace('/', '_')}.log", "w", encoding="utf-8") as lf:
                subprocess.Popen([sys.executable, "setup_profile.py", name], cwd=ROOT,
                                 stdout=lf, stderr=subprocess.STDOUT)
            time.sleep(3)  # 크롬이 뜰 때까지 잠깐 기다렸다가 상태 갱신
            st.rerun()
        with d.popover("🗑", use_container_width=True, disabled=open_now[name] or len(cfg["profiles"]) <= 1):
            st.markdown(f"**{name}** 프로필을 목록에서 뺄까요?")
            st.caption(f"로그인 정보 폴더({p['dir']})는 지우지 않고 남겨 둬요. 게시 기록도 그대로예요.")
            if st.button("목록에서 빼기", key=f"rm_{name}", type="primary"):
                try:
                    remove_profile(name)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    if st.button("🔄 상태 새로고침"):
        st.rerun()

    with st.form("add_profile", clear_on_submit=True, border=False):
        f1, f2 = st.columns([3, 1], vertical_alignment="bottom")
        new_name = f1.text_input("계정 추가", placeholder=f"새 프로필 이름 (예: 유튜브{len(cfg['profiles']) + 1})")
        if f2.form_submit_button("➕ 계정 추가", use_container_width=True):
            try:
                added = add_profile(new_name)
                ss.profile_msg = f"'{added['name']}' 추가됨 ({added['dir']}) — [로그인 창 열기]로 로그인해 주세요."
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    if ss.get("profile_msg"):
        st.success(ss.pop("profile_msg"))

c1, c2, c3 = st.columns([1.15, 1.3, 1], gap="large")

# ---------- ① 영상 불러오기 ----------
with c1:
    st.markdown('<div class="step">① 영상 불러오기</div>', unsafe_allow_html=True)
    mode = st.radio("불러올 영상", ["최신 '연애' 영상", "🔥 뜨기 직전 영상"], horizontal=True,
                    label_visibility="collapsed",
                    help="뜨기 직전: 최근 {lookback_hours}시간, 조회수 {min_views:,}~{max_views:,}, 시간당 {min_views_per_hour}회 이상"
                         .format(**cfg["youtube"]["rising"]))
    if st.button("영상 불러오기", type="primary", use_container_width=True):
        try:
            with st.spinner("유튜브에서 영상을 불러오는 중..."):
                vids = youtube.search_rising(cfg) if mode.startswith("🔥") else youtube.search_latest(cfg)
            db.upsert_videos(vids)
            ss.video_ids = [v["video_id"] for v in vids]
            if not vids:
                st.info("조건에 맞는 영상이 없어요.")
        except youtube.YouTubeError as e:
            st.error(str(e))

    with st.form("link", clear_on_submit=True, border=False):
        lc1, lc2 = st.columns([3, 1])
        link = lc1.text_input("링크", placeholder="또는 유튜브 링크 붙여넣기", label_visibility="collapsed")
        if lc2.form_submit_button("추가", use_container_width=True) and link:
            vid = youtube.parse_video_id(link)
            if not vid:
                st.error("유튜브 영상 링크가 아니에요.")
            else:
                try:
                    vids = youtube.video_details([vid])
                    if not vids:
                        st.error("영상을 찾지 못했어요.")
                    else:
                        db.upsert_videos(vids)
                        ss.video_ids = [vid] + [v for v in ss.video_ids if v != vid]
                        ss.selected = vid
                except youtube.YouTubeError as e:
                    st.error(str(e))

    box = st.container(height=620, border=True)
    if not ss.video_ids:
        box.markdown('<div class="hint">위의 [영상 불러오기]를 누르면 여기에 영상 목록이 떠요.</div>', unsafe_allow_html=True)
    for vid in ss.video_ids:
        v = db.get_video(vid)
        if not v:
            continue
        done = db.active_post_for_video(vid)
        is_sel = ss.selected == vid
        with box.container(border=is_sel):
            a, b = st.columns([1, 1.6])
            if v["thumbnail"]:
                a.image(v["thumbnail"], use_container_width=True)
            b.markdown(f"**{v['title'][:60]}**")
            meta = f"{v['channel']} · {youtube.kst_date(v['published_at'])}"
            if mode.startswith("🔥"):
                meta += f" · 조회 {v['views']:,} · 시간당 {v['views_per_hour']:.0f}"
            b.caption(meta)
            label = "✅ 댓글 완료" if done and done["status"] == "posted" else ("▶ 선택됨" if is_sel else "선택")
            if b.button(label, key=f"sel_{vid}", use_container_width=True, type="primary" if is_sel else "secondary"):
                ss.selected = vid
                ss.last_post = None
                st.rerun()

# ---------- ② 영상 선택 → AI 초안 ----------
draft, errors, warnings, text = None, [], [], ""
with c2:
    st.markdown('<div class="step">② 영상 속 고민 & 댓글 초안</div>', unsafe_allow_html=True)
    video = db.get_video(ss.selected) if ss.selected else None
    if not video:
        st.markdown('<div class="hint">왼쪽 목록에서 영상을 고르면 AI가 자막과 인기 댓글을 읽고 초안을 만들어요.</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f"**[{video['title']}](https://www.youtube.com/watch?v={video['video_id']})**")
        st.caption(f"{video['channel']} · {youtube.kst_date(video['published_at'])}")
        draft = db.get_draft(video["video_id"])  # 한 번 만든 초안은 저장해 두고 재사용 (AI 재호출 X)
        if not draft:
            try:
                with st.spinner(f"AI가 자막·인기 댓글을 읽고 초안을 쓰는 중... ({llm.backend_label(cfg)})"):
                    draft = writer.generate(video, cfg)
            except Exception as e:
                st.error(f"초안 생성 실패: {e}")
        if draft:
            st.markdown("영상 속 고민")
            st.markdown(f'<div class="worry">{draft["worry"]}</div>', unsafe_allow_html=True)
            st.caption(f"📌 근거 장면: {draft['evidence']}  ·  👤 페르소나: {draft['persona']}  ·  자료: {draft['source']}")
            ver_key = f"ver_{video['video_id']}"
            key = f"txt_{video['video_id']}_{ss.get(ver_key, 0)}"
            text = st.text_area("댓글 초안 (직접 고쳐도 돼요)", value=draft["comment"], key=key, height=130)
            errors, warnings = validate.check(
                text, cfg, draft["keywords"], db.recent_comments(exclude_video=video["video_id"]))
            n = len(text.strip())
            st.caption(f"{n}자 / {cfg['comment']['min_chars']}~{cfg['comment']['max_chars']}자")
            for e in errors:
                st.error(e, icon="⛔")
            for w in warnings:
                st.warning(w, icon="⚠️")
            if not errors and not warnings:
                st.success("규칙 검사 통과 — 링크·해시태그·지어낸 후기 없음, 영상 속 장면 언급", icon="✅")
            if st.button("🔄 초안 다시 만들기", use_container_width=True):
                try:
                    with st.spinner("다시 쓰는 중..."):
                        writer.generate(video, cfg)
                    ss[ver_key] = ss.get(ver_key, 0) + 1  # 새 초안으로 입력칸 교체
                    st.rerun()
                except Exception as e:
                    st.error(f"초안 생성 실패: {e}")

# ---------- ③ 댓글 달기 ----------
with c3:
    st.markdown('<div class="step">③ 댓글 달기</div>', unsafe_allow_html=True)
    if not video or not draft:
        st.markdown('<div class="hint">②에서 초안이 나오면 버튼이 켜져요. 누르면 크롬 프로필이 열리고 한 글자씩 입력해 게시해요.</div>',
                    unsafe_allow_html=True)
    else:
        existing = db.active_post_for_video(video["video_id"])
        counts = db.profile_today_counts()
        options = ["자동 배정"] + [p["name"] + ("" if p["name"] in ready_profiles else
                                               " (창 열려 있음)" if open_now[p["name"]] else " (로그인 필요)")
                                  for p in cfg["profiles"]]
        choice = st.selectbox("어느 계정으로 달까요?", options,
                              help="자동 배정: 로그인된 프로필 중 오늘 가장 적게 쓴 계정")
        if choice == "자동 배정":
            profile = min(ready_profiles, key=lambda n: (counts.get(n, 0), ready_profiles.index(n))) if ready_profiles else None
        else:
            profile = choice.split(" (")[0]
            if profile not in ready_profiles:
                profile = None
        if profile:
            st.caption(f"→ **{profile}** 로 게시 (오늘 이 계정 {counts.get(profile, 0)}개)")
        else:
            st.warning("사용할 수 있는 프로필이 없어요. 맨 위 [👤 유튜브 계정 연결]에서 로그인하거나, 열려 있는 크롬 창을 닫아 주세요.")

        total = db.today_count()
        st.progress(min(total / DAILY_MAX, 1.0), text=f"오늘 {total}/{DAILY_MAX}개")
        if cfg["chrome"].get("dry_run"):
            st.info("리허설 모드: 타이핑까지만 하고 게시는 안 해요. (config.yaml → dry_run)")

        blocked = None
        if existing:
            blocked = "이 영상에는 이미 댓글을 달았어요 (영상당 1개)."
        elif total >= DAILY_MAX:
            blocked = f"오늘 상한 {DAILY_MAX}개를 채웠어요."
        elif errors:
            blocked = "② 초안의 규칙 위반(빨간 항목)을 먼저 고쳐 주세요."
        elif not profile:
            blocked = "사용할 프로필이 없어요."

        if existing and existing["status"] == "posted":
            st.success(f"게시 완료 · {existing['profile']}")
            if existing["comment_url"]:
                st.link_button("내 댓글 보기 ↗", existing["comment_url"], use_container_width=True)
        elif blocked:
            st.caption(f"🔒 {blocked}")

        if st.button("💬 댓글 달기", type="primary", use_container_width=True, disabled=bool(blocked)):
            try:
                pid = db.create_post(video["video_id"], profile, text.strip(), DAILY_MAX)
            except db.RuleError as e:
                st.error(str(e))
                pid = None
            if pid:
                log_dir = ROOT / "logs"
                log_dir.mkdir(exist_ok=True)
                with open(log_dir / f"poster_{pid}.log", "w", encoding="utf-8") as lf:
                    proc = subprocess.Popen([sys.executable, "-m", "core.poster", str(pid)],
                                            cwd=ROOT, stdout=lf, stderr=subprocess.STDOUT)
                    with st.status(STATUS["opening"], expanded=True) as s:
                        last = None
                        while True:
                            post = db.get_post(pid)
                            if post["status"] != last:
                                last = post["status"]
                                s.update(label=STATUS.get(last, last))
                                s.write(f"{time.strftime('%H:%M:%S')}  {STATUS.get(last, last)}")
                            if last in ("posted", "failed"):
                                break
                            if proc.poll() is not None:
                                time.sleep(0.5)
                                if db.get_post(pid)["status"] not in ("posted", "failed"):
                                    db.update_post(pid, status="failed", reason=f"게시 프로그램이 비정상 종료됨 (logs/poster_{pid}.log 확인)")
                                continue
                            time.sleep(0.4)
                        s.update(label=STATUS[last], state="complete" if last == "posted" else "error")
                ss.last_post = pid
                st.rerun()

        if ss.last_post:
            lp = db.get_post(ss.last_post)
            if lp and lp["video_id"] == video["video_id"] and lp["status"] == "failed":
                st.error(f"실패 이유: {lp['reason']}")
                if lp["screenshot"]:
                    st.image(lp["screenshot"], caption="실패 당시 화면")

# ---------- 기록 ----------
st.divider()
st.markdown('<div class="step">📋 기록 (시간순)</div>', unsafe_allow_html=True)
rows = db.list_posts()
if not rows:
    st.caption("아직 기록이 없어요.")
else:
    df = pd.DataFrame([{
        "시간": r["created_at"].replace("T", " "),
        "영상": (r["title"] or r["video_id"])[:40],
        "프로필": r["profile"],
        "댓글": r["comment"],
        "결과": STATUS.get(r["status"], r["status"]),
        "실패 이유": r["reason"] or "",
        "댓글 보기": r["comment_url"] or None,
        "캡처": r["screenshot"] or "",
    } for r in rows])
    st.dataframe(df, hide_index=True, use_container_width=True, column_config={
        "댓글": st.column_config.TextColumn(width="large"),
        "댓글 보기": st.column_config.LinkColumn(display_text="열기"),
    })
