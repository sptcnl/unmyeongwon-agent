"""영상 → 고민 한 줄 + 댓글 초안. 규칙 검사에 걸리면 이유를 알려 주고 다시 쓰게 함."""
import random

from . import db, llm, validate, youtube

# 흐름 = 영상 속 말 짚기 → 내 연애 상황 → '잘 본다던데 ~ 보고 싶다/궁금하다' (안 가 본 사람 말투)
# 드라마·예능 클립은 '내 고민' 대신 핵심 장면(고백·반전)에 대한 반응 → 내 바람 → 운명원
FEW_SHOTS = [
    ("드라마 고백 장면", "비 오는 날 우산 하나 들고 끝까지 기다린 장면에서 소리 질렀다ㅠㅠ 저런 직진남 현실엔 왜 없냐고… 운명원 연애사주 그렇게 잘 본다던데 나한테도 저런 인연 오긴 하는지 보고 싶다"),
    ("예능 최종 선택 반전", "서로 관심 없는 척하더니 최종 선택에서 둘 다 서로 고른 거 실화냐ㅋㅋㅋ 나도 저런 반전 좀 있었으면… 운명원 연애사주 잘 본다던데 올해 소개팅운이 있긴 한지 궁금하다"),
    ("남자심리 분석", "남자심리는 진짜 알다가도 모르겠다ㅠㅠ 맨날 차이기만 했던 1인… 심리 알기는 개뿔 그냥 인연이면 만나는 듯. 운명원 연애사주 그렇게 잘 본다던데 나도 언제 짝 만나는지 보고 싶다"),
    ("재회 타이밍", "재회는 타이밍이 전부라는 말이 왜 이렇게 아프냐ㅠ 헤어진 지 반년인데 아직도 프사 확인하는 중. 운명원이 연애사주 잘 본다던데 우리 다시 만날 운이 있긴 한지 궁금하다"),
    ("권태기 극복", "설렘이 끝나야 진짜 사랑이 시작된다는 말 듣고 남친 얼굴 다시 봄ㅋㅋ 5년째라 요즘 무덤덤했는데… 운명원 연애사주 그렇게 유명하던데 우리 궁합 한번 보고 싶어짐"),
    ("30대 연애", "30대 되면 자연스러운 만남이 없다는 거 완전 내 얘기네요. 회사 집 회사 집… 운명원에서 연애사주 잘 봐준다던데 올해 안에 인연 오긴 하는 건지 진짜 궁금함"),
    ("연하남 심리", "연하남은 표현을 아낀다는 거 보고 무릎 탁ㅋㅋ 3살 어린 후배 땜에 혼자 북치고 장구치는 중인데 운명원 연애사주 잘 본다길래 이 사람이 내 짝인지 한번 물어보고 싶다"),
]

PROMPT = """너는 유튜브 연애 영상을 방금 끝까지 본 한국인 시청자야. 아래 자료를 읽고 JSON 하나만 출력해.

[영상 정보]
제목: {title}
채널: {channel}
설명: {description}

[{source_label}]
{body}

[인기 댓글 — 시청자 말투 참고용]
{comments}

[할 일 — 순서대로]
0) skip: 영상이 장애·질병·죽음·폭력·범죄 피해처럼 무거운 사연이라 연애사주 이야기를 꺼내면 무례해 보이면, 그 이유를 한 줄로 쓰고 나머지는 빈 값으로. 아니면 빈 문자열 ""
1) highlight: 자료를 끝까지 읽고, 이 영상의 핵심을 1~2문장으로 (사연의 결론, 반전, 고백, 웃음 포인트처럼 시청자 반응이 가장 클 장면). 도입부 설명이나 나레이션 말고 영상이 실제로 말하려는 것
2) worry: highlight를 보고 이 영상을 본 사람이 품을 연애 감정·고민을 한 줄(35자 이내)로
3) evidence: highlight 장면 속 실제 대사나 말 하나 (자료에 그대로 있는 표현, 20자 이내, 자막이면 [분:초]도). 앞부분 몇 초에서 아무 말이나 고르지 말 것
4) keywords: evidence에서 댓글에 그대로 넣을 핵심 단어 1~3개 (각 2자 이상)
5) persona: 이 영상을 볼 법한 시청자 한 명 (예: "3년 연애 끝나고 혼자 정리 중인 20대 후반")
6) comment: 그 시청자가 쓴 유튜브 댓글

[댓글 규칙]
- 공백 포함 {min_chars}~{max_chars}자. 인기 댓글처럼 편한 구어체 (ㅋㅋ, ㅠㅠ 정도는 OK)
- 영상을 끝까지 본 사람만 쓸 수 있는 댓글로: highlight 장면에 반응하고, keywords 중 하나 이상을 그대로 넣기
- 단어만 따오고 영상과 다른 이야기를 하면 안 됨 (예: 웃긴 반전 장면인데 갑자기 내 이별 고민을 늘어놓기 X)
- 흐름: highlight 장면에 대한 반응(공감·설렘·웃음) → 그 장면과 이어지는 내 상황이나 바람 한 줄 → '{brand}' 연애사주를 한번 보고 싶다는 바람
- 드라마·예능 클립이면 억지로 고민을 만들지 말고, 장면에 설렌·웃긴 감정에서 바로 내 바람으로 넘어가기
- '{brand}'는 정확히 한 번. 아직 안 가 본 사람의 말투로
- '{brand}' 문장은 이 틀로: '{brand} 연애사주 + [들은 얘기] + [알고 싶은 것 하나] + [끝맺음]'
- 이번 댓글은 반드시 들은 얘기 = "{hearsay}", 끝맺음 = "{closing}" 으로 (다른 댓글들과 끝이 똑같아 보이지 않게. 앞뒤 말에 맞춰 어미만 자연스럽게 다듬는 건 OK)
  끝맺음은 표현 그대로 자연스럽게 붙이기. 다른 말과 섞어 새 말을 만들지 말 것 (나쁨: "궁금해하고 싶다", "궁금한데 보러 갈까 고민 중")
  [알고 싶은 것]은 꼭 넣기 (나쁨: "{brand} 연애사주 요즘 많이들 보던데 한번 보고 싶다" → 뭘 보고 싶은지 없음)
  나쁨: "{brand} 연애사주 궁금해서 내 인연은 언제쯤일지 알고 싶다" (들은 얘기 빠짐, '궁금해서'와 '알고 싶다'가 같은 말 반복)
- 한 문장 안에서 '궁금'·'알고 싶다'·'보고 싶다'는 하나만
- 금지: 링크, 해시태그(#), 이모지 2개 이상, '{brand}'를 이용해 본 것 같은 후기(다녀왔다·봤는데 맞더라·추천 등), 광고 문구, 영상·출연자 비판
- 아래 기존 댓글과 표현·문장 구조가 겹치지 않게
{previous}
[좋은 댓글 예시 — 말투·흐름만 참고하고 문장은 절대 베끼지 마]
{few_shots}

[출력 형식 예시 — 카톡 답장 속도를 다룬 다른 영상]
{{"skip": "", "highlight": "썸남 답장이 3시간씩 걸린다는 사연에, 진행자가 그건 관심이 없는 거라고 단호하게 정리함", "worry": "답장이 늦는 사람, 마음이 식은 걸까", "evidence": "[3:12] 답장 3시간은 관심 없는 거예요", "keywords": ["답장 3시간"], "persona": "썸 두 달째인 20대 중반", "comment": "답장 3시간이면 관심 없는 거라는 말에 뜨끔ㅋㅋ 나만 매달리는 썸 이제 그만하고 싶다. 운명원 연애사주 잘 본다던데 이 사람이 내 인연인지 한번 보고 싶네"}}
{retry}
JSON 하나만 출력해. 다른 설명은 쓰지 마."""


# 운명원 문장의 '들은 얘기'와 '끝맺음'. 댓글마다 돌려 써서 같은 사람이 쓴 것처럼 안 보이게.
# (봤는데·다녀왔·맞더라처럼 이용 후기로 읽히는 말은 넣지 말 것 — validate.FAKE_REVIEW에 걸림)
HEARSAY = ["잘 본다던데", "그렇게 유명하던데", "잘 본다길래", "요즘 많이들 보던데", "잘 본다는 얘기 들어서"]
CLOSINGS = ["한번 보고 싶다", "궁금하다", "한번 물어보고 싶다", "한번 봐볼까 싶다", "보러 갈까 고민 중", "알아보고 싶어짐"]


def pick_ending(previous: list[str]) -> tuple[str, str]:
    """기존 댓글에 덜 쓰인 표현 중에서 랜덤으로 하나씩."""
    def least_used(options: list[str]) -> str:
        used = {o: sum(o in p for p in previous) for o in options}
        low = min(used.values())
        return random.choice([o for o in options if used[o] == low])
    return least_used(HEARSAY), least_used(CLOSINGS)


def build_prompt(video: dict, body: str, source: str, comments: list[str],
                 previous: list[str], cfg: dict, retry_note: str = "",
                 ending: tuple[str, str] | None = None) -> str:
    c = cfg["comment"]
    hearsay, closing = ending or pick_ending(previous)
    prev = "\n[기존 댓글]\n" + "\n".join(f"- {p}" for p in previous) + "\n" if previous else ""
    return PROMPT.format(
        title=video["title"], channel=video["channel"],
        description=(video.get("description") or "")[:600] or "(없음)",
        source_label="자막 일부" if source == "자막" else "자막 없음 — 제목·설명만 있음",
        body=body or "(자막 없음)",
        comments="\n".join(f"- {x}" for x in comments) or "(없음)",
        min_chars=c["min_chars"], max_chars=c["max_chars"], brand=c["brand"],
        previous=prev, retry=retry_note, hearsay=hearsay, closing=closing,
        few_shots="\n".join(f"- ({topic} 영상) {text}" for topic, text in FEW_SHOTS),
    )


def generate(video: dict, cfg: dict) -> dict:
    vid = video["video_id"]
    tr = youtube.transcript(vid)
    source = "자막" if tr else "제목·설명"
    body = youtube.excerpt(tr) if tr else ""
    comments = youtube.top_comments(vid)
    previous = db.recent_comments(exclude_video=vid)
    ending = pick_ending(previous)  # 재시도해도 같은 끝맺음 유지

    retry_note, last, last_issues = "", None, []
    attempts = cfg["llm"].get("max_attempts", 3)
    for i in range(1, attempts + 1):
        prompt = build_prompt(video, body, source, comments, previous, cfg, retry_note, ending)
        raw = llm.ask(prompt, cfg)
        try:
            out = llm.extract_json(raw)
        except (llm.LLMError, ValueError):  # 가끔 JSON 대신 설명문으로 답함 → 다시 시도
            if i == attempts and last is None:
                raise llm.LLMError(f"AI 응답에서 JSON을 찾지 못했어요: {raw[:200]}")
            retry_note = "\n[직전 시도의 문제]\n- JSON이 아니었어요. 설명 없이 JSON 하나만 출력해.\n"
            continue
        out["keywords"] = [str(k) for k in (out.get("keywords") or [])]
        out["comment"] = str(out.get("comment", "")).strip().strip('"')
        skip = str(out.get("skip") or "").strip()
        if skip:  # 무거운 사연 → 댓글 안 씀 (빈 댓글이라 규칙 검사에 걸려 게시 불가)
            out.update(worry=f"⚠️ 건너뛰기 권장 — {skip}", comment="", keywords=[])
            last = out
            break
        errors, warnings = validate.check(out["comment"], cfg, out["keywords"],
                                          previous + [c for _, c in FEW_SHOTS])
        last, last_issues = out, errors + warnings
        if not errors and not warnings:
            break
        retry_note = ("\n[직전 시도의 문제 — 고쳐서 다시 써]\n직전 댓글: " + out["comment"] + "\n"
                      + "\n".join(f"- {x}" for x in last_issues) + "\n")
        if not errors and i == attempts:
            break

    evidence = str(last.get("evidence", ""))
    highlight = str(last.get("highlight") or "").strip()
    if highlight:  # 화면의 '근거 장면'에 영상 핵심도 같이 보여 줌 (DB 칸은 그대로)
        evidence = f"{evidence} — 핵심: {highlight}" if evidence else f"핵심: {highlight}"
    draft = {
        "worry": str(last.get("worry", "")), "evidence": evidence,
        "keywords": last["keywords"], "persona": str(last.get("persona", "")),
        "comment": last["comment"], "source": source, "attempts": i,
    }
    db.save_draft(vid, draft)
    return draft
