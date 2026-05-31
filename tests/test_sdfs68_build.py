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

from fat32_image import (  # noqa: E402
    EOC,
    SECTOR_SIZE,
    Fat32File,
    Fat32Layout,
    root_entry,
    write_cluster,
    write_sector,
)
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
        assert data[6] == 1, "SDFS binary format version mismatch"
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
        assert "SDFS/68 V1.2 #141" in stdout, f"missing SDFS banner for {profile}: {stdout!r}"
        assert "SDFS> " in stdout, f"missing SDFS prompt for {profile}: {stdout!r}"
    print("[PASS] test_stage1_boot_runs_built_sdfs_binary")


def test_sdfs_loads_srec_and_ihex_files() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "bin")
        _run_make(profile, "stage1")
        _run_make(profile, "sdfs")
        suffix = expected["suffix"]
        stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
        sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
        image = build_sdfs_image(
            stage1_data=stage1,
            sdfs_data=sdfs,
            extra_files=[
                _file("HELLO.S", _srec_file(0x0200, b"S")),
                _file("HELLO.HEX", _ihex_file(0x0201, b"I")),
                _file("EOF.HEX", _ihex_file(0x0202, b"N", trailing_newline=False)),
            ],
        )
        stdout, stderr, rc = _run_emu_with_sd(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text="BOOT\rLOAD HELLO.S\rD0200\rL HELLO.HEX\rD0201\rLOAD EOF.HEX\rD0202\rX",
            sd_image=image,
            max_cycles=160_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {profile}: rc={rc} stderr={stderr!r}"
        )
        assert "0200 53" in stdout, f"S-record load did not write data for {profile}: {stdout!r}"
        assert "0201 49" in stdout, f"Intel HEX load did not write data for {profile}: {stdout!r}"
        assert "0202 4E" in stdout, f"EOF-without-newline HEX did not load for {profile}: {stdout!r}"
        assert stdout.count("OK") >= 3, f"missing load success messages for {profile}: {stdout!r}"
    print("[PASS] test_sdfs_loads_srec_and_ihex_files")


def test_sdfs_dir_lists_root_files_and_skips_non_files() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "bin")
        _run_make(profile, "stage1")
        _run_make(profile, "sdfs")
        suffix = expected["suffix"]
        stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
        sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
        image = build_sdfs_image(
            stage1_data=stage1,
            sdfs_data=sdfs,
            extra_files=[
                _file("HELLO.S", _srec_file(0x0200, b"S")),
                _file("HELLO.HEX", _ihex_file(0x0201, b"I")),
                _file("README.TXT", b"HELLO\r\n"),
                _raw_file(b"SKIPVOL    ", b"", attr=0x08),
                _raw_file(b"SKIPDIR    ", b"", attr=0x10),
                _raw_file(b"SKIPLFN    ", b"", attr=0x0F),
                _raw_file(bytes([0xE5]) + b"DEL    TXT", b"", attr=0x20),
            ],
        )
        stdout, stderr, rc = _run_emu_with_sd(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text="BOOT\rDIR\rX",
            sd_image=image,
            max_cycles=160_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {profile}: rc={rc} stderr={stderr!r}"
        )
        assert "SDFS.BIN A " in stdout, f"SDFS.BIN missing from DIR for {profile}: {stdout!r}"
        assert "HELLO.S A " in stdout, f"HELLO.S missing from DIR for {profile}: {stdout!r}"
        assert "HELLO.HEX A " in stdout, f"HELLO.HEX missing from DIR for {profile}: {stdout!r}"
        assert "README.TXT A 00000007" in stdout, (
            f"README.TXT missing or size mismatch for {profile}: {stdout!r}"
        )
        assert "SKIPVOL" not in stdout, f"volume label leaked into DIR for {profile}: {stdout!r}"
        assert "SKIPDIR" not in stdout, f"directory entry leaked into DIR for {profile}: {stdout!r}"
        assert "SKIPLFN" not in stdout, f"LFN entry leaked into DIR for {profile}: {stdout!r}"
        assert "DEL.TXT" not in stdout, f"deleted entry leaked into DIR for {profile}: {stdout!r}"
        assert stdout.count("SDFS> ") >= 2, f"DIR did not return to prompt for {profile}: {stdout!r}"
    print("[PASS] test_sdfs_dir_lists_root_files_and_skips_non_files")


def test_sdfs_dir_scans_root_chain() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "stage1")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    image = bytearray(
        build_sdfs_image(
            stage1_data=stage1,
            sdfs_data=sdfs,
            extra_files=[
                _file("HELLO.S", _srec_file(0x0200, b"S")),
                _file("HELLO.HEX", _ihex_file(0x0201, b"I")),
            ],
        )
    )
    layout = _layout_from_image(image)
    root_extra_cluster = 64
    _set_fat_entry(image, layout, layout.root_cluster, root_extra_cluster)
    _set_fat_entry(image, layout, root_extra_cluster, EOC)
    _fill_root_tail_with_skipped_entries(image, layout)
    extra = bytearray(SECTOR_SIZE * layout.sectors_per_cluster)
    extra[0:32] = root_entry(b"LATE    TXT", 0x20, root_extra_cluster + 1, 4)
    extra[32] = 0x00
    write_cluster(image, layout, root_extra_cluster, extra)

    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text="BOOT\rDIR\rX",
        sd_image=bytes(image),
        max_cycles=160_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "HELLO.S A " in stdout, f"first root cluster entry missing: {stdout!r}"
    assert "LATE.TXT A 00000004" in stdout, f"root chain entry missing: {stdout!r}"
    assert stdout.count("SDFS> ") >= 2, f"DIR did not return to prompt: {stdout!r}"
    print("[PASS] test_sdfs_dir_scans_root_chain")


def test_sdfs_dir_returns_prompt_on_empty_followup_root_cluster() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "stage1")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    image = bytearray(build_sdfs_image(stage1_data=stage1, sdfs_data=sdfs, extra_files=[]))
    layout = _layout_from_image(image)
    empty_cluster = 65
    _set_fat_entry(image, layout, layout.root_cluster, empty_cluster)
    _set_fat_entry(image, layout, empty_cluster, EOC)
    _fill_root_tail_with_skipped_entries(image, layout)
    write_cluster(image, layout, empty_cluster, bytes(SECTOR_SIZE * layout.sectors_per_cluster))

    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text="BOOT\rDIR\rX",
        sd_image=bytes(image),
        max_cycles=160_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "SDFS.BIN A " in stdout, f"root entry missing before followup cluster: {stdout!r}"
    assert stdout.count("SDFS> ") >= 2, f"DIR did not recover to prompt: {stdout!r}"
    print("[PASS] test_sdfs_dir_returns_prompt_on_empty_followup_root_cluster")


def test_sdfs_dir_requires_exact_command_and_dump_still_works() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "stage1")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    image = build_sdfs_image(stage1_data=stage1, sdfs_data=sdfs, extra_files=[])
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text="BOOT\rDIR X\rD0100\rX",
        sd_image=image,
        max_cycles=140_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "0100 " in stdout, f"Dhhhh dispatch was broken: {stdout!r}"
    assert "?" in stdout, f"DIR with extra argument was accepted: {stdout!r}"
    assert stdout.count("SDFS> ") >= 3, f"prompt did not recover: {stdout!r}"
    print("[PASS] test_sdfs_dir_requires_exact_command_and_dump_still_works")


def test_sdfs_exit_returns_to_monitor_and_boots_again() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "stage1")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    image = build_sdfs_image(stage1_data=stage1, sdfs_data=sdfs, extra_files=[])
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text="BOOT\rEXIT\rBOOT\rX",
        sd_image=image,
        max_cycles=180_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert stdout.count("SDFS/68 V1.2 #141") >= 2, f"EXIT did not allow BOOT again: {stdout!r}"
    assert stdout.count("] ") >= 2, f"monitor prompt did not return after EXIT: {stdout!r}"
    print("[PASS] test_sdfs_exit_returns_to_monitor_and_boots_again")


def test_sdfs_loader_errors_return_to_prompt() -> None:
    profile = "sbcio_vdg"
    _run_make(profile, "bin")
    _run_make(profile, "stage1")
    _run_make(profile, "sdfs")
    suffix = EXPECTED[profile]["suffix"]
    stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
    sdfs = (PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes()
    image = build_sdfs_image(
        stage1_data=stage1,
        sdfs_data=sdfs,
        extra_files=[
            _file("BAD.HEX", b":00000000FF\r\n"),
            _file("NOEND.S", b"S1060200010203F1\r\n"),
        ],
    )
    stdout, stderr, rc = _run_emu_with_sd(
        rom_path=PROJECT_ROOT / "build" / "mc6800-monitor-sbcio-vdg.bin",
        input_text="BOOT\rLOAD MISSING.S\rLOADHELLO.S\rL BAD.HEX\rL NOEND.S\rX",
        sd_image=image,
        max_cycles=140_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "MISSING.S" in stdout and "LOADHELLO.S" in stdout
    assert "BAD.HEX" in stdout and "NOEND.S" in stdout
    assert stdout.count("SDFS> ") >= 5, f"SDFS prompt did not recover after errors: {stdout!r}"
    assert "?" in stdout, f"missing loader error output: {stdout!r}"
    print("[PASS] test_sdfs_loader_errors_return_to_prompt")


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


def _file(name: str, data: bytes) -> Fat32File:
    stem, _dot, ext = name.partition(".")
    name83 = stem.upper().encode("ascii").ljust(8, b" ")
    name83 += ext.upper().encode("ascii").ljust(3, b" ")
    return Fat32File(name83, data)


def _raw_file(name83: bytes, data: bytes, *, attr: int) -> Fat32File:
    return Fat32File(name83, data, attr=attr)


def _layout_from_image(image: bytes | bytearray) -> Fat32Layout:
    volume_start = int.from_bytes(image[454:458], "little")
    vbr = volume_start * SECTOR_SIZE
    total_volume_sectors = int.from_bytes(image[vbr + 32 : vbr + 36], "little")
    reserved_sectors = int.from_bytes(image[vbr + 14 : vbr + 16], "little")
    fat_count = image[vbr + 16]
    fat_size_sectors = int.from_bytes(image[vbr + 36 : vbr + 40], "little")
    sectors_per_cluster = image[vbr + 13]
    root_cluster = int.from_bytes(image[vbr + 44 : vbr + 48], "little")
    fat_lba = volume_start + reserved_sectors
    data_start_lba = fat_lba + fat_count * fat_size_sectors
    return Fat32Layout(
        volume_start_lba=volume_start,
        fat_lba=fat_lba,
        root_dir_lba=data_start_lba + (root_cluster - 2) * sectors_per_cluster,
        data_start_lba=data_start_lba,
        total_volume_sectors=total_volume_sectors,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size_sectors,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=root_cluster,
    )


def _set_fat_entry(image: bytearray, layout: Fat32Layout, cluster: int, value: int) -> None:
    offset = cluster * 4
    sector_index = offset // SECTOR_SIZE
    sector_offset = offset % SECTOR_SIZE
    for copy_index in range(layout.fat_count):
        lba = layout.fat_lba + copy_index * layout.fat_size_sectors + sector_index
        start = lba * SECTOR_SIZE
        sector = bytearray(image[start : start + SECTOR_SIZE])
        sector[sector_offset : sector_offset + 4] = value.to_bytes(4, "little")
        write_sector(image, lba, sector)


def _fill_root_tail_with_skipped_entries(image: bytearray, layout: Fat32Layout) -> None:
    root_lba = layout.root_dir_lba
    start = root_lba * SECTOR_SIZE
    root = bytearray(image[start : start + SECTOR_SIZE * layout.sectors_per_cluster])
    for index in range(SECTOR_SIZE * layout.sectors_per_cluster // 32):
        entry_start = index * 32
        if root[entry_start] == 0x00:
            for fill_index in range(index, SECTOR_SIZE * layout.sectors_per_cluster // 32):
                fill_start = fill_index * 32
                root[fill_start : fill_start + 32] = root_entry(b"SKIP    TMP", 0x08, 0, 0)
            break
    write_cluster(image, layout, layout.root_cluster, root)


def _srec_file(address: int, data: bytes, trailing_newline: bool = True) -> bytes:
    count = len(data) + 3
    values = [count, (address >> 8) & 0xFF, address & 0xFF, *data]
    checksum = (~sum(values)) & 0xFF
    record = "S1" + "".join(f"{value:02X}" for value in [*values, checksum])
    text = record + "\r\nS9030000FC"
    if trailing_newline:
        text += "\r\n"
    return text.encode("ascii")


def _ihex_file(address: int, data: bytes, trailing_newline: bool = True) -> bytes:
    values = [len(data), (address >> 8) & 0xFF, address & 0xFF, 0x00, *data]
    checksum = (-sum(values)) & 0xFF
    record = ":" + "".join(f"{value:02X}" for value in [*values, checksum])
    text = record + "\r\n:00000001FF"
    if trailing_newline:
        text += "\r\n"
    return text.encode("ascii")


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
        test_sdfs_loads_srec_and_ihex_files,
        test_sdfs_dir_lists_root_files_and_skips_non_files,
        test_sdfs_dir_scans_root_chain,
        test_sdfs_dir_returns_prompt_on_empty_followup_root_cluster,
        test_sdfs_dir_requires_exact_command_and_dump_still_works,
        test_sdfs_exit_returns_to_monitor_and_boots_again,
        test_sdfs_loader_errors_return_to_prompt,
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
