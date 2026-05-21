#!/usr/bin/env python3
"""SDFS/68 minimal binary tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from mk_sdfs_image import build_sdfs_image  # noqa: E402

EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"


EXPECTED = {
    "sbcio_vdg": {
        "suffix": "-sbcio-vdg",
        "SDFS_LOAD_BASE": 0xD000,
        "SDFS_LOAD_LIMIT": 0xDEFF,
    },
    "k6802_vdg": {
        "suffix": "-k6802-vdg",
        "SDFS_LOAD_BASE": 0xB000,
        "SDFS_LOAD_LIMIT": 0xBEFF,
    },
}


def test_sdfs_rejects_base_profile() -> None:
    result = _run_make("base", "sdfs", expect_success=False)
    assert result.returncode != 0
    assert "stage1 target requires" in result.stdout or "stage1 target requires" in result.stderr
    print("[PASS] test_sdfs_rejects_base_profile")


def test_sdfs_profiles_build_and_match_header() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs")
        suffix = expected["suffix"]
        bin_path = PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN"
        lst_path = PROJECT_ROOT / "build" / f"SDFS{suffix}.lst"
        data = bin_path.read_bytes()
        symbols = _load_symbols(
            lst_path,
            "SDFS_LOAD_BASE",
            "SDFS_LOAD_LIMIT",
            "SDFS_ENTRY",
            "SDFS_END",
        )
        assert symbols["SDFS_LOAD_BASE"] == expected["SDFS_LOAD_BASE"], (
            f"{profile} SDFS_LOAD_BASE mismatch"
        )
        assert symbols["SDFS_LOAD_LIMIT"] == expected["SDFS_LOAD_LIMIT"], (
            f"{profile} SDFS_LOAD_LIMIT mismatch"
        )
        assert len(data) <= symbols["SDFS_LOAD_LIMIT"] - symbols["SDFS_LOAD_BASE"] + 1
        assert data[0:6] == b"SDFS68"
        assert data[6] == 1, "SDFS version mismatch"
        assert data[7] == 16, "SDFS header size mismatch"
        entry = (data[8] << 8) | data[9]
        size = (data[10] << 8) | data[11]
        assert entry == symbols["SDFS_ENTRY"], "SDFS entry mismatch"
        assert size == len(data), "SDFS image size mismatch"
        assert data[12:16] == bytes(4), "SDFS reserved bytes must be zero"
    print("[PASS] test_sdfs_profiles_build_and_match_header")


def test_sdfs_api_wrappers_target_stage1_jump_table() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    data = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS{suffix}.lst",
        "SDFS_LOAD_BASE",
        "S1_BASE",
        "SDFS_API_INIT",
        "SDFS_API_READ_SECTOR",
        "SDFS_API_MOUNT",
        "SDFS_API_FIND_83",
        "SDFS_API_LOAD_FILE_83",
        "SDFS_API_GET_ERROR",
    )
    wrappers = {
        "SDFS_API_INIT": 16,
        "SDFS_API_READ_SECTOR": 19,
        "SDFS_API_MOUNT": 22,
        "SDFS_API_FIND_83": 25,
        "SDFS_API_LOAD_FILE_83": 28,
        "SDFS_API_GET_ERROR": 31,
    }
    for name, offset in wrappers.items():
        index = symbols[name] - symbols["SDFS_LOAD_BASE"]
        target = symbols["S1_BASE"] + offset
        assert data[index : index + 4] == bytes(
            [0xBD, (target >> 8) & 0xFF, target & 0xFF, 0x39]
        ), f"{name} wrapper mismatch"
    print("[PASS] test_sdfs_api_wrappers_target_stage1_jump_table")


def test_stage1_boot_runs_built_sdfs_binary() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "bin")
        _run_make(profile, "stage1")
        _run_make(profile, "sdfs")
        suffix = expected["suffix"]
        stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
        sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
        image = build_sdfs_image(stage1_data=stage1, sdfs_data=sdfs, extra_files=[])
        stdout, stderr, rc = _run_emu_with_sd(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text="BOOT\rX",
            sd_image=image,
            max_cycles=120_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {profile}: rc={rc} stderr={stderr!r}"
        )
        assert "SDFS/68 V1" in stdout, f"missing SDFS banner for {profile}: {stdout!r}"
        assert "SDFS> " in stdout, f"missing SDFS prompt for {profile}: {stdout!r}"
    print("[PASS] test_stage1_boot_runs_built_sdfs_binary")


def test_sdfs_rejects_missing_boot_services() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    sdfs_path = PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN"
    sdfs = sdfs_path.read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS{suffix}.lst",
        "SDFS_LOAD_BASE",
        "SDFS_ENTRY",
    )
    input_text = (
        f"M{symbols['SDFS_LOAD_BASE']:04X}\r"
        f"{_hex_bytes(list(sdfs))}\r.\r"
        f"G{symbols['SDFS_ENTRY']:04X}\rX"
    )
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text=input_text,
        max_cycles=40_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "S1?" in stdout, f"missing S1 error: {stdout!r}"
    print("[PASS] test_sdfs_rejects_missing_boot_services")


def test_sdfs_rejects_bad_boot_services_headers() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS{suffix}.lst",
        "S1_BASE",
        "SDFS_LOAD_BASE",
        "SDFS_ENTRY",
    )
    cases = [
        ("bad version", b"S1API68\x02\x06"),
        ("low api count", b"S1API68\x01\x05"),
    ]
    for label, header in cases:
        input_text = (
            f"M{symbols['S1_BASE']:04X}\r"
            f"{_hex_bytes(list(header))}\r.\r"
            f"M{symbols['SDFS_LOAD_BASE']:04X}\r"
            f"{_hex_bytes(list(sdfs))}\r.\r"
            f"G{symbols['SDFS_ENTRY']:04X}\rX"
        )
        stdout, stderr, rc = _run_emu(
            rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
            input_text=input_text,
            max_cycles=40_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {label}: rc={rc} stderr={stderr!r}"
        )
        assert "S1?" in stdout, f"SDFS accepted {label}: {stdout!r}"
    print("[PASS] test_sdfs_rejects_bad_boot_services_headers")


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


def _run_emu_with_sd(
    *,
    rom_path: Path,
    input_text: str,
    sd_image: bytes,
    max_cycles: int,
) -> tuple[str, str, int]:
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as sd_file:
        sd_file.write(sd_image)
        sd_path = Path(sd_file.name)
    try:
        return _run_emu(
            rom_path=rom_path,
            input_text=input_text,
            max_cycles=max_cycles,
            extra_args=["--sd", str(sd_path)],
        )
    finally:
        sd_path.unlink(missing_ok=True)


def _run_emu(
    *,
    rom_path: Path,
    input_text: str,
    max_cycles: int,
    extra_args: list[str] | None = None,
) -> tuple[str, str, int]:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as input_file:
        input_file.write(input_text.encode("ascii"))
        input_path = Path(input_file.name)
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(EMU_PATH),
                str(rom_path),
                "--input",
                str(input_path),
                "--max-cycles",
                str(max_cycles),
                *(extra_args or []),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        return exc.stdout or "", (exc.stderr or "") + "[TIMEOUT]", -1
    finally:
        input_path.unlink(missing_ok=True)


def _hex_bytes(values: list[int]) -> str:
    return "\r".join(f"{value:02X}" for value in values)


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
    print("SDFS/68 build tests")
    print("=" * 50)
    tests = [
        test_sdfs_rejects_base_profile,
        test_sdfs_profiles_build_and_match_header,
        test_sdfs_api_wrappers_target_stage1_jump_table,
        test_stage1_boot_runs_built_sdfs_binary,
        test_sdfs_rejects_missing_boot_services,
        test_sdfs_rejects_bad_boot_services_headers,
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
