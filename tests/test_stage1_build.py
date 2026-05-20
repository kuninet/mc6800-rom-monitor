#!/usr/bin/env python3
"""Stage1 binary layout tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from sd_fixtures import (  # noqa: E402
    MULTI_CLUSTER_1,
    MULTI_CLUSTER_1_PREFIX,
    build_fat32_image,
    layout_for_image,
)

EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"


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
        symbols = _load_symbols(
            lst_path,
            "S1_BASE",
            "S1_LIMIT",
            "SDFS_LOAD_BASE",
            "S1_INIT",
            "S1_READ_SECTOR",
            "S1_MOUNT",
            "S1_FIND_83",
            "S1_LOAD_FILE_83",
            "S1_GET_ERROR",
            "S1_END",
        )
        assert symbols["S1_BASE"] == expected["S1_BASE"], f"{profile} S1_BASE mismatch"
        assert symbols["S1_LIMIT"] == expected["S1_LIMIT"], f"{profile} S1_LIMIT mismatch"
        assert symbols["SDFS_LOAD_BASE"] == expected["SDFS_LOAD_BASE"], (
            f"{profile} SDFS_LOAD_BASE mismatch"
        )
        assert len(data) <= symbols["S1_LIMIT"] - symbols["S1_BASE"] + 1
        _assert_stage1_header(data)
        _assert_jump(data, 16, symbols["S1_INIT"])
        _assert_jump(data, 19, symbols["S1_READ_SECTOR"])
        _assert_jump(data, 22, symbols["S1_MOUNT"])
        _assert_jump(data, 25, symbols["S1_FIND_83"])
        _assert_jump(data, 28, symbols["S1_LOAD_FILE_83"])
        _assert_jump(data, 31, symbols["S1_GET_ERROR"])
    print("[PASS] test_stage1_profiles_build_and_match_layout")


def test_stage1_read_sector_service_reads_known_fixture_sector() -> None:
    profile = "sbcio_vdg"
    _run_make(profile)
    _run_make(profile, target="bin")
    expected = EXPECTED[profile]
    suffix = expected["suffix"]
    stage1_data = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"stage1{suffix}.lst",
        "S1_BASE",
        "SDFS_LOAD_BASE",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
    )
    layout = layout_for_image(with_mbr=True)
    lba = layout.cluster_lba(MULTI_CLUSTER_1)
    dest = symbols["SDFS_LOAD_BASE"]
    harness_addr = 0x0100
    harness = [
        0xBD, ((symbols["S1_BASE"] + 16) >> 8) & 0xFF, (symbols["S1_BASE"] + 16) & 0xFF,
        0x25, 0x1D,
        0x86, (lba >> 24) & 0xFF, 0xB7, (symbols["SD_LBA0"] >> 8) & 0xFF, symbols["SD_LBA0"] & 0xFF,
        0x86, (lba >> 16) & 0xFF, 0xB7, (symbols["SD_LBA1"] >> 8) & 0xFF, symbols["SD_LBA1"] & 0xFF,
        0x86, (lba >> 8) & 0xFF, 0xB7, (symbols["SD_LBA2"] >> 8) & 0xFF, symbols["SD_LBA2"] & 0xFF,
        0x86, lba & 0xFF, 0xB7, (symbols["SD_LBA3"] >> 8) & 0xFF, symbols["SD_LBA3"] & 0xFF,
        0xCE, (dest >> 8) & 0xFF, dest & 0xFF,
        0xBD, ((symbols["S1_BASE"] + 19) >> 8) & 0xFF, (symbols["S1_BASE"] + 19) & 0xFF,
        0x25, 0x01,
        0x3F,
        0x3F,
    ]
    input_text = (
        f"M{symbols['S1_BASE']:04X}\r"
        f"{_hex_bytes(list(stage1_data))}\r.\r"
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{dest:04X}-{dest + 0x0F:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text=input_text,
        sd_image=build_fat32_image(with_mbr=True),
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    line = _dump_line(stdout, dest)
    expected_prefix = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_1_PREFIX[:16])
    assert expected_prefix in line, f"stage1 read mismatch: {line!r}\nstdout={stdout!r}"
    print("[PASS] test_stage1_read_sector_service_reads_known_fixture_sector")


def test_stage1_mount_service_accepts_fat32_fixtures() -> None:
    for with_mbr in (True, False):
        value = _run_stage1_mount_harness(build_fat32_image(with_mbr=with_mbr))
        assert value == 0x42, f"S1_MOUNT failed for with_mbr={with_mbr}: {value:02X}"
    print("[PASS] test_stage1_mount_service_accepts_fat32_fixtures")


def test_stage1_mount_service_rejects_invalid_fat32() -> None:
    value = _run_stage1_mount_harness(bytes(512 * 64))
    assert value == 0xE1, f"S1_MOUNT unexpectedly accepted invalid image: {value:02X}"
    print("[PASS] test_stage1_mount_service_rejects_invalid_fat32")


def test_stage1_find_83_service_finds_root_entries() -> None:
    value = _run_stage1_find_harness(
        build_fat32_image(with_mbr=True),
        b"TEST    S  ",
    )
    assert value == 0x42, f"S1_FIND_83 failed to find TEST.S: {value:02X}"

    value = _run_stage1_find_harness(
        build_fat32_image(with_mbr=True, root_chain=True),
        b"LATE    BIN",
    )
    assert value == 0x42, f"S1_FIND_83 failed to find chained root entry: {value:02X}"
    print("[PASS] test_stage1_find_83_service_finds_root_entries")


def test_stage1_find_83_service_rejects_missing_name() -> None:
    value = _run_stage1_find_harness(
        build_fat32_image(with_mbr=True),
        b"NOPE    BIN",
    )
    assert value == 0xE1, f"S1_FIND_83 unexpectedly found missing file: {value:02X}"
    print("[PASS] test_stage1_find_83_service_rejects_missing_name")


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


def _run_make(
    profile: str,
    target: str = "stage1",
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
            f"make stage1 failed for {profile}: stdout={result.stdout!r} stderr={result.stderr!r}"
        )
    return result


def _run_stage1_mount_harness(sd_image: bytes) -> int:
    profile = "sbcio_vdg"
    _run_make(profile)
    _run_make(profile, target="bin")
    expected = EXPECTED[profile]
    suffix = expected["suffix"]
    stage1_data = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"stage1{suffix}.lst",
        "S1_BASE",
        "SDFS_LOAD_BASE",
    )
    dest = symbols["SDFS_LOAD_BASE"]
    harness_addr = 0x0100
    harness = [
        0xBD, ((symbols["S1_BASE"] + 16) >> 8) & 0xFF, (symbols["S1_BASE"] + 16) & 0xFF,
        0x25, 0x0B,
        0xBD, ((symbols["S1_BASE"] + 22) >> 8) & 0xFF, (symbols["S1_BASE"] + 22) & 0xFF,
        0x25, 0x06,
        0x86, 0x42,
        0xB7, (dest >> 8) & 0xFF, dest & 0xFF,
        0x3F,
        0x86, 0xE1,
        0xB7, (dest >> 8) & 0xFF, dest & 0xFF,
        0x3F,
    ]
    input_text = (
        f"M{symbols['S1_BASE']:04X}\r"
        f"{_hex_bytes(list(stage1_data))}\r.\r"
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{dest:04X}-{dest:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text=input_text,
        sd_image=sd_image,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    line = _dump_line(stdout, dest)
    match = re.search(rf"{dest:04X}\s+([0-9A-Fa-f]{{2}})", line)
    if not match:
        raise AssertionError(f"missing mount result byte: {line!r}\nstdout={stdout!r}")
    return int(match.group(1), 16)


def _run_stage1_find_harness(sd_image: bytes, fat_name: bytes) -> int:
    if len(fat_name) != 11:
        raise AssertionError("FAT name must be exactly 11 bytes")

    profile = "sbcio_vdg"
    _run_make(profile)
    _run_make(profile, target="bin")
    expected = EXPECTED[profile]
    suffix = expected["suffix"]
    stage1_data = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"stage1{suffix}.lst",
        "S1_BASE",
        "SDFS_LOAD_BASE",
    )
    dest = symbols["SDFS_LOAD_BASE"]
    harness_addr = 0x0100
    name_addr = harness_addr + 30
    harness = [
        0xBD, ((symbols["S1_BASE"] + 16) >> 8) & 0xFF, (symbols["S1_BASE"] + 16) & 0xFF,
        0x25, 0x13,
        0xBD, ((symbols["S1_BASE"] + 22) >> 8) & 0xFF, (symbols["S1_BASE"] + 22) & 0xFF,
        0x25, 0x0E,
        0xCE, (name_addr >> 8) & 0xFF, name_addr & 0xFF,
        0xBD, ((symbols["S1_BASE"] + 25) >> 8) & 0xFF, (symbols["S1_BASE"] + 25) & 0xFF,
        0x25, 0x06,
        0x86, 0x42,
        0xB7, (dest >> 8) & 0xFF, dest & 0xFF,
        0x3F,
        0x86, 0xE1,
        0xB7, (dest >> 8) & 0xFF, dest & 0xFF,
        0x3F,
        *fat_name,
    ]
    input_text = (
        f"M{symbols['S1_BASE']:04X}\r"
        f"{_hex_bytes(list(stage1_data))}\r.\r"
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{dest:04X}-{dest:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text=input_text,
        sd_image=sd_image,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    line = _dump_line(stdout, dest)
    match = re.search(rf"{dest:04X}\s+([0-9A-Fa-f]{{2}})", line)
    if not match:
        raise AssertionError(f"missing find result byte: {line!r}\nstdout={stdout!r}")
    return int(match.group(1), 16)


def _run_emu_with_sd(
    *,
    rom_path: Path,
    input_text: str,
    sd_image: bytes,
    max_cycles: int = 60_000_000,
) -> tuple[str, str, int]:
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as input_file:
        input_file.write(input_text.encode("ascii"))
        input_path = Path(input_file.name)
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as sd_file:
        sd_file.write(sd_image)
        sd_path = Path(sd_file.name)
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
                "--sd",
                str(sd_path),
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
        sd_path.unlink(missing_ok=True)


def _hex_bytes(values: list[int]) -> str:
    return "\r".join(f"{value:02X}" for value in values)


def _dump_line(stdout: str, address: int) -> str:
    marker = f"{address:04X}"
    for line in stdout.splitlines():
        if line.lstrip().startswith(marker):
            return line
    raise AssertionError(f"missing dump line {marker}: {stdout!r}")


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
        test_stage1_read_sector_service_reads_known_fixture_sector,
        test_stage1_mount_service_accepts_fat32_fixtures,
        test_stage1_mount_service_rejects_invalid_fat32,
        test_stage1_find_83_service_finds_root_entries,
        test_stage1_find_83_service_rejects_missing_name,
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
