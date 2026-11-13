"""AI 호출부. 기본은 Claude Code 헤드리스(claude -p) — 구독 안에서 돌아서 추가 비용 0원.
config.yaml의 llm.backend를 anthropic_api로 바꾸면 API 키(ANTHROPIC_API_KEY)로도 동작."""
import json
import os
import shutil
import subprocess
import tempfile


class LLMError(Exception):
    pass


def ask(prompt: str, cfg: dict) -> str:
    llm = cfg["llm"]
    backend = llm.get("backend", "claude_cli")
    if backend == "claude_cli":
        return _claude_cli(prompt, llm.get("cli_model", "haiku"))
    if backend == "anthropic_api":
        return _anthropic_api(prompt, llm.get("api_model", "claude-haiku-5-5"))
    raise LLMError(f"알 수 없는 llm.backend: {backend}")


def backend_label(cfg: dict) -> str:
    llm = cfg["llm"]
    if llm.get("backend") == "anthropic_api":
        return f"API 키 · {llm.get('api_model')}"
    return f"Claude Code 헤드리스 · {llm.get('cli_model')}"


def _claude_cli(prompt: str, model: str) -> str:
    exe = shutil.which("claude")
    if not exe:
        raise LLMError("`claude` 명령을 찾을 수 없어요. Claude Code를 설치하고 터미널에서 `claude`로 한 번 로그인해 주세요.")
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # 키가 있으면 CLI가 API 과금으로 넘어가므로 제거 → 구독 사용
    with tempfile.TemporaryDirectory() as tmp:  # 프로젝트 파일을 읽지 않게 빈 폴더에서 실행
        try:
            r = subprocess.run(
                [exe, "-p", "--output-format", "json", "--model", model],
                input=prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=180, cwd=tmp, env=env,
            )
        except subprocess.TimeoutExpired:
            raise LLMError("Claude 응답이 3분 넘게 없어요. 잠시 후 다시 시도해 주세요.")
    if r.returncode != 0:
        raise LLMError(f"claude 실행 실패: {(r.stderr or r.stdout).strip()[:300]}")
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout
    if data.get("is_error"):
        raise LLMError(f"Claude 오류: {str(data.get('result'))[:300]}")
    return data.get("result", "")


def _anthropic_api(prompt: str, model: str) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise LLMError(".env에 ANTHROPIC_API_KEY가 없어요.")
    try:
        import anthropic
    except ImportError:
        raise LLMError("pip install anthropic 이 필요해요.")
    msg = anthropic.Anthropic(api_key=key).messages.create(
        model=model, max_tokens=800, messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def extract_json(text: str) -> dict:
    s, e = text.find("{"), text.rfind("}")
    if s < 0 or e <= s:
        raise LLMError("AI 응답에서 JSON을 찾지 못했어요.")
    return json.loads(text[s: e + 1])
