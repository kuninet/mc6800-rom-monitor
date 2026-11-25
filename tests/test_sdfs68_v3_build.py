#!/usr/bin/env python3
"""SDFS/68 v3 resident stub build tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"
SDFS3SYS_FIXED_LBA = 64
SDFS3SYS_FAT_PARTITION_LBA = 128
SECTOR_SIZE = 512
SDFS3SYS_LOADER_HARNESS_ADDR = 0x0300
TEMP_ROOT = PROJECT_ROOT / "build" / "tmp"

from mk_sdfs3sys import (  # noqa: E402
    CHECKSUM_OFFSET,
    FLAG_CHECKSUM16,
    HEADER_SIZE,
    MAGIC,
    build_sdfs3sys_image,
    checksum16,
    parse_sdfs3sys_header,
)
from fat32_image import Fat32File, build_fat32_image_from_files  # noqa: E402


EXPECTED = {
    "sbcio_4000": {
        "suffix": "-sbcio-4000",
        "SDFS3_LOAD_BASE": 0x5000,
        "SDFS3_LOAD_LIMIT": 0x7EFF,
        "USER_RAM_END": 0x3FFF,
    },
    "k6802_4000": {
        "suffix": "-k6802-4000",
        "SDFS3_LOAD_BASE": 0x5000,
        "SDFS3_LOAD_LIMIT": 0x7EFF,
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
            "SDFS3_LOAD_BASE",
            "SDFS3_LOAD_LIMIT",
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
            "SDFS3_GET_MEMTOP",
            "SDFS3_GET_CAPS",
            "SDFS3_NOT_IMPLEMENTED",
            "SDFS3_INIT",
            "SDFS3_END",
        )
        assert symbols["SDFS3_LOAD_BASE"] == expected["SDFS3_LOAD_BASE"]
        assert symbols["SDFS3_LOAD_LIMIT"] == expected["SDFS3_LOAD_LIMIT"]
        assert symbols["USER_RAM_END"] == expected["USER_RAM_END"]
        assert symbols["SDFS3_API_HEADER"] == symbols["SDFS3_LOAD_BASE"]
        assert len(data) <= symbols["SDFS3_LOAD_LIMIT"] - symbols["SDFS3_LOAD_BASE"] + 1
        assert len(data) == symbols["SDFS3_END"] - symbols["SDFS3_LOAD_BASE"]
        assert data[0:8] == b"SDFS3API"
        assert data[8] == 1, "SDFS3 api major mismatch"
        assert data[9] == 1, "SDFS3 api minor mismatch"
        assert data[10] == 14, "SDFS3 api count mismatch"
        assert data[11] == 0, "SDFS3 flags should be zero in stub"
        assert _word(data, 0x0C) == symbols["SDFS3_JUMP_TABLE"]
        assert _word(data, 0x0E) == symbols["SDFS3_LOAD_BASE"]
        assert _word(data, 0x10) == symbols["SDFS3_END"] - 1
        assert _word(data, 0x12) == expected["USER_RAM_END"]
        assert _word(data, 0x14) == 0
        assert _word(data, 0x16) == 0
        jump_table = symbols["SDFS3_JUMP_TABLE"] - symbols["SDFS3_LOAD_BASE"]
        assert _word(data, jump_table) == symbols["SDFS3_GET_INFO"]
        assert _word(data, jump_table + 2) == symbols["SDFS3_CMD_DISPATCH"]
        assert _word(data, jump_table + 4) == symbols["SDFS3_LOAD_PATH"]
        assert _word(data, jump_table + 6) == symbols["SDFS3_READ_STREAM_OPEN"]
        assert _word(data, jump_table + 8) == symbols["SDFS3_READ_STREAM_GETC"]
        assert _word(data, jump_table + 10) == symbols["SDFS3_READ_STREAM_CLOSE"]
        assert _word(data, jump_table + 12) == symbols["SDFS3_GET_ERROR"]
        assert _word(data, jump_table + 14) == symbols["SDFS3_GET_MEMTOP"]
        assert _word(data, jump_table + 16) == symbols["SDFS3_GET_CAPS"]
        assert _word(data, jump_table + 18) == symbols["SDFS3_NOT_IMPLEMENTED"]
        assert _word(data, jump_table + 20) == symbols["SDFS3_NOT_IMPLEMENTED"]
        assert _word(data, jump_table + 22) == symbols["SDFS3_NOT_IMPLEMENTED"]
        assert _word(data, jump_table + 24) == symbols["SDFS3_NOT_IMPLEMENTED"]
        assert _word(data, jump_table + 26) == symbols["SDFS3_INIT"]
        get_error = symbols["SDFS3_GET_ERROR"] - symbols["SDFS3_LOAD_BASE"]
        assert data[get_error + 3 : get_error + 5] == bytes([0x0C, 0x39])
        assert b"SDFS/68 V3 " in data, "welcome string missing from resident binary"
    print("[PASS] test_sdfs3_profiles_build_and_match_header")


def test_sdfs3_get_info_matches_calling_convention() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "sdfs3")
    suffix = expected["suffix"]
    data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS3_LOAD_BASE",
        "SDFS3_GET_INFO",
        "SDFS3_API_HEADER",
    )
    get_info = symbols["SDFS3_GET_INFO"] - symbols["SDFS3_LOAD_BASE"]
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


def test_sdfs3_memtop_and_caps_match_calling_convention() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs3")
        suffix = expected["suffix"]
        data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
        symbols = _load_symbols(
            PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
            "SDFS3_LOAD_BASE",
            "SDFS3_API_HEADER",
            "SDFS3_GET_MEMTOP",
            "SDFS3_GET_CAPS",
        )
        get_memtop = symbols["SDFS3_GET_MEMTOP"] - symbols["SDFS3_LOAD_BASE"]
        memtop = expected["USER_RAM_END"]
        assert data[get_memtop : get_memtop + 5] == bytes(
            [0xCE, (memtop >> 8) & 0xFF, memtop & 0xFF, 0x0C, 0x39]
        )

        get_caps = symbols["SDFS3_GET_CAPS"] - symbols["SDFS3_LOAD_BASE"]
        header = symbols["SDFS3_API_HEADER"]
        assert data[get_caps : get_caps + 9] == bytes(
            [
                0x86,
                0x00,
                0xC6,
                0x00,
                0xCE,
                (header >> 8) & 0xFF,
                header & 0xFF,
                0x0C,
                0x39,
            ]
        )
    print("[PASS] test_sdfs3_memtop_and_caps_match_calling_convention")


def test_sdfs3_cmd_dispatch_parser_classifies_stub_commands() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3")
    suffix = expected["suffix"]
    resident = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS3_LOAD_BASE",
        "SDFS3_CMD_DISPATCH",
        "SDFS3_GET_ERROR",
    )
    cases = [
        ("DIR", 0x03),
        (" dir ", 0x03),
        ("TYPE README.TXT", 0x03),
        ("LoAd HELLO.S", 0x05),
        ("RUN MISSING.S", 0x06),
        ("FOO.COM ARG", 0x07),
        ("foo.com", 0x07),
        ("", 0x02),
        ("   ", 0x02),
        ("UNKNOWN", 0x02),
    ]
    with _temporary_directory() as tmp:
        harness = _assemble_cmd_dispatch_harness(Path(tmp), symbols, cases)
    result_addr = 0x0200
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{symbols['SDFS3_LOAD_BASE']:04X}\r"
            f"{_hex_bytes(resident)}\r.\r"
            "M0300\r"
            f"{_hex_bytes(harness)}\r.\r"
            "G0300\r"
            f"D{result_addr:04X}-{result_addr + len(cases) * 2 - 1:04X}\r"
            "\r"
        ),
        max_cycles=30_000_000,
        dump_range=f"{result_addr:04X}-{result_addr + len(cases) * 2 - 1:04X}",
        timeout=20,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for CMD_DISPATCH parser: rc={rc} stderr={stderr!r}"
    )
    values = _dump_range_bytes(stdout, result_addr, len(cases) * 2)
    expected_values: list[int] = []
    for _, error_code in cases:
        expected_values.extend([1, error_code])
    assert values == expected_values, (
        f"CMD_DISPATCH parser classification mismatch: {values!r}\nstdout={stdout!r}"
    )
    print("[PASS] test_sdfs3_cmd_dispatch_parser_classifies_stub_commands")


def test_sdfs3sys_profiles_build_and_match_header() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs3sys")
        suffix = expected["suffix"]
        sys_path = PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN"
        bin_path = PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN"
        lst_path = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
        image = sys_path.read_bytes()
        payload = bin_path.read_bytes()
        symbols = _load_symbols(
            lst_path,
            "SDFS3_LOAD_BASE",
            "SDFS3_LOAD_LIMIT",
            "SDFS3_JUMP_TABLE",
            "SDFS3_GET_INFO",
        )
        header = parse_sdfs3sys_header(image)
        assert image[0:8] == MAGIC
        assert header.header_version == 1
        assert header.abi_major == 1
        assert header.abi_minor == 0
        assert header.flags == FLAG_CHECKSUM16
        assert header.load_address == expected["SDFS3_LOAD_BASE"]
        assert header.load_address == symbols["SDFS3_LOAD_BASE"]
        assert len(payload) <= symbols["SDFS3_LOAD_LIMIT"] - symbols["SDFS3_LOAD_BASE"] + 1
        assert header.image_size == HEADER_SIZE + len(payload)
        assert header.entry_offset == symbols["SDFS3_GET_INFO"] - symbols["SDFS3_LOAD_BASE"]
        assert header.api_table_offset == symbols["SDFS3_JUMP_TABLE"] - symbols["SDFS3_LOAD_BASE"]
        assert header.work_min == 0
        assert header.bank_window_hint == 0
        assert header.header_size == HEADER_SIZE
        assert header.checksum == checksum16(image)
        assert image[HEADER_SIZE:] == payload
    print("[PASS] test_sdfs3sys_profiles_build_and_match_header")


def test_sdfs3_load_base_can_differ_from_v2_sdfs_load_base() -> None:
    profile = "k6802_vdg"
    suffix = "-k6802-vdg-sdfs3-5000"
    extra_args = [
        "SDFS3_LOAD_BASE=0x5000",
        "SDFS3_LOAD_LIMIT=0x7EFF",
        "BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000",
    ]
    _run_make(profile, "bin", extra_args=extra_args)
    _run_make(profile, "sdfs3", extra_args=extra_args)

    rom_symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SDFS_LOAD_BASE",
        "SDFS3_LOAD_BASE",
    )
    resident_symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS_LOAD_BASE",
        "SDFS_LOAD_LIMIT",
        "SDFS3_LOAD_BASE",
        "SDFS3_LOAD_LIMIT",
        "SDFS3_API_HEADER",
        "SDFS3_END",
    )
    data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()

    assert rom_symbols["SDFS_LOAD_BASE"] == 0xB000
    assert rom_symbols["SDFS3_LOAD_BASE"] == 0x5000
    assert resident_symbols["SDFS_LOAD_BASE"] == 0xB000
    assert resident_symbols["SDFS_LOAD_LIMIT"] == 0xBEFF
    assert resident_symbols["SDFS3_LOAD_BASE"] == 0x5000
    assert resident_symbols["SDFS3_LOAD_LIMIT"] == 0x7EFF
    assert resident_symbols["SDFS3_API_HEADER"] == 0x5000
    assert len(data) == resident_symbols["SDFS3_END"] - resident_symbols["SDFS3_LOAD_BASE"]
    assert _word(data, 0x0E) == 0x5000
    print("[PASS] test_sdfs3_load_base_can_differ_from_v2_sdfs_load_base")


def test_sdfs3sys_rejects_bad_header_and_checksum() -> None:
    payload = b"SDFS3API" + bytes(range(64))
    image = build_sdfs3sys_image(
        resident_data=payload,
        load_address=0x5000,
        load_limit=0x7EFF,
        entry_address=0x5018,
        api_table_address=0x5018,
    )
    bad_magic = bytearray(image)
    bad_magic[0] = ord("X")
    try:
        parse_sdfs3sys_header(bytes(bad_magic))
    except ValueError as exc:
        assert "magic" in str(exc)
    else:
        raise AssertionError("bad SDFS3SYS magic should be rejected")

    bad_checksum = bytearray(image)
    bad_checksum[-1] ^= 0x01
    try:
        parse_sdfs3sys_header(bytes(bad_checksum))
    except ValueError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("bad SDFS3SYS checksum should be rejected")
    print("[PASS] test_sdfs3sys_rejects_bad_header_and_checksum")


def test_sdfs3sys_rejects_payload_outside_load_range() -> None:
    try:
        build_sdfs3sys_image(
            resident_data=b"X" * 2,
            load_address=0x5000,
            load_limit=0x5000,
            entry_address=0x5000,
            api_table_address=0x5000,
        )
    except ValueError as exc:
        assert "load range" in str(exc)
    else:
        raise AssertionError("payload outside SDFS load range should be rejected")
    print("[PASS] test_sdfs3sys_rejects_payload_outside_load_range")


def test_sdfs3sys_cli_reports_bad_input() -> None:
    with _temporary_directory() as tmp:
        root = Path(tmp)
        payload = root / "SDFS3.BIN"
        listing = root / "SDFS3.lst"
        output = root / "SDFS3SYS.BIN"
        payload.write_bytes(b"SDFS3API")
        listing.write_text("", encoding="ascii")
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "mk_sdfs3sys.py"),
                "--input",
                str(payload),
                "--listing",
                str(listing),
                "--output",
                str(output),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        assert result.returncode == 2
        assert "mk-sdfs3sys:" in result.stderr
        assert not output.exists()
    print("[PASS] test_sdfs3sys_cli_reports_bad_input")


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
        "SDFS3_LOAD_BASE",
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
        ("valid", _sdfs3_header(symbols["SDFS3_LOAD_BASE"]), 0x42),
        ("bad magic", b"XDFS3API" + _sdfs3_header(symbols["SDFS3_LOAD_BASE"])[8:], 0xE1),
        ("bad major", _mutated_header(symbols["SDFS3_LOAD_BASE"], 8, 0x02), 0xE1),
        ("legacy api count 7", _mutated_header(symbols["SDFS3_LOAD_BASE"], 10, 0x07), 0xE1),
        ("short api count 8", _mutated_header(symbols["SDFS3_LOAD_BASE"], 10, 0x08), 0xE1),
        ("legacy api count 9", _mutated_header(symbols["SDFS3_LOAD_BASE"], 10, 0x09), 0xE1),
        ("legacy api count 13", _mutated_header(symbols["SDFS3_LOAD_BASE"], 10, 0x0D), 0xE1),
    ]
    for label, header, expected_status in cases:
        stdout, stderr, rc = _run_emu(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text=(
                f"M{symbols['SDFS3_LOAD_BASE']:04X}\r"
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
                (symbols["SDFS3_LOAD_BASE"] >> 8) & 0xFF,
                symbols["SDFS3_LOAD_BASE"] & 0xFF,
            ], f"{label} returned header address mismatch: {values!r}"
    print("[PASS] test_rom_detects_sdfs3_api_header")


def test_rom_cmd_gateway_calls_resident_dispatch() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "LINE_BUF",
        "SDFS3_LOAD_BASE",
    )
    status_addr = 0x0200
    b_addr = 0x0201
    x_addr = 0x0202
    load_base = symbols["SDFS3_LOAD_BASE"]
    jump_table = load_base + 0x18
    dispatch = jump_table + 0x1C
    header = _sdfs3_header(load_base, jump_table=jump_table, work_end=dispatch + 13)
    jump_table_data = bytes(
        [
            0x00,
            0x00,
            (dispatch >> 8) & 0xFF,
            dispatch & 0xFF,
            *([0x00, 0x00] * 12),
        ]
    )
    dispatch_stub = bytes(
        [
            0xB7,
            (status_addr >> 8) & 0xFF,
            status_addr & 0xFF,
            0xF7,
            (b_addr >> 8) & 0xFF,
            b_addr & 0xFF,
            0xFF,
            (x_addr >> 8) & 0xFF,
            x_addr & 0xFF,
            0x0C,
            0x39,
        ]
    )
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{load_base:04X}\r"
            f"{_hex_bytes(header)}\r.\r"
            f"M{jump_table:04X}\r"
            f"{_hex_bytes(jump_table_data)}\r.\r"
            f"M{dispatch:04X}\r"
            f"{_hex_bytes(dispatch_stub)}\r.\r"
            "CMD DIR\r"
            f"D{status_addr:04X}-{x_addr + 1:04X}\r"
            "\r"
        ),
        max_cycles=20_000_000,
        dump_range=f"{status_addr:04X}-{x_addr + 1:04X}",
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for CMD gateway: rc={rc} stderr={stderr!r}"
    )
    values = _dump_bytes(stdout, status_addr)
    assert values[0] == 0x00, f"CMD gateway should pass A=0: {values!r}\nstdout={stdout!r}"
    assert values[1] == 3, f"CMD gateway should pass tail length 3: {values!r}"
    assert values[2:4] == [
        ((symbols["LINE_BUF"] + 4) >> 8) & 0xFF,
        (symbols["LINE_BUF"] + 4) & 0xFF,
    ], f"CMD gateway should pass tail pointer LINE_BUF+4: {values!r}"

    failing_dispatch = bytes([0x86, 0x01, 0x0D, 0x39])
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{load_base:04X}\r"
            f"{_hex_bytes(header)}\r.\r"
            f"M{jump_table:04X}\r"
            f"{_hex_bytes(jump_table_data)}\r.\r"
            f"M{dispatch:04X}\r"
            f"{_hex_bytes(failing_dispatch)}\r.\r"
            "CMD DIR\r"
            "\r"
        ),
        max_cycles=20_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for failing CMD gateway: rc={rc} stderr={stderr!r}"
    )
    assert "?" in stdout, f"CMD dispatch carry set should return error: {stdout!r}"

    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text="CMD DIR\r\r",
        max_cycles=20_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for unloaded CMD gateway: rc={rc} stderr={stderr!r}"
    )
    assert "?" in stdout, f"CMD without resident should return error: {stdout!r}"
    print("[PASS] test_rom_cmd_gateway_calls_resident_dispatch")


def test_fixed_lba_loader_harness_loads_sdfs3sys() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3sys")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SD_INIT",
        "SD_READ_SECTOR",
        "SDFS3_FIND_API",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
        "SDFS3_LOAD_BASE",
    )
    sdfs3sys = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    assert len(sdfs3sys) <= 16 * 1024, "SDFS3SYS harness keeps the phase 1 image under 16KB"
    payload = sdfs3sys[HEADER_SIZE:]
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r"
            "D0200-0202\r"
            f"D{symbols['SDFS3_LOAD_BASE']:04X}-{symbols['SDFS3_LOAD_BASE'] + len(payload) - 1:04X}\r"
            "\r"
        ),
        max_cycles=120_000_000,
        dump_range=f"0200-{symbols['SDFS3_LOAD_BASE'] + len(payload) - 1:04X}",
        sd_image=_build_sdfs3sys_sd_image(sdfs3sys),
        timeout=20,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for SDFS3SYS loader harness: rc={rc} stderr={stderr!r}"
    )
    status = _dump_bytes(stdout, 0x0200)
    assert status[0] == 0x42, f"SDFS3SYS loader should report success: {status!r}\nstdout={stdout!r}"
    assert status[1:3] == [
        (symbols["SDFS3_LOAD_BASE"] >> 8) & 0xFF,
        symbols["SDFS3_LOAD_BASE"] & 0xFF,
    ], f"SDFS3_FIND_API should return resident base: {status!r}"
    loaded = _dump_range_bytes(stdout, symbols["SDFS3_LOAD_BASE"], len(payload))
    assert bytes(loaded) == payload, f"resident payload was not fully loaded: {stdout!r}"
    print("[PASS] test_fixed_lba_loader_harness_loads_sdfs3sys")


def test_rom_boot3_loads_sdfs3sys_and_enables_cmd() -> None:
    profile = "k6802_vdg"
    suffix = "-k6802-vdg-sdfs3-5000"
    extra_args = [
        "SDFS3_LOAD_BASE=0x5000",
        "SDFS3_LOAD_LIMIT=0x7EFF",
        "BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000",
    ]
    _run_make(profile, "bin", extra_args=extra_args)
    _run_make(profile, "sdfs3sys", extra_args=extra_args)
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SDFS3_LOAD_BASE",
    )
    resident_symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS3_LOAD_BASE",
        "SDFS3_END",
    )
    sdfs3sys = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    payload = sdfs3sys[HEADER_SIZE:]
    sd_image = _build_sdfs3sys_fat_sd_image(
        sdfs3sys,
        [
            Fat32File(b"HELLO   S  ", b"S9030000FC\r\n"),
            Fat32File(b"README  TXT", b"HELLO FROM BOOT3\r\n"),
        ],
    )
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            "BOOT3\r"
            "CMD DIR\r"
            "\r"
        ),
        max_cycles=260_000_000,
        sd_image=sd_image,
        dump_range=f"{symbols['SDFS3_LOAD_BASE']:04X}-{symbols['SDFS3_LOAD_BASE'] + 0x3F:04X}",
        timeout=40,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for ROM BOOT3: rc={rc} stderr={stderr!r}"
    )
    assert "OK" in stdout, f"BOOT3 should report OK after loading resident: {stdout!r}"
    banner = "SDFS/68 V3 01.01"
    base_end = (
        f"BASE={symbols['SDFS3_LOAD_BASE']:04X} "
        f"END={resident_symbols['SDFS3_END'] - 1:04X}"
    )
    assert banner in stdout, f"welcome banner missing: {stdout!r}"
    assert base_end in stdout, f"welcome base/end line missing: {stdout!r}"
    banner_index = stdout.index(banner)
    assert banner_index < stdout.index("OK"), f"welcome should print before OK: {stdout!r}"
    assert "HELLO.S A " in stdout, f"CMD DIR did not use resident after BOOT3: {stdout!r}"
    loaded = _dump_range_bytes(stdout, symbols["SDFS3_LOAD_BASE"], 0x40)
    assert bytes(loaded) == payload[:0x40], f"BOOT3 did not load SDFS3SYS header/code: {stdout!r}"
    rom_bin = (PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin").read_bytes()
    assert b"SDFS/68 V3 " not in rom_bin, "welcome string must not leak into ROM binary"
    print("[PASS] test_rom_boot3_loads_sdfs3sys_and_enables_cmd")


def test_sdfs3_mutable_vars_live_outside_image() -> None:
    """#311: 書き換わる変数は窓の resident ワーク(W+$0320)にあり、イメージの外。"""
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs3")
        lst = PROJECT_ROOT / "build" / f"SDFS3{expected['suffix']}.lst"
        names = (
            "SDFS3_WORK_BASE",
            "MIKBUG_VAR_BASE",
            "SDFS3_LAST_ERROR",
            "SDFS3_PARSE_PTR",
            "SDFS3_PARSE_LEN",
            "SDFS3_TOKEN_PTR",
            "SDFS3_TOKEN_LEN",
            "SDFS3_LOAD_BASE",
            "SDFS3_END",
        )
        symbols = _load_symbols(lst, *names)
        work = symbols["SDFS3_WORK_BASE"]
        assert work == symbols["MIKBUG_VAR_BASE"] + 0x20, f"{profile}: WORK_BASE != W+$0320"
        assert symbols["SDFS3_LAST_ERROR"] == work
        assert symbols["SDFS3_PARSE_PTR"] == work + 1
        assert symbols["SDFS3_PARSE_LEN"] == work + 3
        assert symbols["SDFS3_TOKEN_PTR"] == work + 4
        assert symbols["SDFS3_TOKEN_LEN"] == work + 6
        for name in names[2:7]:
            assert not (symbols["SDFS3_LOAD_BASE"] <= symbols[name] < symbols["SDFS3_END"]), (
                f"{profile}: {name} is inside the resident image"
            )
    print("[PASS] test_sdfs3_mutable_vars_live_outside_image")


def test_sdfs3_core_does_not_reference_ccp() -> None:
    """#311: 核の範囲から CCP の範囲への参照が 0 件。わざと足すと検査が失敗する。"""
    import lst_analyze

    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    lst = PROJECT_ROOT / "build" / f"SDFS3{expected['suffix']}.lst"
    bin_path = PROJECT_ROOT / "build" / f"SDFS3{expected['suffix']}.BIN"
    original_source = PROJECT_ROOT / "src" / "sdfs68_v3" / "resident_stub.asm"
    try:
        _run_make(profile, "sdfs3")
        violations, info = lst_analyze.check_core_ccp_refs(lst)
        assert info["core"] < info["ccp"] < info["end"], f"bad boundary order: {info}"
        assert info["scanned"] > 500, f"core range looks empty (vacuous check): {info}"
        assert violations == [], f"core references CCP: {violations}"
        assert info["last_core_insn"].split()[0] in ("rts", "jmp", "bra", "rti"), (
            f"core may fall through into CCP: {info['last_core_insn']!r}"
        )
        # ジャンプテーブルは検査の対象外。今の ROM が slot 1(CMD_DISPATCH)を呼ぶので、
        # CCP を指してよいのは slot 1 と slot 13(INIT)だけ。#313 で解消する。
        symbols = _load_symbols(lst, "SDFS3_LOAD_BASE", "SDFS3_JUMP_TABLE", "SDFS3_CCP_START")
        data = bin_path.read_bytes()
        table = symbols["SDFS3_JUMP_TABLE"] - symbols["SDFS3_LOAD_BASE"]
        ccp_slots = [
            slot
            for slot in range(data[10])
            if _word(data, table + 2 * slot) >= symbols["SDFS3_CCP_START"]
        ]
        assert ccp_slots == [1, 13], f"unexpected jump table slots pointing into CCP: {ccp_slots}"

        # 負の対照: 核の先頭に CCP への参照を 1 行足した複製ソースで検査が失敗する
        mutations = {
            "jmp": "        jmp     SDFS3_CMD_DIR",
            "ldx": "        ldx     #SDFS3_CMD_DIR",
            "fdb": "        fdb     SDFS3_CMD_DIR",
        }
        text = original_source.read_text(encoding="utf-8")
        assert "SDFS3_CORE_START:\n" in text
        with _temporary_directory() as tmp:
            for kind, line in mutations.items():
                mutated = Path(tmp) / f"mutated_{kind}.asm"
                mutated.write_text(
                    text.replace("SDFS3_CORE_START:\n", "SDFS3_CORE_START:\n" + line + "\n", 1),
                    encoding="utf-8",
                )
                _run_make(profile, "sdfs3", extra_args=[f"SDFS3_TOPSRC={mutated}"])
                violations, _ = lst_analyze.check_core_ccp_refs(lst)
                assert [v[3] for v in violations] == ["SDFS3_CMD_DIR"], (
                    f"{kind}: deliberate core->CCP reference was not detected: {violations}"
                )
                rc = lst_analyze.check_core_ccp_main(lst)
                assert rc == 1, f"{kind}: check CLI should fail"
    finally:
        _run_make(profile, "sdfs3")  # 通常ビルドに戻す
    print("[PASS] test_sdfs3_core_does_not_reference_ccp")


def _boot3_resident_config() -> dict:
    profile = "k6802_vdg"
    suffix = "-k6802-vdg-sdfs3-5000"
    extra_args = [
        "SDFS3_LOAD_BASE=0x5000",
        "SDFS3_LOAD_LIMIT=0x7EFF",
        "BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000",
    ]
    _run_make(profile, "bin", extra_args=extra_args)
    _run_make(profile, "sdfs3sys", extra_args=extra_args)
    resident = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS3_LOAD_BASE",
        "SDFS3_END",
        "SDFS3_LAST_ERROR",
        "SDFS3_GET_ERROR",
        "SDFS3_ERR_COM",
    )
    return {
        "suffix": suffix,
        "rom": PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        "sdfs3sys": (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes(),
        "symbols": resident,
    }


def _get_error_harness_input(get_error: int) -> str:
    # jsr GET_ERROR ; staa $0200 ; swi
    code = bytes([0xBD, get_error >> 8, get_error & 0xFF, 0xB7, 0x02, 0x00, 0x3F])
    return f"M0300\r{_hex_bytes(code)}\r.\rG0300\rD0200-0200\r"


def test_sdfs3_resident_image_unchanged_after_commands() -> None:
    """#311: コマンドを実行してもイメージの範囲の RAM が SDFS3SYS のペイロードと一致する。"""
    _run_make("sbcio_4000", "sdfs-tools")
    config = _boot3_resident_config()
    symbols = config["symbols"]
    sdfs3sys = config["sdfs3sys"]
    payload = sdfs3sys[HEADER_SIZE:]
    base = symbols["SDFS3_LOAD_BASE"]
    end = symbols["SDFS3_END"]
    assert len(payload) == end - base
    hello_com = (PROJECT_ROOT / "build" / "HELLO.COM").read_bytes()
    sd_image = _build_sdfs3sys_fat_sd_image(
        sdfs3sys,
        [
            _file("HELLO.S", _srec_file(0x0200, b"S")),
            _file("README.TXT", b"HELLO FROM README\r\n"),
            _file("HELLO.COM", hello_com),
        ],
    )
    last_error = symbols["SDFS3_LAST_ERROR"]
    stdout, stderr, rc = _run_emu(
        rom_path=config["rom"],
        input_text=(
            "BOOT3\r"
            "CMD DIR\r"
            "CMD TYPE README.TXT\r"
            "CMD LOAD HELLO.S\r"
            "CMD HELLO.COM\r"
            "CMD NOFILE.COM\r"
            f"D{last_error:04X}-{last_error:04X}\r"
            + _get_error_harness_input(symbols["SDFS3_GET_ERROR"])
            + "\r"
        ),
        max_cycles=600_000_000,
        sd_image=sd_image,
        dump_range=f"{base:04X}-{end - 1:04X}",
        timeout=120,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "HELLO.S A " in stdout, f"CMD DIR did not run: {stdout!r}"
    assert "HELLO COM" in stdout, f"CMD HELLO.COM did not run: {stdout!r}"
    assert stdout.count("\n?\n") == 1, f"NOFILE.COM should fail exactly once: {stdout!r}"
    image = bytes(_dump_range_bytes(stdout, base, end - base))
    assert image == payload, "resident image in RAM changed after running commands"
    last_failure = symbols["SDFS3_ERR_COM"]
    assert _dump_bytes(stdout, last_error)[0] == last_failure, (
        f"LAST_ERROR should hold the last failure: {stdout!r}"
    )
    assert _dump_bytes(stdout, 0x0200)[0] == last_failure, f"GET_ERROR mismatch: {stdout!r}"
    print("[PASS] test_sdfs3_resident_image_unchanged_after_commands")


def test_sdfs3_init_clears_last_error() -> None:
    """#311: LAST_ERROR はイメージの外にあり初期値を持たないので、INIT(BOOT3 が呼ぶ)で 0 にする。"""
    config = _boot3_resident_config()
    symbols = config["symbols"]
    last_error = symbols["SDFS3_LAST_ERROR"]
    sd_image = _build_sdfs3sys_sd_image(config["sdfs3sys"])
    stdout, stderr, rc = _run_emu(
        rom_path=config["rom"],
        input_text=(
            f"M{last_error:04X}\rFF\r.\r"
            "BOOT3\r"
            + _get_error_harness_input(symbols["SDFS3_GET_ERROR"])
            + "\r"
        ),
        max_cycles=260_000_000,
        sd_image=sd_image,
        timeout=40,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert _dump_bytes(stdout, 0x0200)[0] == 0, f"GET_ERROR after BOOT3 should be 0: {stdout!r}"
    print("[PASS] test_sdfs3_init_clears_last_error")


# ---------------------------------------------------------------------------
# #312: BIOS 入口表・RAM の和・BIOS 区画
# ---------------------------------------------------------------------------

BIOS_PROFILES = {
    "sbcio_vdg": "-sbcio-vdg",
    "k6802_vdg": "-k6802-vdg",
}
BIOS_ENTRY_TARGETS = [
    ("BIOS_WBOOT", 0xE0E6, "BIOS_WBOOT_IMPL"),
    ("BIOS_INFO", 0xE0E9, "BIOS_INFO_IMPL"),
    ("BIOS_GET_API", 0xE0EC, "SDFS3_FIND_API"),
    ("BIOS_EXEC", 0xE0EF, "BIOS_EXEC_IMPL"),
    ("BIOS_READ_LINE", 0xE0F2, "BIOS_READ_LINE_IMPL"),
    ("BIOS_MONITOR", 0xE0F5, "BIOS_MONITOR_IMPL"),
    ("BIOS_SD_INIT", 0xE0F8, "SD_INIT"),
    ("BIOS_SD_READ", 0xE0FB, "SD_READ_SECTOR"),
    ("BIOS_SD_SELECT", 0xE0FE, "SD_SELECT"),
    ("BIOS_SD_DESELECT", 0xE101, "SD_DESELECT"),
    ("BIOS_SD_SEND_CMD", 0xE104, "SD_SEND_CMD"),
    ("BIOS_SD_XFER", 0xE107, "SD_SPI_XFER"),
    ("BIOS_SD_WAIT_R1", 0xE10A, "SD_WAIT_R1"),
    ("BIOS_SD_WRITE", 0xE10D, "BIOS_UNIMPL"),
    ("BIOS_RSV14", 0xE110, "BIOS_UNIMPL"),
    ("BIOS_RSV15", 0xE113, "BIOS_UNIMPL"),
]
BIOS_HARNESS_ADDR = 0x0300
BIOS_HARNESS2_ADDR = 0x0380
BB_SIZE = 0x20
BB_CHECK_OFFSET = 0x13


def _rom_byte_reader(rom: bytes):
    base = 0x10000 - len(rom)

    def read(address: int, length: int = 1) -> bytes:
        return rom[address - base : address - base + length]

    return read


def test_rom_bios_entry_table_layout() -> None:
    target_names = sorted({target for _, _, target in BIOS_ENTRY_TARGETS})
    for profile, suffix in BIOS_PROFILES.items():
        _run_make(profile, "bin")
        lst = PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst"
        rom = (PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin").read_bytes()
        symbols = _load_symbols(
            lst,
            *[name for name, _, _ in BIOS_ENTRY_TARGETS],
            *target_names,
            "BIOS_TABLE_END",
            "BIOS_GAP_END",
            "MIKBUG_INEEE",
            "MONITOR_REENTRY_AT",
            "MAIN_LOOP",
        )
        read = _rom_byte_reader(rom)
        for index, (name, address, target) in enumerate(BIOS_ENTRY_TARGETS):
            assert address == 0xE0E6 + index * 3, f"{name} expected address is not contiguous"
            assert symbols[name] == address, f"{profile}: {name}={symbols[name]:04X}, want {address:04X}"
            code = read(address, 3)
            want = bytes([0x7E, symbols[target] >> 8, symbols[target] & 0xFF])
            assert code == want, f"{profile}: {name} is {code.hex()} want jmp {target} ({want.hex()})"
        assert symbols["BIOS_TABLE_END"] == 0xE116
        assert symbols["BIOS_GAP_END"] <= symbols["MIKBUG_INEEE"] == 0xE1AC, (
            f"{profile}: BIOS code reaches INEEE: {symbols['BIOS_GAP_END']:04X}"
        )
        assert read(symbols["BIOS_UNIMPL"], 2) == b"\x0D\x39", f"{profile}: BIOS_UNIMPL is not sec;rts"
        assert symbols["MONITOR_REENTRY_AT"] == 0xE20D, f"{profile}: MONITOR_REENTRY_AT moved"
        main_loop = symbols["MAIN_LOOP"]
        assert read(0xE20D, 3) == bytes([0x7E, main_loop >> 8, main_loop & 0xFF]), (
            f"{profile}: $E20D is no longer jmp MAIN_LOOP"
        )
    print("[PASS] test_rom_bios_entry_table_layout")


def _assemble_source(tmp: Path, name: str, source: str) -> bytes:
    src = tmp / f"{name}.asm"
    obj = tmp / f"{name}.p"
    bin_path = tmp / f"{name}.bin"
    lst = tmp / f"{name}.lst"
    src.write_text(source, encoding="ascii")
    result = subprocess.run(
        ["asl", "-q", "-L", "-olist", str(lst), "-o", str(obj), str(src)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(f"assemble {name} failed: {result.stdout!r} {result.stderr!r}")
    result = subprocess.run(
        ["p2bin", str(obj), str(bin_path), "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(f"p2bin {name} failed: {result.stdout!r} {result.stderr!r}")
    return bin_path.read_bytes()


def _equ_lines(symbols: dict[str, int]) -> list[str]:
    return [f"{name:<20} equ ${value:04X}" for name, value in symbols.items()]


def _harness_input(harness: bytes, address: int = BIOS_HARNESS_ADDR) -> str:
    return f"M{address:04X}\r{_hex_bytes(harness)}\r.\r"


def _final_dump(stdout: str, start: int) -> str:
    """エミュレータが終了時に出すダンプ(出力の最後)を、開始番地の行から返す。"""
    matches = list(re.finditer(rf"(?m)^(?:\] )?{start:04X} ", stdout))
    assert matches, f"missing final dump at {start:04X}: {stdout[-400:]!r}"
    return stdout[matches[-1].start() :]


def _after(stdout: str, marker: str) -> str:
    assert marker in stdout, f"missing {marker!r} in output: {stdout!r}"
    return stdout[stdout.index(marker) + len(marker) :]


def test_rom_bios_read_line_and_sd_match_internal() -> None:
    profile, suffix = "sbcio_vdg", BIOS_PROFILES["sbcio_vdg"]
    _run_make(profile, "bin")
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BIOS_READ_LINE",
        "BIOS_SD_INIT",
        "BIOS_SD_READ",
        "READ_LINE",
        "SD_INIT",
        "SD_READ_SECTOR",
        "LINE_BUF",
        "LINE_LEN",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
    )
    source = "\n".join(
        [
            "        cpu     6800",
            *_equ_lines(symbols),
            "COPY_DST equ $0080",
            "COPY_SRC equ $0082",
            "COPY_CNT equ $0084",
            f"        org     ${BIOS_HARNESS_ADDR:04X}",
            "START:",
            "        ldx     #$FFFF",
            "        ldab    #$EE",
            "        jsr     BIOS_READ_LINE",
            "        stx     $0200",
            "        stab    $0202",
            "        ldaa    LINE_LEN",
            "        staa    $0203",
            "        ldx     #$0210",
            "        jsr     COPY16",
            "        jsr     READ_LINE",
            "        ldaa    LINE_LEN",
            "        staa    $0204",
            "        ldx     #$0220",
            "        jsr     COPY16",
            "        jsr     BIOS_SD_INIT",
            "        tpa",
            "        staa    $0205",
            "        jsr     SET_LBA",
            "        ldx     #$1000",
            "        jsr     BIOS_SD_READ",
            "        tpa",
            "        staa    $0206",
            "        jsr     SD_INIT",
            "        tpa",
            "        staa    $0207",
            "        jsr     SET_LBA",
            "        ldx     #$1200",
            "        jsr     SD_READ_SECTOR",
            "        tpa",
            "        staa    $0208",
            "        swi",
            "SET_LBA:",
            "        clr     SD_LBA0",
            "        clr     SD_LBA1",
            "        clr     SD_LBA2",
            f"        ldaa    #{SDFS3SYS_FIXED_LBA}",
            "        staa    SD_LBA3",
            "        rts",
            "COPY16:",
            "        stx     COPY_DST",
            "        ldx     #LINE_BUF",
            "        stx     COPY_SRC",
            "        ldaa    #16",
            "        staa    COPY_CNT",
            "COPY16_LOOP:",
            "        ldx     COPY_SRC",
            "        ldaa    0,x",
            "        inx",
            "        stx     COPY_SRC",
            "        ldx     COPY_DST",
            "        staa    0,x",
            "        inx",
            "        stx     COPY_DST",
            "        dec     COPY_CNT",
            "        bne     COPY16_LOOP",
            "        rts",
            "",
        ]
    )
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_read_line_sd", source)
    sector = bytes((i * 7 + 3) & 0xFF for i in range(SECTOR_SIZE))
    line = "HELLX\x08O BIOS 312"
    expected_line = b"HELLO BIOS 312"
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=_harness_input(harness) + f"G{BIOS_HARNESS_ADDR:04X}\r{line}\r{line}\r\r",
        max_cycles=150_000_000,
        dump_range="0200-13FF",
        sd_image=_build_sdfs3sys_sd_image(sector),
        timeout=40,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    dump = _final_dump(stdout, 0x0200)
    status = _dump_range_bytes(dump, 0x0200, 9)
    assert (status[0] << 8 | status[1]) == symbols["LINE_BUF"], f"BIOS_READ_LINE X != LINE_BUF: {status!r}"
    assert status[2] == len(expected_line), f"BIOS_READ_LINE B != length: {status!r}"
    assert status[3] == status[4] == len(expected_line), f"LINE_LEN differs: {status!r}"
    via_bios = bytes(_dump_range_bytes(dump, 0x0210, 16))
    via_rom = bytes(_dump_range_bytes(dump, 0x0220, 16))
    assert via_bios[: len(expected_line)] == expected_line, f"BIOS_READ_LINE buffer: {via_bios!r}"
    assert via_bios == via_rom, f"BIOS_READ_LINE and READ_LINE differ: {via_bios!r} {via_rom!r}"
    assert status[5] & 1 == 0 and status[7] & 1 == 0, f"SD_INIT should succeed: {status!r}"
    assert status[6] & 1 == 0 and status[8] & 1 == 0, f"SD_READ should succeed: {status!r}"
    assert status[5] == status[7] and status[6] == status[8], f"BIOS and ROM flags differ: {status!r}"
    buf_bios = bytes(_dump_range_bytes(dump, 0x1000, SECTOR_SIZE))
    buf_rom = bytes(_dump_range_bytes(dump, 0x1200, SECTOR_SIZE))
    assert buf_bios == sector, "BIOS_SD_READ did not read LBA 64"
    assert buf_rom == buf_bios, "BIOS_SD_READ and SD_READ_SECTOR differ"
    print("[PASS] test_rom_bios_read_line_and_sd_match_internal")


def test_rom_bios_exec_returns_to_wboot() -> None:
    profile, suffix = "sbcio_vdg", BIOS_PROFILES["sbcio_vdg"]
    _run_make(profile, "bin")
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BIOS_EXEC",
        "BIOS_WBOOT",
        "BIOS_PROG_STACK",
    )
    source = "\n".join(
        [
            "        cpu     6800",
            *_equ_lines(symbols),
            f"        org     ${BIOS_HARNESS_ADDR:04X}",
            "START:",
            "        ldaa    #$77",
            "        ldab    #ARGS_END-ARGS",
            "        ldx     #BLOCK",
            "        jmp     BIOS_EXEC",
            "BLOCK:  fdb     ENTRY,ARGS",
            "ENTRY:",
            "        staa    $0200",
            "        stab    $0201",
            "        stx     $0202",
            "        sts     $0204",
            "        tsx",
            "        ldaa    0,x",
            "        staa    $0206",
            "        ldaa    1,x",
            "        staa    $0207",
            "        ldaa    #$5A",
            "        staa    $0208",
            "        rts",
            "        org     $0340",
            'ARGS:   fcc     "ARG 312"',
            "ARGS_END:",
            "",
        ]
    )
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_exec", source)
    args_addr = 0x0340
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=_harness_input(harness) + f"G{BIOS_HARNESS_ADDR:04X}\rD0200-0208\r\r",
        max_cycles=30_000_000,
        dump_range="0200-0208",
        timeout=20,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    after_go = _after(stdout, f"G{BIOS_HARNESS_ADDR:04X}")
    assert "\n?\n" in after_go.replace("\r", ""), f"WBOOT should print '?': {after_go!r}"
    assert "]" in after_go.split("?", 1)[1], f"monitor prompt missing after WBOOT: {after_go!r}"
    regs = _dump_bytes(_final_dump(stdout, 0x0200), 0x0200)
    assert regs[8] == 0x5A, f"program entry did not run: {regs!r}"
    assert regs[0] == 0, f"A should be 0 at entry: {regs!r}"
    assert regs[1] == len("ARG 312"), f"B should keep the argument length: {regs!r}"
    assert (regs[2] << 8 | regs[3]) == args_addr, f"X should be argptr: {regs!r}"
    assert (regs[4] << 8 | regs[5]) == symbols["BIOS_PROG_STACK"] - 2, f"SP at entry: {regs!r}"
    assert (regs[6] << 8 | regs[7]) == symbols["BIOS_WBOOT"], f"return address should be WBOOT: {regs!r}"
    print("[PASS] test_rom_bios_exec_returns_to_wboot")


def test_rom_bios_info_and_reserved() -> None:
    profile, suffix = "sbcio_vdg", BIOS_PROFILES["sbcio_vdg"]
    _run_make(profile, "bin")
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BIOS_INFO",
        "BIOS_GET_API",
        "BIOS_SD_WRITE",
        "BIOS_RSV14",
        "BIOS_RSV15",
        "BIOS_VERSION",
    )
    lines = [
        "        cpu     6800",
        *_equ_lines(symbols),
        f"        org     ${BIOS_HARNESS_ADDR:04X}",
        "        clra",
        "        clrb",
        "        jsr     BIOS_INFO",
        "        staa    $0200",
        "        stab    $0201",
    ]
    for index, name in enumerate(("BIOS_SD_WRITE", "BIOS_RSV14", "BIOS_RSV15", "BIOS_GET_API")):
        lines += ["        clc", f"        jsr     {name}", "        tpa", f"        staa    ${0x0202 + index:04X}"]
    lines += ["        swi", ""]
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_info", "\n".join(lines))
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=_harness_input(harness) + f"G{BIOS_HARNESS_ADDR:04X}\r\r",
        max_cycles=30_000_000,
        dump_range="0200-0205",
        timeout=20,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    values = _dump_bytes(_final_dump(stdout, 0x0200), 0x0200)
    assert values[0] == symbols["BIOS_VERSION"] == 1, f"BIOS_INFO A: {values!r}"
    assert values[1] == 16, f"BIOS_INFO B: {values!r}"
    assert all(flag & 1 for flag in values[2:5]), f"reserved entries should return C=1: {values!r}"
    assert values[5] & 1, f"BIOS_GET_API before BOOT3 should return C=1: {values!r}"
    print("[PASS] test_rom_bios_info_and_reserved")


def _bb_block(
    *,
    img_base: int = 0x5000,
    core_base: int = 0x5800,
    img_last: int = 0x5FFF,
    ccp_vec: int = 0x5400,
    magic: tuple[int, int] = (0xB3, 0x4C),
    fix_check: bool = True,
) -> bytearray:
    block = bytearray(BB_SIZE)
    block[0:2] = bytes(magic)
    for offset, value in (
        (0x02, img_base),
        (0x04, core_base),
        (0x06, img_last),
        (0x08, 0x1234),
        (0x0A, 0xBEEF),
        (0x0C, ccp_vec),
        (0x0E, SDFS3SYS_FIXED_LBA),
        (0x10, 0x5A5A),
    ):
        block[offset] = value >> 8
        block[offset + 1] = value & 0xFF
    block[0x12] = 0
    block[0x14:0x20] = bytes(range(0x60, 0x6C))
    if fix_check:
        block[BB_CHECK_OFFSET] = (-sum(block[:BB_CHECK_OFFSET])) & 0xFF
    return block


def test_rom_bios_block_rejects_garbage() -> None:
    profile, suffix = "sbcio_vdg", BIOS_PROFILES["sbcio_vdg"]
    _run_make(profile, "bin")
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BB_CHECK_VALID",
        "BIOS_BLOCK",
        "SDFS3_WORK_BASE",
        "USER_RAM_END",
        "SDFS3_RAM_FLOOR",
    )
    assert symbols["USER_RAM_END"] == 0x7FFF and symbols["SDFS3_RAM_FLOOR"] == 0x4000
    cases: list[tuple[str, bytes, int]] = []
    seed = 0x312
    for index in range(8):
        data = bytearray()
        for _ in range(BB_SIZE):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            data.append((seed >> 16) & 0xFF)
        assert data[0:2] != b"\xB3\x4C"
        cases.append((f"random{index}", bytes(data), 1))
    cases += [
        ("valid", bytes(_bb_block()), 0),
        ("valid_bounds", bytes(_bb_block(img_base=0x4000, core_base=0x4000, img_last=0x7FFF, ccp_vec=0x4000)), 0),
        ("valid_plan_b", bytes(_bb_block(img_base=0x6C00, core_base=0x7000, img_last=0x7FFF, ccp_vec=0x6C00)), 0),
        ("valid_312_layout", bytes(_bb_block(core_base=0x5000, ccp_vec=0x5000)), 0),
        ("img_below_floor", bytes(_bb_block(img_base=0x3FFF, ccp_vec=0x5000)), 1),
        ("img_above_core", bytes(_bb_block(img_base=0x5801)), 1),
        ("core_below_img", bytes(_bb_block(core_base=0x4FFF)), 1),
        ("core_above_last", bytes(_bb_block(core_base=0x6000)), 1),
        ("last_above_user_ram", bytes(_bb_block(img_last=0x8000)), 1),
        ("last_below_core", bytes(_bb_block(img_last=0x57FF)), 1),
        ("ccp_below_img", bytes(_bb_block(ccp_vec=0x4FFF)), 1),
        ("ccp_above_core", bytes(_bb_block(ccp_vec=0x5801)), 1),
        ("magic_hi", bytes(_bb_block(magic=(0xB2, 0x4C))), 1),
        ("magic_lo", bytes(_bb_block(magic=(0xB3, 0x4D))), 1),
    ]
    broken = _bb_block()
    broken[0x12] ^= 0x01
    cases.append(("one_byte_changed", bytes(broken), 1))
    marker_addr = symbols["SDFS3_WORK_BASE"]
    lines = [
        "        cpu     6800",
        *_equ_lines(symbols),
        "SRC     equ $0080",
        "DST     equ $0082",
        "CNT     equ $0084",
        "RES     equ $0086",
        f"        org     ${BIOS_HARNESS_ADDR:04X}",
        "        ldx     #CASES",
        "        stx     SRC",
        "        ldx     #$0200",
        "        stx     RES",
        "        ldx     #MARKER",
        "        ldaa    #$A5",
        "        staa    0,x",
        "        staa    7,x",
        "NEXT:",
        "        ldx     SRC",
        "        cpx     #CASES_END",
        "        beq     DONE",
        "        ldx     #BIOS_BLOCK",
        "        stx     DST",
        f"        ldaa    #{BB_SIZE}",
        "        staa    CNT",
        "COPY:",
        "        ldx     SRC",
        "        ldaa    0,x",
        "        inx",
        "        stx     SRC",
        "        ldx     DST",
        "        staa    0,x",
        "        inx",
        "        stx     DST",
        "        dec     CNT",
        "        bne     COPY",
        "        clc",
        "        jsr     BB_CHECK_VALID",
        "        tpa",
        "        anda    #1",
        "        ldx     RES",
        "        staa    0,x",
        "        inx",
        "        stx     RES",
        "        bra     NEXT",
        "DONE:",
        "        swi",
        f"MARKER  equ ${marker_addr:04X}",
        "CASES:",
    ]
    for name, data, _ in cases:
        lines.append(f"        fcb     {','.join(f'${b:02X}' for b in data)} ; {name}")
    lines += ["CASES_END:", ""]
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_block_check", "\n".join(lines))
    block = symbols["BIOS_BLOCK"]
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            _harness_input(harness)
            + f"G{BIOS_HARNESS_ADDR:04X}\r"
            + f"D0200-{0x0200 + len(cases) - 1:04X}\r\r"
        ),
        max_cycles=200_000_000,
        dump_range=f"{block:04X}-{marker_addr + 7:04X}",
        timeout=60,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    after_go = _after(stdout, f"G{BIOS_HARNESS_ADDR:04X}")
    assert "BRK" in after_go, f"harness did not reach SWI: {after_go[:400]!r}"
    results = _dump_range_bytes(after_go, 0x0200, len(cases))
    for (name, _, want), got in zip(cases, results):
        assert got == want, f"BB_CHECK_VALID {name}: C={got}, want {want}"
    after = _final_dump(stdout, block)
    final_block = bytes(_dump_range_bytes(after, block, BB_SIZE))
    assert final_block == cases[-1][1], "BB_CHECK_VALID must not write the block"
    markers = _dump_range_bytes(after, marker_addr, 8)
    assert markers[0] == 0xA5 and markers[7] == 0xA5, f"RAM outside the block changed: {markers!r}"
    print("[PASS] test_rom_bios_block_rejects_garbage")


def test_rom_boot3_writes_bios_block() -> None:
    profile = "k6802_vdg"
    suffix = "-k6802-vdg-sdfs3-5000"
    extra_args = [
        "SDFS3_LOAD_BASE=0x5000",
        "SDFS3_LOAD_LIMIT=0x7EFF",
        "BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000",
    ]
    _run_make(profile, "bin", extra_args=extra_args)
    _run_make(profile, "sdfs3sys", extra_args=extra_args)
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BB_CHECK_VALID",
        "BIOS_RAM_SUM",
        "BIOS_GET_API",
        "BIOS_BLOCK",
        "BB_IMG_BASE",
        "BB_IMG_LAST",
        "BB_STATE",
        "BB_WORK",
        "SDFS3_LOAD_BASE",
    )
    resident = _load_symbols(PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst", "SDFS3_END")
    sdfs3sys = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    header = parse_sdfs3sys_header(sdfs3sys)
    payload = sdfs3sys[HEADER_SIZE:]
    payload_sum = sum(payload) & 0xFFFF
    load = symbols["SDFS3_LOAD_BASE"]
    assert load == 0x5000
    source = "\n".join(
        [
            "        cpu     6800",
            *_equ_lines({k: v for k, v in symbols.items() if k != "SDFS3_LOAD_BASE"}),
            f"        org     ${BIOS_HARNESS_ADDR:04X}",
            "        clc",
            "        jsr     BB_CHECK_VALID",
            "        tpa",
            "        anda    #1",
            "        staa    $0200",
            "        ldx     BB_IMG_LAST",
            "        inx",
            "        stx     BB_WORK",
            "        ldx     BB_IMG_BASE",
            "        jsr     BIOS_RAM_SUM",
            "        staa    $0201",
            "        stab    $0202",
            "        jsr     BIOS_GET_API",
            "        stx     $0203",
            "        tpa",
            "        anda    #1",
            "        staa    $0205",
            "        swi",
            f"        org     ${BIOS_HARNESS2_ADDR:04X}",
            "        clc",
            "        jsr     BB_CHECK_VALID",
            "        tpa",
            "        anda    #1",
            "        staa    $0210",
            "        swi",
            "",
        ]
    )
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_boot3_block", source)
    sd_image = _build_sdfs3sys_fat_sd_image(
        sdfs3sys,
        [
            Fat32File(b"HELLO   S  ", b"S9030000FC\r\n"),
            Fat32File(b"README  TXT", b"HELLO FROM BOOT3\r\n"),
        ],
    )
    block = symbols["BIOS_BLOCK"]
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            "BOOT3\r"
            "CMD DIR\r"
            + _harness_input(harness)
            + f"G{BIOS_HARNESS_ADDR:04X}\r"
            + f"D{block:04X}-{block + BB_SIZE - 1:04X}\r"
            + f"M{symbols['BB_STATE']:04X}\r01\r.\r"
            + f"G{BIOS_HARNESS2_ADDR:04X}\r"
            + "\r"
        ),
        max_cycles=300_000_000,
        sd_image=sd_image,
        dump_range="0200-0210",
        timeout=60,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed for BOOT3: rc={rc} stderr={stderr!r}"
    assert "OK" in stdout and "SDFS/68 V3 01.01" in stdout, f"BOOT3 should still succeed: {stdout!r}"
    assert "HELLO.S A " in stdout, f"CMD DIR should still list files: {stdout!r}"
    after_go = _after(stdout, f"G{BIOS_HARNESS_ADDR:04X}")
    bb = bytes(_dump_range_bytes(after_go, block, BB_SIZE))

    def word(offset: int) -> int:
        return bb[offset] << 8 | bb[offset + 1]

    assert bb[0:2] == b"\xB3\x4C", f"BB_MAGIC: {bb.hex()}"
    assert word(0x02) == load, f"BB_IMG_BASE: {bb.hex()}"
    assert word(0x04) == load, f"BB_CORE_BASE should be the SDFS3API header: {bb.hex()}"
    assert word(0x06) == resident["SDFS3_END"] - 1 == load + len(payload) - 1, f"BB_IMG_LAST: {bb.hex()}"
    assert word(0x08) == 0, f"BB_SUM_CCP: {bb.hex()}"
    assert word(0x0A) == payload_sum, f"BB_SUM_CORE {word(0x0A):04X} != payload sum {payload_sum:04X}"
    assert word(0x0C) == load, f"BB_CCP_VEC: {bb.hex()}"
    assert word(0x0E) == SDFS3SYS_FIXED_LBA, f"BB_SLOT_LBA: {bb.hex()}"
    assert word(0x10) == header.checksum, f"BB_IMG_SUM should copy header +$18: {bb.hex()}"
    assert bb[0x12] == 0, f"BB_STATE: {bb.hex()}"
    assert sum(bb[: BB_CHECK_OFFSET + 1]) & 0xFF == 0, f"BB_CHECK: {bb.hex()}"
    final = _final_dump(stdout, 0x0200)
    results = _dump_bytes(final, 0x0200)
    assert results[0] == 0, f"self-check should pass after BOOT3: {results!r}"
    assert (results[1] << 8 | results[2]) == payload_sum, f"RAM sum differs from saved sum: {results!r}"
    assert (results[3] << 8 | results[4]) == load and results[5] == 0, f"BIOS_GET_API: {results!r}"
    second = _dump_bytes(final, 0x0210)
    assert second[0] == 1, f"self-check should fail after changing one byte with M: {second!r}"
    print("[PASS] test_rom_boot3_writes_bios_block")


def test_rom_boot3_rejects_bad_sdfs3sys() -> None:
    profile = "k6802_vdg"
    suffix = "-k6802-vdg-sdfs3-5000"
    extra_args = [
        "SDFS3_LOAD_BASE=0x5000",
        "SDFS3_LOAD_LIMIT=0x7EFF",
        "BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000",
    ]
    _run_make(profile, "bin", extra_args=extra_args)
    _run_make(profile, "sdfs3sys", extra_args=extra_args)
    sdfs3sys = bytearray((PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes())
    sdfs3sys[0] = ord("X")
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text="BOOT3\rCMD DIR\r\r",
        max_cycles=160_000_000,
        sd_image=_build_sdfs3sys_sd_image(bytes(sdfs3sys)),
        timeout=30,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for bad ROM BOOT3 image: rc={rc} stderr={stderr!r}"
    )
    assert stdout.count("\n?\n") >= 2, f"BOOT3 and unloaded CMD should both fail: {stdout!r}"
    print("[PASS] test_rom_boot3_rejects_bad_sdfs3sys")


def test_sdfs3_cmd_dir_and_type_read_fat_files() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3sys")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SD_INIT",
        "SD_READ_SECTOR",
        "SDFS3_FIND_API",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
        "SDFS3_LOAD_BASE",
    )
    sdfs3sys = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)
    sd_image = _build_sdfs3sys_fat_sd_image(
        sdfs3sys,
        [
            Fat32File(b"HELLO   S  ", b"S9030000FC\r\n"),
            Fat32File(b"README  TXT", b"HELLO FROM README\r\n"),
            Fat32File(b"NOTE    TXT", b"HELLO FROM DOCS\r\n", path=(b"DOCS       ",)),
        ],
    )
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r"
            "CMD DIR\r"
            "CMD DIR DOCS\r"
            "CMD DIR MISSING\r"
            "CMD TYPE README.TXT\r"
            "CMD TYPE DOCS/NOTE.TXT\r"
            "CMD TYPE MISSING.TXT\r"
            "\r"
        ),
        max_cycles=220_000_000,
        sd_image=sd_image,
        timeout=30,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for SDFS3 DIR/TYPE: rc={rc} stderr={stderr!r}"
    )
    assert "HELLO.S A " in stdout, f"CMD DIR did not list HELLO.S: {stdout!r}"
    assert "README.TXT A 00000013" in stdout, f"CMD DIR did not list README.TXT: {stdout!r}"
    assert "DOCS D 00000000" in stdout, f"CMD DIR did not list DOCS directory: {stdout!r}"
    assert "NOTE.TXT A 00000011" in stdout, f"CMD DIR DOCS did not list NOTE.TXT: {stdout!r}"
    assert "HELLO FROM README" in stdout, f"CMD TYPE README.TXT did not print file: {stdout!r}"
    assert "HELLO FROM DOCS" in stdout, f"CMD TYPE DOCS/NOTE.TXT did not print file: {stdout!r}"
    assert stdout.count("\n?\n") == 2, (
        f"missing DIR/TYPE did not return exactly two monitor errors: {stdout!r}"
    )
    print("[PASS] test_sdfs3_cmd_dir_and_type_read_fat_files")


def test_sdfs3_cmd_load_run_and_com_read_fat_files() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3sys")
    _run_make(profile, "sdfs-tools")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SD_INIT",
        "SD_READ_SECTOR",
        "SDFS3_FIND_API",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
        "SDFS3_LOAD_BASE",
    )
    sdfs3sys = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    hello_com = (PROJECT_ROOT / "build" / "HELLO.COM").read_bytes()
    args_com = (PROJECT_ROOT / "build" / "ARGS.COM").read_bytes()
    run_program = bytes(
        [
            0xCE,
            0x01,
            0x07,
            0xBD,
            0xE0,
            0x7E,
            0x3F,
            0x0D,
            0x0A,
            *b"HELLO, WORLD",
            0x0D,
            0x0A,
            0x04,
        ]
    )
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)
    sd_image = _build_sdfs3sys_fat_sd_image(
        sdfs3sys,
        [
            _file("HELLO.S", _srec_file(0x0200, b"S")),
            _file("HELLO.HEX", _ihex_file(0x0201, b"I")),
            _file("RUN.S", _srec_file(0x0100, run_program, entry_address=0x0100)),
            _file("HELLO.COM", hello_com),
            _file("ARGS.COM", args_com),
            _file("EMPTY.COM", b""),
            _file("BIG.COM", b"\x39" * 0x3F01),
        ],
    )
    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            "M0110\r3F\r.\r"
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r"
            "CMD LOAD HELLO.S\r"
            "D0200-0200\r"
            "CMD LOAD HELLO.HEX\r"
            "D0201-0201\r"
            "CMD RUN 0110\r"
            "CMD HELLO.COM\r"
            "CMD ARGS.COM AAA BBB\r"
            "CMD NOFILE.COM\r"
            "CMD EMPTY.COM\r"
            "CMD BIG.COM\r"
            "CMD RUN HELLO.HEX\r"
            "CMD RUN RUN.S\r"
            "\r"
        ),
        max_cycles=360_000_000,
        sd_image=sd_image,
        timeout=40,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for SDFS3 LOAD/RUN/.COM: rc={rc} stderr={stderr!r}"
    )
    assert stdout.count("OK") >= 2, f"CMD LOAD did not report success: {stdout!r}"
    assert "0200 53" in stdout, f"CMD LOAD HELLO.S did not write S-record data: {stdout!r}"
    assert "0201 49" in stdout, f"CMD LOAD HELLO.HEX did not write HEX data: {stdout!r}"
    assert "BRK 0110" in stdout, f"CMD RUN addr did not jump to the requested address: {stdout!r}"
    assert "HELLO COM" in stdout, f"CMD HELLO.COM did not execute: {stdout!r}"
    assert "ARGS AAA BBB" in stdout, f"CMD ARGS.COM did not pass arguments: {stdout!r}"
    assert stdout.count("\n?\n") == 4, f"bad .COM/RUN inputs were not rejected exactly once: {stdout!r}"
    assert "HELLO, WORLD" in stdout, f"CMD RUN RUN.S did not execute S-record entry: {stdout!r}"
    assert "BRK 0106" in stdout, f"RUN.S did not reach SWI through entry address: {stdout!r}"
    print("[PASS] test_sdfs3_cmd_load_run_and_com_read_fat_files")


def test_fixed_lba_loader_harness_rejects_bad_sdfs3sys() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3sys")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "SD_INIT",
        "SD_READ_SECTOR",
        "SDFS3_FIND_API",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
        "SDFS3_LOAD_BASE",
    )
    image = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
    assert len(image) <= 16 * 1024, "SDFS3SYS harness keeps the phase 1 image under 16KB"
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)

    cases = [
        ("bad magic", lambda data: data.__setitem__(0, ord("X")), 0xE1),
        ("bad version", lambda data: data.__setitem__(0x08, 0x02), 0xE2),
        ("bad load address", lambda data: data.__setitem__(0x0C, 0x40), 0xE3),
        ("bad small size", lambda data: data.__setitem__(slice(0x0E, 0x10), b"\x00\x20"), 0xE4),
        ("bad oversize", lambda data: data.__setitem__(slice(0x0E, 0x10), b"\x40\x01"), 0xE4),
        ("bad checksum", lambda data: data.__setitem__(-1, data[-1] ^ 0x01), 0xE5),
        ("bad resident api", _break_resident_api_and_refresh_checksum, 0xE7),
    ]
    for label, mutate, expected_status in cases:
        bad_image = bytearray(image)
        mutate(bad_image)
        stdout, stderr, rc = _run_emu(
            rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
            input_text=(
                f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
                f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\rD0200-0200\r\r"
            ),
            max_cycles=120_000_000,
            dump_range="0200-0200",
            sd_image=_build_sdfs3sys_sd_image(bytes(bad_image)),
            timeout=20,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {label}: rc={rc} stderr={stderr!r}"
        )
        status = _dump_bytes(stdout, 0x0200)
        assert status[0] == expected_status, (
            f"{label} status mismatch: {status!r}\nstdout={stdout!r}"
        )

    stdout, stderr, rc = _run_emu(
        rom_path=PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin",
        input_text=(
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\rD0200-0200\r\r"
        ),
        max_cycles=120_000_000,
        dump_range="0200-0200",
        sd_image=bytes(SECTOR_SIZE * SDFS3SYS_FIXED_LBA),
        timeout=20,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for read failure: rc={rc} stderr={stderr!r}"
    )
    status = _dump_bytes(stdout, 0x0200)
    assert status[0] == 0xE6, f"SD read failure should be reported: {status!r}\nstdout={stdout!r}"
    print("[PASS] test_fixed_lba_loader_harness_rejects_bad_sdfs3sys")


def _word(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _sdfs3_header(
    load_base: int,
    *,
    jump_table: int | None = None,
    work_end: int | None = None,
) -> bytes:
    jump_table = jump_table if jump_table is not None else load_base
    work_end = work_end if work_end is not None else load_base
    return bytes(
        [
            *b"SDFS3API",
            0x01,
            0x01,
            0x0E,
            0x00,
            (jump_table >> 8) & 0xFF,
            jump_table & 0xFF,
            (load_base >> 8) & 0xFF,
            load_base & 0xFF,
            (work_end >> 8) & 0xFF,
            work_end & 0xFF,
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


def _build_sdfs3sys_sd_image(image: bytes) -> bytes:
    image_sectors = (len(image) + SECTOR_SIZE - 1) // SECTOR_SIZE
    sectors = bytearray(SECTOR_SIZE * (SDFS3SYS_FIXED_LBA + image_sectors))
    start = SECTOR_SIZE * SDFS3SYS_FIXED_LBA
    sectors[start : start + len(image)] = image
    return bytes(sectors)


def _build_sdfs3sys_fat_sd_image(system_image: bytes, files: list[Fat32File]) -> bytes:
    fat_image, _layout = build_fat32_image_from_files(
        files,
        with_mbr=True,
        partition_start_lba=SDFS3SYS_FAT_PARTITION_LBA,
        total_volume_sectors=256,
    )
    system_end = (SDFS3SYS_FIXED_LBA * SECTOR_SIZE) + len(system_image)
    mutable = bytearray(max(len(fat_image), system_end))
    mutable[: len(fat_image)] = fat_image
    start = SDFS3SYS_FIXED_LBA * SECTOR_SIZE
    mutable[start : start + len(system_image)] = system_image
    return bytes(mutable)


def _file(name: str, data: bytes, path: tuple[str, ...] = ()) -> Fat32File:
    stem, _dot, ext = name.partition(".")
    name83 = stem.upper().encode("ascii").ljust(8, b" ")
    name83 += ext.upper().encode("ascii").ljust(3, b" ")
    path83 = tuple(part.upper().encode("ascii").ljust(8, b" ") + b"   " for part in path)
    return Fat32File(name83, data, path=path83)


def _srec_file(
    address: int,
    data: bytes,
    trailing_newline: bool = True,
    entry_address: int = 0,
) -> bytes:
    count = len(data) + 3
    values = [count, (address >> 8) & 0xFF, address & 0xFF, *data]
    checksum = (~sum(values)) & 0xFF
    record = "S1" + "".join(f"{value:02X}" for value in [*values, checksum])
    entry_values = [3, (entry_address >> 8) & 0xFF, entry_address & 0xFF]
    entry_checksum = (~sum(entry_values)) & 0xFF
    entry_record = "S9" + "".join(f"{value:02X}" for value in [*entry_values, entry_checksum])
    text = record + "\r\n" + entry_record
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


def _break_resident_api_and_refresh_checksum(data: bytearray) -> None:
    data[HEADER_SIZE] = ord("X")
    data[CHECKSUM_OFFSET] = 0
    data[CHECKSUM_OFFSET + 1] = 0
    checksum = checksum16(bytes(data))
    data[CHECKSUM_OFFSET] = (checksum >> 8) & 0xFF
    data[CHECKSUM_OFFSET + 1] = checksum & 0xFF


def _assemble_fixed_lba_loader_harness(tmp: Path, symbols: dict[str, int]) -> bytes:
    source = tmp / "sdfs3sys_loader_harness.asm"
    obj = tmp / "sdfs3sys_loader_harness.p"
    bin_path = tmp / "sdfs3sys_loader_harness.bin"
    lst = tmp / "sdfs3sys_loader_harness.lst"
    source.write_text(_fixed_lba_loader_harness_source(symbols), encoding="ascii")
    result = subprocess.run(
        ["asl", "-q", "-L", "-olist", str(lst), "-o", str(obj), str(source)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(f"assemble loader harness failed: {result.stdout!r} {result.stderr!r}")
    result = subprocess.run(
        ["p2bin", str(obj), str(bin_path), "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(f"p2bin loader harness failed: {result.stdout!r} {result.stderr!r}")
    return bin_path.read_bytes()


def _assemble_cmd_dispatch_harness(
    tmp: Path,
    symbols: dict[str, int],
    cases: list[tuple[str, int]],
) -> bytes:
    source = tmp / "sdfs3_cmd_dispatch_harness.asm"
    obj = tmp / "sdfs3_cmd_dispatch_harness.p"
    bin_path = tmp / "sdfs3_cmd_dispatch_harness.bin"
    lst = tmp / "sdfs3_cmd_dispatch_harness.lst"
    source.write_text(_cmd_dispatch_harness_source(symbols, cases), encoding="ascii")
    result = subprocess.run(
        ["asl", "-q", "-L", "-olist", str(lst), "-o", str(obj), str(source)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"assemble CMD_DISPATCH harness failed: {result.stdout!r} {result.stderr!r}"
        )
    result = subprocess.run(
        ["p2bin", str(obj), str(bin_path), "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"p2bin CMD_DISPATCH harness failed: {result.stdout!r} {result.stderr!r}"
        )
    return bin_path.read_bytes()


def _cmd_dispatch_harness_source(
    symbols: dict[str, int],
    cases: list[tuple[str, int]],
) -> str:
    lines = [
        "        cpu     6800",
        "        org     $0300",
        "",
        "RESULTS         equ $0200",
        f"SDFS3_CMD_DISPATCH equ ${symbols['SDFS3_CMD_DISPATCH']:04X}",
        f"SDFS3_GET_ERROR equ ${symbols['SDFS3_GET_ERROR']:04X}",
        "",
        "START:",
    ]
    for index, (tail, _) in enumerate(cases):
        lines.extend(
            [
                f"        ldx     #TAIL{index}",
                f"        ldab    #{len(tail)}",
                "        clra",
                "        jsr     SDFS3_CMD_DISPATCH",
                f"        bcs     CASE{index}_CARRY",
                "        clra",
                f"        bra     CASE{index}_STORE_STATUS",
                f"CASE{index}_CARRY:",
                "        ldaa    #1",
                f"CASE{index}_STORE_STATUS:",
                f"        staa    RESULTS+{index * 2}",
                "        jsr     SDFS3_GET_ERROR",
                f"        staa    RESULTS+{index * 2 + 1}",
            ]
        )
    lines.extend(["        swi", ""])
    for index, (tail, _) in enumerate(cases):
        if tail:
            escaped = tail.replace('"', '""')
            lines.append(f'TAIL{index}:        fcc     "{escaped}"')
        else:
            lines.append(f"TAIL{index}:        fcb     0")
    return "\n".join(lines) + "\n"


def _fixed_lba_loader_harness_source(symbols: dict[str, int]) -> str:
    def equ(name: str) -> str:
        return f"${symbols[name]:04X}"

    load_base_hi = (symbols["SDFS3_LOAD_BASE"] >> 8) & 0xFF
    load_base_lo = symbols["SDFS3_LOAD_BASE"] & 0xFF
    return f"""        cpu     6800
        org     ${SDFS3SYS_LOADER_HARNESS_ADDR:04X}

STATUS          equ $0200
RESULT_X        equ $0201
EXPECTED_SUM    equ $0203
COMPUTED_SUM    equ $0205
REMAIN          equ $0207
SRC_PTR         equ $0209
DST_PTR         equ $020B
PAYLOAD_REMAIN equ $020D
COUNT           equ $020F

SD_INIT         equ {equ("SD_INIT")}
SD_READ_SECTOR  equ {equ("SD_READ_SECTOR")}
SDFS3_FIND_API  equ {equ("SDFS3_FIND_API")}
SD_LBA0         equ {equ("SD_LBA0")}
SD_LBA1         equ {equ("SD_LBA1")}
SD_LBA2         equ {equ("SD_LBA2")}
SD_LBA3         equ {equ("SD_LBA3")}
SD_SECTOR_BUF   equ {equ("SD_SECTOR_BUF")}
SDFS3_LOAD_BASE  equ {equ("SDFS3_LOAD_BASE")}

START:
        jsr     SD_INIT
        bcs     FAIL_SD
        jsr     SET_FIXED_LBA
        jsr     READ_CURRENT_SECTOR
        bcs     FAIL_SD
        jsr     CHECK_HEADER
        bcs     FAIL
        jsr     COPY_PAYLOAD
        jsr     SDFS3_FIND_API
        bcs     FAIL_API
        stx     RESULT_X
        ldaa    #$42
        staa    STATUS
        swi

FAIL_API:
        ldaa    #$E7
        bra     FAIL
FAIL_SD:
        ldaa    #$E6
FAIL:
        staa    STATUS
        swi

CHECK_HEADER:
        ldx     #SD_SECTOR_BUF
        ldaa    0,x
        cmpa    #'S'
        beq     MAGIC0_OK
        jmp     FAIL_MAGIC
MAGIC0_OK:
        ldaa    1,x
        cmpa    #'D'
        beq     MAGIC1_OK
        jmp     FAIL_MAGIC
MAGIC1_OK:
        ldaa    2,x
        cmpa    #'F'
        beq     MAGIC2_OK
        jmp     FAIL_MAGIC
MAGIC2_OK:
        ldaa    3,x
        cmpa    #'S'
        beq     MAGIC3_OK
        jmp     FAIL_MAGIC
MAGIC3_OK:
        ldaa    4,x
        cmpa    #'3'
        beq     MAGIC4_OK
        jmp     FAIL_MAGIC
MAGIC4_OK:
        ldaa    5,x
        cmpa    #'S'
        beq     MAGIC5_OK
        jmp     FAIL_MAGIC
MAGIC5_OK:
        ldaa    6,x
        cmpa    #'Y'
        beq     MAGIC6_OK
        jmp     FAIL_MAGIC
MAGIC6_OK:
        ldaa    7,x
        cmpa    #'S'
        beq     MAGIC7_OK
        jmp     FAIL_MAGIC
MAGIC7_OK:
        ldaa    8,x
        cmpa    #1
        beq     VERSION_OK
        jmp     FAIL_VERSION
VERSION_OK:
        ldaa    9,x
        cmpa    #1
        beq     ABI_MAJOR_OK
        jmp     FAIL_VERSION
ABI_MAJOR_OK:
        ldaa    11,x
        cmpa    #1
        beq     FLAGS_OK
        jmp     FAIL_VERSION
FLAGS_OK:
        ldaa    12,x
        cmpa    #${load_base_hi:02X}
        beq     LOAD_HI_OK
        jmp     FAIL_LOAD
LOAD_HI_OK:
        ldaa    13,x
        cmpa    #${load_base_lo:02X}
        beq     LOAD_LO_OK
        jmp     FAIL_LOAD
LOAD_LO_OK:
        ldaa    26,x
        beq     HEADER_SIZE_HI_OK
        jmp     FAIL_SIZE
HEADER_SIZE_HI_OK:
        ldaa    27,x
        cmpa    #$20
        beq     HEADER_SIZE_LO_OK
        jmp     FAIL_SIZE
HEADER_SIZE_LO_OK:
        ldaa    14,x
        cmpa    #$40
        blo     SIZE_UNDER_MAX
        bne     FAIL_SIZE_JMP
        ldaa    15,x
        beq     SIZE_UNDER_MAX
FAIL_SIZE_JMP:
        jmp     FAIL_SIZE
SIZE_UNDER_MAX:
        ldaa    14,x
        bne     SIZE_OK
        ldaa    15,x
        cmpa    #$21
        bhs     SIZE_OK
        jmp     FAIL_SIZE
SIZE_OK:
        ldaa    24,x
        staa    EXPECTED_SUM
        ldaa    25,x
        staa    EXPECTED_SUM+1
        clr     24,x
        clr     25,x
        clr     COMPUTED_SUM
        clr     COMPUTED_SUM+1
        ldaa    14,x
        staa    REMAIN
        ldaa    15,x
        staa    REMAIN+1
        jsr     SUM_CURRENT_BUFFER
SUM_SECTOR_LOOP:
        ldaa    REMAIN
        oraa    REMAIN+1
        beq     SUM_DONE
        jsr     INC_LBA
        jsr     READ_CURRENT_SECTOR
        bcs     SUM_READ_FAIL
        jsr     SUM_CURRENT_BUFFER
        bra     SUM_SECTOR_LOOP
SUM_READ_FAIL:
        jmp     FAIL_SD
SUM_DONE:
        ldaa    COMPUTED_SUM
        cmpa    EXPECTED_SUM
        beq     SUM_HI_OK
        jmp     FAIL_CHECKSUM
SUM_HI_OK:
        ldaa    COMPUTED_SUM+1
        cmpa    EXPECTED_SUM+1
        beq     SUM_LO_OK
        jmp     FAIL_CHECKSUM
SUM_LO_OK:
        clc
        rts

SUM_CURRENT_BUFFER:
        jsr     SET_COUNT_MIN_512
        ldx     #SD_SECTOR_BUF
SUM_LOOP:
        ldaa    COUNT
        oraa    COUNT+1
        beq     SUM_CURRENT_DONE
        ldaa    0,x
        jsr     ADD_SUM
        inx
        jsr     DEC_COUNT_AND_REMAIN
        bra     SUM_LOOP
SUM_CURRENT_DONE:
        rts

COPY_PAYLOAD:
        jsr     SET_FIXED_LBA
        jsr     READ_CURRENT_SECTOR
        bcs     COPY_FAIL_SD
        ldx     #SD_SECTOR_BUF
        ldaa    14,x
        staa    PAYLOAD_REMAIN
        ldaa    15,x
        suba    #$20
        staa    PAYLOAD_REMAIN+1
        bcc     COPY_SIZE_OK
        dec     PAYLOAD_REMAIN
COPY_SIZE_OK:
        ldx     #SD_SECTOR_BUF+$20
        stx     SRC_PTR
        ldx     #SDFS3_LOAD_BASE
        stx     DST_PTR
        jsr     SET_COUNT_MIN_480
        jsr     COPY_CURRENT_BUFFER
COPY_SECTOR_LOOP:
        ldaa    PAYLOAD_REMAIN
        oraa    PAYLOAD_REMAIN+1
        beq     COPY_DONE
        jsr     INC_LBA
        jsr     READ_CURRENT_SECTOR
        bcs     COPY_FAIL_SD
        ldx     #SD_SECTOR_BUF
        stx     SRC_PTR
        jsr     SET_PAYLOAD_COUNT_MIN_512
        jsr     COPY_CURRENT_BUFFER
        bra     COPY_SECTOR_LOOP
COPY_DONE:
        rts
COPY_FAIL_SD:
        jmp     FAIL_SD

COPY_CURRENT_BUFFER:
COPY_LOOP:
        ldaa    COUNT
        oraa    COUNT+1
        beq     COPY_CURRENT_DONE
        ldx     SRC_PTR
        ldaa    0,x
        inx
        stx     SRC_PTR
        ldx     DST_PTR
        staa    0,x
        inx
        stx     DST_PTR
        jsr     DEC_COUNT_AND_PAYLOAD
        bra     COPY_LOOP
COPY_CURRENT_DONE:
        rts

SET_FIXED_LBA:
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        ldaa    #${SDFS3SYS_FIXED_LBA:02X}
        staa    SD_LBA3
        rts

READ_CURRENT_SECTOR:
        ldx     #SD_SECTOR_BUF
        jmp     SD_READ_SECTOR

INC_LBA:
        inc     SD_LBA3
        bne     INC_LBA_DONE
        inc     SD_LBA2
        bne     INC_LBA_DONE
        inc     SD_LBA1
        bne     INC_LBA_DONE
        inc     SD_LBA0
INC_LBA_DONE:
        rts

SET_COUNT_MIN_512:
        ldaa    REMAIN
        cmpa    #2
        bhs     SET_COUNT_512
        staa    COUNT
        ldaa    REMAIN+1
        staa    COUNT+1
        rts
SET_COUNT_512:
        ldaa    #2
        staa    COUNT
        clr     COUNT+1
        rts

SET_PAYLOAD_COUNT_MIN_512:
        ldaa    PAYLOAD_REMAIN
        cmpa    #2
        bhs     SET_COUNT_512
        staa    COUNT
        ldaa    PAYLOAD_REMAIN+1
        staa    COUNT+1
        rts

SET_COUNT_MIN_480:
        ldaa    PAYLOAD_REMAIN
        cmpa    #1
        bhi     SET_COUNT_480
        bne     SET_COUNT_PAYLOAD_REMAIN
        ldaa    PAYLOAD_REMAIN+1
        cmpa    #$E0
        bhs     SET_COUNT_480
SET_COUNT_PAYLOAD_REMAIN:
        ldaa    PAYLOAD_REMAIN
        staa    COUNT
        ldaa    PAYLOAD_REMAIN+1
        staa    COUNT+1
        rts
SET_COUNT_480:
        ldaa    #1
        staa    COUNT
        ldaa    #$E0
        staa    COUNT+1
        rts

ADD_SUM:
        adda    COMPUTED_SUM+1
        staa    COMPUTED_SUM+1
        bcc     ADD_SUM_DONE
        inc     COMPUTED_SUM
ADD_SUM_DONE:
        rts

DEC_COUNT_AND_REMAIN:
        jsr     DEC_COUNT
        dec     REMAIN+1
        ldaa    REMAIN+1
        cmpa    #$FF
        bne     DEC_REMAIN_DONE
        dec     REMAIN
DEC_REMAIN_DONE:
        rts

DEC_COUNT_AND_PAYLOAD:
        jsr     DEC_COUNT
        dec     PAYLOAD_REMAIN+1
        ldaa    PAYLOAD_REMAIN+1
        cmpa    #$FF
        bne     DEC_PAYLOAD_DONE
        dec     PAYLOAD_REMAIN
DEC_PAYLOAD_DONE:
        rts

DEC_COUNT:
        dec     COUNT+1
        ldaa    COUNT+1
        cmpa    #$FF
        bne     DEC_COUNT_DONE
        dec     COUNT
DEC_COUNT_DONE:
        rts

FAIL_MAGIC:
        ldaa    #$E1
        bra     CHECK_FAIL
FAIL_VERSION:
        ldaa    #$E2
        bra     CHECK_FAIL
FAIL_LOAD:
        ldaa    #$E3
        bra     CHECK_FAIL
FAIL_SIZE:
        ldaa    #$E4
        bra     CHECK_FAIL
FAIL_CHECKSUM:
        ldaa    #$E5
CHECK_FAIL:
        sec
        rts
"""


def _hex_bytes(data: bytes) -> str:
    return "\r".join(f"{value:02X}" for value in data)


@contextmanager
def _temporary_directory():
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT / f"codex-{uuid4().hex}"
    path.mkdir()
    yield str(path)


def _run_emu(
    *,
    rom_path: Path,
    input_text: str,
    max_cycles: int,
    dump_range: str = "0200-0202",
    sd_image: bytes | None = None,
    timeout: int = 10,
) -> tuple[str, str, int]:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="ascii", delete=False, dir=TEMP_ROOT) as f:
        f.write(input_text)
        input_path = Path(f.name)
    sd_path: Path | None = None
    if sd_image is not None:
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False, dir=TEMP_ROOT) as f:
            f.write(sd_image)
            sd_path = Path(f.name)
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
            dump_range,
        ]
        if sd_path is not None:
            cmd.extend(["--sd", str(sd_path)])
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    finally:
        input_path.unlink(missing_ok=True)
        if sd_path is not None:
            sd_path.unlink(missing_ok=True)
    return result.stdout, result.stderr, result.returncode


def _dump_bytes(stdout: str, address: int) -> list[int]:
    for line in stdout.splitlines():
        stripped = line.lstrip("] ")
        if stripped.startswith(f"{address:04X} "):
            parts = re.findall(r"\b[0-9A-Fa-f]{2}\b", stripped.split("  ", 1)[0])
            return [int(part, 16) for part in parts]
    raise AssertionError(f"missing dump line for {address:04X}: {stdout!r}")


def _dump_range_bytes(stdout: str, address: int, length: int) -> list[int]:
    result: list[int] = []
    current = address
    while len(result) < length:
        line_values = _dump_bytes(stdout, current)
        if not line_values:
            raise AssertionError(f"empty dump line for {current:04X}: {stdout!r}")
        take = min(len(line_values), length - len(result))
        result.extend(line_values[:take])
        current += len(line_values)
    return result


def _run_make(
    profile: str,
    target: str,
    expect_success: bool = True,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    make_args = ["make", target, f"MONITOR_PROFILE={profile}"]
    if extra_args:
        make_args.extend(extra_args)
    if sys.platform == "win32":
        make_args.extend(["PYTHON=python", "ASL_INCLUDE_ARG=build;include;src"])
    result = subprocess.run(
        make_args,
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
        test_sdfs3_memtop_and_caps_match_calling_convention,
        test_sdfs3_cmd_dispatch_parser_classifies_stub_commands,
        test_sdfs3sys_profiles_build_and_match_header,
        test_sdfs3_load_base_can_differ_from_v2_sdfs_load_base,
        test_sdfs3sys_rejects_bad_header_and_checksum,
        test_sdfs3sys_rejects_payload_outside_load_range,
        test_sdfs3sys_cli_reports_bad_input,
        test_rom_detects_sdfs3_api_header,
        test_rom_cmd_gateway_calls_resident_dispatch,
        test_fixed_lba_loader_harness_loads_sdfs3sys,
        test_rom_boot3_loads_sdfs3sys_and_enables_cmd,
        test_sdfs3_cmd_dir_and_type_read_fat_files,
        test_sdfs3_cmd_load_run_and_com_read_fat_files,
        test_fixed_lba_loader_harness_rejects_bad_sdfs3sys,
        test_rom_boot3_rejects_bad_sdfs3sys,
        test_sdfs3_mutable_vars_live_outside_image,
        test_sdfs3_core_does_not_reference_ccp,
        test_sdfs3_resident_image_unchanged_after_commands,
        test_sdfs3_init_clears_last_error,
        test_rom_bios_entry_table_layout,
        test_rom_bios_read_line_and_sd_match_internal,
        test_rom_bios_exec_returns_to_wboot,
        test_rom_bios_info_and_reserved,
        test_rom_bios_block_rejects_garbage,
        test_rom_boot3_writes_bios_block,
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
