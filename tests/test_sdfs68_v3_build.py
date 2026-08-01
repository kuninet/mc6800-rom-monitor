#!/usr/bin/env python3
"""SDFS/68 v3 resident stub build tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"

from mk_sdfs3sys import (  # noqa: E402
    FLAG_CHECKSUM16,
    HEADER_SIZE,
    MAGIC,
    build_sdfs3sys_image,
    checksum16,
    parse_sdfs3sys_header,
)


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
            "SDFS3_GET_MEMTOP",
            "SDFS3_GET_CAPS",
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
        assert data[10] == 9, "SDFS3 api count mismatch"
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
        assert _word(data, jump_table + 14) == symbols["SDFS3_GET_MEMTOP"]
        assert _word(data, jump_table + 16) == symbols["SDFS3_GET_CAPS"]
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


def test_sdfs3_memtop_and_caps_match_calling_convention() -> None:
    for profile, expected in EXPECTED.items():
        _run_make(profile, "sdfs3")
        suffix = expected["suffix"]
        data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
        symbols = _load_symbols(
            PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
            "SDFS_LOAD_BASE",
            "SDFS3_API_HEADER",
            "SDFS3_GET_MEMTOP",
            "SDFS3_GET_CAPS",
        )
        get_memtop = symbols["SDFS3_GET_MEMTOP"] - symbols["SDFS_LOAD_BASE"]
        memtop = expected["USER_RAM_END"]
        assert data[get_memtop : get_memtop + 5] == bytes(
            [0xCE, (memtop >> 8) & 0xFF, memtop & 0xFF, 0x0C, 0x39]
        )

        get_caps = symbols["SDFS3_GET_CAPS"] - symbols["SDFS_LOAD_BASE"]
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
            "SDFS_LOAD_BASE",
            "SDFS_LOAD_LIMIT",
            "SDFS3_JUMP_TABLE",
            "SDFS3_GET_INFO",
        )
        header = parse_sdfs3sys_header(image)
        assert image[0:8] == MAGIC
        assert header.header_version == 1
        assert header.abi_major == 1
        assert header.abi_minor == 0
        assert header.flags == FLAG_CHECKSUM16
        assert header.load_address == expected["SDFS_LOAD_BASE"]
        assert header.load_address == symbols["SDFS_LOAD_BASE"]
        assert len(payload) <= symbols["SDFS_LOAD_LIMIT"] - symbols["SDFS_LOAD_BASE"] + 1
        assert header.image_size == HEADER_SIZE + len(payload)
        assert header.entry_offset == symbols["SDFS3_GET_INFO"] - symbols["SDFS_LOAD_BASE"]
        assert header.api_table_offset == symbols["SDFS3_JUMP_TABLE"] - symbols["SDFS_LOAD_BASE"]
        assert header.work_min == 0
        assert header.bank_window_hint == 0
        assert header.header_size == HEADER_SIZE
        assert header.checksum == checksum16(image)
        assert image[HEADER_SIZE:] == payload
    print("[PASS] test_sdfs3sys_profiles_build_and_match_header")


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
    with tempfile.TemporaryDirectory() as tmp:
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
        ("legacy api count 7", _mutated_header(symbols["SDFS_LOAD_BASE"], 10, 0x07), 0xE1),
        ("short api count 8", _mutated_header(symbols["SDFS_LOAD_BASE"], 10, 0x08), 0xE1),
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


def test_rom_cmd_gateway_calls_resident_dispatch() -> None:
    profile = "sbcio_4000"
    expected = EXPECTED[profile]
    _run_make(profile, "bin")
    suffix = expected["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "LINE_BUF",
        "SDFS_LOAD_BASE",
    )
    status_addr = 0x0200
    b_addr = 0x0201
    x_addr = 0x0202
    load_base = symbols["SDFS_LOAD_BASE"]
    jump_table = load_base + 0x18
    dispatch = jump_table + 0x12
    header = _sdfs3_header(load_base, jump_table=jump_table, work_end=dispatch + 13)
    jump_table_data = bytes(
        [
            0x00,
            0x00,
            (dispatch >> 8) & 0xFF,
            dispatch & 0xFF,
            *([0x00, 0x00] * 7),
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
            0x00,
            0x09,
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


def _hex_bytes(data: bytes) -> str:
    return "\r".join(f"{value:02X}" for value in data)


def _run_emu(
    *,
    rom_path: Path,
    input_text: str,
    max_cycles: int,
    dump_range: str = "0200-0202",
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
            dump_range,
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
        test_sdfs3_memtop_and_caps_match_calling_convention,
        test_sdfs3sys_profiles_build_and_match_header,
        test_sdfs3sys_rejects_bad_header_and_checksum,
        test_sdfs3sys_rejects_payload_outside_load_range,
        test_sdfs3sys_cli_reports_bad_input,
        test_rom_detects_sdfs3_api_header,
        test_rom_cmd_gateway_calls_resident_dispatch,
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
