#!/usr/bin/env python3
"""PreToolUse hook: server 자리가 tests/·e2e/ 파일과 검사 장치
(해시 기준선, verify_tests.py, 이 훅, 훅 설정)를 Edit·Write로 고치는 것을 막는다.

대표 실수를 막는 장치일 뿐이다. Bash 등으로 우회할 수 있으므로
최종 확인은 scripts/verify_tests.py check 로 한다.
"""
import json
import os
import sys

PROTECTED_DIRS = ("tests", "e2e")
# 검사 장치 자체: 기준선·검사 스크립트·훅을 바꿀 수 있으면 보호가 의미 없어진다
PROTECTED_FILES = {
    "scripts/test_hashes.json": "테스트 해시 기준선",
    "scripts/verify_tests.py": "테스트 검사 스크립트",
    ".claude/hooks/guard_test_dirs.py": "보호 훅",
    ".claude/settings.json": "훅 설정",
}
# server 자리 판별: OpenRig이 seat마다 넣어 주는 세션 이름 (예: dev-server@tkt)
SERVER_SESSION_PREFIX = "dev-server@"


def next_step(rel_posix: str, condition: str, subject: str) -> str:
    return (
        "다음 할 일: 이 파일을 직접 고치지 마세요(Bash 등으로 우회하지 마세요). "
        f"{condition} 일반 메시지(rig send) 대신 큐 아이템으로 lead에게 올리세요. "
        "큐 아이템은 lead가 다른 일을 하고 있어도 남아 있습니다.\n"
        f'  rig queue create --destination dev-lead@tkt --summary "{subject}: {rel_posix}" '
        '--body "<무엇이 왜 틀렸는지, 근거(실패 출력·요구사항)와 제안하는 변경>"'
    )


def main() -> int:
    session = os.environ.get("OPENRIG_SESSION_NAME", "")
    if not session.startswith(SERVER_SESSION_PREFIX):
        return 0

    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not target:
        return 0

    project = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    project = os.path.realpath(project)
    path = target if os.path.isabs(target) else os.path.join(payload.get("cwd") or project, target)
    path = os.path.realpath(path)

    try:
        rel = os.path.relpath(path, project)
    except ValueError:
        return 0
    rel_posix = rel.replace(os.sep, "/")
    first = rel_posix.split("/", 1)[0]
    if first in PROTECTED_DIRS:
        print(
            f"차단: server 자리는 {first}/ 를 수정할 수 없습니다 ({rel_posix}). 테스트는 dev.test 소유입니다.\n"
            + next_step(rel_posix, "테스트가 틀렸다고 판단되면", "테스트 수정 요청"),
            file=sys.stderr,
        )
        return 2
    if rel_posix in PROTECTED_FILES:
        print(
            f"차단: server 자리는 {PROTECTED_FILES[rel_posix]} {rel_posix} 을 수정할 수 없습니다. lead 소유입니다.\n"
            + next_step(rel_posix, "변경이 필요하다고 판단되면", "검사 장치 변경 요청"),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
