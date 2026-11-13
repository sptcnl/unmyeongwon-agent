"""댓글 규칙 검사. errors = 게시 불가, warnings = 게시는 되지만 품질 경고."""
import difflib
import re

LINK = re.compile(r"(https?://|www\.|youtu\.be|\.(com|kr|net|co|me|io)\b)", re.I)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# 운명원을 직접 이용해 본 것처럼 쓰는 후기 표현
FAKE_REVIEW = re.compile(
    r"(봤는데|봤더니|받았는데|받아봤|받아 봤|다녀왔|다녀옴|갔었|가봤|가 봤|해봤|해 봤|보고 왔|보고왔|"
    r"후기|용하더|맞더라|맞췄|맞추더|소름|추천해요|추천합니다|강추)"
)

# 운명원 문장의 '들은 얘기' / '끝맺음'. 같은 종류가 두 번 나오면 어색함 (예: "잘 본다길래 잘 본다는 얘기 들어서")
# 긴 표현을 앞에 둬야 "물어보고 싶"이 "보고 싶"으로 두 번 세지지 않음
HEARSAY_RE = re.compile(r"잘 (?:본|봐준)다(?:던데|길래|고|는)|유명하던데|많이들 보던데")
CLOSING_RE = re.compile(r"물어보고 싶|알아보고 싶|보고 싶|알고 싶|궁금|고민 중|봐볼까")


def _eul(word: str) -> str:
    """받침 있으면 '을', 없으면 '를'."""
    ch = word[-1] if word else ""
    return "을" if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else "를"


def _iga(word: str) -> str:
    ch = word[-1] if word else ""
    return "이" if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else "가"


def check(comment: str, cfg: dict, keywords: list[str] | None = None,
          previous: list[str] | None = None) -> tuple[list[str], list[str]]:
    c = cfg["comment"]
    brand = c["brand"]
    text = (comment or "").strip()
    errors, warnings = [], []

    n = len(text)
    if n < c["min_chars"]:
        errors.append(f"{n}자 — {c['min_chars']}자 이상이어야 해요")
    if n > c["max_chars"]:
        errors.append(f"{n}자 — {c['max_chars']}자 이하여야 해요")
    if LINK.search(text):
        errors.append("링크가 들어 있어요")
    if "#" in text:
        errors.append("해시태그(#)가 들어 있어요")

    cnt = text.count(brand)
    if cnt == 0:
        errors.append(f"'{brand}'{_iga(brand)} 없어요")
    elif cnt > 1:
        errors.append(f"'{brand}'{_iga(brand)} {cnt}번 나와요 (1번만)")
    else:
        i = text.index(brand)
        window = text[max(0, i - 8): i + len(brand) + 30]
        if FAKE_REVIEW.search(window):
            errors.append(f"'{brand}'{_eul(brand)} 이용해 본 것 같은 후기 표현이 있어요")
        tail = text[i:]  # '{brand}'부터 끝까지 = 운명원 문장
        hs = HEARSAY_RE.findall(tail)
        if len(hs) >= 2:
            errors.append(f"'{brand}' 문장에 '들은 얘기'가 {len(hs)}번 겹쳐요 ({' / '.join(hs)}) — 하나만 남겨 주세요")
        cl = CLOSING_RE.findall(tail)
        if len(cl) >= 2:
            warnings.append(f"'{brand}' 문장 끝맺음이 겹쳐요 ({' / '.join(cl)}) — 하나만 남겨 주세요")

    if len(EMOJI.findall(text)) >= 2:
        warnings.append("이모지가 많아요")
    kws = [k for k in (keywords or []) if len(k.strip()) >= 2]
    if kws and not any(k in text for k in kws):
        warnings.append("영상 속 장면·말(키워드)이 댓글에 안 보여요")
    for p in previous or []:
        if difflib.SequenceMatcher(None, text, p).ratio() >= 0.6:
            warnings.append("기존 댓글과 너무 비슷해요")
            break
    return errors, warnings
