#!/usr/bin/env python3
"""Stage1 binary layout tests."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


EXPECTED = {
    "sbcio_vdg": {
        "suffix": "-sbcio-vdg",
        "S1_BASE": 0xC400,
        "S1_LIMIT": 0xCBFF,
        "SDFS_LOAD_BASE": 0xCC00,
    },
    "k6802_vdg": {
        "suffix": "-k6802-vdg",
        "S1_BASE": 0xA400,
        "S1_LIMIT": 0xABFF,
        "SDFS_LOAD_BASE": 0xAC00,
    },
}


def test_stage1_rejects_base_profile() -> None:
    result = _run_make("base", expect_success=False)
    assert result.returncode != 0
    assert "stage1 target requires" in result.stdout or "stage1 target requires" in result.stderr
    print("[PASS] test_stage1_rejects_base_profile")


def test_stage1_profiles_build_and_match_layout() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile)
        suffix = expected["suffix"]
        bin_path = PROJECT_ROOT / "build" / f"stage1{suffix}.bin"
        lst_path = PROJECT_ROOT / "build" / f"stage1{suffix}.lst"
        data = bin_path.read_bytes()
        symbols = _load_symbols(lst_path, "S1_BASE", "S1_LIMIT", "SDFS_LOAD_BASE", "S1_END")
        assert symbols["S1_BASE"] == expected["S1_BASE"], f"{profile} S1_BASE mismatch"
        assert symbols["S1_LIMIT"] == expected["S1_LIMIT"], f"{profile} S1_LIMIT mismatch"
        assert symbols["SDFS_LOAD_BASE"] == expected["SDFS_LOAD_BASE"], (
            f"{profile} SDFS_LOAD_BASE mismatch"
        )
        assert len(data) <= symbols["S1_LIMIT"] - symbols["S1_BASE"] + 1
        _assert_stage1_header(data)
        _assert_jump(data, 16, symbols["S1_BASE"] + 0x22)
        _assert_jump(data, 19, symbols["S1_BASE"] + 0x26)
        _assert_jump(data, 22, symbols["S1_BASE"] + 0x2A)
        _assert_jump(data, 25, symbols["S1_BASE"] + 0x2E)
        _assert_jump(data, 28, symbols["S1_BASE"] + 0x32)
        _assert_jump(data, 31, symbols["S1_BASE"] + 0x36)
    print("[PASS] test_stage1_profiles_build_and_match_layout")


def _assert_stage1_header(data: bytes) -> None:
    assert data[0:7] == b"S1API68"
    assert data[7] == 1, "API version mismatch"
    assert data[8] == 6, "API count mismatch"
    assert data[9] == 0, "flags mismatch"
    assert data[10:16] == bytes(6), "reserved bytes must be zero"


def _assert_jump(data: bytes, offset: int, target: int) -> None:
    assert data[offset] == 0x7E, f"missing JMP opcode at +{offset}"
    actual = (data[offset + 1] << 8) | data[offset + 2]
    assert actual == target, f"JMP target mismatch at +{offset}: {actual:04X} != {target:04X}"


def _run_make(profile: str, expect_success: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["make", "stage1", f"MONITOR_PROFILE={profile}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"make stage1 failed for {profile}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def _load_symbols(path: Path, *names: str) -> dict[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    result: dict[str, int] = {}
    for name in names:
        patterns = [
            re.compile(rf":\s*=\$([0-9A-Fa-f]{{1,4}})\s+{re.escape(name)}\s+equ\b"),
            re.compile(rf"/([0-9A-Fa-f]{{1,4}})\s+:\s+.*\b{re.escape(name)}:\s*$"),
            re.compile(rf"\b{re.escape(name)}\s+:\s+([0-9A-Fa-f]{{1,4}})\b"),
        ]
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                result[name] = int(match.group(1), 16)
                break
        if name not in result:
            raise AssertionError(f"missing symbol in listing: {name}")
    return result


def main() -> None:
    print("=" * 50)
    print("stage1 build tests")
    print("=" * 50)
    tests = [
        test_stage1_rejects_base_profile,
        test_stage1_profiles_build_and_match_layout,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"[ERROR] {test.__name__}: {exc}")
            failed += 1
    print()
    print(f"Result: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
