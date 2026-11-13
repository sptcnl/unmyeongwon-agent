# 💬 운명원 유튜브 댓글 에이전트

영상을 불러오고 → 고르고 → 버튼 한 번에 크롬 프로필이 열려 **한 글자씩 타이핑해 댓글을 게시**하는 로컬 대시보드.

```
① 영상 불러오기 ──→ ② 영상 선택 ──────────────→ ③ 댓글 달기
  최신 '연애' 영상     AI가 자막·인기 댓글을 읽고     크롬 프로필 열기 → 댓글창 →
  🔥 뜨기 직전 영상    고민 한 줄 + 댓글 초안 생성     한 글자씩 입력 → 게시 → 내 댓글 확인
  링크 직접 입력       규칙 검사 → 어기면 자동 재작성   실패 시 이유 + 화면 캡처
```

## 제작 의도

**운명원(연애 사주) 이야기가 자연스럽게 나오는 '시청자 댓글'을, 사람이 하나하나 쓰는 시간 없이 꾸준히 만들기 위해** 만들었어요.

연애 영상 댓글창은 이미 "나도 저랬는데…", "내 인연은 언제 오지" 같은 고민이 오가는 곳이라, 연애 사주를 떠올리게 하기 좋은 자리예요.
하지만 직접 하려면 영상을 찾고, 끝까지 보고, 영상마다 다른 댓글을 써야 해서 시간이 많이 들어요.
반대로 같은 문구를 복사해 붙이는 자동화는 광고로 바로 티가 나서 역효과가 나요.
그래서 **"영상을 끝까지 본 시청자가 쓴 것 같은 댓글"** 을 기준으로 잡고, 아래 원칙에 맞춰 설계했어요.

1. **영상을 제대로 보고 쓴다** — AI가 자막을 끝까지 읽고 영상의 핵심 장면(결말·반전·고백)을 먼저 정리한 뒤, 그 장면의 실제 대사를 댓글에 넣어요.
   앞부분 몇 초에서 단어만 따오거나 영상과 상관없는 고민을 붙이지 않도록 프롬프트와 규칙 검사로 막아요.
2. **광고처럼 보이지 않는다** — 운명원은 한 번만, "잘 본다던데 ~ 보고 싶다"처럼 **아직 안 가 본 사람의 말투**로 써요.
   이용해 본 척하는 후기("봤는데 맞더라", "추천")·링크·해시태그는 규칙 검사에서 게시 불가로 막아요.
3. **같은 사람이 쓴 것처럼 보이지 않는다** — 좋은 댓글 예시(few-shot)는 말투만 참고하게 하고, 예시나 기존 댓글과 너무 비슷하면 다시 쓰게 해요.
   운명원 문장의 '들은 얘기'와 '끝맺음'도 덜 쓰인 표현을 골라 댓글마다 돌려 써요.
4. **달면 안 되는 곳에는 달지 않는다** — 장애·질병·사고처럼 무거운 사연 영상은 AI가 판단해 건너뛰기를 권하고, 댓글을 만들지 않아요.
5. **사람이 마지막에 확인한다** — 초안은 대시보드에서 바로 고칠 수 있고, 규칙을 어기면 게시 버튼이 잠겨요. 리허설 모드로 게시 직전까지만 돌려 볼 수도 있어요.
6. **과하게 달지 않는다** — 영상당 댓글 1개, 하루 상한, 동시 게시 금지를 DB에서 강제해요.
7. **보일 자리를 고른다** — 조회수가 아직 적은데 빠르게 오르는 **'뜨기 직전 영상'** (최근 48시간 · 조회수 1,000~5,000 · 시간당 150회 이상)을 따로 찾아,
   댓글이 묻히기 전에 먼저 자리 잡을 수 있게 했어요.
8. **운영 비용 0원** — YouTube 무료 할당량, 오픈소스 자막 라이브러리, 이미 쓰는 Claude 구독(`claude -p`)만으로 돌아가요.

## 비용: 0원 구조

| 부분 | 방법 | 비용 |
|---|---|---|
| 영상 목록·인기 댓글 | YouTube Data API v3 (하루 무료 할당량) | 0원 |
| 자막 | youtube-transcript-api (오픈소스) | 0원 |
| AI 초안 | **Claude Code 헤드리스 모드 `claude -p`** — 기존 구독 안에서 실행, API 키 불필요 | 추가 0원 |
| 게시 | Playwright `launch_persistent_context` (= `--user-data-dir`) | 0원 |

- 초안은 **영상을 고를 때만** 만들고 DB에 저장 → 같은 영상을 다시 골라도 AI를 다시 부르지 않음
- 긴 자막은 앞·중간·끝만 잘라 넣어 사용량 절약
- `config.yaml`의 `llm.backend: anthropic_api` 로 바꾸면 API 키로도 동작 (확장용)

## 설치 (처음 한 번)

1. **[uv](https://docs.astral.sh/uv/)** 설치 (Python은 uv가 알아서 받아요)
   ```bash
   # Windows (PowerShell)
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   # macOS / Linux
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. 프로젝트 폴더에서 가상환경 만들고 패키지 설치
   ```bash
   uv venv --python 3.12
   uv pip install -r requirements.txt
   uv run playwright install chromium     # 크롬이 이미 설치돼 있으면 생략 가능
   ```
3. **Claude Code** 설치 후 터미널에서 `claude` 를 한 번 실행해 로그인 → 이후 `claude -p "안녕"` 이 답하면 준비 완료
4. **YouTube API 키** 받기 (무료)
   - [Google Cloud Console](https://console.cloud.google.com/) → 새 프로젝트 → *API 및 서비스 > 라이브러리* → **YouTube Data API v3** 사용 설정
   - *사용자 인증 정보 > API 키 만들기* → 복사
   - `.env.example`을 `.env`로 복사하고 `YOUTUBE_API_KEY=` 뒤에 붙여넣기
5. **크롬 프로필 로그인** (계정마다 한 번, 유튜브1은 필수)
   대시보드 맨 위 **👤 유튜브 계정 연결**에서 [로그인 창 열기] → 열린 크롬에서 구글 로그인 →
   유튜브가 한국어인지 확인 → 크롬 창 닫기 → [상태 새로고침]. 로그인 여부는 쿠키로 확인해서 ✅로 표시돼요.
   터미널로 하려면 `uv run python setup_profile.py 유튜브1` (유튜브2·3도 같은 방식).
   계정을 늘리거나 빼는 것도 같은 칸에서 [➕ 계정 추가] / 🗑 버튼으로 할 수 있어요 (config.yaml에 자동 반영).
   프로필은 `chrome_profiles/` 폴더에 따로 저장돼요 (평소 쓰는 크롬과 분리).

## 실행

```bash
uv run streamlit run app.py
```
브라우저에 대시보드(http://localhost:8501)가 열려요. ① → ② → ③ 순서로 누르면 됩니다.
`uv run`이 프로젝트의 `.venv`를 알아서 쓰기 때문에 가상환경을 따로 켤 필요는 없어요.

> 💡 시연 전 리허설: `config.yaml`의 `chrome.dry_run: true` → 타이핑까지만 하고 게시는 안 해요.

## 운영 규칙 (코드에서 강제)

| 규칙 | 어디서 막나 |
|---|---|
| 영상당 댓글 1개 | DB 유니크 인덱스(`one_comment_per_video`) + 버튼 비활성화 |
| 하루 게시 상한 (기본 10개) | 게시 기록 만들 때 트랜잭션 안에서 오늘 개수 확인 |
| 동시에 두 개 게시 금지 | 진행 중인 게시가 있으면 거절 |
| 40~120자 · 링크/해시태그 금지 · 운명원 1회 · 지어낸 후기 금지 · '들은 얘기' 중복 금지 | `core/validate.py` — 위반이면 AI가 이유를 받고 다시 씀, 직접 고친 댓글도 위반이면 게시 버튼 잠김 |
| 영상 속 장면 언급 · 기존 댓글·예시와 겹침 · 끝맺음 중복 | 경고 표시 + 자동 재작성 |
| 기록 | 어느 영상 · 어느 프로필 · 무슨 댓글 · 성공/실패 · 이유 · 캡처를 시간순 표로 |

## 폴더 구조

```
app.py               대시보드 (Streamlit)
setup_profile.py     크롬 프로필 로그인
config.yaml          설정 (프로필, 글자 수, 하루 상한, AI 백엔드)
core/
  youtube.py         영상 목록 · 뜨기 직전 영상 · 자막 · 인기 댓글
  writer.py          프롬프트 + 규칙 검사 재시도 루프
  llm.py             claude -p / API 백엔드
  validate.py        댓글 규칙 검사
  poster.py          Playwright 게시기 (별도 프로세스로 실행)
  browser.py         프로필 폴더 지정 실행
  db.py              SQLite + 운영 규칙
```

## 문제 해결

- **"크롬 프로필을 열지 못했어요"** → 같은 프로필로 열린 크롬 창을 닫고 다시 시도
- **구글 로그인이 '안전하지 않은 브라우저'로 막힘** → `config.yaml`에서 `chrome.channel: chrome` 확인 (설치된 크롬 사용), 그래도 막히면 잠시 후 재시도
- **댓글 입력창을 못 찾음** → 유튜브 화면 구조 변경 가능성. 실패 캡처(`logs/screens/`)를 확인하고 `core/poster.py`의 선택자 수정
- **`claude` 명령을 찾을 수 없음** → Claude Code 설치 후 새 터미널에서 실행

## 사용한 오픈소스

- [Streamlit](https://github.com/streamlit/streamlit) (Apache-2.0)
- [Playwright for Python](https://github.com/microsoft/playwright-python) (Apache-2.0)
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api) (MIT)
- [Requests](https://github.com/psf/requests), [PyYAML](https://github.com/yaml/pyyaml), [python-dotenv](https://github.com/theskumar/python-dotenv)
