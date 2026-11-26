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
V3_CCP_BASE = 0x6C00
V3_XLDR_BASE = 0x6800  # XLDR.OVL が動く上端の一時区画(#316)
V3_CORE_BASE = 0x7000
V3_CORE_OFFSET = V3_CORE_BASE - V3_CCP_BASE
V3_MEMTOP = 0x6FFF
V3_COM_MAX = V3_CORE_BASE - 0x0100  # .COM は GET_MEMTOP まで(#315)
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
        "BB_SLOT_LBA",
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
        "SDFS3_ERR_NOT_FOUND",
    )
    assert resident["SDFS3_CCP_BASE"] == V3_CCP_BASE and resident["SDFS3_CORE_BASE"] == V3_CORE_BASE
    config = {
        "profile": profile,
        "suffix": suffix,
        "rom": build / f"mc6800-monitor{suffix}.bin",
        "sdfs3sys": (build / f"SDFS3SYS{suffix}.BIN").read_bytes(),
        "hello_com": (build / "HELLO.COM").read_bytes(),
        "args_com": (build / "ARGS.COM").read_bytes(),
        "hello_s": (build / "HELLO.S").read_bytes(),
        "load_com": (build / "LOAD.COM").read_bytes(),
        "run_com": (build / "RUN.COM").read_bytes(),
        "xldr": (build / "XLDR.OVL").read_bytes(),
        "symbols": {**rom, **resident},
    }
    _V3_CACHE[profile] = config
    return config


def _xldr_files(config: dict, *, where: str = "bin", xldr: bytes | None = None) -> list:
    """LOAD.COM・RUN.COM は /BIN に、XLDR.OVL は where("bin"・"root"・"none")に置く(#316)。"""
    files = [
        _file("LOAD.COM", config["load_com"], ("BIN",)),
        _file("RUN.COM", config["run_com"], ("BIN",)),
    ]
    body = config["xldr"] if xldr is None else xldr
    if where == "bin":
        files.append(_file("XLDR.OVL", body, ("BIN",)))
    elif where == "root":
        files.append(_file("XLDR.OVL", body))
    return files


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
            "SDFS3_STREAM_OPEN",
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
        file_api = {symbols[name] for name in slot_names[2:6]}
        assert len(file_api) == 4 and symbols["SDFS3_NOT_IMPLEMENTED"] not in file_api, (
            f"{profile}: slot 2-5 must be implemented (#315)"
        )
        get_error = symbols["SDFS3_GET_ERROR"] - base
        assert data[get_error + 3 : get_error + 5] == bytes([0x0C, 0x39])
        # INIT は出力しない: clr LAST_ERROR / clr PENDING_ERR / clr STREAM_OPEN / clc / rts だけ
        init = symbols["SDFS3_INIT"] - base
        last_error, pending = symbols["SDFS3_LAST_ERROR"], symbols["SDFS3_PENDING_ERR"]
        stream = symbols["SDFS3_STREAM_OPEN"]
        assert data[init : init + 11] == bytes(
            [0x7F, last_error >> 8, last_error & 0xFF, 0x7F, pending >> 8, pending & 0xFF,
             0x7F, stream >> 8, stream & 0xFF, 0x0C, 0x39]
        ), f"{profile}: INIT should only clear the error variables and the handle: {data[init:init + 11].hex()}"
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
        # LOAD・RUN は CCP の内蔵ではなくなり、拡張子のない語として LOAD.COM・RUN.COM を探す(#316)
        ("LoAd HELLO.S", 0x03),
        ("RUN MISSING.S", 0x03),
        # .COM は核の LOAD_PATH のコードを残す(マウントの失敗は 3。#315)
        ("FOO.COM ARG", 0x03),
        ("foo.com", 0x03),
        ("", 0x02),
        ("   ", 0x02),
        ("UNKNOWN", 0x03),
        ("EXITX", 0x03),
        # 「.」のある語は、最初の「.」から後ろがちょうど .COM のときだけ .COM として扱う
        ("HELLO.S", 0x02),
        ("A.COMX", 0x02),
        ("A.B.COM", 0x02),
        # 暗黙の検索で組める語は 31 文字まで(32 文字はパスの失敗 7)
        ("A" * 31, 0x03),
        ("A" * 32, 0x07),
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
                *_xldr_files(config),
            ],
        )
        out = _v3_run(
            config,
            "M0300\r3F\r.\r"
            "BOOT3\r"
            "DIR\r"
            "TYPE README.TXT\r"
            "HELLO.COM\r"
            "ARGS.COM AAA BBB\r"
            "RETADDR.COM\r"
            "LOAD HELLO.S\r"
            "RUN RTS.S\r"
            "RUN 0300\r"
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
        assert boot.startswith(f"{WELCOME}\nBASE={V3_CCP_BASE:04X} END={end:04X}\n{PROMPT}DIR\n"), (
            f"{profile}: BOOT3 should go straight from Welcome to the DOS prompt: {boot[:200]!r}"
        )
        assert "README.TXT A 00000013" in _dos(out, "DIR")
        assert "HELLO FROM README" in _dos(out, "TYPE README.TXT")
        assert "HELLO COM" in _dos(out, "HELLO.COM")
        assert "ARGS AAA BBB" in _dos(out, "ARGS.COM AAA BBB")
        assert "?" not in _dos(out, "RETADDR.COM")
        assert "OK" in _dos(out, "LOAD HELLO.S")
        assert "RUN RTS" in _dos(out, "RUN RTS.S"), f"{profile}: RUN file with RTS should return to DOS"
        run_brk = _after(out, PROMPT + "RUN 0300\n")
        assert run_brk.lstrip("\n").startswith("BRK 0300"), f"{profile}: RUN addr: {run_brk[:200]!r}"
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
            *_xldr_files(config),
        ],
    )
    out = _v3_run(
        config,
        "M0300\r3F\r.\r"
        "BOOT3\r"
        "LOAD HELLO.S\r"
        "LOAD HELLO.HEX\r"
        "EXIT\r"
        "D0200-0201\r"
        "DOS\r"
        "RUN 0300\r"
        "DOS\r"
        "HELLO.COM\r"
        "ARGS.COM AAA BBB\r"
        "NOFILE.COM\r"
        "EMPTY.COM\r"
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
    assert _after(out, PROMPT + "RUN 0300\n").lstrip("\n").startswith("BRK 0300"), "RUN addr"
    assert "HELLO COM" in _dos(out, "HELLO.COM")
    assert "ARGS AAA BBB" in _dos(out, "ARGS.COM AAA BBB")
    assert _dos(out, "NOFILE.COM") == "?\n"
    assert _dos(out, "EMPTY.COM") == "?\n"
    # 大きさの境界($6F00 / $6F01 バイト)は test_com_max_size_runs_and_returns_through_reload(#315)
    assert _dos(out, "RUN HELLO.HEX") == "?\n"
    run_file = _after(out, PROMPT + "RUN RUN.S\n")
    assert "HELLO, WORLD" in run_file and "BRK 0106" in run_file, f"RUN file: {run_file[:300]!r}"
    assert out.count("] DOS\n" + PROMPT) == 3, f"each DOS from the monitor should reach the prompt: {out[-300:]!r}"
    assert out.count("\n?\n") == 3, f"bad .COM/RUN inputs should fail exactly three times: {out!r}"
    assert out.count(WELCOME) == 1
    print("[PASS] test_sdfs3_cmd_load_run_and_com_read_fat_files")


# ---------------------------------------------------------------------------
# #314 戻り口の検査と静かな再ロード、BOOT3 の 1 回読み、モニタの門、スタックの分離
# ---------------------------------------------------------------------------

# CCP($6C00-$6FFF)を $00 で埋めて RTS(大きな .COM が CCP を潰した代わり)
ZAPCCP_COM = bytes(
    [0xCE, V3_CCP_BASE >> 8, V3_CCP_BASE & 0xFF, 0x6F, 0x00, 0x08,
     0x8C, V3_CORE_BASE >> 8, V3_CORE_BASE & 0xFF, 0x26, 0xF8, 0x39]
)
ZAPCORE_ADDR = V3_CORE_BASE + 0x100
# 核の 1 バイトを反転して RTS
ZAPCORE_COM = bytes([0xB6, ZAPCORE_ADDR >> 8, ZAPCORE_ADDR & 0xFF, 0x43,
                     0xB7, ZAPCORE_ADDR >> 8, ZAPCORE_ADDR & 0xFF, 0x39])
SWI_DATA_ADDR = V3_CCP_BASE + 0x100
SWI_PROG_ADDR = 0x0200  # RUN.COM の入口($0100-$0188)とかぶらない番地に置く(決定 6)
SWI_BREAK_ADDR = SWI_PROG_ADDR + 5
# $0200: CCP の +$100 に $5A を置き、$0205 の NOP(ここに B で SWI を置く)、CCP の +$100 を $0210 へ
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
    fail_count: int | None = None,
    fail_cmd0_after: int | None = None,
    swap_image: bytes | None = None,
    swap_at: int | None = None,
    stack_watch: int | None = None,
    extra_args: list[str] | None = None,
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
    if fail_count is not None:
        args += ["--sd-fail-cmd17-count", str(fail_count)]
    if fail_cmd0_after is not None:
        args += ["--sd-fail-cmd0-after", str(fail_cmd0_after)]
    if swap_image is not None:
        swap_path.write_bytes(swap_image)
        args += ["--sd-swap-image", str(swap_path), "--sd-swap-at", str(swap_at)]
    if stack_watch is not None:
        args += ["--stack-watch", f"{stack_watch:04X}"]
    if extra_args:
        args += extra_args
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


def _system_sectors(
    config: dict, base: int = SDFS3SYS_FIXED_LBA, ccp_base: int = V3_CCP_BASE
) -> dict[str, list[int]]:
    """slot(先頭 LBA = base)の SDFS3SYS のセクタの LBA。ccp・core は読み直しで読むはずの
    LBA(先頭セクタは 1 回)。"""
    size = len(config["sdfs3sys"])
    last = base + (size - 1) // SECTOR_SIZE
    ccp_end = HEADER_SIZE + (V3_CORE_BASE - ccp_base)  # ファイル上の CCP の終端(最後の次)
    ccp = list(range(base, base + (ccp_end - 1) // SECTOR_SIZE + 1))
    core_first = base + ccp_end // SECTOR_SIZE
    core = [base, *range(core_first, last + 1)]
    return {"all": list(range(base, last + 1)), "ccp": ccp, "core": core}


def _wboot_sd_image(config: dict) -> bytes:
    return _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            _file("README.TXT", b"HELLO FROM README\r\n"),
            _file("HELLO.COM", config["hello_com"]),
            _file("ZAPCCP.COM", ZAPCCP_COM),
            _file("ZAPCORE.COM", ZAPCORE_COM),
            _file("SWI.S", _srec_file(SWI_PROG_ADDR, SWI_PROG, entry_address=SWI_PROG_ADDR)),
            *_xldr_files(config),
        ],
    )


def _reset_address(config: dict) -> int:
    rom = config["rom"].read_bytes()
    return (rom[-2] << 8) | rom[-1]


def test_rom_boot3_reads_image_once() -> None:
    """BOOT3 は既存の単一 LBA イメージ(marker なし)を slot A として、64 から 1 回ずつ読む
    (2 回読みならセクタ数の 2 倍。#301 のシナリオ 10)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sectors = _system_sectors(config)
        raw, log, _ = _v3_run_sd(config, "BOOT3\rDIR\r\r", sd_image=_wboot_sd_image(config))
        start, stop = _segment(raw, "] BOOT3")
        reads = _reads(log, start, stop)
        # marker なし(LBA 48 は 0)なので、48 と両 slot の先頭で世代を見てから A を読む(#301)
        assert reads[:3] == [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA], f"{profile}: slot pick read {reads}"
        assert reads[3:] == sectors["all"], f"{profile}: BOOT3 should read each sector once: {reads}"
        assert len(reads[3:]) == -(-len(config["sdfs3sys"]) // SECTOR_SIZE)
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
            f"B{SWI_BREAK_ADDR:04X}\rDOS\rRUN {SWI_PROG_ADDR:04X}\rR\rDIR\rEXIT\r"
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
        start, stop = _segment(raw, PROMPT + f"RUN {SWI_PROG_ADDR:04X}", end="] R\r\n")
        brk = raw[start:stop].replace("\r", "")
        assert re.search(rf"\nBRK {SWI_BREAK_ADDR:04X} A=5A [^\n]*\n\*SDFS3 CCP\n$", brk), f"{profile}: SWI: {brk!r}"
        assert _reads(log, raw.index(f"BRK {SWI_BREAK_ADDR:04X}", start), stop) == [], f"{profile}: SWI must not reload"
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

        for label, code, kwargs in (
            ("no card", "2", {"fail_from": first_reload}),
            ("swapped", "7", {"swap_image": bytes(swap_image), "swap_at": first_reload}),
        ):
            raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image, **kwargs)
            out = raw.replace("\r", "")
            assert f"{PROMPT}ZAPCCP.COM\n?{code}\n] DOS\n?6\n] " in out, f"{profile} {label}: {out[-600:]!r}"
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


# ---------------------------------------------------------------------------
# system slot A/B と active marker(#300・#301)
# ---------------------------------------------------------------------------

SDFS3MRK_LBA = 48
SLOT_A_LBA = SDFS3SYS_FIXED_LBA
SLOT_B_LBA = 96
SLOT_GEN_OFFSET = 0x1C
SLOT_TAG_ADDR = V3_MEMTOP  # CCP の末尾の埋め草($FF)。和の範囲に入るので、目印にして slot を区別する
SLOT_TAG = 0xB0


def _slot_image(config: dict, generation: int, *, tag: int | None = None) -> bytes:
    """世代(+$1C)と、あれば CCP の末尾の目印を入れ、和を付け直した SDFS3SYS。"""
    data = bytearray(config["sdfs3sys"])
    data[SLOT_GEN_OFFSET : SLOT_GEN_OFFSET + 2] = bytes([generation >> 8, generation & 0xFF])
    if tag is not None:
        data[HEADER_SIZE + SLOT_TAG_ADDR - V3_CCP_BASE] = tag
    _refresh_checksum(data)
    return bytes(data)


def _marker(active: int, *, fix_sum: bool = True, **fields) -> bytes:
    """active marker の 512B(#300 の形式)。fields で欄を差し替え、既定では和を付け直す。"""
    values = {
        "magic": b"SDFS3MRK", "version": 1, "active": active, "slot_count": 2, "flags": 0x01,
        "generation": 1, "slot_max": 32, "slot_a": SLOT_A_LBA, "slot_b": SLOT_B_LBA, "size": 32,
    }
    values.update(fields)
    sector = bytearray(SECTOR_SIZE)
    sector[0:8] = values["magic"]
    sector[8:12] = bytes([values["version"], values["active"], values["slot_count"], values["flags"]])
    for offset, name in ((0x0C, "generation"), (0x0E, "slot_max"), (0x10, "slot_a"), (0x12, "slot_b"), (0x1A, "size")):
        sector[offset : offset + 2] = bytes([values[name] >> 8, values[name] & 0xFF])
    if fix_sum:
        checksum = checksum16(bytes(sector))
        sector[0x18:0x1A] = bytes([checksum >> 8, checksum & 0xFF])
    return bytes(sector)


def _slots_sd_image(
    config: dict, slot_a: bytes | None, slot_b: bytes | None, marker: bytes | None, *, cut: int | None = None
) -> bytes:
    """marker(48)・slot A(64)・slot B(96)・FAT32(128)の SD。None の所は 0 のまま。
    cut を渡すとその LBA より先を切る(そこから先の CMD17 は失敗する)。"""
    image = bytearray(_wboot_sd_image(config))
    image[SLOT_A_LBA * SECTOR_SIZE : SDFS3SYS_FAT_PARTITION_LBA * SECTOR_SIZE] = bytes(
        (SDFS3SYS_FAT_PARTITION_LBA - SLOT_A_LBA) * SECTOR_SIZE
    )
    for lba, data in ((SDFS3MRK_LBA, marker), (SLOT_A_LBA, slot_a), (SLOT_B_LBA, slot_b)):
        if data is not None:
            assert len(data) <= 32 * SECTOR_SIZE
            image[lba * SECTOR_SIZE : lba * SECTOR_SIZE + len(data)] = data
    if cut is not None:
        del image[cut * SECTOR_SIZE :]
    return bytes(image)


def _low_reads(log: list, start: int, stop: int) -> list[int]:
    """start〜stop の CMD17 のうち marker と slot(48〜127)の LBA。MBR(0)と FAT32 は除く。"""
    return [lba for lba in _reads(log, start, stop) if SDFS3MRK_LBA <= lba < SDFS3SYS_FAT_PARTITION_LBA]


def _boot3_slot(config: dict, sd_image: bytes, extra: str = "") -> tuple[str, list, list[int], int]:
    """BOOT3(と extra)を動かし、(出力, 記録, BOOT3 で読んだ低位の LBA, BB_SLOT_LBA) を返す。"""
    slot_lba = config["symbols"]["BB_SLOT_LBA"]
    raw, log, _ = _v3_run_sd(
        config,
        "BOOT3\r" + extra + "\r",
        sd_image=sd_image,
        dump_range=f"{slot_lba:04X}-{slot_lba + 1:04X}",
    )
    start, stop = _segment(raw, "] BOOT3") if PROMPT in raw else _segment(raw, "] BOOT3", end="] ")
    out = raw.replace("\r", "")
    # 終了時のダンプはプロンプト(「] 」か「SDFS3> 」)の後ろに出る
    dumps = re.findall(rf"{slot_lba:04X} ([0-9A-F]{{2}}) ([0-9A-F]{{2}})", out)
    assert dumps, f"missing final dump at {slot_lba:04X}: {out[-400:]!r}"
    hi, lo = dumps[-1]
    return raw, log, _low_reads(log, start, stop), (int(hi, 16) << 8) | int(lo, 16)


def test_boot3_marker_slot_and_wboot_reload_from_it() -> None:
    """marker が指す slot から起動し、CCP を潰す .COM から戻ると、その slot から読み直す。
    起動後に marker を A に戻しても B から読み、B の中身が替わっていたら中止して「?」
    (#301 のシナリオ 1〜4)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        slot_a = _slot_image(config, 1)
        slot_b = _slot_image(config, 2, tag=SLOT_TAG)
        a_sectors = _system_sectors(config, SLOT_A_LBA)
        b_sectors = _system_sectors(config, SLOT_B_LBA)
        tag_dump = f"D{SLOT_TAG_ADDR:04X}-{SLOT_TAG_ADDR:04X}"

        # 1. active=A なら 48 と A のセクタだけ
        raw, _log, reads, lba = _boot3_slot(config, _slots_sd_image(config, slot_a, slot_b, _marker(0)), f"EXIT\r{tag_dump}\r")
        assert reads == [SDFS3MRK_LBA, *a_sectors["all"]], f"{profile}: active=A read {reads}"
        assert lba == SLOT_A_LBA and WELCOME in raw
        assert _dump_bytes(_after(raw.replace("\r", ""), f"] {tag_dump}\n"), SLOT_TAG_ADDR) == [0xFF]

        # 1・2. active=B: 48 と B のセクタだけを読み、ZAPCCP.COM の戻りは B の CCP だけを読み直す
        sd_image = _slots_sd_image(config, slot_a, slot_b, _marker(1))
        input_text = f"ZAPCCP.COM\rDIR\rEXIT\r{tag_dump}\r"
        raw, log, reads, lba = _boot3_slot(config, sd_image, input_text)
        out = raw.replace("\r", "")
        assert reads == [SDFS3MRK_LBA, *b_sectors["all"]], f"{profile}: active=B read {reads}"
        assert lba == SLOT_B_LBA, f"{profile}: BB_SLOT_LBA = {lba}"
        start, stop = _segment(raw, PROMPT + "ZAPCCP.COM")
        assert raw[start:stop] == "\r\n", f"{profile}: reload must be silent: {raw[start:stop]!r}"
        assert _low_reads(log, start, stop) == b_sectors["ccp"], f"{profile}: reload read {_low_reads(log, start, stop)}"
        assert "README.TXT" in _dos(out, "DIR")
        assert _dump_bytes(_after(out, f"] {tag_dump}\n"), SLOT_TAG_ADDR) == [SLOT_TAG]
        first_reload = next(n for n, l, _r1, tx in log if tx >= start and l == SLOT_B_LBA)

        # 3. 読み直しの先頭から marker を A に戻したカードに替わっても、B から読む(B はバイト一致)
        swap = _slots_sd_image(config, slot_a, slot_b, _marker(0, generation=2))
        raw, log, _ = _v3_run_sd(config, "BOOT3\r" + input_text + "\r", sd_image=sd_image,
                                 swap_image=swap, swap_at=first_reload)
        out = raw.replace("\r", "")
        late = [l for n, l, _r1, _tx in log if n >= first_reload and SDFS3MRK_LBA <= l < SDFS3SYS_FAT_PARTITION_LBA]
        assert late == b_sectors["ccp"], f"{profile}: reload after marker change read {late}"
        assert SDFS3MRK_LBA not in [l for n, l, _r1, _tx in log if n >= first_reload]
        assert "README.TXT" in _dos(out, "DIR") and "\n?\n" not in out
        assert _dump_bytes(_after(out, f"] {tag_dump}\n"), SLOT_TAG_ADDR) == [SLOT_TAG]

        # 4. 差し替え先の B の中身が違う(+$18 が違う)なら、B の先頭セクタだけ読んで「?」
        changed = bytearray(slot_b)
        changed[HEADER_SIZE + 0x0200] ^= 0x01
        _refresh_checksum(changed)
        assert changed[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] != slot_b[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2]
        swap = _slots_sd_image(config, slot_a, bytes(changed), _marker(0, generation=2))
        ccp_dump = f"D{V3_CCP_BASE:04X}-{V3_CCP_BASE + 15:04X}"
        raw, log, _ = _v3_run_sd(config, f"BOOT3\rZAPCCP.COM\rDOS\r{ccp_dump}\r\r", sd_image=sd_image,
                                 swap_image=swap, swap_at=first_reload)
        out = raw.replace("\r", "")
        assert f"{PROMPT}ZAPCCP.COM\n?7\n] DOS\n?6\n] " in out, f"{profile}: changed slot B: {out[-600:]!r}"
        late = [(l, r1) for n, l, r1, _tx in log if n >= first_reload]
        assert late == [(SLOT_B_LBA, 0x00)], f"{profile}: changed slot B should stop at its header: {late}"
        ccp = _dump_range_bytes(_after(out, f"] {ccp_dump}"), V3_CCP_BASE, 16)
        assert ccp == [0] * 16, f"{profile}: RAM must not be written: {ccp}"
    print("[PASS] test_boot3_marker_slot_and_wboot_reload_from_it")


def test_boot3_invalid_marker_falls_back_to_generation() -> None:
    """marker の欄が 1 つでも #300 の有効条件を外れたら、世代の大きい B から起動する
    (欄を壊したら和は付け直す。和のケースだけ付け直さない)。境界の 32・$0100・512 は有効
    (#301 のシナリオ 5)。"""
    cases = [
        ("valid", {}, True),
        ("size 32", {"size": 32}, True),
        ("size $0100", {"size": 0x0100}, True),
        ("size 512", {"size": 512}, True),
        ("magic", {"magic": b"SDFS3MRX"}, False),
        ("version 2", {"version": 2}, False),
        ("active 2", {"active": 2}, False),
        ("slot_count 3", {"slot_count": 3}, False),
        ("flags bit0", {"flags": 0x02}, False),
        ("slot_max 33", {"slot_max": 33}, False),
        ("slot_max $0120", {"slot_max": 0x0120}, False),
        ("slot_a 65", {"slot_a": 65}, False),
        ("slot_a $0140", {"slot_a": 0x0140}, False),
        ("slot_b 97", {"slot_b": 97}, False),
        ("slot_b $0160", {"slot_b": 0x0160}, False),
        ("size 31", {"size": 31}, False),
        ("size 513", {"size": 513}, False),
        ("size $0300", {"size": 0x0300}, False),
        ("checksum", {"fix_sum": False}, False),
    ]
    for profile in V3_PROFILES:
        config = _v3(profile)
        slot_a = _slot_image(config, 3)
        slot_b = _slot_image(config, 4, tag=SLOT_TAG)
        for label, fields, valid in cases:
            marker = _marker(**{"active": 0, **fields})
            if label == "checksum":
                marker = bytearray(marker)
                marker[0x18] ^= 0x01
                marker = bytes(marker)
            raw, _log, reads, lba = _boot3_slot(config, _slots_sd_image(config, slot_a, slot_b, marker))
            if valid:
                want = [SDFS3MRK_LBA, *_system_sectors(config, SLOT_A_LBA)["all"]]
            else:
                want = [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA, *_system_sectors(config, SLOT_B_LBA)["all"]]
            assert reads == want, f"{profile} {label}: read {reads}, want {want}"
            assert lba == (SLOT_A_LBA if valid else SLOT_B_LBA), f"{profile} {label}: BB_SLOT_LBA = {lba}"
            assert WELCOME in raw and PROMPT in raw, f"{profile} {label}: {raw[-400:]!r}"
    print("[PASS] test_boot3_invalid_marker_falls_back_to_generation")


def test_boot3_generation_picks_first_slot() -> None:
    """marker が無いときは世代で先に試す slot を決める。両方 0 でなく B > A のときだけ B。
    上位バイトで決まる組、同値、A が空(0 埋め)を含む(#301 のシナリオ 6)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        a_all = _system_sectors(config, SLOT_A_LBA)["all"]
        b_all = _system_sectors(config, SLOT_B_LBA)["all"]
        head = [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA]
        cases = [
            ("A 3 / B 2", 3, 2, head + a_all, SLOT_A_LBA),
            ("A 3 / B 4", 3, 4, head + b_all, SLOT_B_LBA),
            ("A 0 / B 5", 0, 5, head + a_all, SLOT_A_LBA),
            ("A 5 / B 0", 5, 0, head + a_all, SLOT_A_LBA),
            ("A 5 / B 5", 5, 5, head + a_all, SLOT_A_LBA),
            ("A $0100 / B $00FF", 0x0100, 0x00FF, head + a_all, SLOT_A_LBA),
            ("A $00FF / B $0100", 0x00FF, 0x0100, head + b_all, SLOT_B_LBA),
            ("A $FFFF / B $0001", 0xFFFF, 0x0001, head + a_all, SLOT_A_LBA),
            ("A empty / B 0", None, 0, head + [SLOT_A_LBA] + b_all, SLOT_B_LBA),
        ]
        for label, gen_a, gen_b, want, want_lba in cases:
            slot_a = None if gen_a is None else _slot_image(config, gen_a)
            slot_b = _slot_image(config, gen_b, tag=SLOT_TAG)
            raw, _log, reads, lba = _boot3_slot(config, _slots_sd_image(config, slot_a, slot_b, None))
            assert reads == want, f"{profile} {label}: read {reads}, want {want}"
            assert lba == want_lba and PROMPT in raw, f"{profile} {label}: BB_SLOT_LBA = {lba}"
    print("[PASS] test_boot3_generation_picks_first_slot")


def test_boot3_falls_back_from_bad_active_slot() -> None:
    """active の slot が和の不一致・ヘッダ不正・読めないときは他方から起動し、その後の
    読み直しも起動した slot から読む。両方だめなら BOOT3 も DOS も「?」(#301 のシナリオ 7〜9)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        block = config["symbols"]["BIOS_BLOCK"]
        a_sectors = _system_sectors(config, SLOT_A_LBA)
        b_sectors = _system_sectors(config, SLOT_B_LBA)
        slot_a = _slot_image(config, 1)
        slot_b = _slot_image(config, 2, tag=SLOT_TAG)
        bad_sum_b = bytearray(slot_b)
        bad_sum_b[-1] ^= 0x01  # ペイロードだけ壊す(ヘッダの和は元のまま)
        bad_magic_a = bytearray(slot_a)
        bad_magic_a[0] = ord("X")

        # 7. active=B の和が不一致: B を全部読んでから A を全部読み、A から。読み直しも A
        raw, log, reads, lba = _boot3_slot(
            config, _slots_sd_image(config, slot_a, bytes(bad_sum_b), _marker(1)), "ZAPCCP.COM\rDIR\r"
        )
        assert reads == [SDFS3MRK_LBA, *b_sectors["all"], *a_sectors["all"]], f"{profile}: sum fallback read {reads}"
        assert lba == SLOT_A_LBA, f"{profile}: BB_SLOT_LBA = {lba}"
        start, stop = _segment(raw, PROMPT + "ZAPCCP.COM")
        assert _low_reads(log, start, stop) == a_sectors["ccp"], f"{profile}: reload read {_low_reads(log, start, stop)}"
        assert "README.TXT" in _dos(raw.replace("\r", ""), "DIR")

        # 8. active=A のヘッダ不正: A は先頭セクタだけ読み、B から
        raw, _log, reads, lba = _boot3_slot(config, _slots_sd_image(config, bytes(bad_magic_a), slot_b, _marker(0)))
        assert reads == [SDFS3MRK_LBA, SLOT_A_LBA, *b_sectors["all"]], f"{profile}: header fallback read {reads}"
        assert lba == SLOT_B_LBA and PROMPT in raw

        # active=B が読めない(カードが 96 の手前で終わる): 96 の失敗のあと A から
        raw, log, reads, lba = _boot3_slot(config, _slots_sd_image(config, slot_a, None, _marker(1), cut=SLOT_B_LBA))
        assert reads == [SDFS3MRK_LBA, SLOT_B_LBA, *a_sectors["all"]], f"{profile}: read-error fallback read {reads}"
        assert [r1 for _n, l, r1, _tx in log if l == SLOT_B_LBA] == [0x04]
        assert lba == SLOT_A_LBA and WELCOME in raw

        # marker なしで B の先頭が読めない: 世代は比べずに A から(BOOT3_PICK の読み出し失敗の分岐)
        raw, log, reads, lba = _boot3_slot(config, _slots_sd_image(config, slot_a, None, None, cut=SLOT_B_LBA))
        assert reads == [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA, *a_sectors["all"]], f"{profile}: no-marker read error read {reads}"
        assert [r1 for _n, l, r1, _tx in log if l == SLOT_B_LBA] == [0x04]
        assert lba == SLOT_A_LBA and WELCOME in raw

        # 9. 両方だめ: BOOT3 も DOS も「?」、区画は無効
        raw, log, _ = _v3_run_sd(
            config,
            "BOOT3\rDOS\r\r",
            sd_image=_slots_sd_image(config, bytes(bad_magic_a), bytes(bad_sum_b), _marker(1)),
            dump_range=f"{block:04X}-{block + 1:04X}",
        )
        out = raw.replace("\r", "")
        # A はヘッダ不正(3)、B は和の不一致(5)。B を先に試しても A → B の順に出る(#307)
        assert "] BOOT3\n?35\n] DOS\n?6\n] " in out, f"{profile}: both bad: {out[-400:]!r}"
        assert PROMPT not in out and WELCOME not in out
        assert [l for _n, l, _r1, _tx in log] == [SDFS3MRK_LBA, *b_sectors["all"], SLOT_A_LBA], f"{profile}: {log}"
        assert _dump_bytes(_final_dump(out, block), block)[0] == 0, f"{profile}: BB_MAGIC should be cleared"
    print("[PASS] test_boot3_falls_back_from_bad_active_slot")


# ---------------------------------------------------------------------------
# BOOT3 と WBOOT の失敗コード(#307)
# ---------------------------------------------------------------------------


def test_boot3_error_codes_name_each_slot() -> None:
    """cold の BOOT3 は「?」のあとに slot A と slot B の理由を 1 桁ずつ出す(1 = SD の初期化、
    2 = 読み出し、3 = ヘッダ不正、4 = API の不一致、5 = 和の不一致)。順は試した順ではなく A → B。
    どの失敗でも区画は無効で、続く DOS は ?6。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        block = config["symbols"]["BIOS_BLOCK"]
        slot_a = _slot_image(config, 1)
        bad_magic_a = bytearray(slot_a)
        bad_magic_a[0] = ord("X")
        bad_sum_a = bytearray(slot_a)
        bad_sum_a[-1] ^= 0x01
        bad_api_a = bytearray(slot_a)
        bad_api_a[0x09] = 0x01
        _refresh_checksum(bad_api_a)
        core = HEADER_SIZE + V3_CORE_OFFSET
        bad_core_sig_a = bytearray(slot_a)  # 核の SDFS3API の署名(BB_STORE の BB_CHECK_API)
        bad_core_sig_a[core] = ord("X")
        _refresh_checksum(bad_core_sig_a)
        bad_entry_a = bytearray(slot_a)  # CCP 入口表が核の位置(BB_STORE の BB_CHECK_VALID)
        bad_entry_a[0x10:0x12] = bytes([V3_CORE_OFFSET >> 8, V3_CORE_OFFSET & 0xFF])
        _refresh_checksum(bad_entry_a)
        bad_magic_b = bytearray(_slot_image(config, 2))
        bad_magic_b[0] = ord("X")
        good_card = _slots_sd_image(config, slot_a, None, None)
        cases = [
            # (名前, SD, 失敗注入, コード, 読む LBA(None なら見ない))
            ("SD_INIT fails", good_card, {"fail_cmd0_after": 0}, "11", []),
            ("every read fails", good_card, {"fail_from": 1}, "22",
             [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA, SLOT_A_LBA, SLOT_B_LBA]),  # 選ぶための 3 回と、試す 2 回
            ("A bad header, B empty", _slots_sd_image(config, bytes(bad_magic_a), None, None), {}, "33", None),
            # A を試したあと、B の前の SD_INIT のし直しで失敗: B の理由は SD の初期化
            ("SD_INIT fails before B", _slots_sd_image(config, bytes(bad_magic_a), None, None),
             {"fail_cmd0_after": 4}, "31", [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA, SLOT_A_LBA]),
            ("A bad sum, B empty", _slots_sd_image(config, bytes(bad_sum_a), None, None), {}, "53", None),
            ("A old API major, B empty", _slots_sd_image(config, bytes(bad_api_a), None, None), {}, "43", None),
            ("A bad core API, B empty", _slots_sd_image(config, bytes(bad_core_sig_a), None, None), {}, "43", None),
            ("A entry table in core, B empty", _slots_sd_image(config, bytes(bad_entry_a), None, None), {}, "33", None),
            (
                "active B bad header, A bad sum",
                _slots_sd_image(config, bytes(bad_sum_a), bytes(bad_magic_b), _marker(1)),
                {},
                "53",
                [SDFS3MRK_LBA, SLOT_B_LBA, *_system_sectors(config, SLOT_A_LBA)["all"]],
            ),
        ]
        for label, sd_image, kwargs, code, reads in cases:
            raw, log, _ = _v3_run_sd(
                config, "BOOT3\rDOS\r\r", sd_image=sd_image, dump_range=f"{block:04X}-{block + 1:04X}", **kwargs
            )
            out = raw.replace("\r", "")
            assert f"] BOOT3\n?{code}\n] DOS\n?6\n] " in out, f"{profile} {label}: {out[-400:]!r}"
            assert PROMPT not in out and WELCOME not in out, f"{profile} {label}: resident must not run"
            assert _dump_bytes(_final_dump(out, block), block)[0] == 0, f"{profile} {label}: BB_MAGIC"
            if reads is not None:
                got = [lba for _n, lba, _r1, _tx in log]
                assert got == reads, f"{profile} {label}: read {got}"
    print("[PASS] test_boot3_error_codes_name_each_slot")


def test_wboot_error_codes_name_the_cause() -> None:
    """warm(WBOOT・DOS)は「?」のあとに 1 桁を出す(6 = 区画が無効、1 = SD の初期化、2 = 読み出し、
    7 = カードの差し替え、5 = 読み直したあとの和の不一致)。6 以外は区画を無効にするので、
    続く DOS は ?6。CCP を潰す ZAPCCP.COM の戻りで読み直すところを狙う。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sd_image = _wboot_sd_image(config)
        input_text = "DOS\rBOOT3\rHELLO.COM\rZAPCCP.COM\rDOS\r\r"
        raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image)
        out = raw.replace("\r", "")
        assert "] DOS\n?6\n] BOOT3\n" in out, f"{profile}: DOS before BOOT3: {out[:400]!r}"
        # 健全なカードなら読み直しは何も出さずに SDFS3> へ戻る(DOS は CCP のコマンドではないので CCP の ?)
        assert f"{PROMPT}ZAPCCP.COM\n{PROMPT}DOS\n?\n" in out, f"{profile}: healthy run: {out[-600:]!r}"
        start, _stop = _segment(raw, PROMPT + "ZAPCCP.COM")
        first_reload = next(n for n, lba, _r1, tx in log if tx >= start and lba == SDFS3SYS_FIXED_LBA)

        base = SDFS3SYS_FIXED_LBA * SECTOR_SIZE
        swapped = bytearray(sd_image)  # +$18 の違う版
        swapped[base + HEADER_SIZE + 0x0200] ^= 0x01
        image = bytearray(swapped[base : base + len(config["sdfs3sys"])])
        _refresh_checksum(image)
        swapped[base : base + len(image)] = image
        same_sum = bytearray(sd_image)  # +$18 は同じで、CCP の中身だけ違う(読み直しても和が合わない)
        same_sum[base + HEADER_SIZE + 0x0010] ^= 0x01

        for label, code, kwargs, late_want in (
            ("SD_INIT fails", "1", {"fail_cmd0_after": first_reload - 1}, []),
            ("header read fails", "2", {"fail_from": first_reload}, [(SDFS3SYS_FIXED_LBA, 0x04)]),
            # 先頭セクタはバッファにあるので、次の CMD17 は CCP の 2 セクタ目
            ("CCP read fails", "2", {"fail_from": first_reload + 1}, [(SDFS3SYS_FIXED_LBA, 0), (SDFS3SYS_FIXED_LBA + 1, 0x04)]),
            ("card swapped", "7", {"swap_image": bytes(swapped), "swap_at": first_reload}, [(SDFS3SYS_FIXED_LBA, 0)]),
            ("sum after reload", "5", {"swap_image": bytes(same_sum), "swap_at": first_reload}, None),
        ):
            raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image, **kwargs)
            out = raw.replace("\r", "")
            assert f"{PROMPT}ZAPCCP.COM\n?{code}\n] DOS\n?6\n] " in out, f"{profile} {label}: {out[-600:]!r}"
            late = [(lba, r1) for n, lba, r1, _tx in log if n >= first_reload]
            if late_want is not None:
                assert late == late_want, f"{profile} {label}: {late}"
            else:
                assert late == [(lba, 0) for lba in _system_sectors(config)["ccp"]], f"{profile} {label}: {late}"
    print("[PASS] test_wboot_error_codes_name_the_cause")


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
        assert "SDFS> EXIT\n] DOS\n?6\n] " in out, f"{profile}: v2 EXIT / DOS: {out[-600:]!r}"
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
        assert out.count("BRK 0183") == 2 and "] DOS\n?5\n" in out, f"{profile}: {out[-900:]!r}"
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
    # 区画が無効なら ?6。形の正しい区画は読み直しに進み、+$18 が違うので差し替え扱いの ?7(#307)
    for label, code, block_data in (
        ("zero", "6", None), ("garbage", "6", bytes(garbage)), ("bad sums", "7", bytes(shaped))
    ):
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
        assert f"] DOS\n?{code}\n] " in out, f"{label}: DOS without a valid block should fail: {out[-300:]!r}"
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
    assert dos[1].startswith("?6\n"), f"v2 BOOT should invalidate the v3 block: {dos[1][:80]!r}"
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
    # 期待するコード(#307): 上位 = slot A の理由。カードは slot B(LBA 96)の手前で終わるので、
    # B はいつも読み出しの失敗(2)
    cases = [
        ("old resident (major 1, load $5000)", "42", old_v1),
        ("header major 1", "42", patched(lambda data: data.__setitem__(0x09, 0x01))),
        ("api major 1", "42", patched(lambda data: data.__setitem__(core + 8, 0x01))),
        ("api signature", "42", patched(lambda data: data.__setitem__(core, ord("X")))),
        ("load below RAM floor", "32", patched(put16(0x0C, 0x3F00))),
        # 最後のバイトが $8000 に来る load(1 バイトだけ USER_RAM_END を越える)
        ("image beyond USER_RAM_END", "32", patched(put16(0x0C, 0x8000 - (len(good) - HEADER_SIZE) + 1))),
        ("api offset outside image", "32", patched(put16(0x12, 0x2000))),
        ("entry table outside CCP", "32", patched(put16(0x10, V3_CORE_OFFSET))),
        ("bad magic", "32", bytes(bad_magic)),
        ("bad checksum", "52", bytes(bad_sum)),
    ]
    block = symbols["BIOS_BLOCK"]
    for label, code, image in cases:
        out = _v3_run(
            config,
            "BOOT3\rDOS\r\r",
            sd_image=_build_sdfs3sys_sd_image(image),
            dump_range=f"{block:04X}-{block + 1:04X}",
            max_cycles=300_000_000,
            timeout=60,
        )
        assert f"] BOOT3\n?{code}\n] DOS\n?6\n] " in out, f"{label}: BOOT3 and DOS should both fail: {out[-400:]!r}"
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
        _remake_sdfs3(profile, "sdfs3sys")  # 通常ビルドに戻す
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
            *_xldr_files(config),
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
    last_failure = symbols["SDFS3_ERR_NOT_FOUND"]  # .COM は核の LOAD_PATH のコードを残す(#315)
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
    assert f"] BOOT3\n{WELCOME}\nBASE={V3_CCP_BASE:04X} END={end:04X}\n{PROMPT}EXIT\n" in out, (
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


# #317 resident は SD ドライバを持たず、ROM の BIOS 入口を呼ぶ
SD_DRIVER_LABELS = (
    "SD_PIA_INIT", "SD_SELECT", "SD_DESELECT", "SD_SEND_CMD", "SD_WAIT_R1", "SD_SPI_XFER", "SD_FAIL_A",
)


def test_sdfs3_resident_calls_rom_sd_entries() -> None:
    for profile, suffix in V3_PROFILES.items():
        config = _v3(profile)
        listing_path = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
        symbols = _load_symbols(listing_path, "SD_INIT", "SD_READ_SECTOR")
        assert symbols == {"SD_INIT": 0xE0F8, "SD_READ_SECTOR": 0xE0FB}, f"{profile}: {symbols!r}"
        listing = listing_path.read_text(encoding="utf-8", errors="replace")
        left = [name for name in SD_DRIVER_LABELS if re.search(rf"\b{name}\b", listing)]
        assert not left, f"{profile}: resident still has the SD driver: {left}"
        payload = config["sdfs3sys"][HEADER_SIZE:]
        for address in symbols.values():
            call = bytes([0xBD, address >> 8, address & 0xFF])
            assert call in payload, f"{profile}: resident never calls ${address:04X}"
    print("[PASS] test_sdfs3_resident_calls_rom_sd_entries")


def test_sdfs3_commands_match_output_with_rom_sd_driver() -> None:
    """DIR・TYPE・.COM・LOAD の出力は、SD ドライバを外す前の resident と同じ。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        hello_s = (PROJECT_ROOT / "build" / "HELLO.S").read_bytes()
        sd_image = _build_sdfs3sys_fat_sd_image(
            config["sdfs3sys"],
            [_file("HELLO.S", hello_s), _file("HELLO.COM", config["hello_com"]), *_xldr_files(config)],
        )
        out = _v3_run(
            config,
            "BOOT3\rDIR\rTYPE HELLO.S\rHELLO.COM\rLOAD HELLO.S\rEXIT\rD0200-0211\r\r",
            sd_image=sd_image,
        )
        listing = f"HELLO.S A {len(hello_s):08X}\nHELLO.COM A {len(config['hello_com']):08X}\nBIN D 00000000\n"
        assert _dos(out, "DIR") == listing, f"{profile}: DIR: {out!r}"
        typed = hello_s.decode("ascii").replace("\r", "")
        assert _dos(out, "TYPE HELLO.S") == typed, f"{profile}: TYPE: {out!r}"
        assert _dos(out, "HELLO.COM") == "\nHELLO COM\n", f"{profile}: .COM: {out!r}"
        assert _dos(out, "LOAD HELLO.S") == "OK\n", f"{profile}: LOAD: {out!r}"
        # HELLO.S(ORG $0200)の先頭 18 バイト
        assert "] D0200-0211\n0200 CE 02 12 BD 02 07 3F A6 00 27 06 BD E0 75 08 20 " in out, (
            f"{profile}: LOAD did not write HELLO.S: {out!r}"
        )
        assert "\n0210 F6 39 " in out, f"{profile}: LOAD did not write HELLO.S: {out!r}"
    print("[PASS] test_sdfs3_commands_match_output_with_rom_sd_driver")


def test_sdfs3_sd_access_goes_through_bios_table() -> None:
    """入口表の 1 本だけを失敗にすると、ROM の BOOT3 は通り(内部は表を使わない)、DIR が失敗する。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sd_image = _build_sdfs3sys_fat_sd_image(config["sdfs3sys"], [_file("HELLO.S", b"S9030000FC\r\n")])
        rom = config["rom"].read_bytes()
        base = 0x10000 - len(rom)
        unimpl = _rom_byte_reader(rom)(0xE10D, 3)  # 予約の入口 BIOS_SD_WRITE(C=1 を返す)
        for entry in (0xE0F8, 0xE0FB):
            offset = entry - base
            assert rom[offset] == 0x7E and unimpl[0] == 0x7E, f"{profile}: BIOS entry should be jmp"
            patched = rom[:offset] + unimpl + rom[offset + 3 :]
            with _temporary_directory() as tmp:
                rom_path = Path(tmp) / "rom.bin"
                rom_path.write_bytes(patched)
                out = _v3_run({**config, "rom": rom_path}, "BOOT3\rDIR\r\r", sd_image=sd_image)
            assert WELCOME in out, f"{profile}: BOOT3 should not use ${entry:04X}: {out!r}"
            assert _dos(out, "DIR") == "?\n", f"{profile}: DIR should use ${entry:04X}: {out!r}"
    print("[PASS] test_sdfs3_sd_access_goes_through_bios_table")


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
    assert "\n?6\n" in after_go.replace("\r", ""), f"WBOOT without a block should print '?6': {after_go!r}"
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


def _remake_sdfs3(profile: str, target: str, extra_args: list[str] | None = None) -> None:
    """resident を作り直す。macOS の GNU Make 3.81 は時刻を 1 秒単位で比べるので、同じ秒に
    .p を作り直すと .BIN と SDFS3SYS が古いまま残る。先に消してから作る。"""
    suffix = V3_PROFILES[profile]
    for name in (f"SDFS3{suffix}.BIN", f"SDFS3SYS{suffix}.BIN"):
        (PROJECT_ROOT / "build" / name).unlink(missing_ok=True)
    _run_make(profile, target, extra_args=extra_args)


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


# ---------------------------------------------------------------------------
# #315 ファイル API(slot 2〜5)と、核の LOAD_PATH による .COM の起動
# ---------------------------------------------------------------------------

COM_MARK_ADDR = 0x0100
COM_MARK = 0xAA
# $0100 から NOP を並べ、最後のバイト($6FFF)を RTS にした最大の .COM。一時区画と CCP($6800-$6FFF)を潰す
BIG_COM = b"\x01" * (V3_COM_MAX - 1) + b"\x39"
TOOBIG_COM = b"\x39" * (V3_COM_MAX + 1)
FOURK_COM = b"\x39" + b"\x01" * 4095


def _file_api_sd_image(config: dict, extra: list | None = None) -> bytes:
    return _build_sdfs3sys_fat_sd_image(
        config["sdfs3sys"],
        [
            _file("README.TXT", b"HELLO FROM README\r\n"),
            _file("BIG.COM", BIG_COM),
            _file("TOOBIG.COM", TOOBIG_COM),
            _file("FOURK.COM", FOURK_COM),
            *(extra or []),
        ],
    )


def _numbers(log: list, start: int, stop: int) -> list[int]:
    """出力の位置 start〜stop の間に起きた CMD17 の番号。"""
    return [n for n, _lba, _r1, tx in log if start <= tx <= stop]


def test_com_max_size_runs_and_returns_through_reload() -> None:
    """シナリオ 1・2・3: $6F00 バイトの .COM は CCP を潰して起動し、RTS のあと WBOOT が CCP だけを
    読み直して DOS に戻る。$6F01 バイトは読み込みの前に「?」で、ファイルの中身も SDFS3SYS も
    読まない。読み込みの途中で SD が失敗したら「?」を 1 回だけ出して DOS に戻る。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        sectors = _system_sectors(config)
        payload = config["sdfs3sys"][HEADER_SIZE:]
        pending = symbols["SDFS3_PENDING_ERR"]
        sd_image = _file_api_sd_image(config)
        ccp_dump = f"D{V3_CCP_BASE:04X}-{V3_CCP_BASE + 15:04X}"
        input_text = (
            f"M{COM_MARK_ADDR:04X}\r{COM_MARK:02X}\r.\r"
            "BOOT3\rTOOBIG.COM\rEXIT\r"
            f"D{COM_MARK_ADDR:04X}-{COM_MARK_ADDR:04X}\r"
            "DOS\rFOURK.COM\rEXIT\r"
            f"D{COM_MARK_ADDR:04X}-{COM_MARK_ADDR:04X}\r"
            f"D{pending:04X}-{pending:04X}\r"
            "DOS\rBIG.COM\rDIR\rEXIT\r"
            f"{ccp_dump}\r\r"
        )
        run = dict(sd_image=sd_image, max_cycles=3_000_000_000, timeout=600)
        raw, log, _ = _v3_run_sd(config, input_text, **run)
        out = raw.replace("\r", "")
        # 2. 大きすぎる: mount とディレクトリだけ読んで「?」。$0100 の目印は残る
        assert _dos(out, "TOOBIG.COM") == "?\n", f"{profile}: $6F01 bytes must be rejected: {out[-600:]!r}"
        start, stop = _segment(raw, PROMPT + "TOOBIG.COM")
        reads = _reads(log, start, stop)
        assert 1 <= len(reads) <= 3, f"{profile}: TOOBIG.COM must not read the file data: {reads}"
        assert _reads(log, start, stop, system_only=True) == [], f"{profile}: TOOBIG.COM reloaded the system"
        marks = [_dump_bytes(_after(out[m.start():], ""), COM_MARK_ADDR)[0]
                 for m in re.finditer(rf"\] D{COM_MARK_ADDR:04X}-{COM_MARK_ADDR:04X}\n", out)]
        assert marks[0] == COM_MARK, f"{profile}: TOOBIG.COM must not write the TPA: {marks}"
        assert marks[1] == 0x39, f"{profile}: FOURK.COM should have been loaded: {marks}"
        assert _dos(out, "FOURK.COM") == "", f"{profile}: FOURK.COM: {out[-600:]!r}"
        # 1. 最大: 何も出さずに戻り、CCP のセクタだけを読み直す。続く DIR が動く
        start, stop = _segment(raw, PROMPT + "BIG.COM")
        assert raw[start:stop] == "\r\n", f"{profile}: BIG.COM should return silently: {raw[start:stop]!r}"
        big_numbers = _numbers(log, start, stop)
        system = _reads(log, start, stop, system_only=True)
        assert system == sectors["ccp"], f"{profile}: BIG.COM should reload only the CCP: {system}"
        assert "README.TXT A 00000013" in _dos(out, "DIR")
        ccp = _dump_range_bytes(_after(out, f"] {ccp_dump}\n"), V3_CCP_BASE, 16)
        assert bytes(ccp) == payload[:16], f"{profile}: CCP should be reloaded from SD: {ccp}"
        assert "\n?\n" in out and out.count("\n?\n") == 1, f"{profile}: only TOOBIG.COM should fail: {out!r}"
        assert out.count(WELCOME) == 1

        start, stop = _segment(raw, PROMPT + "FOURK.COM")
        fourk = _numbers(log, start, stop)
        assert len(fourk) >= 6, f"{profile}: FOURK.COM reads: {fourk}"
        # 3. 読み込みの 3 回目の CMD17 から失敗(mount 2 回とディレクトリ 1 回のあと)
        cases = [
            ("load 3rd read onward", dict(fail_from=fourk[3 + 2]), "FOURK.COM", 0x39, False),
            # Issue の字面どおり「コマンドの頭から 3 回目」はディレクトリの読み出し(読み込み前、C=1 で戻る)
            ("command 3rd read", dict(fail_from=fourk[2], fail_count=1), "FOURK.COM", COM_MARK, False),
            # CCP の範囲を書いたあと(最後のデータのセクタ)で 1 回だけ失敗: WBOOT が CCP を読み直す
            ("big last read", dict(fail_from=big_numbers[-len(sectors["ccp"]) - 1], fail_count=1), "BIG.COM", None, True),
        ]
        for label, kwargs, command, mark, reload in cases:
            raw, log, _ = _v3_run_sd(config, input_text, **run, **kwargs)
            out = raw.replace("\r", "")
            assert f"{PROMPT}{command}\n?\n{PROMPT}" in out, f"{profile} {label}: {out[-900:]!r}"
            start, stop = _segment(raw, PROMPT + command)
            system = _reads(log, start, stop, system_only=True)
            if reload:
                assert system == sectors["ccp"], f"{profile} {label}: should reload the CCP: {system}"
                failed = [lba for n, lba, r1, _tx in log if r1 != 0]
                assert len(failed) == 1, f"{profile} {label}: one failed read: {failed}"
                assert "README.TXT A 00000013" in _dos(out, "DIR"), f"{profile} {label}: DIR after reload"
            else:
                assert system == [], f"{profile} {label}: CCP is intact, no reload: {system}"
                marks = [_dump_bytes(_after(out[m.start():], ""), COM_MARK_ADDR)[0]
                         for m in re.finditer(rf"\] D{COM_MARK_ADDR:04X}-{COM_MARK_ADDR:04X}\n", out)]
                assert marks[1] == mark, f"{profile} {label}: $0100 = {marks[1]:02X}, want {mark:02X}"
                assert _dump_bytes(_after(out, f"] D{pending:04X}-{pending:04X}\n"), pending) == [0], (
                    f"{profile} {label}: the warm entry should clear PENDING_ERR"
                )
            assert out.count(f"{PROMPT}{command}\n?\n") == 1, f"{profile} {label}: '?' should be shown once"
            assert out.count(WELCOME) == 1, f"{profile} {label}: no cold entry"
    print("[PASS] test_com_max_size_runs_and_returns_through_reload")


STREAM_RES = 0x0400
STREAM_BUF = 0x0420
STREAM_LOAD = 0x0500
README = b"HELLO FROM README\r\n"


def _stream_com(tmp: Path) -> bytes:
    """BIOS_GET_API で表を引き、slot 2〜6 を呼んで結果を STREAM_RES に残す .COM。"""
    readme_len = len(README)
    source = f"""
        cpu     6800
BIOS_GET_API equ $E0EC
RES     equ ${STREAM_RES:04X}
BUF     equ ${STREAM_BUF:04X}
        org     $0100
        jsr     BIOS_GET_API
        ldx     $0C,x
        ldaa    4,x
        staa    VLOAD+1
        ldaa    5,x
        staa    VLOAD+2
        ldaa    6,x
        staa    VOPEN+1
        ldaa    7,x
        staa    VOPEN+2
        ldaa    8,x
        staa    VGETC+1
        ldaa    9,x
        staa    VGETC+2
        ldaa    10,x
        staa    VCLOSE+1
        ldaa    11,x
        staa    VCLOSE+2
        ldaa    12,x
        staa    VERR+1
        ldaa    13,x
        staa    VERR+2
        ldx     #NAME
        ldab    #NAME_END-NAME
        jsr     VOPEN
        tpa
        staa    RES+0
        ldx     #BUF
        stx     PTR
LOOP:   ldab    #$5A
        ldx     PTR
        jsr     VGETC
        bcs     EOF
        cmpb    #$5A
        bne     BAD
        cpx     PTR
        bne     BAD
        staa    0,x
        inx
        stx     PTR
        bra     LOOP
BAD:    ldaa    #$EE
        staa    RES+15
        rts
EOF:    tpa
        staa    RES+1
        jsr     VERR
        staa    RES+2
        ldx     PTR
        stx     RES+3
        jsr     VCLOSE
        jsr     VGETC
        tpa
        staa    RES+5
        jsr     VERR
        staa    RES+6
        ldx     #MISSING
        ldab    #MISSING_END-MISSING
        jsr     VOPEN
        tpa
        staa    RES+7
        jsr     VERR
        staa    RES+8
        ldx     #BLK1
        jsr     VLOAD
        tpa
        staa    RES+9
        stx     RES+10
        ldx     #BLK2
        jsr     VLOAD
        tpa
        staa    RES+12
        jsr     VERR
        staa    RES+13
        ldx     #BLK3
        jsr     VLOAD
        tpa
        staa    RES+14
        jsr     VERR
        staa    RES+15
        rts
VLOAD:  jmp     $0000
VOPEN:  jmp     $0000
VGETC:  jmp     $0000
VCLOSE: jmp     $0000
VERR:   jmp     $0000
PTR:    fdb     0
NAME:   fcc     "/HELLO.S"
NAME_END:
MISSING: fcc    "MISSING.S"
MISSING_END:
RNAME:  fcc     "README.TXT"
RNAME_END:
; LOAD_PATH bit0=0: exact fit / one byte short / limit above MEMTOP
BLK1:   fdb     RNAME
        fcb     RNAME_END-RNAME
        fdb     ${STREAM_LOAD:04X}
        fdb     ${STREAM_LOAD + readme_len - 1:04X}
        fcb     0
        fdb     0
        fcb     0
BLK2:   fdb     RNAME
        fcb     RNAME_END-RNAME
        fdb     ${STREAM_LOAD:04X}
        fdb     ${STREAM_LOAD + readme_len - 2:04X}
        fcb     0
        fdb     0
        fcb     0
BLK3:   fdb     RNAME
        fcb     RNAME_END-RNAME
        fdb     ${V3_MEMTOP - 0x0F:04X}
        fdb     ${V3_MEMTOP + 1:04X}
        fcb     0
        fdb     0
        fcb     0
        end
"""
    return _assemble_source(tmp, "STREAM", source)


def test_read_stream_api_from_com() -> None:
    """シナリオ 4: .COM から slot 3〜5 で HELLO.S を 1 バイトずつ読め、終わりで C=1・GET_ERROR = 0。
    CLOSE のあとの GETC と、見つからない OPEN は C=1 とコード。LOAD_PATH(bit0 = 0)は戻る。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        hello = _srec_file(0x0200, b"S")
        with _temporary_directory() as tmp:
            stream = _stream_com(Path(tmp))
        assert len(stream) < STREAM_RES - 0x0100, "STREAM.COM overlaps its result area"
        sd_image = _build_sdfs3sys_fat_sd_image(
            config["sdfs3sys"],
            [_file("HELLO.S", hello), _file("README.TXT", README), _file("STREAM.COM", stream)],
        )
        out = _v3_run(
            config,
            "BOOT3\rSTREAM.COM\rDIR\r\r",
            sd_image=sd_image,
            dump_range=f"{STREAM_RES:04X}-{STREAM_LOAD + 0x3F:04X}",
        )
        assert _dos(out, "STREAM.COM") == "", f"{profile}: STREAM.COM: {out[-600:]!r}"
        assert "README.TXT" in _dos(out, "DIR"), f"{profile}: DOS after STREAM.COM"
        # 終了時のダンプは DOS のプロンプトの直後に続くので、最後の「0400 」から読む
        dump = out[out.rindex(f"{STREAM_RES:04X} ") :]
        res = _dump_range_bytes(dump, STREAM_RES, 16)
        buf = bytes(_dump_range_bytes(dump, STREAM_BUF, len(hello)))
        loaded = bytes(_dump_range_bytes(dump, STREAM_LOAD, len(README)))
        c = lambda cc: cc & 0x01  # noqa: E731
        assert c(res[0]) == 0, f"{profile}: OPEN HELLO.S should succeed: {res}"
        assert buf == hello, f"{profile}: GETC bytes differ: {buf!r} != {hello!r}"
        assert c(res[1]) == 1 and res[2] == 0, f"{profile}: EOF should be C=1 and GET_ERROR=0: {res}"
        assert (res[3] << 8 | res[4]) == STREAM_BUF + len(hello), f"{profile}: byte count: {res}"
        assert c(res[5]) == 1 and res[6] == 9, f"{profile}: GETC after CLOSE should be C=1, code 9: {res}"
        not_found = symbols["SDFS3_ERR_NOT_FOUND"]
        assert c(res[7]) == 1 and res[8] == not_found, f"{profile}: missing OPEN should be C=1, code 4: {res}"
        assert c(res[9]) == 0 and (res[10] << 8 | res[11]) == STREAM_LOAD + len(README), (
            f"{profile}: LOAD_PATH without exec should return C=0 and X=end+1: {res}"
        )
        assert loaded == README, f"{profile}: LOAD_PATH data: {loaded!r}"
        assert c(res[12]) == 1 and res[13] == 8, f"{profile}: LOAD_PATH one byte short should be code 8: {res}"
        assert c(res[14]) == 1 and res[15] == 8, f"{profile}: LOAD_PATH above MEMTOP should be code 8: {res}"
        assert "\n?\n" not in out, f"{profile}: nothing should fail: {out!r}"
    print("[PASS] test_read_stream_api_from_com")


# ---------------------------------------------------------------------------
# #316 LOAD.COM・RUN.COM・XLDR.OVL(本体は $6800 で動く)と、暗黙の .COM の検索
# ---------------------------------------------------------------------------

WINDOW_MARK = 0xC3


def _srec_data(srec: bytes) -> dict[int, int]:
    """S1/S2 のデータを {番地: 値} にする。"""
    result: dict[int, int] = {}
    for line in srec.decode("ascii").split():
        if line[:2] not in ("S1", "S2"):
            continue
        raw = bytes.fromhex(line[2:])
        width = 2 if line[1] == "1" else 3
        address = int.from_bytes(raw[1 : 1 + width], "big")
        for i, value in enumerate(raw[1 + width : raw[0]]):
            result[address + i] = value
    return result


def _srec_to_ihex(srec: bytes) -> bytes:
    """S-record のデータを Intel HEX(00 のレコードと 01 の終わり)に写す。"""
    data = _srec_data(srec)
    lines = []
    addresses = sorted(data)
    for start in range(0, len(addresses), 16):
        chunk = addresses[start : start + 16]
        assert chunk[-1] - chunk[0] == len(chunk) - 1, "the sample must be contiguous"
        values = [len(chunk), chunk[0] >> 8, chunk[0] & 0xFF, 0x00, *(data[a] for a in chunk)]
        values.append((-sum(values)) & 0xFF)
        lines.append(":" + "".join(f"{v:02X}" for v in values))
    lines.append(":00000001FF")
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def _window_base(config: dict) -> int:
    return config["symbols"]["SDFS3_WORK_BASE"] - 0x0320


def test_xldr_load_run_and_write_range() -> None:
    """シナリオ 1〜3 と受入基準: LOAD HELLO.S のあと EXIT して D0200 で中身が見え、DOS で戻れる。
    RUN HELLO.S は HELLO を出して SWI でモニタに着く。LOAD HELLO.HEX のあと RUN 0200 で動く。
    $6800 以上・窓・$7000 へのレコードは「?」で、本体の手前($67FF)までは書ける。どの LOAD・RUN の
    あとも CCP と核は無傷で、SDFS3SYS を読み直さない(XLDR は $6800-$6BFF に収まる)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        symbols = config["symbols"]
        payload = config["sdfs3sys"][HEADER_SIZE:]
        # 本体・入口・resident が別々に持つ番地がそろっている(本体は CCP の手前で終わる)
        build = PROJECT_ROOT / "build"
        xldr = _load_symbols(build / "XLDR.lst", "XLDR_BASE", "XLDR_TOP", "XLDR_VARS_END", "X_API_MAJOR")
        stubs = [_load_symbols(build / f"{n}_COM.lst", "XLDR_BASE", "X_API_MAJOR") for n in ("LOAD", "RUN")]
        resident = _load_symbols(build / f"SDFS3{config['suffix']}.lst", "SDFS3_XLDR_BASE")
        assert xldr["XLDR_BASE"] == resident["SDFS3_XLDR_BASE"] == V3_XLDR_BASE, f"{profile}: {xldr} {resident}"
        assert all(st["XLDR_BASE"] == V3_XLDR_BASE and st["X_API_MAJOR"] == V3_API_MAJOR for st in stubs), stubs
        assert xldr["X_API_MAJOR"] == V3_API_MAJOR and xldr["XLDR_TOP"] == V3_CCP_BASE
        assert xldr["XLDR_VARS_END"] <= V3_CCP_BASE, f"XLDR overlaps the CCP: {xldr}"
        hello = _srec_data(config["hello_s"])
        first, last = min(hello), max(hello)
        assert first == 0x0200, f"HELLO.S should start at $0200: {first:04X}"
        window = _window_base(config) + 0x0C00
        core_dump = f"D{V3_CORE_BASE:04X}-{V3_CORE_BASE + 15:04X}"
        files = [
            _file("HELLO.S", config["hello_s"]),
            _file("HELLO.HEX", _srec_to_ihex(config["hello_s"])),
            _file("BAD.S", _srec_file(V3_CORE_BASE, b"\xAA\xAA\xAA\xAA", entry_address=V3_CORE_BASE)),
            _file("HI.S", _srec_file(V3_XLDR_BASE, b"\xAA")),
            _file("CROSS.S", _srec_file(V3_XLDR_BASE - 2, b"\x11\x22\x33")),
            _file("EDGE.S", _srec_file(V3_XLDR_BASE - 1, b"\x5A")),
            _file("WIN.S", _srec_file(window, b"\xAA")),
            _file("NOENTRY.HEX", _ihex_file(0x0300, b"\x39")),
            # 最後のレコードの後ろに行末がない(GETC の終わりを GET_ERROR = 0 で見分ける)
            _file("NOEOL.S", _srec_file(0x0300, b"\x77", trailing_newline=False)),
            _file("NOEOL.HEX", _ihex_file(0x0301, b"\x78", trailing_newline=False)),
            *_xldr_files(config),
        ]
        sd_image = _build_sdfs3sys_fat_sd_image(config["sdfs3sys"], files)
        bad = ["LOAD BAD.S", "LOAD HI.S", "LOAD CROSS.S", "LOAD WIN.S", "RUN NOENTRY.HEX", "LOAD MISSING.S", "RUN"]
        raw, log, _ = _v3_run_sd(
            config,
            f"M{window:04X}\r{WINDOW_MARK:02X}\r.\r"
            "BOOT3\r"
            "LOAD HELLO.S\rEXIT\r"
            f"D{first:04X}-{last:04X}\r"
            "DOS\rRUN HELLO.S\r"
            f"F{first:04X}-{last:04X} 00\r"
            "DOS\rLOAD HELLO.HEX\rRUN 0200\r"
            "DOS\r" + "".join(f"{command}\r" for command in bad) + "LOAD EDGE.S\rLOAD NOEOL.S\rLOAD NOEOL.HEX\r"
            "DIR\rEXIT\r"
            "D0300-0301\r"
            f"D{V3_XLDR_BASE - 2:04X}-{V3_XLDR_BASE - 1:04X}\r"
            f"D{window:04X}-{window:04X}\r"
            f"{core_dump}\r\r",
            sd_image=sd_image,
            max_cycles=3_000_000_000,
            timeout=600,
        )
        out = raw.replace("\r", "")
        # 1. 読み込んで残る
        assert _dos(out, "LOAD HELLO.S") == "OK\n", f"{profile}: LOAD HELLO.S: {out[-900:]!r}"
        dumped = _dump_range_bytes(_after(out, f"] D{first:04X}-{last:04X}\n"), first, last - first + 1)
        assert dumped == [hello[a] for a in range(first, last + 1)], f"{profile}: $0200 after LOAD: {dumped}"
        # 2. 読み込んで動かす(SWI でモニタへ)。2 回目は Intel HEX を読んで RUN addr
        assert out.count("\nHELLO SREC\n") == 2, f"{profile}: RUN HELLO.S / RUN 0200 should print HELLO: {out!r}"
        for command in ("RUN HELLO.S", "RUN 0200"):
            ran = _after(out, PROMPT + command + "\n")
            assert re.match(r"\s*HELLO SREC\n+BRK 0206 ", ran), f"{profile}: {command}: {ran[:200]!r}"
        assert _dos(out, "LOAD HELLO.HEX") == "OK\n"
        assert f"] DOS\n{PROMPT}LOAD HELLO.HEX" in out, f"{profile}: DOS after BRK"
        # 3. 書き込みの範囲($0000-$67FF)の外は「?」。手前までは書ける
        for command in bad:
            assert _dos(out, command) == "?\n", f"{profile}: {command} should fail: {_dos(out, command)!r}"
        assert _dos(out, "LOAD EDGE.S") == "OK\n"
        assert _dos(out, "LOAD NOEOL.S") == "OK\n" and _dos(out, "LOAD NOEOL.HEX") == "OK\n"
        assert _dump_range_bytes(_after(out, "] D0300-0301\n"), 0x0300, 2) == [0x77, 0x78], f"{profile}: NOEOL"
        edge = _dump_range_bytes(_after(out, f"] D{V3_XLDR_BASE - 2:04X}-"), V3_XLDR_BASE - 2, 2)
        assert edge == [0x11, 0x5A], f"{profile}: CROSS.S writes $67FE-$67FF before failing, EDGE.S $67FF: {edge}"
        assert _dump_bytes(_after(out, f"] D{window:04X}-"), window) == [WINDOW_MARK], f"{profile}: window written"
        core = _dump_range_bytes(_after(out, f"] {core_dump}\n"), V3_CORE_BASE, 16)
        assert bytes(core) == payload[V3_CORE_OFFSET : V3_CORE_OFFSET + 16], f"{profile}: core written: {core}"
        assert _dos(out, "DIR").count(" A ") == 10, f"{profile}: DIR after the failures: {_dos(out, 'DIR')!r}"
        # 核と CCP は無傷: どの LOAD・RUN のあとも SDFS3SYS を読み直さず、モニタの門も注意を出さない
        for command in ["LOAD HELLO.S", "LOAD HELLO.HEX", *bad, "LOAD EDGE.S", "LOAD NOEOL.S", "DIR"]:
            start, stop = _segment(raw, PROMPT + command + "\r\n")
            assert _reads(log, start, stop, system_only=True) == [], f"{profile}: {command} reloaded the system"
        for command in ("RUN HELLO.S", "RUN 0200"):
            start, stop = _segment(raw, PROMPT + command + "\r\n", end="BRK")
            assert _reads(log, start, stop, system_only=True) == [], f"{profile}: {command} reloaded the system"
        assert "*SDFS3" not in out, f"{profile}: CCP and core must stay intact: {out!r}"
        assert out.count(WELCOME) == 1
        assert out.count("\n?\n") == len(bad), f"{profile}: only the bad inputs should fail: {out!r}"
    print("[PASS] test_xldr_load_run_and_write_range")


def test_xldr_missing_or_in_root() -> None:
    """XLDR.OVL がないとき、署名が違うとき、memtop を越えるときは「?」で DOS のプロンプトに戻る。
    /BIN になくルートにあれば、ルートのものを使う。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        hello = [_file("HELLO.S", config["hello_s"])]
        cases = [
            ("none", None, "?\n"),
            ("bin", config["hello_com"], "?\n"),  # 署名 "XLDR" がない
            ("bin", b"\x39" * (V3_MEMTOP - V3_XLDR_BASE + 2), "?\n"),  # memtop を 1 バイト越える
            ("root", None, "OK\n"),
        ]
        for where, body, expected in cases:
            sd_image = _build_sdfs3sys_fat_sd_image(
                config["sdfs3sys"], [*hello, *_xldr_files(config, where=where, xldr=body)]
            )
            run = "RUN 0300\r" if expected == "?\n" else ""  # 本体があれば $0300 を起動してしまう
            out = _v3_run(
                config,
                f"BOOT3\rLOAD HELLO.S\r{run}DIR\rEXIT\rD0200-0200\r\r",
                sd_image=sd_image,
                max_cycles=1_500_000_000,
                timeout=300,
            )
            label = f"{profile} {where} {len(body) if body else '-'}"
            assert _dos(out, "LOAD HELLO.S") == expected, f"{label}: {out[-900:]!r}"
            assert "HELLO.S A " in _dos(out, "DIR"), f"{label}: DOS should keep working: {out[-900:]!r}"
            if expected == "?\n":
                assert _dos(out, "RUN 0300") == "?\n", f"{label}: RUN without the body: {out[-900:]!r}"
                assert _dump_bytes(_after(out, "] D0200-0200\n"), 0x0200) != [0xCE], f"{label}: nothing loaded"
            else:
                assert _dump_bytes(_after(out, "] D0200-0200\n"), 0x0200) == [0xCE], f"{label}: HELLO.S loaded"
            assert out.count(WELCOME) == 1 and "*SDFS3" not in out, f"{label}: {out[-900:]!r}"
    print("[PASS] test_xldr_missing_or_in_root")


def test_ccp_implicit_com_search() -> None:
    """決定 5: 拡張子のない語は <語>.COM をルート → /BIN の順に探す。ルートで見つからない
    (コード 4)ときだけ /BIN を探し、ルートで大きすぎる(コード 8)なら /BIN を探さない。
    「.COM」付きの語はそのまま(/BIN を探さない)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        sd_image = _build_sdfs3sys_fat_sd_image(
            config["sdfs3sys"],
            [
                _file("HELLO.COM", config["hello_com"]),
                _file("TOOBIG.COM", TOOBIG_COM),
                _file("HELLO.COM", _print_program(b"BIN HELLO", 0x39), ("BIN",)),
                _file("ARGS.COM", config["args_com"], ("BIN",)),
                _file("TOOBIG.COM", _print_program(b"BIN TOOBIG", 0x39), ("BIN",)),
                _file("ONLYBIN.COM", _print_program(b"ONLY IN BIN", 0x39), ("BIN",)),
            ],
        )
        commands = ["HELLO", "hello", "ARGS AAA BBB", "/BIN/HELLO", "BIN/HELLO", "NOSUCH", "TOOBIG", "ONLYBIN.COM"]
        raw, log, _ = _v3_run_sd(
            config,
            "BOOT3\r" + "".join(f"{command}\r" for command in commands) + "\r",
            sd_image=sd_image,
            max_cycles=1_500_000_000,
            timeout=300,
        )
        out = raw.replace("\r", "")
        assert "HELLO COM" in _dos(out, "HELLO") and "BIN HELLO" not in _dos(out, "HELLO"), "root comes first"
        assert "HELLO COM" in _dos(out, "hello")
        assert "ARGS AAA BBB" in _dos(out, "ARGS AAA BBB"), "falls back to /BIN with the arguments"
        assert "BIN HELLO" in _dos(out, "/BIN/HELLO") and "BIN HELLO" in _dos(out, "BIN/HELLO")
        assert _dos(out, "NOSUCH") == "?\n"
        assert _dos(out, "TOOBIG") == "?\n", "a root file that is too big must not fall back to /BIN"
        assert _dos(out, "ONLYBIN.COM") == "?\n", "an explicit .COM name is not searched in /BIN"
        assert out.count("\n?\n") == 3
        # NOSUCH はルートと /BIN を探す(mount とディレクトリを 2 回)。TOOBIG はルートだけ
        start, stop = _segment(raw, PROMPT + "NOSUCH\r\n")
        nosuch = _reads(log, start, stop)
        start, stop = _segment(raw, PROMPT + "TOOBIG\r\n")
        toobig = _reads(log, start, stop)
        assert len(nosuch) > len(toobig) >= 1, f"NOSUCH {nosuch} should read more than TOOBIG {toobig}"
    print("[PASS] test_ccp_implicit_com_search")


def test_xldr_overlapping_ccp_reloads_only_ccp() -> None:
    """シナリオ 4: CCP_BASE を $6800 に下げた試験用のイメージでは、XLDR が CCP にかぶる。
    LOAD HELLO.S の戻りで CCP のセクタだけを読み直し、動きは同じ。"""
    low_ccp = V3_XLDR_BASE
    for profile, suffix in V3_PROFILES.items():
        base = _v3(profile)
        try:
            _remake_sdfs3(profile, "sdfs3sys", [f"SDFS3_ASL_DEFS=-D SDFS3_CCP_BASE_TEST={low_ccp}"])
            lst = PROJECT_ROOT / "build" / f"SDFS3{suffix}.lst"
            symbols = _load_symbols(lst, "SDFS3_CCP_BASE", "SDFS3_CCP_END", "SDFS3_END")
            assert symbols["SDFS3_CCP_BASE"] == low_ccp, f"{profile}: test build CCP_BASE {symbols}"
            config = {**base, "sdfs3sys": (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()}
        finally:
            _remake_sdfs3(profile, "sdfs3sys")  # 通常ビルドに戻す
        assert _load_symbols(lst, "SDFS3_CCP_BASE")["SDFS3_CCP_BASE"] == V3_CCP_BASE
        restored = (PROJECT_ROOT / "build" / f"SDFS3SYS{suffix}.BIN").read_bytes()
        assert restored == base["sdfs3sys"], f"{profile}: the normal SDFS3SYS was not rebuilt"
        sectors = _system_sectors(config, ccp_base=low_ccp)
        sd_image = _build_sdfs3sys_fat_sd_image(
            config["sdfs3sys"], [_file("HELLO.S", config["hello_s"]), *_xldr_files(config)]
        )
        raw, log, _ = _v3_run_sd(
            config,
            "BOOT3\rDIR\rLOAD HELLO.S\rDIR\rEXIT\rD0200-0200\r\r",
            sd_image=sd_image,
            max_cycles=1_500_000_000,
            timeout=300,
        )
        out = raw.replace("\r", "")
        end = symbols["SDFS3_END"] - 1
        assert f"{WELCOME}\nBASE={low_ccp:04X} END={end:04X}\n" in out, f"{profile}: {out[:300]!r}"
        assert _dos(out, "LOAD HELLO.S") == "OK\n", f"{profile}: {out[-900:]!r}"
        start, stop = _segment(raw, PROMPT + "LOAD HELLO.S\r\n")
        reads = _reads(log, start, stop, system_only=True)
        assert reads == sectors["ccp"], f"{profile}: LOAD should reload only the CCP: {reads}, want {sectors['ccp']}"
        assert out.count(PROMPT + "DIR\n") == 2 and "HELLO.S A " in _dos(out[out.index("LOAD HELLO.S"):], "DIR")
        assert _dump_bytes(_after(out, "] D0200-0200\n"), 0x0200) == [0xCE]
        assert out.count(WELCOME) == 1 and "\n?\n" not in out
    print("[PASS] test_xldr_overlapping_ccp_reloads_only_ccp")


# ---------------------------------------------------------------------------
# #304 AUTOEXEC.COM(CCP の cold 入口でだけ、核の SDFS3_AUTOEXEC が LOAD_PATH の exec で起動する)
# ---------------------------------------------------------------------------

AE_MARK_ADDR = 0x0300
AE_TEXT = b"AUTOEXEC RAN"
# stab $0300 / ldx #$010A / jsr PDATA1 / rts / CR LF text CR LF EOT。B(引数の長さ)を $0300 に残す
AUTOEXEC_COM = bytes([0xF7, 0x03, 0x00, 0xCE, 0x01, 0x0A, 0xBD, 0xE0, 0x7E, 0x39,
                      0x0D, 0x0A, *AE_TEXT, 0x0D, 0x0A, 0x04])
FAT_FIRST_LBA = SDFS3SYS_FAT_PARTITION_LBA


def _ae_symbols(config: dict) -> dict[str, int]:
    """入力の保留に使う番地。ROM の CONSOLE_GETC と、CCP の cold 入口。"""
    if "ae" not in config:
        build = PROJECT_ROOT / "build"
        rom = _load_symbols(build / f"mc6800-monitor{config['suffix']}.lst", "CONSOLE_GETC")
        resident = _load_symbols(build / f"SDFS3{config['suffix']}.lst", "SDFS3_CCP_COLD")
        config["ae"] = {**rom, **resident}
    return config["ae"]


def _ae_hold(config: dict, *, key: bool = False) -> list[str]:
    """1 行ずつ保留する(CR を渡したら次の CONSOLE_GETC まで見せない)。key なら、キーボードの
    入力を CCP の cold 入口に着くまで見せない(BOOT3 の読み込み中に押した形)。"""
    symbols = _ae_symbols(config)
    args = ["--input-hold-pc", f"{symbols['CONSOLE_GETC']:04X}"]
    if key:
        args += ["--key-input-hold-pc", f"{symbols['SDFS3_CCP_COLD']:04X}"]
    return args


def _ae_sd_image(config: dict, autoexec: bytes | None) -> bytes:
    files = [_file("README.TXT", b"HELLO FROM README\r\n"), _file("HELLO.COM", config["hello_com"])]
    if autoexec is not None:
        files.append(_file("AUTOEXEC.COM", autoexec))
    return _build_sdfs3sys_fat_sd_image(config["sdfs3sys"], files)


def _cold_segment(raw: str) -> tuple[int, int]:
    """Welcome の 2 行目(BASE= END=)の行末から、最初の SDFS3> の手前までの位置。"""
    start = raw.index("\r\n", raw.index(" END=")) + 2
    return start, raw.index(PROMPT, start)


def _fat_reads(log: list, start: int, stop: int) -> list[int]:
    return [lba for lba in _reads(log, start, stop) if lba >= FAT_FIRST_LBA]


def test_autoexec_runs_once_on_cold_and_returns() -> None:
    """シナリオ 1・2: ルートの AUTOEXEC.COM は BOOT3(cold)のあと 1 回だけ動き、B=0 で起動され、
    RTS で WBOOT → CCP の warm に戻る(SDFS3SYS は読み直さない)。.COM の戻りと DOS(warm)では動かない。"""
    text = AE_TEXT.decode()
    for profile in V3_PROFILES:
        config = _v3(profile)
        input_text = (
            f"M{AE_MARK_ADDR:04X}\r55\r.\r"
            "BOOT3\rDIR\rHELLO\rEXIT\r"
            f"D{AE_MARK_ADDR:04X}-{AE_MARK_ADDR:04X}\r"
            "DOS\rDIR\rEXIT\r\r"
        )
        raw, log, _ = _v3_run_sd(
            config, input_text, sd_image=_ae_sd_image(config, AUTOEXEC_COM), extra_args=_ae_hold(config)
        )
        out = raw.replace("\r", "")
        start, stop = _cold_segment(raw)
        assert raw[start:stop] == f"\r\n{text}\r\n", f"{profile}: AUTOEXEC output: {raw[start:stop]!r}"
        assert _fat_reads(log, start, stop), f"{profile}: AUTOEXEC.COM should be read from the FAT"
        assert _reads(log, start, stop, system_only=True) == [], f"{profile}: RTS must not reload the system"
        assert out.count(text) == 1, f"{profile}: AUTOEXEC must run only on cold: {out!r}"
        assert out.count(WELCOME) == 1 and "?" not in out.replace("?S", ""), f"{profile}: {out!r}"
        assert "*SDFS3" not in out, f"{profile}: the monitor gate should not warn: {out!r}"
        assert out.count("README.TXT A 00000013") == 2, f"{profile}: DIR before and after DOS: {out!r}"
        assert "HELLO" in _dos(out, "HELLO"), f"{profile}: HELLO.COM: {out[-600:]!r}"
        mark = _dump_bytes(_after(out, f"] D{AE_MARK_ADDR:04X}-{AE_MARK_ADDR:04X}\n"), AE_MARK_ADDR)
        assert mark == [0], f"{profile}: AUTOEXEC.COM should start with B=0: {mark}"
        assert f"] DOS\n{PROMPT}DIR\n" in out, f"{profile}: DOS should enter the warm prompt: {out[-600:]!r}"
    print("[PASS] test_autoexec_runs_once_on_cold_and_returns")


def test_autoexec_absent_searches_quietly() -> None:
    """シナリオ 3: AUTOEXEC.COM がなければ、FAT を探したうえで何も出さずにプロンプトへ。LAST_ERROR = 0。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        last_error = config["symbols"]["SDFS3_LAST_ERROR"]
        input_text = f"BOOT3\rDIR\rEXIT\rD{last_error:04X}-{last_error:04X}\r\r"
        raw, log, _ = _v3_run_sd(
            config, input_text, sd_image=_ae_sd_image(config, None), extra_args=_ae_hold(config)
        )
        out = raw.replace("\r", "")
        start, stop = _cold_segment(raw)
        assert raw[start:stop] == "", f"{profile}: nothing between Welcome and the prompt: {raw[start:stop]!r}"
        assert _fat_reads(log, start, stop), f"{profile}: the cold entry should look for AUTOEXEC.COM"
        assert _reads(log, start, stop, system_only=True) == []
        assert "README.TXT A 00000013" in _dos(out, "DIR"), f"{profile}: DIR: {out[-600:]!r}"
        # 最後の D は DIR のあと。DIR も LAST_ERROR を 0 にするので、cold の直後の値は下の別の実行で見る
        assert _dump_bytes(_after(out, f"] D{last_error:04X}-{last_error:04X}\n"), last_error) == [0]
        raw, _log, _ = _v3_run_sd(
            config,
            f"BOOT3\rEXIT\rD{last_error:04X}-{last_error:04X}\r\r",
            sd_image=_ae_sd_image(config, None),
            extra_args=_ae_hold(config),
        )
        out = raw.replace("\r", "")
        assert f"{PROMPT}EXIT\n" in out, f"{profile}: {out[-600:]!r}"
        assert _dump_bytes(_after(out, f"] D{last_error:04X}-{last_error:04X}\n"), last_error) == [0], (
            f"{profile}: a missing AUTOEXEC.COM must leave LAST_ERROR = 0"
        )
    print("[PASS] test_autoexec_absent_searches_quietly")


def test_autoexec_skipped_by_pending_key() -> None:
    """シナリオ 4・5: AUTOEXEC を探す時点でコンソール(ACIA1、キーボードの ACIA2)に文字が届いて
    いれば、SD を読まずに飛ばす。文字は読まずに残り、プロンプトの最初の入力になる(Enter なら空行)。"""
    text = AE_TEXT.decode()
    for profile in V3_PROFILES:
        config = _v3(profile)
        sd_image = _ae_sd_image(config, AUTOEXEC_COM)
        cases = [
            # ACIA1: 保留しないので、BOOT3 の直後の Enter が読み込み中から届いている
            ("acia1", "BOOT3\r\rDIR\rEXIT\r\r", []),
            # キーボード: ACIA1 は 1 行ずつ保留し、キーボードの Enter は cold 入口に着くまで見せない
            ("keyboard", "BOOT3\rDIR\rEXIT\r\r", _ae_hold(config, key=True)),
        ]
        for label, input_text, extra in cases:
            if label == "keyboard":
                with tempfile.NamedTemporaryFile("wb", delete=False, dir=TEMP_ROOT) as f:
                    f.write(b"\r")
                    key_path = Path(f.name)
                extra = [*extra, "--key-input", str(key_path)]
            try:
                raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image, extra_args=extra)
            finally:
                if label == "keyboard":
                    key_path.unlink(missing_ok=True)
            out = raw.replace("\r", "")
            start, stop = _cold_segment(raw)
            assert raw[start:stop] == "", f"{profile} {label}: {raw[start:stop]!r}"
            assert _reads(log, start, stop) == [], f"{profile} {label}: a pending key must skip the SD"
            assert text not in out, f"{profile} {label}: AUTOEXEC must be skipped: {out!r}"
            assert f"{PROMPT}\n{PROMPT}DIR\n" in out, f"{profile} {label}: Enter should be an empty line: {out!r}"
            assert "README.TXT A 00000013" in _dos(out, "DIR"), f"{profile} {label}: DIR: {out[-600:]!r}"
            assert "?" not in out.replace("?S", ""), f"{profile} {label}: {out!r}"
    print("[PASS] test_autoexec_skipped_by_pending_key")


def test_autoexec_failures_show_one_error() -> None:
    """シナリオ 6: 大きすぎる AUTOEXEC.COM は読み込みの前に「?」。読み込みの途中で SD が 1 回失敗したら、
    WBOOT → warm が「?」を 1 回出す。どちらも続く DIR が動き、AUTOEXEC を繰り返さない。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        input_text = "BOOT3\rDIR\rEXIT\r\r"
        hold = _ae_hold(config)
        # 大きすぎる: 読み込みの前に C=1 → CCP が「?」
        raw, log, _ = _v3_run_sd(config, input_text, sd_image=_ae_sd_image(config, TOOBIG_COM), extra_args=hold)
        out = raw.replace("\r", "")
        start, stop = _cold_segment(raw)
        assert raw[start:stop] == "?\r\n", f"{profile} toobig: {raw[start:stop]!r}"
        assert 1 <= len(_fat_reads(log, start, stop)) <= 3, f"{profile} toobig: must not read the file data"
        assert "README.TXT A 00000013" in _dos(out, "DIR"), f"{profile} toobig: DIR: {out[-600:]!r}"
        # 4KB(先頭が RTS)は黙って戻る。その読み出しの番号から、データの途中の 1 回を失敗させる
        sd_image = _ae_sd_image(config, FOURK_COM)
        raw, log, _ = _v3_run_sd(config, input_text, sd_image=sd_image, extra_args=hold)
        start, stop = _cold_segment(raw)
        assert raw[start:stop] == "", f"{profile} fourk: {raw[start:stop]!r}"
        numbers = _numbers(log, start, stop)
        assert len(numbers) >= 6, f"{profile} fourk reads: {numbers}"
        raw, log, _ = _v3_run_sd(
            config, input_text, sd_image=sd_image, extra_args=hold, fail_from=numbers[5], fail_count=1
        )
        out = raw.replace("\r", "")
        start, stop = _cold_segment(raw)
        assert raw[start:stop] == "?\r\n", f"{profile} mid-load: {raw[start:stop]!r}"
        assert len([1 for _n, _lba, r1, _tx in log if r1 != 0]) == 1, f"{profile} mid-load: one failed read"
        assert _reads(log, start, stop, system_only=True) == [], f"{profile} mid-load: CCP is intact"
        assert out.count(WELCOME) == 1 and out.count("?\n") == 1, f"{profile} mid-load: {out!r}"
        assert "README.TXT A 00000013" in _dos(out, "DIR"), f"{profile} mid-load: DIR: {out[-600:]!r}"
    print("[PASS] test_autoexec_failures_show_one_error")


# ---------------------------------------------------------------------------
# 生成ツール(#299): make sdfs3-image / tools/mk_sdfs3_image.py が作るカード
# ---------------------------------------------------------------------------

SD_IMAGE_COMMANDS = [
    "DIR",
    "DIR /BIN",
    "TYPE README.TXT",
    "LOAD HELLO.S",
    "RUN HELLO.S",
]
SD_IMAGE_AFTER_SWI = ["HELLO.COM", "HELLO", "ARGS AAA BBB"]


def _sd_image_tool(config: dict, fat_start: int) -> bytes:
    """2048 は make sdfs3-image(Makefile の経路)で、それ以外はツールを直に呼んで作る。"""
    build = PROJECT_ROOT / "build"
    if fat_start == 2048:
        _run_make(config["profile"], "sdfs3-image")
        return (build / f"SDFS3SD{config['suffix']}.img").read_bytes()
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    output = TEMP_ROOT / f"sdfs3sd-{uuid4().hex}.img"
    try:
        result = subprocess.run(
            [
                sys.executable, str(PROJECT_ROOT / "tools" / "mk_sdfs3_image.py"),
                "--system", str(build / f"SDFS3SYS{config['suffix']}.BIN"),
                "--output", str(output), "--fat-start", str(fat_start), "--tools-dir", str(build),
                f"README.TXT={build / 'README.TXT'}", f"HELLO.S={build / 'HELLO.S'}",
                f"HELLO.COM={build / 'HELLO.COM'}", f"ARGS.COM={build / 'ARGS.COM'}",
            ],
            capture_output=True, text=True, timeout=60,
        )
        assert result.returncode == 0, f"mk_sdfs3_image failed: {result.stderr}"
        return output.read_bytes()
    finally:
        output.unlink(missing_ok=True)


def test_sd_image_tool_boots_and_runs_dos_commands() -> None:
    """受入基準: 生成ツールのカードで BOOT3 → DIR → LOAD HELLO.S → RUN HELLO.S → HELLO.COM が通る。
    BOOT3 は marker(48)と slot A だけを読み(96 は読まない)、slot A から起動する。FAT32 の開始は
    既定の 2048(make sdfs3-image)と、今のカードの 128(--fat-start 128)。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        _run_make(profile, "sdfs3-image")  # build/README.TXT を作る
        readme = (PROJECT_ROOT / "sdfs_tools" / "SDCARD.TXT").read_text(encoding="ascii")
        for fat_start in (2048, 128):
            image = _sd_image_tool(config, fat_start)
            # 置いたもの: MBR の区画、marker、世代 1 の slot A、空の slot B と stage1 領域
            assert int.from_bytes(image[446 + 8 : 446 + 12], "little") == fat_start
            assert image[SDFS3MRK_LBA * SECTOR_SIZE : (SDFS3MRK_LBA + 1) * SECTOR_SIZE] == _marker(0)
            slot_a = _slot_image(config, 1)
            assert image[SLOT_A_LBA * SECTOR_SIZE : SLOT_A_LBA * SECTOR_SIZE + len(slot_a)] == slot_a
            assert not any(image[SLOT_B_LBA * SECTOR_SIZE : SDFS3SYS_FAT_PARTITION_LBA * SECTOR_SIZE])
            assert not any(image[16 * SECTOR_SIZE : SDFS3MRK_LBA * SECTOR_SIZE])
            extra = "".join(f"{c}\r" for c in SD_IMAGE_COMMANDS) + "DOS\r" + "".join(f"{c}\r" for c in SD_IMAGE_AFTER_SWI)
            raw, _log, boot_reads, slot_lba = _boot3_slot(config, image, extra)
            out = raw.replace("\r", "")
            where = f"{profile} fat={fat_start}"
            assert boot_reads == [SDFS3MRK_LBA, *_system_sectors(config)["all"]], f"{where}: BOOT3 read {boot_reads}"
            assert slot_lba == SLOT_A_LBA, f"{where}: BB_SLOT_LBA={slot_lba}"
            assert out.count(WELCOME) == 1, f"{where}: {out[-800:]!r}"
            root = _dos(out, "DIR")
            for line in ("README.TXT A ", "HELLO.S A ", "HELLO.COM A ", "ARGS.COM A ", "BIN D "):
                assert line in root, f"{where}: DIR missing {line!r}: {root!r}"
            listing = _dos(out, "DIR /BIN")
            assert all(f"{n} A " in listing for n in ("LOAD.COM", "RUN.COM", "XLDR.OVL")), f"{where}: {listing!r}"
            typed = _dos(out, "TYPE README.TXT")
            assert all(line in typed for line in readme.splitlines()), f"{where}: TYPE: {typed!r}"
            assert _dos(out, "LOAD HELLO.S") == "OK\n", f"{where}: LOAD: {out[-800:]!r}"
            ran = _after(out, PROMPT + "RUN HELLO.S\n")
            assert re.match(r"\s*HELLO SREC\n+BRK 0206 ", ran), f"{where}: RUN HELLO.S: {ran[:200]!r}"
            assert f"] DOS\n{PROMPT}HELLO.COM\n" in out, f"{where}: DOS after BRK"
            assert "HELLO COM" in _dos(out, "HELLO.COM") and "HELLO COM" in _dos(out, "HELLO")
            assert "ARGS AAA BBB" in _dos(out, "ARGS AAA BBB"), f"{where}: ARGS"
            assert "\n?" not in out, f"{where}: no command should fail: {out!r}"
    print("[PASS] test_sd_image_tool_boots_and_runs_dos_commands")


def test_sd_image_tool_first_update_survives_marker_loss() -> None:
    """#302 の残件: 生成したカードの slot A は世代 1。最初の更新で slot B(世代 2)を書いたあと
    marker の書き込みが途中で切れても(48 が 0)、ROM は世代を比べて B から起動する。"""
    for profile in V3_PROFILES:
        config = _v3(profile)
        image = bytearray(_sd_image_tool(config, 2048))
        slot_b = _slot_image(config, 2, tag=SLOT_TAG)
        image[SLOT_B_LBA * SECTOR_SIZE : SLOT_B_LBA * SECTOR_SIZE + len(slot_b)] = slot_b
        image[SDFS3MRK_LBA * SECTOR_SIZE : (SDFS3MRK_LBA + 1) * SECTOR_SIZE] = bytes(SECTOR_SIZE)
        raw, _log, boot_reads, slot_lba = _boot3_slot(config, bytes(image), "DIR\r")
        out = raw.replace("\r", "")
        want = [SDFS3MRK_LBA, SLOT_A_LBA, SLOT_B_LBA, *_system_sectors(config, SLOT_B_LBA)["all"]]
        assert boot_reads == want, f"{profile}: BOOT3 read {boot_reads}, want {want}"
        assert slot_lba == SLOT_B_LBA, f"{profile}: should boot slot B: BB_SLOT_LBA={slot_lba}"
        assert "BIN D " in _dos(out, "DIR"), f"{profile}: {out[-600:]!r}"
    print("[PASS] test_sd_image_tool_first_update_survives_marker_loss")


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
        test_sdfs3_resident_calls_rom_sd_entries,
        test_sdfs3_commands_match_output_with_rom_sd_driver,
        test_sdfs3_sd_access_goes_through_bios_table,
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
        test_boot3_marker_slot_and_wboot_reload_from_it,
        test_boot3_invalid_marker_falls_back_to_generation,
        test_boot3_generation_picks_first_slot,
        test_boot3_falls_back_from_bad_active_slot,
        test_boot3_error_codes_name_each_slot,
        test_wboot_error_codes_name_the_cause,
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
        test_read_stream_api_from_com,
        test_com_max_size_runs_and_returns_through_reload,
        test_xldr_load_run_and_write_range,
        test_xldr_missing_or_in_root,
        test_ccp_implicit_com_search,
        test_xldr_overlapping_ccp_reloads_only_ccp,
        test_autoexec_runs_once_on_cold_and_returns,
        test_autoexec_absent_searches_quietly,
        test_autoexec_skipped_by_pending_key,
        test_autoexec_failures_show_one_error,
        test_sd_image_tool_boots_and_runs_dos_commands,
        test_sd_image_tool_first_update_survives_marker_loss,
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
