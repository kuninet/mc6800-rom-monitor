#!/usr/bin/env python3
"""SDFS/68 v3 resident stub build tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"


EXPECTED = {
    "sbcio_4000": {
        "suffix": "-sbcio-4000",
        "SDFS_LOAD_BASE": 0x5000,
        "SDFS_LOAD_LIMIT": 0x7EFF,
        "USER_RAM_END": 0x3FFF,
    },
    "k6802_4000": {
        "suffix": "-k6802-4000",
        "SDFS_LOAD_BASE": 0x5000,
        "SDFS_LOAD_LIMIT": 0x7EFF,
        "USER_RAM_END": 0x3FFF,
    },
}


def test_sdfs3_profiles_build_and_match_header() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs3")
        suffix = expected["suffix"]
        bin_path = PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN"
        lst_path = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
        data = bin_path.read_bytes()
        symbols = _load_symbols(
            lst_path,
            "SDFS_LOAD_BASE",
            "SDFS_LOAD_LIMIT",
            "USER_RAM_END",
            "SDFS3_API_HEADER",
            "SDFS3_JUMP_TABLE",
            "SDFS3_GET_INFO",
            "SDFS3_CMD_DISPATCH",
            "SDFS3_LOAD_PATH",
            "SDFS3_READ_STREAM_OPEN",
            "SDFS3_READ_STREAM_GETC",
            "SDFS3_READ_STREAM_CLOSE",
            "SDFS3_GET_ERROR",
            "SDFS3_END",
        )
        assert symbols["SDFS_LOAD_BASE"] == expected["SDFS_LOAD_BASE"]
        assert symbols["SDFS_LOAD_LIMIT"] == expected["SDFS_LOAD_LIMIT"]
        assert symbols["USER_RAM_END"] == expected["USER_RAM_END"]
        assert symbols["SDFS3_API_HEADER"] == symbols["SDFS_LOAD_BASE"]
        assert len(data) <= symbols["SDFS_LOAD_LIMIT"] - symbols["SDFS_LOAD_BASE"] + 1
        assert len(data) == symbols["SDFS3_END"] - symbols["SDFS_LOAD_BASE"]
        assert data[0:8] == b"SDFS3API"
        assert data[8] == 1, "SDFS3 api major mismatch"
        assert data[9] == 0, "SDFS3 api minor mismatch"
        assert data[10] == 7, "SDFS3 api count mismatch"
        assert data[11] == 0, "SDFS3 flags should be zero in stub"
        assert _word(data, 0x0C) == symbols["SDFS3_JUMP_TABLE"]
        assert _word(data, 0x0E) == symbols["SDFS_LOAD_BASE"]
        assert _word(data, 0x10) == symbols["SDFS3_END"] - 1
        assert _word(data, 0x12) == expected["USER_RAM_END"]
        assert _word(data, 0x14) == 0
        assert _word(data, 0x16) == 0
        jump_table = symbols["SDFS3_JUMP_TABLE"] - symbols["SDFS_LOAD_BASE"]
        assert _word(data, jump_table) == symbols["SDFS3_GET_INFO"]
        assert _word(data, jump_table + 2) == symbols["SDFS3_CMD_DISPATCH"]
        assert _word(data, jump_table + 4) == symbols["SDFS3_LOAD_PATH"]
        assert _word(data, jump_table + 6) == symbols["SDFS3_READ_STREAM_OPEN"]
        assert _word(data, jump_table + 8) == symbols["SDFS3_READ_STREAM_GETC"]
        assert _word(data, jump_table + 10) == symbols["SDFS3_READ_STREAM_CLOSE"]
        assert _word(data, jump_table + 12) == symbols["SDFS3_GET_ERROR"]
        get_error = symbols["SDFS3_GET_ERROR"] - symbols["SDFS_LOAD_BASE"]
        assert data[get_error + 3 : get_error + 5] == bytes([0x0C, 0x39])
    print("[PASS] test_sdfs3_profiles_build_and_match_header")


def test_sdfs3_get_info_matches_calling_convention() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "sdfs3")
    suffix = expected["suffix"]
    data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS_LOAD_BASE",
        "SDFS3_GET_INFO",
        "SDFS3_API_HEADER",
    )
    get_info = symbols["SDFS3_GET_INFO"] - symbols["SDFS_LOAD_BASE"]
    header = symbols["SDFS3_API_HEADER"]
    assert data[get_info : get_info + 8] == bytes(
        [
            0x86,
            0x01,
            0xC6,
            0x00,
            0xCE,
            (header >> 8) & 0xFF,
            header & 0xFF,
            0x0C,
        ]
    )
    assert data[get_info + 8] == 0x39
    print("[PASS] test_sdfs3_get_info_matches_calling_convention")


def test_sdfs3_rejects_base_profile() -> None:
    result = _run_make("base", "sdfs3", expect_success=False)
    assert result.returncode != 0
    assert "FEATURE_SD=1" in result.stdout or "FEATURE_SD=1" in result.stderr
    print("[PASS] test_sdfs3_rejects_base_profile")


def test_rom_detects_sdfs3_api_header() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SDFS3_FIND_API",
        "SDFS_LOAD_BASE",
    )
    status_addr = 0x0200
    result_addr = 0x0201
    harness_addr = 0x0100
    find_api = symbols["SDFS3_FIND_API"]
    harness = bytes(
        [
            0xBD,
            (find_api >> 8) & 0xFF,
            find_api & 0xFF,
            0x25,
            0x09,
            0xFF,
            (result_addr >> 8) & 0xFF,
            result_addr & 0xFF,
            0x86,
            0x42,
            0xB7,
            (status_addr >> 8) & 0xFF,
            status_addr & 0xFF,
            0x3F,
            0x86,
            0xE1,
            0xB7,
            (status_addr >> 8) & 0xFF,
            status_addr & 0xFF,
            0x3F,
        ]
    )

    cases = [
        ("valid", _sdfs3_header(symbols["SDFS_LOAD_BASE"]), 0x42),
        ("bad magic", b"XDFS3API" + _sdfs3_header(symbols["SDFS_LOAD_BASE"])[8:], 0xE1),
        ("bad major", _mutated_header(symbols["SDFS_LOAD_BASE"], 8, 0x02), 0xE1),
        ("short api count", _mutated_header(symbols["SDFS_LOAD_BASE"], 10, 0x06), 0xE1),
    ]
    for label, header, expected_status in cases:
        stdout, stderr, rc = _run_emu(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text=(
                f"M{symbols['SDFS_LOAD_BASE']:04X}\r"
                f"{_hex_bytes(header)}\r.\r"
                f"M{harness_addr:04X}\r"
                f"{_hex_bytes(harness)}\r.\r"
                f"G{harness_addr:04X}\r"
                f"D{status_addr:04X}-{result_addr + 1:04X}\r"
                "\r"
            ),
            max_cycles=20_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {label}: rc={rc} stderr={stderr!r}"
        )
        values = _dump_bytes(stdout, status_addr)
        assert values[0] == expected_status, (
            f"{label} status mismatch: {values!r}\nstdout={stdout!r}"
        )
        if expected_status == 0x42:
            assert values[1:3] == [
                (symbols["SDFS_LOAD_BASE"] >> 8) & 0xFF,
                symbols["SDFS_LOAD_BASE"] & 0xFF,
            ], f"{label} returned header address mismatch: {values!r}"
    print("[PASS] test_rom_detects_sdfs3_api_header")


def _word(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _sdfs3_header(load_base: int) -> bytes:
    return bytes(
        [
            *b"SDFS3API",
            0x01,
            0x00,
            0x07,
            0x00,
            (load_base >> 8) & 0xFF,
            load_base & 0xFF,
            (load_base >> 8) & 0xFF,
            load_base & 0xFF,
            (load_base >> 8) & 0xFF,
            load_base & 0xFF,
            0x3F,
            0xFF,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )


def _mutated_header(load_base: int, offset: int, value: int) -> bytes:
    data = bytearray(_sdfs3_header(load_base))
    data[offset] = value
    return bytes(data)


def _hex_bytes(data: bytes) -> str:
    return "\r".join(f"{value:02X}" for value in data)


def _run_emu(
    *,
    rom_path: Path,
    input_text: str,
    max_cycles: int,
) -> tuple[str, str, int]:
    with tempfile.NamedTemporaryFile("w", encoding="ascii", delete=False) as f:
        f.write(input_text)
        input_path = Path(f.name)
    try:
        cmd = [
            sys.executable,
            str(EMU_PATH),
            str(rom_path),
            "--input",
            str(input_path),
            "--max-cycles",
            str(max_cycles),
            "--dump-memory",
            "0200-0202",
        ]
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    finally:
        input_path.unlink(missing_ok=True)
    return result.stdout, result.stderr, result.returncode


def _dump_bytes(stdout: str, address: int) -> list[int]:
    for line in stdout.splitlines():
        if line.startswith(f"{address:04X} "):
            parts = re.findall(r"\b[0-9A-Fa-f]{2}\b", line.split("  ", 1)[0])
            return [int(part, 16) for part in parts]
    raise AssertionError(f"missing dump line for {address:04X}: {stdout!r}")


def _run_make(
    profile: str,
    target: str,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["make", target, f"MONITOR_PROFILE={profile}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(
            f"make {target} failed for {profile}: stdout={result.stdout!r} stderr={result.stderr!r}"
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
    print("SDFS/68 v3 build tests")
    print("=" * 50)
    tests = [
        test_sdfs3_rejects_base_profile,
        test_sdfs3_profiles_build_and_match_header,
        test_sdfs3_get_info_matches_calling_convention,
        test_rom_detects_sdfs3_api_header,
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
