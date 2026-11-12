#!/usr/bin/env python3
"""스토리별 통과·실패 개수를 표로 출력한다.

사용: uv run python scripts/story_report.py [pytest 경로 ...]   (기본 tests/contract, tests/api)
테스트 이름 test_us<NN>_... 에서 스토리를 읽는다.
[열린 질문]이 붙어 테스트를 만들지 않은 인수 조건은 docs/stories 에서 읽어 목록으로 보여 준다.
실패가 하나라도 있으면 종료 코드 1.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_pytest(targets: list[str]) -> list[tuple[str, str]]:
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "report.xml"
        subprocess.run(
            [sys.executable, "-m", "pytest", *targets, "-q", "--tb=no", "-p", "no:cacheprovider", f"--junitxml={xml_path}"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not xml_path.exists():
            sys.exit("pytest 결과를 읽지 못했다")
        results = []
        for case in ET.parse(xml_path).getroot().iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            results.append((case.get("name", ""), outcome))
        return results


def group_of(name: str) -> str | None:
    m = re.match(r"test_us(\d\d)_", name)
    if m:
        return f"US-{m.group(1)}"
    return None


def skipped_acs() -> list[str]:
    """[열린 질문] 표시가 붙은 인수 조건 제목."""
    out = []
    for f in sorted((ROOT / "docs" / "stories").glob("US-*.md")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.startswith("### AC-") and "[열린 질문" in line:
                out.append(line[4:].strip())
    return out


def main() -> int:
    targets = sys.argv[1:] or [t for t in ("tests/contract", "tests/api") if (ROOT / t).is_dir()]
    table: "OrderedDict[str, dict[str, int]]" = OrderedDict(
        (k, {"passed": 0, "failed": 0, "skipped": 0}) for k in ("US-01", "US-02", "US-03", "US-04")
    )
    for name, outcome in run_pytest(targets):
        g = group_of(name)
        if g is not None:
            table[g][outcome] += 1

    print(f"{'스토리':<8}{'통과':>6}{'실패':>6}{'건너뜀':>8}{'합계':>6}")
    print("-" * 34)
    total = {"passed": 0, "failed": 0, "skipped": 0}
    for story, c in table.items():
        print(f"{story:<8}{c['passed']:>6}{c['failed']:>6}{c['skipped']:>8}{sum(c.values()):>6}")
        for k in total:
            total[k] += c[k]
    print("-" * 34)
    print(f"{'합계':<8}{total['passed']:>6}{total['failed']:>6}{total['skipped']:>8}{sum(total.values()):>6}")

    skipped = skipped_acs()
    if skipped:
        print("\n[열린 질문]으로 테스트를 만들지 않은 인수 조건:")
        for s in skipped:
            print(f"  - {s}")
    return 1 if total["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
