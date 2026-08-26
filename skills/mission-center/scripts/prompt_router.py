#!/usr/bin/env python3
"""Read-only, bounded semantic routing for the Mission Center skill hook."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


MAX_STDIN_BYTES = 64 * 1024
MAX_PROMPT_CHARS = 12_000
HOOK_EVENT_NAME = "UserPromptSubmit"

INVOCATION_PATTERNS = (
    re.compile(r"(?<![\\\w])\$mission-center(?![\w-])", re.IGNORECASE),
    re.compile(r"(?<![\\\w])plugin://mission-center(?:[/?#][^\s]*)?(?![\w-])", re.IGNORECASE),
    re.compile(r"(?<![\\\w])@mission[ \t]+center(?![\w-])", re.IGNORECASE),
)
QUOTED_SPAN_PATTERN = re.compile(
    r"```.*?```|`[^`\r\n]*`|'[^'\r\n]*'|\"[^\"\r\n]*\"|「[^」\r\n]*」|『[^』\r\n]*』",
    re.DOTALL,
)
HIGH_IMPACT_PATTERN = re.compile(
    r"高影響|高風險|重大|關鍵|嚴重|高影响|高风险|关键|严重|"
    r"high[- ]impact|high[- ]risk|critical|security|production|migration|"
    r"高い影響|重大|重要|高リスク|重大な|높은 영향|고위험|중요|보안|마이그레이션",
    re.IGNORECASE,
)
MULTI_STEP_PATTERN = re.compile(
    r"多步驟|多階段|跨模組|跨團隊|跨專案|多步骤|多阶段|跨模块|跨团队|跨项目|"
    r"multi[- ]step|multi[- ]phase|multiple steps|several steps|cross[- ](?:team|module|project)|"
    r"複数ステップ|複数段階|複数の工程|複数フェーズ|여러 단계|다단계|여러 작업",
    re.IGNORECASE,
)
PLANNING_PATTERN = re.compile(
    r"專案規劃|專案計畫|任務規劃|任務計畫|規劃.{0,12}(?:專案|目標|任務)|(?:專案|目標|任務).{0,12}規劃|"
    r"项目规划|项目计划|任务规划|里程碑|路线图|规划.{0,12}(?:项目|目标|任务)|(?:项目|目标|任务).{0,12}规划|"
    r"project planning|project plan|roadmap|milestone|plan a project|"
    r"プロジェクト計画|計画を立て|ロードマップ|マイルストーン|프로젝트 계획|로드맵|마일스톤",
    re.IGNORECASE,
)
PURE_EXPLANATION_PATTERN = re.compile(
    r"^\s*(?:please\s+|請(?:幫我)?|请(?:帮我)?|説明して|説明を|설명해줘)?"
    r"(?:explain|describe|解釋|說明|解释|说明|引用|引用する|인용|quote)",
    re.IGNORECASE,
)
DIRECT_NEGATION_PATTERN = re.compile(
    r"(?:不要|別|勿|不必|禁止)(?:用|使用|啟動|启动|開啟|开启|執行|执行|呼叫)?\s*$|"
    r"(?:do not|don't|dont|no need to)\s+(?:use|invoke|open|launch|run|activate)\s*$|"
    r"(?:やめて|しないで|하지 마)\s*$",
    re.IGNORECASE,
)
NEGATED_REQUEST_PATTERN = re.compile(
    r"^\s*(?:please\s+|請|请)?\s*(?:不要|別|勿|不必|禁止|"
    r"do not|don't|dont|no need to|やめて|しないで|하지 마)",
    re.IGNORECASE,
)
RESUME_PATTERN = re.compile(
    r"(?:resume|continue|pick up|carry on|recover|restart).{0,24}(?:mission ?center|mission|workspace|work)"
    r"|(?:mission ?center|mission|workspace|work).{0,24}(?:resume|continue|recover|restart)"
    r"|恢復|恢复|繼續任務|继续任务|繼續工作區|继续工作区|再開|再開する|続き|재개|계속",
    re.IGNORECASE,
)
STANDALONE_GO_OK_PATTERN = re.compile(r"^(?:go|ok)[.!?;:,。！？；：，、…]*$", re.IGNORECASE)


def _visible_prompt(prompt: str) -> str:
    return QUOTED_SPAN_PATTERN.sub(" ", prompt)


def _explicit_invocation(prompt: str) -> bool:
    for pattern in INVOCATION_PATTERNS:
        for match in pattern.finditer(prompt):
            prefix = prompt[max(0, match.start() - 64) : match.start()]
            if not DIRECT_NEGATION_PATTERN.search(prefix[-32:]):
                return True
    return False


def _has_existing_workspace(cwd: object) -> bool:
    if not isinstance(cwd, str) or not cwd.strip():
        return False
    try:
        return (Path(cwd) / "MissionCenter" / "tasks.md").is_file()
    except (OSError, ValueError):
        return False


def _is_standalone_go_ok(prompt: str) -> bool:
    compact = re.sub(r"\s+", "", prompt)
    return bool(STANDALONE_GO_OK_PATTERN.fullmatch(compact))


def route(payload: object) -> dict[str, Any]:
    """Return a short hook context only when bounded routing is warranted."""
    if not isinstance(payload, dict) or payload.get("hook_event_name") != HOOK_EVENT_NAME:
        return {}
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt or len(prompt) > MAX_PROMPT_CHARS:
        return {}
    visible = _visible_prompt(prompt)
    if not visible.strip() or PURE_EXPLANATION_PATTERN.match(visible):
        return {}
    if _explicit_invocation(visible):
        return {
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT_NAME,
                "additionalContext": "Explicit Mission Center request detected; follow bounded intake, approval, and evidence gates.",
            },
        }
    if NEGATED_REQUEST_PATTERN.match(visible):
        return {}
    high_impact = bool(HIGH_IMPACT_PATTERN.search(visible))
    multi_step = bool(MULTI_STEP_PATTERN.search(visible))
    planning = bool(PLANNING_PATTERN.search(visible))
    if (high_impact or multi_step) and planning:
        return {
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT_NAME,
                "additionalContext": "This appears to be a high-impact or multi-step project request; consider Mission Center intake, research, approval, and evidence gates.",
            },
        }
    if (
        (RESUME_PATTERN.search(visible) or _is_standalone_go_ok(visible))
        and _has_existing_workspace(payload.get("cwd"))
    ):
        return {
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT_NAME,
                "additionalContext": "An existing MissionCenter workspace is present; consider bounded Mission Center resume routing before changing task state.",
            },
        }
    return {}


def bounded_hook_input(stream: Any = None) -> dict[str, Any] | None:
    stream = stream or sys.stdin.buffer
    try:
        raw = stream.read(MAX_STDIN_BYTES + 1)
        if len(raw) > MAX_STDIN_BYTES:
            return None
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    payload = bounded_hook_input()
    if payload is not None:
        result = route(payload)
        if result:
            sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
