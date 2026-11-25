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

# ---------------------------------------------------------------------------
# 案 B の配置(#313)。v3 は sbcio_vdg・k6802_vdg で作る(4000 work は v2 専用。決定 11)
# ---------------------------------------------------------------------------

V3_PROFILES = {
    "sbcio_vdg": "-sbcio-vdg",
    "k6802_vdg": "-k6802-vdg",
}
V3_CCP_BASE = 0x6400
V3_CORE_BASE = 0x7000
V3_CORE_OFFSET = V3_CORE_BASE - V3_CCP_BASE
V3_MEMTOP = 0x6FFF
V3_COM_MAX = V3_CCP_BASE - 0x0100
V3_API_MAJOR = 2
V3_API_MINOR = 0
PROMPT = "SDFS3> "
WELCOME = "SDFS/68 V3 02.00"
_V3_CACHE: dict[str, dict] = {}

# tsx / ldaa 0,x / staa $0210 / ldaa 1,x / staa $0211 / rts。スタックの一番上(戻り番地)を残す
RETADDR_COM = bytes([0x30, 0xA6, 0x00, 0xB7, 0x02, 0x10, 0xA6, 0x01, 0xB7, 0x02, 0x11, 0x39])


def _print_program(text: bytes, last: int) -> bytes:
    """ldx #$0107 / jsr PDATA1 / <last> の後ろに CR LF text CR LF EOT を置く($0100 から)。"""
    return bytes([0xCE, 0x01, 0x07, 0xBD, 0xE0, 0x7E, last, 0x0D, 0x0A, *text, 0x0D, 0x0A, 0x04])


def _v3(profile: str) -> dict:
    """ROM・SDFS3SYS・サンプルの .COM を作り、番地をまとめて返す(プロファイルごとに 1 回)。"""
    if profile in _V3_CACHE:
        return _V3_CACHE[profile]
    suffix = V3_PROFILES[profile]
    _run_make(profile, "bin")
    _run_make(profile, "sdfs3sys")
    _run_make(profile, "sdfs-tools")
    build = PROJECT_ROOT / "build"
    rom = _load_symbols(
        build / f"mc6800-monitor{suffix}.lst",
        "BIOS_WBOOT",
        "BIOS_BLOCK",
        "BB_MAGIC",
        "SDFS3_WORK_BASE",
    )
    resident = _load_symbols(
        build / f"SDFS3{suffix}.lst",
        "SDFS3_CCP_BASE",
        "SDFS3_CORE_BASE",
        "SDFS3_END",
        "SDFS3_LAST_ERROR",
        "SDFS3_PENDING_ERR",
        "SDFS3_GET_ERROR",
        "SDFS3_CMD_DISPATCH",
        "SDFS3_ERR_COM",
    )
    assert resident["SDFS3_CCP_BASE"] == V3_CCP_BASE and resident["SDFS3_CORE_BASE"] == V3_CORE_BASE
    config = {
        "profile": profile,
        "suffix": suffix,
        "rom": build / f"mc6800-monitor{suffix}.bin",
        "sdfs3sys": (build / f"SDFS3SYS{suffix}.BIN").read_bytes(),
        "hello_com": (build / "HELLO.COM").read_bytes(),
        "args_com": (build / "ARGS.COM").read_bytes(),
        "symbols": {**rom, **resident},
    }
    _V3_CACHE[profile] = config
    return config


def _v3_run(
    config: dict,
    input_text: str,
    *,
    sd_image: bytes,
    dump_range: str = "0200-0211",
    max_cycles: int = 600_000_000,
    timeout: int = 120,
) -> str:
    stdout, stderr, rc = _run_emu(
        rom_path=config["rom"],
        input_text=input_text,
        max_cycles=max_cycles,
        sd_image=sd_image,
        dump_range=dump_range,
        timeout=timeout,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"{config['profile']}: emulator failed: rc={rc} stderr={stderr[-400:]!r}"
    )
    return stdout.replace("\r", "")


def _dos(out: str, command: str) -> str:
    """DOS のプロンプトで打った command の出力(次の SDFS3> まで)を返す。
    次のプロンプトが無ければ DOS に戻っていないので失敗にする。"""
    marker = PROMPT + command + "\n"
    assert marker in out, f"DOS did not accept {command!r}: {out[-1500:]!r}"
    rest = out[out.index(marker) + len(marker) :]
    assert PROMPT in rest, f"{command!r} did not return to the DOS prompt: {rest[:600]!r}"
    return rest[: rest.index(PROMPT)]


def _refresh_checksum(data: bytearray) -> None:
    data[CHECKSUM_OFFSET] = 0
    data[CHECKSUM_OFFSET + 1] = 0
    checksum = checksum16(bytes(data))
    data[CHECKSUM_OFFSET] = (checksum >> 8) & 0xFF
    data[CHECKSUM_OFFSET + 1] = checksum & 0xFF


def test_sdfs3_rejects_4000_work_profiles() -> None:
    for profile in ("sbcio_4000", "k6802_4000"):
        result = _run_make(profile, "sdfs3sys", expect_success=False)
        output = result.stdout + result.stderr
        assert result.returncode != 0, f"{profile}: v3 build should be rejected"
        assert "4000 work profiles are v2 only" in output, f"{profile}: unclear error: {output!r}"
    print("[PASS] test_sdfs3_rejects_4000_work_profiles")


def test_sdfs3_profiles_build_and_match_header() -> None:
    slot_names = [
        "SDFS3_GET_INFO",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_LOAD_PATH",
        "SDFS3_READ_STREAM_OPEN",
        "SDFS3_READ_STREAM_GETC",
        "SDFS3_READ_STREAM_CLOSE",
        "SDFS3_GET_ERROR",
        "SDFS3_GET_MEMTOP",
        "SDFS3_GET_CAPS",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_INIT",
        "SDFS3_NOT_IMPLEMENTED",
        "SDFS3_NOT_IMPLEMENTED",
    ]
    for profile, suffix in V3_PROFILES.items():
        _run_make(profile, "sdfs3")
        data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
        symbols = _load_symbols(
            PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
            "SDFS3_CCP_BASE",
            "SDFS3_CORE_BASE",
            "SDFS3_MEMTOP",
            "SDFS3_COM_MAX",
            "USER_RAM_END",
            "SDFS3_CCP_START",
            "SDFS3_CCP_VECTORS",
            "SDFS3_CCP_COLD",
            "SDFS3_CCP_WARM",
            "SDFS3_CCP_END",
            "SDFS3_CORE_START",
            "SDFS3_API_HEADER",
            "SDFS3_JUMP_TABLE",
            "SDFS3_LAST_ERROR",
            "SDFS3_PENDING_ERR",
            "SDFS3_END",
            *sorted(set(slot_names)),
        )
        base = symbols["SDFS3_CCP_BASE"]
        assert base == V3_CCP_BASE, f"{profile}: CCP_BASE"
        assert symbols["SDFS3_CORE_BASE"] == V3_CORE_BASE, f"{profile}: CORE_BASE"
        assert symbols["SDFS3_MEMTOP"] == V3_MEMTOP and symbols["SDFS3_COM_MAX"] == V3_COM_MAX
        assert symbols["USER_RAM_END"] == 0x7FFF
        assert symbols["SDFS3_CCP_START"] == symbols["SDFS3_CCP_VECTORS"] == base
        assert symbols["SDFS3_CCP_END"] <= V3_CORE_BASE, f"{profile}: CCP overflows into the core"
        assert symbols["SDFS3_CORE_START"] == symbols["SDFS3_API_HEADER"] == V3_CORE_BASE
        assert symbols["SDFS3_END"] - 1 <= 0x7FFF, f"{profile}: core exceeds $7FFF"
        assert len(data) == symbols["SDFS3_END"] - base
        cold, warm = symbols["SDFS3_CCP_COLD"], symbols["SDFS3_CCP_WARM"]
        assert data[0:9] == bytes(
            [0x7E, cold >> 8, cold & 0xFF, 0x7E, warm >> 8, warm & 0xFF, 0x7E, warm >> 8, warm & 0xFF]
        ), f"{profile}: CCP entry table must be jmp cold / jmp warm / jmp warm: {data[0:9].hex()}"
        header = data[V3_CORE_OFFSET:]
        assert header[0:8] == b"SDFS3API"
        assert header[8] == V3_API_MAJOR, "SDFS3 api major mismatch"
        assert header[9] == V3_API_MINOR, "SDFS3 api minor mismatch"
        assert header[10] == 16, "SDFS3 api count mismatch"
        assert header[11] == 0, "SDFS3 flags should be zero"
        assert _word(header, 0x0C) == symbols["SDFS3_JUMP_TABLE"]
        assert _word(header, 0x0E) == base, "work_base should be the image start (CCP)"
        assert _word(header, 0x10) == symbols["SDFS3_END"] - 1
        assert _word(header, 0x12) == V3_MEMTOP, "memtop should be CORE_BASE-1"
        assert _word(header, 0x14) == 0 and _word(header, 0x16) == 0
        table = symbols["SDFS3_JUMP_TABLE"] - base
        for slot, name in enumerate(slot_names):
            assert _word(data, table + 2 * slot) == symbols[name], f"{profile}: slot {slot} != {name}"
            assert _word(data, table + 2 * slot) >= V3_CORE_BASE, f"{profile}: slot {slot} points into CCP"
        get_error = symbols["SDFS3_GET_ERROR"] - base
        assert data[get_error + 3 : get_error + 5] == bytes([0x0C, 0x39])
        # INIT は出力しない: clr LAST_ERROR / clr PENDING_ERR / clc / rts だけ
        init = symbols["SDFS3_INIT"] - base
        last_error, pending = symbols["SDFS3_LAST_ERROR"], symbols["SDFS3_PENDING_ERR"]
        assert data[init : init + 8] == bytes(
            [0x7F, last_error >> 8, last_error & 0xFF, 0x7F, pending >> 8, pending & 0xFF, 0x0C, 0x39]
        ), f"{profile}: INIT should only clear the error variables: {data[init:init + 8].hex()}"
        ccp_part = data[: symbols["SDFS3_CCP_END"] - base]
        core_part = data[V3_CORE_OFFSET:]
        assert b"SDFS/68 V3 " in ccp_part and b"SDFS/68 V3 " not in core_part, "Welcome belongs to CCP"
        assert b"SDFS3> " in ccp_part, "DOS prompt string missing"
    print("[PASS] test_sdfs3_profiles_build_and_match_header")


def test_sdfs3_get_info_matches_calling_convention() -> None:
    profile, suffix = "sbcio_vdg", V3_PROFILES["sbcio_vdg"]
    _run_make(profile, "sdfs3")
    data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
        "SDFS3_CCP_BASE",
        "SDFS3_GET_INFO",
        "SDFS3_API_HEADER",
    )
    get_info = symbols["SDFS3_GET_INFO"] - symbols["SDFS3_CCP_BASE"]
    header = symbols["SDFS3_API_HEADER"]
    assert data[get_info : get_info + 9] == bytes(
        [0x86, V3_API_MAJOR, 0xC6, 0x00, 0xCE, (header >> 8) & 0xFF, header & 0xFF, 0x0C, 0x39]
    )
    print("[PASS] test_sdfs3_get_info_matches_calling_convention")


def test_sdfs3_memtop_and_caps_match_calling_convention() -> None:
    for profile, suffix in V3_PROFILES.items():
        _run_make(profile, "sdfs3")
        data = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
        symbols = _load_symbols(
            PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
            "SDFS3_CCP_BASE",
            "SDFS3_API_HEADER",
            "SDFS3_GET_MEMTOP",
            "SDFS3_GET_CAPS",
        )
        get_memtop = symbols["SDFS3_GET_MEMTOP"] - symbols["SDFS3_CCP_BASE"]
        assert data[get_memtop : get_memtop + 5] == bytes(
            [0xCE, (V3_MEMTOP >> 8) & 0xFF, V3_MEMTOP & 0xFF, 0x0C, 0x39]
        ), f"{profile}: GET_MEMTOP should return $6FFF"
        get_caps = symbols["SDFS3_GET_CAPS"] - symbols["SDFS3_CCP_BASE"]
        header = symbols["SDFS3_API_HEADER"]
        assert data[get_caps : get_caps + 9] == bytes(
            [0x86, 0x00, 0xC6, 0x00, 0xCE, (header >> 8) & 0xFF, header & 0xFF, 0x0C, 0x39]
        )
    print("[PASS] test_sdfs3_memtop_and_caps_match_calling_convention")


def test_sdfs3sys_profiles_build_and_match_header() -> None:
    for profile, suffix in V3_PROFILES.items():
        # 上書き(SDFS3_LOAD_BASE など)の指定なしで通ること(#313 の受入基準)
        _run_make(profile, "sdfs3sys")
        image = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
        payload = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.BIN").read_bytes()
        symbols = _load_symbols(
            PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst",
            "SDFS3_CCP_BASE",
            "SDFS3_CCP_VECTORS",
            "SDFS3_API_HEADER",
            "SDFS3_END",
        )
        header = parse_sdfs3sys_header(image)
        assert image[0:8] == MAGIC
        assert header.header_version == 1
        assert header.abi_major == V3_API_MAJOR, "SDFS3SYS +$09 must carry API major 2"
        assert header.abi_minor == V3_API_MINOR
        assert header.flags == FLAG_CHECKSUM16
        assert header.load_address == symbols["SDFS3_CCP_BASE"] == V3_CCP_BASE
        assert header.image_size == HEADER_SIZE + len(payload)
        assert header.load_address + len(payload) - 1 == symbols["SDFS3_END"] - 1 <= 0x7FFF
        assert header.entry_offset == symbols["SDFS3_CCP_VECTORS"] - V3_CCP_BASE == 0
        assert header.api_table_offset == symbols["SDFS3_API_HEADER"] - V3_CCP_BASE == V3_CORE_OFFSET
        assert header.work_min == 0
        assert header.bank_window_hint == 0
        assert header.header_size == HEADER_SIZE
        assert header.checksum == checksum16(image)
        assert image[HEADER_SIZE:] == payload
    print("[PASS] test_sdfs3sys_profiles_build_and_match_header")


def test_rom_drops_cmd_gateway_and_fixed_load_base() -> None:
    """ROM のリスティングに SDFS3_LOAD_BASE・CMD_SDFS3 などが残っていない(#313 の受入基準)。"""
    gone = (
        "SDFS3_LOAD_BASE",
        "SDFS3_LOAD_LIMIT",
        "CMD_SDFS3",
        "IS_CMD_CMD",
        "SDFS3_FIND_API",
        "SDFS3_API_MIN_COUNT",
        "SDFS3_DISPATCH",
        "SDFS3_RETURN",
    )
    for profile, suffix in V3_PROFILES.items():
        _run_make(profile, "bin")
        rom_text = (PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst").read_text(errors="replace")
        config_text = (PROJECT_ROOT / "build" / "monitor_config.inc").read_text()
        for name in gone:
            assert not re.search(rf"\b{name}\b", rom_text), f"{profile}: {name} still in ROM listing"
            assert not re.search(rf"\b{name}\b", config_text), f"{profile}: {name} still generated"
        assert re.search(r"\bIS_CMD_DOS\b", rom_text) and re.search(r"\bBIOS_WBOOT_IMPL\b", rom_text)
        _run_make(profile, "sdfs3")
        resident_text = (PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst").read_text(errors="replace")
        assert not re.search(r"\bSDFS3_LOAD_BASE\b", resident_text), f"{profile}: resident still uses LOAD_BASE"
    print("[PASS] test_rom_drops_cmd_gateway_and_fixed_load_base")


def test_sdfs3_cmd_dispatch_parser_classifies_stub_commands() -> None:
    """BOOT3 で置いた resident の CMD_DISPATCH を、EXIT してからハーネスで直接呼ぶ。
    SD に FAT が無いので、ファイルを使うコマンドはマウントで失敗し、種類ごとのエラーになる。"""
    config = _v3("sbcio_vdg")
    symbols = config["symbols"]
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
        ("EXITX", 0x02),
    ]
    with _temporary_directory() as tmp:
        harness = _assemble_cmd_dispatch_harness(Path(tmp), symbols, cases)
    result_addr = 0x0200
    out = _v3_run(
        config,
        "BOOT3\rEXIT\r"
        f"M0300\r{_hex_bytes(harness)}\r.\r"
        "G0300\r"
        f"D{result_addr:04X}-{result_addr + len(cases) * 2 - 1:04X}\r"
        "\r",
        sd_image=_build_sdfs3sys_sd_image(config["sdfs3sys"]),
        dump_range=f"{result_addr:04X}-{result_addr + len(cases) * 2 - 1:04X}",
        max_cycles=300_000_000,
        timeout=60,
    )
    values = _dump_range_bytes(_after(out, "G0300"), result_addr, len(cases) * 2)
    expected_values: list[int] = []
    for _, error_code in cases:
        expected_values.extend([1, error_code])
    assert values == expected_values, f"CMD_DISPATCH classification mismatch: {values!r}\n{out[-1500:]!r}"
    print("[PASS] test_sdfs3_cmd_dispatch_parser_classifies_stub_commands")


def test_rom_boot3_enters_dos_and_com_returns_through_wboot() -> None:
    """両プロファイルで BOOT3 → Welcome → DOS のプロンプト → DIR・TYPE・.COM・LOAD・RUN →
    EXIT → モニタ → DOS(Welcome なし)。.COM の RTS は ROM の WBOOT を通って戻る。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        sd_image = _build_sdfs3sys_fat_sd_image(
            config["sdfs3sys"],
            [
                _file("README.TXT", b"HELLO FROM README\r\n"),
                _file("HELLO.S", _srec_file(0x0200, b"S")),
                _file("HELLO.COM", config["hello_com"]),
                _file("ARGS.COM", config["args_com"]),
                _file("RETADDR.COM", RETADDR_COM),
                _file("RTS.S", _srec_file(0x0100, _print_program(b"RUN RTS", 0x39), entry_address=0x0100)),
            ],
        )
        out = _v3_run(
            config,
            "M0180\r3F\r.\r"
            "BOOT3\r"
            "DIR\r"
            "TYPE README.TXT\r"
            "HELLO.COM\r"
            "ARGS.COM AAA BBB\r"
            "RETADDR.COM\r"
            "LOAD HELLO.S\r"
            "RUN RTS.S\r"
            "RUN 0180\r"
            "DOS\r"
            "EXIT\r"
            "D0200-0200\r"
            "DOS\r"
            "DIR\r"
            "\r",
            sd_image=sd_image,
        )
        end = symbols["SDFS3_END"] - 1
        boot = _after(out, "] BOOT3\n")
        assert boot.startswith(f"{WELCOME}\nBASE=6400 END={end:04X}\n{PROMPT}DIR\n"), (
            f"{profile}: BOOT3 should go straight from Welcome to the DOS prompt: {boot[:200]!r}"
        )
        assert "README.TXT A 00000013" in _dos(out, "DIR")
        assert "HELLO FROM README" in _dos(out, "TYPE README.TXT")
        assert "HELLO COM" in _dos(out, "HELLO.COM")
        assert "ARGS AAA BBB" in _dos(out, "ARGS.COM AAA BBB")
        assert "?" not in _dos(out, "RETADDR.COM")
        assert "OK" in _dos(out, "LOAD HELLO.S")
        assert "RUN RTS" in _dos(out, "RUN RTS.S"), f"{profile}: RUN file with RTS should return to DOS"
        run_brk = _after(out, PROMPT + "RUN 0180\n")
        assert run_brk.lstrip("\n").startswith("BRK 0180"), f"{profile}: RUN addr: {run_brk[:200]!r}"
        assert f"] DOS\n{PROMPT}EXIT\n] D0200-0200\n0200 53" in out, (
            f"{profile}: DOS after BRK, EXIT and the monitor dump did not chain: {out[-900:]!r}"
        )
        assert out.count(PROMPT + "DIR\n") == 2, f"{profile}: second DIR after DOS missing"
        assert out.count(WELCOME) == 1, f"{profile}: warm entries must not print Welcome: {out!r}"
        assert "\n?\n" not in out, f"{profile}: no command should fail: {out!r}"
        # 終了時のダンプは DOS のプロンプトの直後に続くので、最後の「0200 」から読む
        ret = _dump_range_bytes(out[out.rindex("0200 ") :], 0x0200, 0x12)
        assert (ret[0x10] << 8 | ret[0x11]) == symbols["BIOS_WBOOT"] == 0xE0E6, (
            f"{profile}: .COM return address should be ROM WBOOT: {ret!r}"
        )
    print("[PASS] test_rom_boot3_enters_dos_and_com_returns_through_wboot")


def test_sdfs3_cmd_dir_and_type_read_fat_files() -> None:
    config = _v3("sbcio_vdg")
    sd_image = _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            Fat32File(b"HELLO   S  ", b"S9030000FC\r\n"),
            Fat32File(b"README  TXT", b"HELLO FROM README\r\n"),
            Fat32File(b"NOTE    TXT", b"HELLO FROM DOCS\r\n", path=(b"DOCS       ",)),
        ],
    )
    commands = ["DIR", "DIR DOCS", "DIR MISSING", "TYPE README.TXT", "TYPE DOCS/NOTE.TXT", "TYPE MISSING.TXT"]
    out = _v3_run(
        config,
        "BOOT3\r" + "".join(f"{command}\r" for command in commands) + "\r",
        sd_image=sd_image,
    )
    listing = _dos(out, "DIR")
    assert "HELLO.S A " in listing and "README.TXT A 00000013" in listing and "DOCS D 00000000" in listing
    assert "NOTE.TXT A 00000011" in _dos(out, "DIR DOCS")
    assert _dos(out, "DIR MISSING") == "?\n"
    assert "HELLO FROM README" in _dos(out, "TYPE README.TXT")
    assert "HELLO FROM DOCS" in _dos(out, "TYPE DOCS/NOTE.TXT")
    assert _dos(out, "TYPE MISSING.TXT") == "?\n"
    assert out.count("\n?\n") == 2, f"missing DIR/TYPE should fail exactly twice: {out!r}"
    print("[PASS] test_sdfs3_cmd_dir_and_type_read_fat_files")


def test_sdfs3_cmd_load_run_and_com_read_fat_files() -> None:
    config = _v3("k6802_vdg")
    sd_image = _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            _file("HELLO.S", _srec_file(0x0200, b"S")),
            _file("HELLO.HEX", _ihex_file(0x0201, b"I")),
            _file("RUN.S", _srec_file(0x0100, _print_program(b"HELLO, WORLD", 0x3F), entry_address=0x0100)),
            _file("HELLO.COM", config["hello_com"]),
            _file("ARGS.COM", config["args_com"]),
            _file("EMPTY.COM", b""),
            _file("BIG.COM", b"\x39" * (V3_COM_MAX + 1)),
            _file("MAX.COM", b"\x39" * V3_COM_MAX),
        ],
    )
    out = _v3_run(
        config,
        "M0110\r3F\r.\r"
        "BOOT3\r"
        "LOAD HELLO.S\r"
        "LOAD HELLO.HEX\r"
        "EXIT\r"
        "D0200-0201\r"
        "DOS\r"
        "RUN 0110\r"
        "DOS\r"
        "HELLO.COM\r"
        "ARGS.COM AAA BBB\r"
        "NOFILE.COM\r"
        "EMPTY.COM\r"
        "BIG.COM\r"
        "MAX.COM\r"
        "RUN HELLO.HEX\r"
        "RUN RUN.S\r"
        "DOS\r"
        "\r",
        sd_image=sd_image,
        max_cycles=2_000_000_000,
        timeout=400,
    )
    assert "OK" in _dos(out, "LOAD HELLO.S")
    assert "OK" in _dos(out, "LOAD HELLO.HEX")
    assert "] D0200-0201\n0200 53 49" in out, f"LOAD did not write S-record/HEX data: {out!r}"
    assert _after(out, PROMPT + "RUN 0110\n").lstrip("\n").startswith("BRK 0110"), "RUN addr"
    assert "HELLO COM" in _dos(out, "HELLO.COM")
    assert "ARGS AAA BBB" in _dos(out, "ARGS.COM AAA BBB")
    assert _dos(out, "NOFILE.COM") == "?\n"
    assert _dos(out, "EMPTY.COM") == "?\n"
    assert _dos(out, "BIG.COM") == "?\n", f".COM larger than CCP_BASE-$0100 must be rejected: {out!r}"
    assert _dos(out, "MAX.COM") == "", f".COM of exactly CCP_BASE-$0100 bytes should run: {out!r}"
    assert _dos(out, "RUN HELLO.HEX") == "?\n"
    run_file = _after(out, PROMPT + "RUN RUN.S\n")
    assert "HELLO, WORLD" in run_file and "BRK 0106" in run_file, f"RUN file: {run_file[:300]!r}"
    assert out.count("] DOS\n" + PROMPT) == 3, f"each DOS from the monitor should reach the prompt: {out[-300:]!r}"
    assert out.count("\n?\n") == 4, f"bad .COM/RUN inputs should fail exactly four times: {out!r}"
    assert out.count(WELCOME) == 1
    print("[PASS] test_sdfs3_cmd_load_run_and_com_read_fat_files")


# ---------------------------------------------------------------------------
# #314 戻り口の検査と静かな再ロード、BOOT3 の 1 回読み、モニタの門、スタックの分離
# ---------------------------------------------------------------------------

# $6400-$6FFF を $00 で埋めて RTS(大きな .COM が CCP を潰した代わり)
ZAPCCP_COM = bytes(
    [0xCE, V3_CCP_BASE >> 8, V3_CCP_BASE & 0xFF, 0x6F, 0x00, 0x08,
     0x8C, V3_CORE_BASE >> 8, V3_CORE_BASE & 0xFF, 0x26, 0xF8, 0x39]
)
ZAPCORE_ADDR = V3_CORE_BASE + 0x100
# 核の 1 バイトを反転して RTS
ZAPCORE_COM = bytes([0xB6, ZAPCORE_ADDR >> 8, ZAPCORE_ADDR & 0xFF, 0x43,
                     0xB7, ZAPCORE_ADDR >> 8, ZAPCORE_ADDR & 0xFF, 0x39])
SWI_DATA_ADDR = V3_CCP_BASE + 0x100
SWI_BREAK_ADDR = 0x0105
# $0100: CCP の $6500 に $5A を置き、$0105 の NOP(ここに B で SWI を置く)、$6500 を $0210 へ
# 写して RTS。モニタの SWI はブレークポイントとして扱われ(R は SWI の番地から再開する)、
# B が置いた SWI だけが元の命令に戻るので、止める SWI は B で置く。
SWI_PROG = bytes([0x86, 0x5A, 0xB7, SWI_DATA_ADDR >> 8, SWI_DATA_ADDR & 0xFF, 0x01,
                  0xB6, SWI_DATA_ADDR >> 8, SWI_DATA_ADDR & 0xFF, 0xB7, 0x02, 0x10, 0x39])


def _v3_run_sd(
    config: dict,
    input_text: str,
    *,
    sd_image: bytes,
    fail_from: int | None = None,
    swap_image: bytes | None = None,
    swap_at: int | None = None,
    stack_watch: int | None = None,
    dump_range: str = "0200-0211",
    max_cycles: int = 900_000_000,
    timeout: int = 240,
) -> tuple[str, list[tuple[int, int, int, int]], str]:
    """エミュレータを SD の記録付きで動かす。(\\r を残した出力, CMD17 の記録, stderr) を返す。
    記録は (番号, LBA, R1, その時点の送信済みバイト数)。送信済みバイト数は出力の位置と同じ。"""
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = TEMP_ROOT / f"sdlog-{uuid4().hex}.txt"
    swap_path = TEMP_ROOT / f"swap-{uuid4().hex}.img"
    args = ["--sd-log", str(log_path)]
    if fail_from is not None:
        args += ["--sd-fail-cmd17-from", str(fail_from)]
    if swap_image is not None:
        swap_path.write_bytes(swap_image)
        args += ["--sd-swap-image", str(swap_path), "--sd-swap-at", str(swap_at)]
    if stack_watch is not None:
        args += ["--stack-watch", f"{stack_watch:04X}"]
    try:
        stdout, stderr, rc = _run_emu(
            rom_path=config["rom"],
            input_text=input_text,
            max_cycles=max_cycles,
            sd_image=sd_image,
            dump_range=dump_range,
            timeout=timeout,
            extra_args=args,
            keep_cr=True,
        )
        log = [
            tuple(int(v, 16) if i == 2 else int(v) for i, v in enumerate(line.split()))
            for line in log_path.read_text(encoding="ascii").splitlines()
        ]
    finally:
        log_path.unlink(missing_ok=True)
        swap_path.unlink(missing_ok=True)
    assert rc == 0 and "[TIMEOUT]" not in stderr and "サイクル上限" not in stderr, (
        f"{config['profile']}: emulator failed: rc={rc} stderr={stderr[-400:]!r}"
    )
    return stdout, log, stderr


def _segment(raw: str, marker: str, nth: int = 0, end: str = PROMPT) -> tuple[int, int]:
    """raw の nth 番目の marker の直後から、次の end の手前までの位置を返す。"""
    pos = -1
    for _ in range(nth + 1):
        pos = raw.index(marker, pos + 1)
    start = pos + len(marker)
    return start, raw.index(end, start)


def _reads(log: list, start: int, stop: int, *, system_only: bool = False) -> list[int]:
    """出力の位置 start〜stop(両端を含む)の間に起きた CMD17 の LBA。system_only なら SDFS3SYS の
    範囲だけ。記録の送信済みバイト数は「その時点までに出した文字数」なので、stop の文字(次の
    プロンプトの先頭)を出す前の読み出しは tx == stop になる。"""
    return [
        lba
        for _n, lba, _r1, tx in log
        if start <= tx <= stop
        and (not system_only or SDFS3SYS_FIXED_LBA <= lba < SDFS3SYS_FAT_PARTITION_LBA)
    ]


def _system_sectors(config: dict) -> dict[str, list[int]]:
    """SDFS3SYS のセクタの LBA。ccp・core は読み直しで読むはずの LBA(先頭セクタは 1 回)。"""
    size = len(config["sdfs3sys"])
    last = SDFS3SYS_FIXED_LBA + (size - 1) // SECTOR_SIZE
    ccp_end = HEADER_SIZE + (V3_CORE_BASE - V3_CCP_BASE)  # ファイル上の CCP の終端(最後の次)
    ccp = list(range(SDFS3SYS_FIXED_LBA, SDFS3SYS_FIXED_LBA + (ccp_end - 1) // SECTOR_SIZE + 1))
    core_first = SDFS3SYS_FIXED_LBA + ccp_end // SECTOR_SIZE
    core = [SDFS3SYS_FIXED_LBA, *range(core_first, last + 1)]
    return {"all": list(range(SDFS3SYS_FIXED_LBA, last + 1)), "ccp": ccp, "core": core}


def _wboot_sd_image(config: dict) -> bytes:
    return _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            _file("README.TXT", b"HELLO FROM README\r\n"),
            _file("HELLO.COM", config["hello_com"]),
            _file("ZAPCCP.COM", ZAPCCP_COM),
            _file("ZAPCORE.COM", ZAPCORE_COM),
            _file("SWI.S", _srec_file(0x0100, SWI_PROG, entry_address=0x0100)),
        ],
    )


def _reset_address(config: dict) -> int:
    rom = config["rom"].read_bytes()
    return (rom[-2] << 8) | rom[-1]


def test_rom_boot3_reads_image_once() -> None:
    """BOOT3 は SDFS3SYS のセクタを 64 から 1 回ずつ読む(2 回読みならセクタ数の 2 倍)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sectors = _system_sectors(config)
        raw, log, _ = _v3_run_sd(config, "BOOT3\rDIR\r\r", sd_image=_wboot_sd_image(config))
        start, stop = _segment(raw, "] BOOT3")
        reads = _reads(log, start, stop)
        assert reads == sectors["all"], f"{profile}: BOOT3 should read each sector once: {reads}"
        assert len(reads) == -(-len(config["sdfs3sys"]) // SECTOR_SIZE)
        assert "README.TXT" in _dos(raw.replace("\r", ""), "DIR")
    print("[PASS] test_rom_boot3_reads_image_once")


def test_wboot_reloads_only_broken_parts() -> None:
    """健全な戻りは SD を読まない。CCP だけ・核だけが壊れたら、その範囲のセクタだけを
    何も表示せずに読み直す。SWI で止めたときは注意だけ出して読み直さず、R で再開した
    プログラムの RTS が WBOOT に着いてから CCP を読み直す(シナリオ 1・2・3・5)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sectors = _system_sectors(config)
        payload = config["sdfs3sys"][HEADER_SIZE:]
        swi_orig = payload[SWI_DATA_ADDR - V3_CCP_BASE]
        assert swi_orig != 0x5A
        raw, log, _ = _v3_run_sd(
            config,
            "BOOT3\rHELLO.COM\rZAPCCP.COM\rDIR\rZAPCORE.COM\rDIR\rLOAD SWI.S\rEXIT\r"
            f"B{SWI_BREAK_ADDR:04X}\rDOS\rRUN 0100\rR\rDIR\rEXIT\r"
            f"D0210-0210\rD{SWI_DATA_ADDR:04X}-{SWI_DATA_ADDR:04X}\r\r",
            sd_image=_wboot_sd_image(config),
        )
        out = raw.replace("\r", "")
        # 1. 健全な戻り: HELLO.COM の出力からプロンプトまで SD を読まない
        start, stop = _segment(raw, PROMPT + "HELLO.COM")
        done = raw.index("HELLO COM", start) + len("HELLO COM")
        assert _reads(log, start, done), f"{profile}: HELLO.COM should be read from FAT"
        assert _reads(log, start, done, system_only=True) == []
        assert _reads(log, done, stop) == [], f"{profile}: healthy return must not touch SD"
        # 2. CCP が潰れた: CCP のセクタだけを、何も出さずに読み直す
        start, stop = _segment(raw, PROMPT + "ZAPCCP.COM")
        assert raw[start:stop] == "\r\n", f"{profile}: reload must be silent: {raw[start:stop]!r}"
        reads = _reads(log, start, stop, system_only=True)
        assert reads == sectors["ccp"], f"{profile}: CCP reload read {reads}, want {sectors['ccp']}"
        assert "README.TXT" in _dos(out, "DIR")
        # 3. 核が壊れた: 先頭セクタ(ヘッダの照合)と核のセクタだけ
        start, stop = _segment(raw, PROMPT + "ZAPCORE.COM")
        assert raw[start:stop] == "\r\n", f"{profile}: core reload must be silent: {raw[start:stop]!r}"
        reads = _reads(log, start, stop, system_only=True)
        assert reads == sectors["core"], f"{profile}: core reload read {reads}, want {sectors['core']}"
        before = out[: out.index("LOAD SWI.S")]
        assert before.count("README.TXT A 00000013") == 2, f"{profile}: DIR after reloads: {before[-900:]!r}"
        # 5. SWI(B で置いたブレークポイント): 注意を 1 行出すが読み直さない。R のあとの RTS で
        #    WBOOT に着き、CCP を読み直す
        start, stop = _segment(raw, PROMPT + "RUN 0100", end="] R\r\n")
        brk = raw[start:stop].replace("\r", "")
        assert re.search(r"\nBRK 0105 A=5A [^\n]*\n\*SDFS3 CCP\n$", brk), f"{profile}: SWI: {brk!r}"
        assert _reads(log, raw.index("BRK 0105", start), stop) == [], f"{profile}: SWI must not reload"
        start, stop = _segment(raw, "] R\r\n")
        assert raw[start:stop] == "", f"{profile}: resume and reload must be silent: {raw[start:stop]!r}"
        reads = _reads(log, start, stop)
        assert reads == sectors["ccp"], f"{profile}: reload after R read {reads}"
        assert _dump_bytes(_after(out, "] D0210-0210\n"), 0x0210) == [0x5A], (
            f"{profile}: the resumed program must see its data in the CCP area"
        )
        assert out.count("README.TXT A 00000013") == 3, f"{profile}: DIR after the resumed program"
        restored = _dump_bytes(_after(out, f"] D{SWI_DATA_ADDR:04X}-{SWI_DATA_ADDR:04X}\n"), SWI_DATA_ADDR)
        assert restored == [swi_orig], f"{profile}: CCP should be reloaded after the program ended"
        assert out.count(WELCOME) == 1, f"{profile}: reloads must not print Welcome"
        assert out.count("*SDFS3") == 1, f"{profile}: only the SWI stop should warn: {out!r}"
        assert "\n?\n" not in out, f"{profile}: no command should fail: {out[-900:]!r}"
    print("[PASS] test_wboot_reloads_only_broken_parts")


def test_wboot_reload_fails_without_card_or_after_swap() -> None:
    """CCP が壊れた状態で SD が読めない(抜いた)とき、カードが別の版に替わったときは、
    読み直しをやめて「?」でモニタへ。区画は無効になり、DOS も「?」。差し替えでは RAM に
    書かない(シナリオ 6・7)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        payload = config["sdfs3sys"][HEADER_SIZE:]
        sd_image = _wboot_sd_image(config)
        core_dump = f"D{V3_CORE_BASE:04X}-{V3_CORE_BASE + 15:04X}"
        input_text = f"BOOT3\rHELLO.COM\rZAPCCP.COM\rDOS\rD{V3_CCP_BASE:04X}-{V3_CCP_BASE + 15:04X}\r{core_dump}\r\r"
        raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image)
        start, _stop = _segment(raw, PROMPT + "ZAPCCP.COM")
        first_reload = next(n for n, lba, _r1, tx in log if tx >= start and lba == SDFS3SYS_FIXED_LBA)

        swapped = bytearray(config["sdfs3sys"])
        swapped[HEADER_SIZE + 0x0200] ^= 0x01
        _refresh_checksum(swapped)
        assert swapped[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] != config["sdfs3sys"][CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2]
        swap_image = bytearray(sd_image)
        base = SDFS3SYS_FIXED_LBA * SECTOR_SIZE
        swap_image[base : base + len(swapped)] = swapped

        for label, kwargs in (
            ("no card", {"fail_from": first_reload}),
            ("swapped", {"swap_image": bytes(swap_image), "swap_at": first_reload}),
        ):
            raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image, **kwargs)
            out = raw.replace("\r", "")
            assert f"{PROMPT}ZAPCCP.COM\n?\n] DOS\n?\n] " in out, f"{profile} {label}: {out[-600:]!r}"
            late = [(lba, r1) for n, lba, r1, _tx in log if n >= first_reload]
            if label == "no card":
                assert late and late[0] == (SDFS3SYS_FIXED_LBA, 0x04), f"{profile}: {late}"
            else:
                assert late == [(SDFS3SYS_FIXED_LBA, 0x00)], f"{profile}: swapped card should stop at the header: {late}"
            ccp = _dump_range_bytes(_after(out, f"] D{V3_CCP_BASE:04X}"), V3_CCP_BASE, 16)
            assert ccp == [0] * 16, f"{profile} {label}: RAM must not be written: {ccp}"
            core = _dump_range_bytes(_after(out, f"] {core_dump}\n"), V3_CORE_BASE, 16)
            assert bytes(core) == payload[V3_CORE_OFFSET : V3_CORE_OFFSET + 16], f"{profile} {label}: core changed"
    print("[PASS] test_wboot_reload_fails_without_card_or_after_swap")


def test_monitor_gate_warns_and_dos_after_reset_and_ramtest() -> None:
    """モニタ行きの門($E20D・G の RTS)は検査して STATE に記録し、注意を 1 行出すが読み直さない。
    リセットと RAMTEST のあとの DOS は読み直さずに入り、F で CCP と核を潰したあとの DOS は
    両方を読み直す(シナリオ 4・8・11)。リセットは G でリセットの番地へ飛んで代える。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        block = symbols["BIOS_BLOCK"]
        sectors = _system_sectors(config)
        payload = config["sdfs3sys"][HEADER_SIZE:]
        ccp_addr, core_addr = V3_CCP_BASE + 0x10, V3_CORE_BASE + 0x100
        ccp_orig, core_orig = payload[ccp_addr - V3_CCP_BASE], payload[core_addr - V3_CCP_BASE]
        dump_block = f"D{block:04X}-{block + BB_SIZE - 1:04X}"

        def poke(address: int, value: int) -> str:
            return f"M{address:04X}\r{value:02X}\r.\r"

        raw, log, _ = _v3_run_sd(
            config,
            "BOOT3\rEXIT\rM0180\r39\r.\r"
            + poke(ccp_addr, ccp_orig ^ 0x01)
            + f"GE20D\r{dump_block}\r"
            + poke(core_addr, core_orig ^ 0x80)
            + f"G0180\r{dump_block}\r"
            + poke(ccp_addr, ccp_orig)
            + poke(core_addr, core_orig)
            + f"G0180\r{dump_block}\r"
            + f"G{_reset_address(config):04X}\rDOS\rEXIT\rRAMTEST 0100-7FFF\rDOS\rEXIT\r"
            + "F0100-7FFF 00\rDOS\rDIR\r\r",
            sd_image=_wboot_sd_image(config),
        )
        out = raw.replace("\r", "")
        gates = out.split(f"] {dump_block}\n")
        assert len(gates) == 4, f"{profile}: {out[-900:]!r}"
        assert gates[0].endswith("] GE20D\n*SDFS3 CCP\n"), f"{profile}: $E20D gate: {gates[0][-200:]!r}"
        assert gates[1].endswith("] G0180\n*SDFS3 CCP CORE\n"), f"{profile}: G RTS gate: {gates[1][-200:]!r}"
        assert gates[2].endswith("] G0180\n"), f"{profile}: healthy gate must be quiet: {gates[2][-200:]!r}"
        for index, want_state in ((1, 0x01), (2, 0x03), (3, 0x00)):
            data = _dump_range_bytes(gates[index], block, BB_SIZE)
            assert data[0x12] == want_state, f"{profile}: STATE after gate {index}: {data[0x12]:02X}"
            assert sum(data[: BB_CHECK_OFFSET + 1]) & 0xFF == 0, f"{profile}: CHECK not refreshed"
            assert data[0] == 0xB3, f"{profile}: the gate must keep the block valid"
        # モニタ行きの門は読み直さない
        start = raw.index("] GE20D")
        stop = raw.index("] G" + f"{_reset_address(config):04X}")
        assert _reads(log, start, stop) == [], f"{profile}: monitor gates must not read SD"
        # 8. リセットのあと: 読み直しなしで DOS に入る
        assert out.count("MC6800 MONITOR") == 2, f"{profile}: reset did not restart the monitor"
        start, stop = _segment(raw, "] DOS")
        assert raw[start:stop] == "\r\n" and _reads(log, start, stop) == [], (
            f"{profile}: DOS after reset should enter without reload: {raw[start:stop]!r}"
        )
        # 4. RAMTEST は 1 バイトごとに元の値を書き戻すので、正常な RAM では読み直さずに入る。
        #    F で CCP と核を潰したあとは、両方を読み直す(先頭セクタは 1 回)
        assert "] RAMTEST 0100-7FFF\nRAMTEST 0100-7FFF\nOK\n" in out, f"{profile}: {out[-700:]!r}"
        start, stop = _segment(raw, "] DOS", nth=1)
        assert raw[start:stop] == "\r\n" and _reads(log, start, stop) == [], f"{profile}: DOS after RAMTEST"
        start, stop = _segment(raw, "] DOS", nth=2)
        assert raw[start:stop] == "\r\n", f"{profile}: reload after F must be silent"
        reads = _reads(log, start, stop)
        assert reads == sectors["all"], f"{profile}: reload after F read {reads}"
        assert "README.TXT A 00000013" in _dos(out, "DIR")
        assert out.count(WELCOME) == 1
    print("[PASS] test_monitor_gate_warns_and_dos_after_reset_and_ramtest")


def test_v2_boot_exit_returns_to_monitor_and_disables_dos() -> None:
    """v3 のあとに v2 を起動すると、v2 の EXIT($E20D)は今までどおりモニタに戻り、注意は出ない。
    区画は無効なので DOS は「?」(シナリオ 9)。"""
    from mk_sdfs_image import build_sdfs_image

    for profile in V3_PROFILES:
        config = _v3(profile)
        suffix = config["suffix"]
        block = config["symbols"]["BIOS_BLOCK"]
        _run_make(profile, "stage1")
        _run_make(profile, "sdfs")
        stage1 = (PROJECT_ROOT / "build" / f"stage1{suffix}.bin").read_bytes()
        image = bytearray(
            build_sdfs_image(
                stage1_data=stage1,
                sdfs_data=(PROJECT_ROOT / "build" / f"SDFS{suffix}.BIN").read_bytes(),
                extra_files=[],
                partition_start_lba=SDFS3SYS_FAT_PARTITION_LBA,
                total_volume_sectors=256,
            )
        )
        stage1_end = 16 + -(-len(stage1) // SECTOR_SIZE)
        system_end = SDFS3SYS_FIXED_LBA + -(-len(config["sdfs3sys"]) // SECTOR_SIZE)
        assert stage1_end <= SDFS3SYS_FIXED_LBA and system_end <= SDFS3SYS_FAT_PARTITION_LBA
        base = SDFS3SYS_FIXED_LBA * SECTOR_SIZE
        assert not any(image[base : system_end * SECTOR_SIZE]), "SDFS3SYS slot must be free in the v2 image"
        image[base : base + len(config["sdfs3sys"])] = config["sdfs3sys"]
        raw, _log, _ = _v3_run_sd(
            config,
            f"BOOT3\rEXIT\rBOOT\rEXIT\rDOS\rD{block:04X}-{block + 1:04X}\r\r",
            sd_image=bytes(image),
            dump_range=f"{block:04X}-{block + 1:04X}",
        )
        out = raw.replace("\r", "")
        assert "SDFS> EXIT\n] DOS\n?\n] " in out, f"{profile}: v2 EXIT / DOS: {out[-600:]!r}"
        assert "*SDFS3" not in out, f"{profile}: v2 mode must not warn"
        assert _dump_bytes(_after(out, f"] D{block:04X}"), block)[0] == 0, f"{profile}: BOOT must clear BB_MAGIC"
    print("[PASS] test_v2_boot_exit_returns_to_monitor_and_disables_dos")


def test_monitor_stack_fits_in_128_bytes() -> None:
    """決定 16: モニタ(SWI で止めたあとを含む)が使うスタックが W+$1F80-$1FFF の 128B に収まる。
    DOS(CCP・核)はプログラムが止まっていないときだけ動くので、数字は別に出すだけ。"""
    results = []
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        block = symbols["BIOS_BLOCK"]
        stack_top = block - 0x0300 + 0x1FFF
        floor = stack_top - 0x7F
        header = config["sdfs3sys"][:HEADER_SIZE]
        # 形と和が正しい偽の区画($5000-$5FFF は 0 の RAM)。+$18 は本物と同じにして、
        # DOS の読み直しで SD_INIT・ヘッダ・範囲の読み込みまで通す(和が合わずに「?」で終わる)
        fake = _bb_block(img_base=0x5000, core_base=0x5800, img_last=0x5FFF, ccp_vec=0x5000)
        fake[0x08:0x0C] = bytes(4)
        fake[0x10:0x12] = header[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2]
        fake[BB_CHECK_OFFSET] = (-sum(fake[:BB_CHECK_OFFSET])) & 0xFF
        srec = _srec_file(0x0200, b"STACK").decode("ascii").replace("\r\n", "\r")
        # $0180: lds #$3FFF / nop / jmp $E20D。プログラムのスタックを窓の外に置き、モニタだけを測る。
        # $0183 の NOP に B で SWI を置いて止め、止めたままモニタのコマンドを打ってから R で再開する
        prog = bytes([0x8E, 0x3F, 0xFF, 0x01, 0x7E, 0xE2, 0x0D])
        monitor_cmds = (
            f"M{block:04X}\r{_hex_bytes(fake)}\r.\r"
            f"M0180\r{_hex_bytes(prog)}\r.\r"
            "M5000\r01\r.\r"
            "GE20D\r"
            "B0183\rG0180\r"
            "H\rD0100-013F\rD\rDS0100\rU0180\rMAP\rB\rUW\rF0300-030F AA\r"
            "RAMTEST 0300-03FF\r" + f"L\r{srec}"
            "R\r"
            "DOS\r"
            "M5000\r00\r.\r"
            "B0183\rG0180\rH\rD0100\rR\rB0190\rC\r\r"
        )
        _raw, _log, stderr = _v3_run_sd(
            config, monitor_cmds, sd_image=_wboot_sd_image(config), stack_watch=floor
        )
        out = _raw.replace("\r", "")
        assert out.count("BRK 0183") == 2 and "] DOS\n?\n" in out, f"{profile}: {out[-900:]!r}"
        assert out.count("*SDFS3 CCP") == 3, f"{profile}: $E20D, BRK and the resumed jmp $E20D should warn"
        match = re.search(r"\[EMU\] stack-watch rom_min=(\S+) ram_min=(\S+)", stderr)
        assert match and match.group(2) == "none", f"{profile}: {stderr[-300:]!r}"
        monitor_min = int(match.group(1)[1:], 16)
        _raw, _log, stderr = _v3_run_sd(
            config,
            "BOOT3\rDIR\rTYPE README.TXT\rHELLO.COM\rZAPCCP.COM\rZAPCORE.COM\rEXIT\rDOS\rDIR\r\r",
            sd_image=_wboot_sd_image(config),
            stack_watch=floor,
        )
        match = re.search(r"\[EMU\] stack-watch rom_min=(\S+) ram_min=(\S+)", stderr)
        assert match, f"{profile}: {stderr[-300:]!r}"
        dos_min = min(int(v[1:], 16) for v in match.groups() if v != "none")
        assert monitor_min >= floor, f"{profile}: monitor stack reaches {monitor_min:04X} (< {floor:04X})"
        results.append(
            f"{profile}: モニタ {stack_top - monitor_min + 1}B(最小 SP ${monitor_min:04X})、"
            f"DOS を含む {stack_top - dos_min + 1}B(最小 SP ${dos_min:04X})"
        )
    print("[PASS] test_monitor_stack_fits_in_128_bytes: " + " / ".join(results))


def test_dos_gate_rejects_unloaded_block_without_writing() -> None:
    """未ロード(区画が 0 またはゴミ)の DOS は「?」になり、区画にも CCP の場所にも書かない。
    v2 の BOOT は区画を無効にするので、BOOT3 のあとに BOOT すると DOS は「?」になる。"""
    config = _v3("sbcio_vdg")
    symbols = config["symbols"]
    block = symbols["BIOS_BLOCK"]
    sd_image = _build_sdfs3sys_sd_image(config["sdfs3sys"])
    marker = bytes(range(0xA0, 0xB0))
    seed = 0x313
    garbage = bytearray()
    for _ in range(BB_SIZE):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        garbage.append((seed >> 16) & 0xFF)
    # 形は正しい(MAGIC・CHECK・範囲が通る)が、和が RAM と合わない区画
    shaped = _bb_block(img_base=V3_CCP_BASE, core_base=V3_CORE_BASE, img_last=0x7C00, ccp_vec=V3_CCP_BASE)
    for label, block_data in (("zero", None), ("garbage", bytes(garbage)), ("bad sums", bytes(shaped))):
        prefix = "" if block_data is None else f"M{block:04X}\r{_hex_bytes(block_data)}\r.\r"
        out = _v3_run(
            config,
            prefix
            + f"M{V3_CCP_BASE:04X}\r{_hex_bytes(marker)}\r.\rDOS\r"
            + f"D{V3_CCP_BASE:04X}-{V3_CCP_BASE + 15:04X}\r\r",
            sd_image=sd_image,
            dump_range=f"{block:04X}-{block + BB_SIZE - 1:04X}",
            max_cycles=100_000_000,
            timeout=40,
        )
        assert "] DOS\n?\n] " in out, f"{label}: DOS without a valid block should fail: {out[-300:]!r}"
        assert PROMPT not in out
        assert bytes(_dump_range_bytes(_after(out, "] DOS\n"), V3_CCP_BASE, 16)) == marker, (
            f"{label}: DOS must not write the CCP area"
        )
        final = bytes(_dump_range_bytes(_final_dump(out, block), block, BB_SIZE))
        want = bytes(BB_SIZE) if block_data is None else block_data
        if label != "bad sums":
            assert final == want, f"{label}: DOS must not write the block: {final.hex()}"
        else:
            # 形の正しい区画は検査に通るので、STATE(両方の不一致)を記録して読み直しに進み、
            # SD のヘッダ +$18 が IMG_SUM と違う(カードが替わった扱い)ので MAGIC を消して「?」
            header_sum = config["sdfs3sys"][CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2]
            assert want[0x10:0x12] != header_sum
            assert final[0] == 0 and final[1:0x12] == want[1:0x12] and final[0x12] == 0x03, (
                f"{label}: DOS should record STATE and clear MAGIC: {final.hex()}"
            )
    out = _v3_run(
        config,
        f"M{V3_CCP_BASE:04X}\r{_hex_bytes(marker)}\r.\rDOS\rD{V3_CCP_BASE:04X}-{V3_CCP_BASE + 15:04X}\r\r",
        sd_image=sd_image,
        max_cycles=100_000_000,
        timeout=40,
    )
    assert bytes(_dump_range_bytes(_after(out, "] DOS\n"), V3_CCP_BASE, 16)) == marker, (
        "DOS without a valid block must not touch the CCP area"
    )
    out = _v3_run(
        config,
        "BOOT3\rEXIT\rDOS\rEXIT\rBOOT\rDOS\r\r",
        sd_image=sd_image,
        dump_range=f"{block:04X}-{block + 1:04X}",
        max_cycles=400_000_000,
        timeout=90,
    )
    dos = out.split("] DOS\n")[1:]
    assert len(dos) == 2 and dos[0].startswith(PROMPT), f"DOS after BOOT3 should work: {out[-600:]!r}"
    assert dos[1].startswith("?\n"), f"v2 BOOT should invalidate the v3 block: {dos[1][:80]!r}"
    # clr BB_MAGIC は上位バイトだけ消す。それで MAGIC が合わなくなり、区画は無効になる
    assert _dump_bytes(_final_dump(out, block), block)[0] == 0, "BB_MAGIC should be cleared by BOOT"
    print("[PASS] test_dos_gate_rejects_unloaded_block_without_writing")


def test_rom_boot3_rejects_bad_images() -> None:
    """古い resident(major 1)や壊れたヘッダは BOOT3 が「?」で弾き、区画は無効のまま。暴走しない。"""
    config = _v3("k6802_vdg")
    symbols = config["symbols"]
    good = config["sdfs3sys"]

    def patched(mutate) -> bytes:
        data = bytearray(good)
        mutate(data)
        _refresh_checksum(data)
        return bytes(data)

    def put16(offset: int, value: int):
        return lambda data: data.__setitem__(slice(offset, offset + 2), bytes([value >> 8, value & 0xFF]))

    old_payload = bytes(
        [*b"SDFS3API", 0x01, 0x01, 0x0E, 0x00, 0x50, 0x18, 0x50, 0x00, 0x50, 0x3F, 0x3F, 0xFF, 0, 0, 0, 0]
    ) + bytes([0x39] * 40)
    old_v1 = build_sdfs3sys_image(
        resident_data=old_payload,
        load_address=0x5000,
        load_limit=0x7EFF,
        entry_address=0x5000,
        api_table_address=0x5018,
    )
    core = HEADER_SIZE + V3_CORE_OFFSET
    bad_magic = bytearray(good)
    bad_magic[0] = ord("X")
    bad_sum = bytearray(good)
    bad_sum[-1] ^= 0x01
    cases = [
        ("old resident (major 1, load $5000)", old_v1),
        ("header major 1", patched(lambda data: data.__setitem__(0x09, 0x01))),
        ("api major 1", patched(lambda data: data.__setitem__(core + 8, 0x01))),
        ("api signature", patched(lambda data: data.__setitem__(core, ord("X")))),
        ("load below RAM floor", patched(put16(0x0C, 0x3F00))),
        ("image beyond USER_RAM_END", patched(put16(0x0C, 0x6C00))),
        ("api offset outside image", patched(put16(0x12, 0x2000))),
        ("entry table outside CCP", patched(put16(0x10, V3_CORE_OFFSET))),
        ("bad magic", bytes(bad_magic)),
        ("bad checksum", bytes(bad_sum)),
    ]
    block = symbols["BIOS_BLOCK"]
    for label, image in cases:
        out = _v3_run(
            config,
            "BOOT3\rDOS\r\r",
            sd_image=_build_sdfs3sys_sd_image(image),
            dump_range=f"{block:04X}-{block + 1:04X}",
            max_cycles=300_000_000,
            timeout=60,
        )
        assert "] BOOT3\n?\n] DOS\n?\n] " in out, f"{label}: BOOT3 and DOS should both fail: {out[-400:]!r}"
        assert PROMPT not in out and WELCOME not in out, f"{label}: resident must not run: {out[-400:]!r}"
        assert _dump_bytes(_final_dump(out, block), block)[0] == 0, f"{label}: BB_MAGIC should be cleared"
    print("[PASS] test_rom_boot3_rejects_bad_images")


def test_sdfs3_mutable_vars_live_outside_image() -> None:
    """#311: 書き換わる変数は窓の resident ワーク(W+$0320)にあり、イメージの外。"""
    for profile, suffix in V3_PROFILES.items():
        _run_make(profile, "sdfs3")
        lst = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
        names = (
            "SDFS3_WORK_BASE",
            "MIKBUG_VAR_BASE",
            "SDFS3_LAST_ERROR",
            "SDFS3_PARSE_PTR",
            "SDFS3_PARSE_LEN",
            "SDFS3_TOKEN_PTR",
            "SDFS3_TOKEN_LEN",
            "SDFS3_PENDING_ERR",
            "SDFS3_EXEC_BLOCK",
            "SDFS3_CCP_BASE",
            "SDFS3_END",
        )
        symbols = _load_symbols(lst, *names)
        work = symbols["SDFS3_WORK_BASE"]
        assert work == symbols["MIKBUG_VAR_BASE"] + 0x20, f"{profile}: WORK_BASE != W+$0320"
        offsets = {
            "SDFS3_LAST_ERROR": 0,
            "SDFS3_PARSE_PTR": 1,
            "SDFS3_PARSE_LEN": 3,
            "SDFS3_TOKEN_PTR": 4,
            "SDFS3_TOKEN_LEN": 6,
            "SDFS3_PENDING_ERR": 7,
            "SDFS3_EXEC_BLOCK": 8,
        }
        for name, offset in offsets.items():
            assert symbols[name] == work + offset, f"{profile}: {name}"
            assert not (symbols["SDFS3_CCP_BASE"] <= symbols[name] < symbols["SDFS3_END"]), (
                f"{profile}: {name} is inside the resident image"
            )
    print("[PASS] test_sdfs3_mutable_vars_live_outside_image")


def test_sdfs3_core_does_not_reference_ccp() -> None:
    """#311/#313: 核(API ヘッダとジャンプテーブルを含む)から CCP への参照が 0 件。
    わざと足すと検査が失敗する。"""
    import lst_analyze

    profile, suffix = "sbcio_vdg", V3_PROFILES["sbcio_vdg"]
    lst = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
    original_source = PROJECT_ROOT / "src" / "sdfs68_v3" / "resident_stub.asm"
    try:
        _run_make(profile, "sdfs3")
        violations, info = lst_analyze.check_core_ccp_refs(lst)
        assert info["ccp"] < info["ccp_end"] <= info["core"] < info["end"], f"bad boundary order: {info}"
        assert info["core"] == V3_CORE_BASE and info["ccp"] == V3_CCP_BASE, f"unexpected layout: {info}"
        assert info["scanned"] > 500, f"core range looks empty (vacuous check): {info}"
        assert violations == [], f"core references CCP: {violations}"
        assert info["last_ccp_insn"].split()[0] in ("rts", "jmp", "bra", "rti"), (
            f"CCP may fall through into the gap: {info['last_ccp_insn']!r}"
        )
        assert lst_analyze.check_core_ccp_main(lst) == 0

        # 負の対照: 核の先頭の近く(INIT の頭)と、ジャンプテーブルの slot 1 に CCP への参照を足す
        text = original_source.read_text(encoding="utf-8")
        anchor = "SDFS3_INIT:\n"
        slot1 = "        fdb     SDFS3_GET_INFO\n        fdb     SDFS3_NOT_IMPLEMENTED\n"
        assert anchor in text and slot1 in text
        mutations = {
            "jmp": text.replace(anchor, anchor + "        jmp     SDFS3_CMD_DIR\n", 1),
            "ldx": text.replace(anchor, anchor + "        ldx     #SDFS3_CMD_DIR\n", 1),
            "fdb": text.replace(anchor, anchor + "        fdb     SDFS3_CMD_DIR\n", 1),
            "slot1": text.replace(slot1, "        fdb     SDFS3_GET_INFO\n        fdb     SDFS3_CMD_DIR\n", 1),
        }
        with _temporary_directory() as tmp:
            for kind, mutated_text in mutations.items():
                mutated = Path(tmp) / f"mutated_{kind}.asm"
                mutated.write_text(mutated_text, encoding="utf-8")
                _run_make(profile, "sdfs3", extra_args=[f"SDFS3_TOPSRC={mutated}"])
                violations, _ = lst_analyze.check_core_ccp_refs(lst)
                assert [v[3] for v in violations] == ["SDFS3_CMD_DIR"], (
                    f"{kind}: deliberate core->CCP reference was not detected: {violations}"
                )
                assert lst_analyze.check_core_ccp_main(lst) == 1, f"{kind}: check CLI should fail"
    finally:
        _run_make(profile, "sdfs3")  # 通常ビルドに戻す
    print("[PASS] test_sdfs3_core_does_not_reference_ccp")


def _get_error_harness_input(get_error: int) -> str:
    # jsr GET_ERROR ; staa $0200 ; swi
    code = bytes([0xBD, get_error >> 8, get_error & 0xFF, 0xB7, 0x02, 0x00, 0x3F])
    return f"M0300\r{_hex_bytes(code)}\r.\rG0300\rD0200-0200\r"


def test_sdfs3_resident_image_unchanged_after_commands() -> None:
    """#311: コマンドを実行してもイメージの範囲の RAM が SDFS3SYS のペイロードと一致する。"""
    config = _v3("k6802_vdg")
    symbols = config["symbols"]
    payload = config["sdfs3sys"][HEADER_SIZE:]
    base, end = symbols["SDFS3_CCP_BASE"], symbols["SDFS3_END"]
    assert len(payload) == end - base
    sd_image = _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            _file("HELLO.S", _srec_file(0x0200, b"S")),
            _file("README.TXT", b"HELLO FROM README\r\n"),
            _file("HELLO.COM", config["hello_com"]),
        ],
    )
    last_error = symbols["SDFS3_LAST_ERROR"]
    out = _v3_run(
        config,
        "BOOT3\r"
        "DIR\r"
        "TYPE README.TXT\r"
        "LOAD HELLO.S\r"
        "HELLO.COM\r"
        "NOFILE.COM\r"
        "EXIT\r"
        "DOS\r"
        "EXIT\r"
        f"D{last_error:04X}-{last_error:04X}\r"
        + _get_error_harness_input(symbols["SDFS3_GET_ERROR"])
        + "\r",
        sd_image=sd_image,
        dump_range=f"{base:04X}-{end - 1:04X}",
    )
    assert "HELLO.S A " in _dos(out, "DIR")
    assert "HELLO COM" in _dos(out, "HELLO.COM")
    assert _dos(out, "NOFILE.COM") == "?\n"
    assert out.count("\n?\n") == 1, f"NOFILE.COM should fail exactly once: {out!r}"
    assert f"] DOS\n{PROMPT}EXIT" in out, "DOS gate should accept the image after the commands"
    image = bytes(_dump_range_bytes(_final_dump(out, base), base, end - base))
    assert image == payload, "resident image in RAM changed after running commands"
    last_failure = symbols["SDFS3_ERR_COM"]
    assert _dump_bytes(_after(out, f"] D{last_error:04X}"), last_error)[0] == last_failure, (
        f"LAST_ERROR should hold the last failure: {out[-600:]!r}"
    )
    assert _dump_bytes(_after(out, "G0300"), 0x0200)[0] == last_failure, "GET_ERROR mismatch"
    print("[PASS] test_sdfs3_resident_image_unchanged_after_commands")


def test_sdfs3_init_clears_errors_and_warm_shows_pending() -> None:
    """#311/#313: CCP の cold が呼ぶ INIT は LAST_ERROR と PENDING_ERR を 0 にする(何も出さない)。
    warm は PENDING_ERR が立っていれば「?」を出して消す。"""
    config = _v3("k6802_vdg")
    symbols = config["symbols"]
    last_error, pending = symbols["SDFS3_LAST_ERROR"], symbols["SDFS3_PENDING_ERR"]
    out = _v3_run(
        config,
        f"M{last_error:04X}\rFF\r.\r"
        f"M{pending:04X}\rFF\r.\r"
        "BOOT3\r"
        "EXIT\r"
        + _get_error_harness_input(symbols["SDFS3_GET_ERROR"])
        + f"D{pending:04X}-{pending:04X}\r"
        + f"M{pending:04X}\r01\r.\r"
        + "DOS\r"
        + "EXIT\r"
        + f"D{pending:04X}-{pending:04X}\r"
        + "\r",
        sd_image=_build_sdfs3sys_sd_image(config["sdfs3sys"]),
        max_cycles=400_000_000,
        timeout=90,
    )
    end = symbols["SDFS3_END"] - 1
    assert f"] BOOT3\n{WELCOME}\nBASE=6400 END={end:04X}\n{PROMPT}EXIT\n" in out, (
        f"cold entry should not show the pending error: {out[:600]!r}"
    )
    assert _dump_bytes(_after(out, "G0300"), 0x0200)[0] == 0, "GET_ERROR after BOOT3 should be 0"
    assert _dump_bytes(_after(out, f"] D{pending:04X}"), pending)[0] == 0, "INIT should clear PENDING_ERR"
    assert f"] DOS\n?\n{PROMPT}EXIT\n" in out, f"warm entry should show the pending error once: {out!r}"
    last = out.rindex(f"] D{pending:04X}")
    assert _dump_bytes(out[last:], pending)[0] == 0, "warm entry should clear PENDING_ERR"
    print("[PASS] test_sdfs3_init_clears_errors_and_warm_shows_pending")


def test_sdfs3_rejects_base_profile() -> None:
    result = _run_make("base", "sdfs3", expect_success=False)
    assert result.returncode != 0
    assert "FEATURE_SD=1" in result.stdout or "FEATURE_SD=1" in result.stderr
    print("[PASS] test_sdfs3_rejects_base_profile")


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


# ---------------------------------------------------------------------------
# #312: BIOS 入口表・RAM の和・BIOS 区画(#313 で GET_API と自己検査を変えた)
# ---------------------------------------------------------------------------

BIOS_PROFILES = {
    "sbcio_vdg": "-sbcio-vdg",
    "k6802_vdg": "-k6802-vdg",
}
BIOS_ENTRY_TARGETS = [
    ("BIOS_WBOOT", 0xE0E6, "BIOS_WBOOT_IMPL"),
    ("BIOS_INFO", 0xE0E9, "BIOS_INFO_IMPL"),
    ("BIOS_GET_API", 0xE0EC, "BIOS_GET_API_IMPL"),
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
            "MON_GATE",
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
        gate = symbols["MON_GATE"]
        assert read(0xE20D, 3) == bytes([0x7E, gate >> 8, gate & 0xFF]), (
            f"{profile}: $E20D should be jmp MON_GATE (#314)"
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
        # #313: 仕様 1-3 どおり IMG_BASE < CORE_BASE、CCP_VEC < CORE_BASE に戻した。
        # #312 で C=0 だった core=img の 2 件は C=1 に変わる
        ("core_equals_img", bytes(_bb_block(img_base=0x4000, core_base=0x4000, img_last=0x7FFF, ccp_vec=0x4000)), 1),
        ("core_equals_img_312_layout", bytes(_bb_block(core_base=0x5000, ccp_vec=0x5000)), 1),
        ("valid_min_ccp", bytes(_bb_block(img_base=0x4000, core_base=0x4001, img_last=0x7FFF, ccp_vec=0x4000)), 0),
        ("valid_plan_b", bytes(_bb_block(img_base=0x6C00, core_base=0x7000, img_last=0x7FFF, ccp_vec=0x6C00)), 0),
        ("valid_313_layout", bytes(_bb_block(img_base=0x6400, core_base=0x7000, img_last=0x7C3E, ccp_vec=0x6400)), 0),
        ("ccp_just_below_core", bytes(_bb_block(ccp_vec=0x57FF)), 0),
        ("ccp_equals_core", bytes(_bb_block(ccp_vec=0x5800)), 1),
        ("core_equals_last", bytes(_bb_block(core_base=0x5FFF)), 0),
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
    """BOOT3 が区画に CCP と核の和を 2 本書き、自己検査と BIOS_GET_API が通る(#313 で 2 本に分けた)。"""
    config = _v3("k6802_vdg")
    suffix = config["suffix"]
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.lst",
        "BB_CHECK_VALID",
        "BIOS_RAM_SUM",
        "BIOS_GET_API",
        "BIOS_BLOCK",
        "BB_STATE",
        "BB_WORK",
    )
    end = config["symbols"]["SDFS3_END"]
    header = parse_sdfs3sys_header(config["sdfs3sys"])
    payload = config["sdfs3sys"][HEADER_SIZE:]
    sum_ccp = sum(payload[:V3_CORE_OFFSET]) & 0xFFFF
    sum_core = sum(payload[V3_CORE_OFFSET:]) & 0xFFFF
    source = "\n".join(
        [
            "        cpu     6800",
            *_equ_lines(symbols),
            f"        org     ${BIOS_HARNESS_ADDR:04X}",
            "        clc",
            "        jsr     BB_CHECK_VALID",
            "        tpa",
            "        anda    #1",
            "        staa    $0200",
            f"        ldx     #${V3_CORE_BASE:04X}",
            "        stx     BB_WORK",
            f"        ldx     #${V3_CCP_BASE:04X}",
            "        jsr     BIOS_RAM_SUM",
            "        staa    $0201",
            "        stab    $0202",
            f"        ldx     #${end:04X}",
            "        stx     BB_WORK",
            f"        ldx     #${V3_CORE_BASE:04X}",
            "        jsr     BIOS_RAM_SUM",
            "        staa    $0203",
            "        stab    $0204",
            "        jsr     BIOS_GET_API",
            "        stx     $0205",
            "        tpa",
            "        anda    #1",
            "        staa    $0207",
            "        swi",
            f"        org     ${BIOS_HARNESS2_ADDR:04X}",
            "        clc",
            "        jsr     BB_CHECK_VALID",
            "        tpa",
            "        anda    #1",
            "        staa    $0210",
            "        jsr     BIOS_GET_API",
            "        tpa",
            "        anda    #1",
            "        staa    $0211",
            "        swi",
            "",
        ]
    )
    with _temporary_directory() as tmp:
        harness = _assemble_source(Path(tmp), "bios_boot3_block", source)
    block = symbols["BIOS_BLOCK"]
    out = _v3_run(
        config,
        "BOOT3\r"
        "EXIT\r"
        + _harness_input(harness)
        + f"G{BIOS_HARNESS_ADDR:04X}\r"
        + f"D{block:04X}-{block + BB_SIZE - 1:04X}\r"
        + f"M{symbols['BB_STATE']:04X}\r01\r.\r"
        + f"G{BIOS_HARNESS2_ADDR:04X}\r"
        + "\r",
        sd_image=_build_sdfs3sys_sd_image(config["sdfs3sys"]),
        max_cycles=400_000_000,
        timeout=90,
    )
    assert WELCOME in out and PROMPT + "EXIT" in out, f"BOOT3 should enter DOS: {out[:400]!r}"
    after_go = _after(out, f"G{BIOS_HARNESS_ADDR:04X}")
    bb = bytes(_dump_range_bytes(after_go, block, BB_SIZE))

    def word(offset: int) -> int:
        return bb[offset] << 8 | bb[offset + 1]

    assert bb[0:2] == b"\xB3\x4C", f"BB_MAGIC: {bb.hex()}"
    assert word(0x02) == V3_CCP_BASE, f"BB_IMG_BASE: {bb.hex()}"
    assert word(0x04) == V3_CORE_BASE, f"BB_CORE_BASE should be the SDFS3API header: {bb.hex()}"
    assert word(0x06) == end - 1 == V3_CCP_BASE + len(payload) - 1, f"BB_IMG_LAST: {bb.hex()}"
    assert word(0x08) == sum_ccp, f"BB_SUM_CCP {word(0x08):04X} != {sum_ccp:04X}"
    assert word(0x0A) == sum_core, f"BB_SUM_CORE {word(0x0A):04X} != {sum_core:04X}"
    assert word(0x0C) == V3_CCP_BASE + header.entry_offset, f"BB_CCP_VEC: {bb.hex()}"
    assert word(0x0E) == SDFS3SYS_FIXED_LBA, f"BB_SLOT_LBA: {bb.hex()}"
    assert word(0x10) == header.checksum, f"BB_IMG_SUM should copy header +$18: {bb.hex()}"
    assert bb[0x12] == 0, f"BB_STATE: {bb.hex()}"
    assert sum(bb[: BB_CHECK_OFFSET + 1]) & 0xFF == 0, f"BB_CHECK: {bb.hex()}"
    results = _dump_bytes(_final_dump(out, 0x0200), 0x0200)
    assert results[0] == 0, f"self-check should pass after BOOT3: {results!r}"
    assert (results[1] << 8 | results[2]) == sum_ccp, f"RAM CCP sum differs: {results!r}"
    assert (results[3] << 8 | results[4]) == sum_core, f"RAM core sum differs: {results!r}"
    assert (results[5] << 8 | results[6]) == V3_CORE_BASE and results[7] == 0, f"BIOS_GET_API: {results!r}"
    second = _dump_bytes(_final_dump(out, 0x0200), 0x0210)
    assert second[0] == 1, f"self-check should fail after changing one byte with M: {second!r}"
    assert second[1] == 1, f"BIOS_GET_API should report C=1 for an invalid block: {second!r}"
    print("[PASS] test_rom_boot3_writes_bios_block")


def _fixed_lba_symbols(config: dict) -> dict[str, int]:
    symbols = _load_symbols(
        PROJECT_ROOT / "build" / f"mc6800-monitor{config['suffix']}.lst",
        "SD_INIT",
        "SD_READ_SECTOR",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
    )
    symbols["LOAD_ADDR"] = V3_CCP_BASE
    symbols["CORE_ADDR"] = V3_CORE_BASE
    return symbols


def test_fixed_lba_loader_harness_loads_sdfs3sys() -> None:
    config = _v3("sbcio_vdg")
    symbols = _fixed_lba_symbols(config)
    sdfs3sys = config["sdfs3sys"]
    assert len(sdfs3sys) <= 16 * 1024, "SDFS3SYS harness keeps the phase 1 image under 16KB"
    payload = sdfs3sys[HEADER_SIZE:]
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)
    last = V3_CCP_BASE + len(payload) - 1
    stdout, stderr, rc = _run_emu(
        rom_path=config["rom"],
        input_text=(
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r"
            "D0200-0202\r"
            "\r"
        ),
        max_cycles=160_000_000,
        dump_range=f"0200-{last:04X}",
        sd_image=_build_sdfs3sys_sd_image(sdfs3sys),
        timeout=60,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for SDFS3SYS loader harness: rc={rc} stderr={stderr!r}"
    )
    status = _dump_bytes(stdout, 0x0200)
    assert status[0] == 0x42, f"SDFS3SYS loader should report success: {status!r}\nstdout={stdout[-600:]!r}"
    assert status[1:3] == [V3_CORE_BASE >> 8, V3_CORE_BASE & 0xFF], f"API header address: {status!r}"
    loaded = _dump_range_bytes(_final_dump(stdout, 0x0200), V3_CCP_BASE, len(payload))
    assert bytes(loaded) == payload, "resident payload was not fully loaded"
    print("[PASS] test_fixed_lba_loader_harness_loads_sdfs3sys")


def test_fixed_lba_loader_harness_rejects_bad_sdfs3sys() -> None:
    config = _v3("sbcio_vdg")
    symbols = _fixed_lba_symbols(config)
    image = config["sdfs3sys"]
    with _temporary_directory() as tmp:
        harness = _assemble_fixed_lba_loader_harness(Path(tmp), symbols)

    def break_api(data: bytearray) -> None:
        data[HEADER_SIZE + V3_CORE_OFFSET] = ord("X")
        _refresh_checksum(data)

    cases = [
        ("bad magic", lambda data: data.__setitem__(0, ord("X")), 0xE1),
        ("bad version", lambda data: data.__setitem__(0x08, 0x02), 0xE2),
        ("bad load address", lambda data: data.__setitem__(0x0C, 0x40), 0xE3),
        ("bad small size", lambda data: data.__setitem__(slice(0x0E, 0x10), b"\x00\x20"), 0xE4),
        ("bad oversize", lambda data: data.__setitem__(slice(0x0E, 0x10), b"\x40\x01"), 0xE4),
        ("bad checksum", lambda data: data.__setitem__(-1, data[-1] ^ 0x01), 0xE5),
        ("bad resident api", break_api, 0xE7),
    ]
    for label, mutate, expected_status in cases:
        bad_image = bytearray(image)
        mutate(bad_image)
        stdout, stderr, rc = _run_emu(
            rom_path=config["rom"],
            input_text=(
                f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
                f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\rD0200-0200\r\r"
            ),
            max_cycles=160_000_000,
            dump_range="0200-0200",
            sd_image=_build_sdfs3sys_sd_image(bytes(bad_image)),
            timeout=60,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, (
            f"emulator failed for {label}: rc={rc} stderr={stderr!r}"
        )
        status = _dump_bytes(stdout, 0x0200)
        assert status[0] == expected_status, f"{label} status mismatch: {status!r}"

    stdout, stderr, rc = _run_emu(
        rom_path=config["rom"],
        input_text=(
            f"M{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\r{_hex_bytes(harness)}\r.\r"
            f"G{SDFS3SYS_LOADER_HARNESS_ADDR:04X}\rD0200-0200\r\r"
        ),
        max_cycles=160_000_000,
        dump_range="0200-0200",
        sd_image=bytes(SECTOR_SIZE * SDFS3SYS_FIXED_LBA),
        timeout=60,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, (
        f"emulator failed for read failure: rc={rc} stderr={stderr!r}"
    )
    status = _dump_bytes(stdout, 0x0200)
    assert status[0] == 0xE6, f"SD read failure should be reported: {status!r}"
    print("[PASS] test_fixed_lba_loader_harness_rejects_bad_sdfs3sys")


def _word(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


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

    load_base_hi = (symbols["LOAD_ADDR"] >> 8) & 0xFF
    load_base_lo = symbols["LOAD_ADDR"] & 0xFF
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
CORE_ADDR       equ {equ("CORE_ADDR")}
SD_LBA0         equ {equ("SD_LBA0")}
SD_LBA1         equ {equ("SD_LBA1")}
SD_LBA2         equ {equ("SD_LBA2")}
SD_LBA3         equ {equ("SD_LBA3")}
SD_SECTOR_BUF   equ {equ("SD_SECTOR_BUF")}
LOAD_ADDR       equ {equ("LOAD_ADDR")}

START:
        jsr     SD_INIT
        bcs     FAIL_SD
        jsr     SET_FIXED_LBA
        jsr     READ_CURRENT_SECTOR
        bcs     FAIL_SD
        jsr     CHECK_HEADER
        bcs     FAIL
        jsr     COPY_PAYLOAD
        jsr     CHECK_API
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
        cmpa    #2
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
        ldx     #LOAD_ADDR
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

CHECK_API:
        ldx     #CORE_ADDR
        ldaa    0,x
        cmpa    #'S'
        bne     CHECK_API_FAIL
        ldaa    1,x
        cmpa    #'D'
        bne     CHECK_API_FAIL
        ldaa    2,x
        cmpa    #'F'
        bne     CHECK_API_FAIL
        ldaa    3,x
        cmpa    #'S'
        bne     CHECK_API_FAIL
        ldaa    4,x
        cmpa    #'3'
        bne     CHECK_API_FAIL
        ldaa    5,x
        cmpa    #'A'
        bne     CHECK_API_FAIL
        ldaa    6,x
        cmpa    #'P'
        bne     CHECK_API_FAIL
        ldaa    7,x
        cmpa    #'I'
        bne     CHECK_API_FAIL
        ldaa    8,x
        cmpa    #2
        bne     CHECK_API_FAIL
        clc
        rts
CHECK_API_FAIL:
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
    extra_args: list[str] | None = None,
    keep_cr: bool = False,
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
        if extra_args:
            cmd.extend(extra_args)
        if keep_cr:
            # 出力を 1 文字 = 送信 1 バイトのまま受け取る(text モードは \r\n を \n に変える)
            result_bytes = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, timeout=timeout)
            return (
                result_bytes.stdout.decode("latin-1"),
                result_bytes.stderr.decode("utf-8", errors="replace"),
                result_bytes.returncode,
            )
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
        test_sdfs3_rejects_4000_work_profiles,
        test_sdfs3_profiles_build_and_match_header,
        test_sdfs3_get_info_matches_calling_convention,
        test_sdfs3_memtop_and_caps_match_calling_convention,
        test_sdfs3sys_profiles_build_and_match_header,
        test_rom_drops_cmd_gateway_and_fixed_load_base,
        test_sdfs3sys_rejects_bad_header_and_checksum,
        test_sdfs3sys_rejects_payload_outside_load_range,
        test_sdfs3sys_cli_reports_bad_input,
        test_rom_bios_entry_table_layout,
        test_rom_bios_read_line_and_sd_match_internal,
        test_rom_bios_exec_returns_to_wboot,
        test_rom_bios_info_and_reserved,
        test_rom_bios_block_rejects_garbage,
        test_rom_boot3_writes_bios_block,
        test_rom_boot3_enters_dos_and_com_returns_through_wboot,
        test_sdfs3_cmd_dir_and_type_read_fat_files,
        test_sdfs3_cmd_load_run_and_com_read_fat_files,
        test_rom_boot3_reads_image_once,
        test_wboot_reloads_only_broken_parts,
        test_wboot_reload_fails_without_card_or_after_swap,
        test_monitor_gate_warns_and_dos_after_reset_and_ramtest,
        test_v2_boot_exit_returns_to_monitor_and_disables_dos,
        test_monitor_stack_fits_in_128_bytes,
        test_dos_gate_rejects_unloaded_block_without_writing,
        test_rom_boot3_rejects_bad_images,
        test_sdfs3_cmd_dispatch_parser_classifies_stub_commands,
        test_fixed_lba_loader_harness_loads_sdfs3sys,
        test_fixed_lba_loader_harness_rejects_bad_sdfs3sys,
        test_sdfs3_mutable_vars_live_outside_image,
        test_sdfs3_resident_image_unchanged_after_commands,
        test_sdfs3_init_clears_errors_and_warm_shows_pending,
        test_sdfs3_core_does_not_reference_ccp,
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
