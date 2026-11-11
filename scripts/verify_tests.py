#!/usr/bin/env python3
"""보호할 테스트 파일(tests/, e2e/)의 SHA-256 해시를 기록·확인한다.

  python3 scripts/verify_tests.py record   # 현재 tests/·e2e/ 상태를 기준선으로 기록 (lead)
  python3 scripts/verify_tests.py check    # 기준선과 비교. 변경·삭제·추가가 있으면 exit 1

기준선은 scripts/test_hashes.json 에 저장되며 lead 소유다.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROTECTED_DIRS = ("tests", "e2e")
MANIFEST = ROOT / "scripts" / "test_hashes.json"
IGNORED_PARTS = {"__pycache__", ".pytest_cache", "node_modules"}


def collect() -> dict:
    hashes = {}
    for d in PROTECTED_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or IGNORED_PARTS.intersection(p.parts) or p.suffix == ".pyc":
                continue
            hashes[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def record() -> int:
    hashes = collect()
    MANIFEST.write_text(json.dumps({"files": hashes}, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"기록: {len(hashes)}개 파일 -> {MANIFEST.relative_to(ROOT)}")
    return 0


def check() -> int:
    if not MANIFEST.exists():
        print(f"실패: 기준선 {MANIFEST.relative_to(ROOT)} 이 없습니다. 먼저 record 하세요.")
        return 1
    expected = json.loads(MANIFEST.read_text()).get("files", {})
    actual = collect()
    changed = sorted(f for f in expected if f in actual and actual[f] != expected[f])
    missing = sorted(f for f in expected if f not in actual)
    added = sorted(f for f in actual if f not in expected)
    for label, files in (("변경", changed), ("삭제", missing), ("추가(미기록)", added)):
        for f in files:
            print(f"{label}: {f}")
    if changed or missing or added:
        print(f"실패: 보호된 테스트 파일이 기준선과 다릅니다 (변경 {len(changed)}, 삭제 {len(missing)}, 추가 {len(added)}).")
        return 1
    print(f"통과: {len(expected)}개 테스트 파일이 기준선과 일치합니다.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["record", "check"])
    args = parser.parse_args()
    return record() if args.command == "record" else check()


if __name__ == "__main__":
    sys.exit(main())
