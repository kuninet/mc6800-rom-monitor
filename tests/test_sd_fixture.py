#!/usr/bin/env python3
"""SD/PIA emulator fixture tests."""

from __future__ import annotations

import os
import re
import sys
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "emu"))
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"


def _default_build_stem() -> str:
    suffix_by_profile = {
        "base": "",
        "sbcio": "-sbcio",
        "sbcio_vdg": "-sbcio-vdg",
        "k6802_vdg": "-k6802-vdg",
        "sbcio_4000": "-sbcio-4000",
        "k6802_4000": "-k6802-4000",
    }
    suffix = suffix_by_profile.get(os.environ.get("MONITOR_PROFILE", "base"), "")
    return f"mc6800-monitor{suffix}"


DEFAULT_BUILD_ROM_PATH = PROJECT_ROOT / "build" / f"{_default_build_stem()}.bin"
DEFAULT_BUILD_LST_PATH = PROJECT_ROOT / "build" / f"{_default_build_stem()}.lst"


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


BUILD_ROM_PATH = _path_from_env("MONITOR_ROM_PATH", DEFAULT_BUILD_ROM_PATH)
if os.environ.get("MONITOR_LST_PATH"):
    BUILD_LST_PATH = _path_from_env("MONITOR_LST_PATH", DEFAULT_BUILD_LST_PATH)
elif os.environ.get("MONITOR_ROM_PATH"):
    BUILD_LST_PATH = BUILD_ROM_PATH.with_suffix(".lst")
else:
    BUILD_LST_PATH = DEFAULT_BUILD_LST_PATH

from sbc6800_emu import PIA, PIA_CRB, PIA_PRB, SDCard, SPI_CS, SPI_MISO, SPI_MOSI, SPI_SCLK
from sd_fixtures import (
    EOC,
    BIG_S_CLUSTER_1,
    BIG_S_CONTENT,
    LATE_BIN_CLUSTER,
    LATE_BIN_CONTENT,
    MULTI_CLUSTER_1,
    MULTI_CLUSTER_1_PREFIX,
    MULTI_CLUSTER_2,
    MULTI_CLUSTER_2_PREFIX,
    PARTITION_START_LBA,
    ROOT_CLUSTER,
    ROOT_EXTRA_CLUSTER,
    SECTOR_SIZE,
    TEST_HEX_CLUSTER,
    TEST_HEX_CONTENT,
    TEST_S_CLUSTER,
    TEST_S_CONTENT,
    build_fat32_image,
    layout_for_image,
    sector,
)
from mk_sdfs_image import build_sdfs_image


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def fat_entry(fat: bytes, cluster: int) -> int:
    return u32(fat, cluster * 4) & 0x0FFFFFFF


def entry_cluster(entry: bytes) -> int:
    return (u16(entry, 20) << 16) | u16(entry, 26)


def assert_common_bpb(image: bytes, volume_lba: int, sectors_per_cluster: int = 1) -> None:
    bpb = sector(image, volume_lba)
    assert bpb[510:512] == b"\x55\xAA", "missing BPB signature"
    assert u16(bpb, 11) == SECTOR_SIZE, "unexpected bytes per sector"
    assert bpb[13] == sectors_per_cluster, "unexpected sectors per cluster"
    assert u16(bpb, 14) == 4, "unexpected reserved sector count"
    assert bpb[16] == 2, "unexpected FAT count"
    assert u16(bpb, 17) == 0, "FAT32 root entry count must be zero"
    assert u32(bpb, 36) == 1, "unexpected FAT32 FAT size"
    assert u32(bpb, 44) == ROOT_CLUSTER, "unexpected root cluster"
    assert bpb[82:90] == b"FAT32   ", "missing FAT32 label"


def assert_root_directory(image: bytes, with_mbr: bool) -> None:
    layout = layout_for_image(with_mbr)
    root = sector(image, layout.root_dir_lba)
    assert root[0:11] == b"TEST    S  ", "TEST.S entry missing"
    assert u32(root, 28) == len(TEST_S_CONTENT), "TEST.S size mismatch"
    assert root[32:43] == b"TEST    HEX", "TEST.HEX entry missing"
    assert u32(root, 32 + 28) == len(TEST_HEX_CONTENT), "TEST.HEX size mismatch"
    assert root[64:75] == b"MULTI   BIN", "MULTI.BIN entry missing"
    assert entry_cluster(root[64:96]) == MULTI_CLUSTER_1, "MULTI.BIN first cluster mismatch"
    assert u32(root, 64 + 28) == SECTOR_SIZE * 2, "MULTI.BIN size mismatch"

    fat = sector(image, layout.fat_lba)
    assert fat_entry(fat, ROOT_CLUSTER) == EOC, "root cluster must be EOC"
    assert fat_entry(fat, TEST_S_CLUSTER) == EOC, "TEST.S cluster must be EOC"
    assert fat_entry(fat, TEST_HEX_CLUSTER) == EOC, "TEST.HEX cluster must be EOC"
    assert fat_entry(fat, MULTI_CLUSTER_1) == MULTI_CLUSTER_2, "MULTI.BIN chain must start 5 -> 6"
    assert fat_entry(fat, MULTI_CLUSTER_2) == EOC, "MULTI.BIN chain must end at EOC"

    assert sector(image, layout.cluster_lba(TEST_S_CLUSTER)).startswith(TEST_S_CONTENT)
    assert sector(image, layout.cluster_lba(TEST_HEX_CLUSTER)).startswith(TEST_HEX_CONTENT)
    assert sector(image, layout.cluster_lba(MULTI_CLUSTER_1)).startswith(MULTI_CLUSTER_1_PREFIX)
    assert sector(image, layout.cluster_lba(MULTI_CLUSTER_2)).startswith(MULTI_CLUSTER_2_PREFIX)


def assert_chained_root_directory(image: bytes, with_mbr: bool) -> None:
    layout = layout_for_image(with_mbr)
    root = sector(image, layout.root_dir_lba)
    assert root[96] != 0x00, "first root cluster should not terminate when chained"
    extra_root = sector(image, layout.cluster_lba(ROOT_EXTRA_CLUSTER))
    assert extra_root[0:11] == b"LATE    BIN", "LATE.BIN entry missing in chained root"
    assert entry_cluster(extra_root[0:32]) == LATE_BIN_CLUSTER
    assert u32(extra_root, 28) == len(LATE_BIN_CONTENT)
    fat = sector(image, layout.fat_lba)
    assert fat_entry(fat, ROOT_CLUSTER) == ROOT_EXTRA_CLUSTER
    assert fat_entry(fat, ROOT_EXTRA_CLUSTER) == EOC
    assert fat_entry(fat, LATE_BIN_CLUSTER) == EOC


def sd_command(card: SDCard, cmd: int, arg: int = 0, crc: int = 0xFF, extra: int = 0) -> list[int]:
    frame = [
        0x40 | cmd,
        (arg >> 24) & 0xFF,
        (arg >> 16) & 0xFF,
        (arg >> 8) & 0xFF,
        arg & 0xFF,
        crc,
    ]
    for byte in frame:
        card.transfer_byte(byte)
    response = _poll_response(lambda: card.transfer_byte(0xFF))
    return [response] + [card.transfer_byte(0xFF) for _ in range(extra)]


def sd_read_sector(card: SDCard, lba: int) -> bytes:
    response = sd_command(card, 17, lba)
    assert response == [0x00], f"CMD17 failed: {response!r}"
    _poll_until(lambda: card.transfer_byte(0xFF), 0xFE)
    payload = bytes(card.transfer_byte(0xFF) for _ in range(SECTOR_SIZE))
    card.transfer_byte(0xFF)
    card.transfer_byte(0xFF)
    return payload


def pia_setup(pia: PIA) -> None:
    outputs = SPI_SCLK | SPI_MOSI | SPI_CS
    pia.write(PIA_CRB, 0x00)
    pia.write(PIA_PRB, outputs)
    pia.write(PIA_CRB, 0x04)
    pia.write(PIA_PRB, SPI_CS)


def pia_select(pia: PIA) -> None:
    pia.write(PIA_PRB, 0x00)


def pia_deselect(pia: PIA) -> None:
    pia.write(PIA_PRB, SPI_CS)


def pia_spi_transfer(pia: PIA, value: int) -> int:
    read_value = 0
    for bit in range(7, -1, -1):
        mosi = SPI_MOSI if value & (1 << bit) else 0
        pia.write(PIA_PRB, mosi)
        pia.write(PIA_PRB, mosi | SPI_SCLK)
        if pia.read(PIA_PRB) & SPI_MISO:
            read_value |= 1 << bit
        pia.write(PIA_PRB, mosi)
    return read_value


def pia_command(pia: PIA, cmd: int, arg: int = 0, crc: int = 0xFF, extra: int = 0) -> list[int]:
    frame = [
        0x40 | cmd,
        (arg >> 24) & 0xFF,
        (arg >> 16) & 0xFF,
        (arg >> 8) & 0xFF,
        arg & 0xFF,
        crc,
    ]
    for byte in frame:
        pia_spi_transfer(pia, byte)
    response = _poll_response(lambda: pia_spi_transfer(pia, 0xFF))
    return [response] + [pia_spi_transfer(pia, 0xFF) for _ in range(extra)]


def pia_read_sector(pia: PIA, lba: int) -> bytes:
    response = pia_command(pia, 17, lba)
    assert response == [0x00], f"PIA CMD17 failed: {response!r}"
    _poll_until(lambda: pia_spi_transfer(pia, 0xFF), 0xFE)
    payload = bytes(pia_spi_transfer(pia, 0xFF) for _ in range(SECTOR_SIZE))
    pia_spi_transfer(pia, 0xFF)
    pia_spi_transfer(pia, 0xFF)
    return payload


def _poll_response(read_byte) -> int:
    for _ in range(16):
        value = read_byte()
        if value != 0xFF:
            return value
    raise AssertionError("SD response timeout")


def _poll_until(read_byte, expected: int) -> int:
    for _ in range(32):
        value = read_byte()
        if value == expected:
            return value
    raise AssertionError(f"SD byte {expected:02X} timeout")


def _load_symbol_addresses(*names: str) -> dict[str, int]:
    text = BUILD_LST_PATH.read_text(encoding="utf-8", errors="replace")
    result: dict[str, int] = {}
    wanted = set(names)
    symbol_patterns = {
        name: [
            re.compile(rf"\b{re.escape(name)}\s*:\s*([0-9A-Fa-f]{{1,4}})\b"),
            re.compile(rf"/([0-9A-Fa-f]{{1,4}})\s*:\s+.*\b{re.escape(name)}:\s*$"),
            re.compile(rf":\s*=\$([0-9A-Fa-f]{{1,4}})\s+{re.escape(name)}\s+equ\b"),
            re.compile(rf":\s*=([0-9A-Fa-f]{{1,4}})\s+{re.escape(name)}\s+equ\b"),
        ]
        for name in names
    }
    for name, patterns in symbol_patterns.items():
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                result[name] = int(match.group(1), 16)
                break
    missing = wanted - set(result)
    if missing:
        raise AssertionError(f"missing symbols in listing: {sorted(missing)}")
    return result


def _is_sbcio_4000_build() -> bool:
    if os.environ.get("MONITOR_PROFILE") == "sbcio_4000":
        return True
    return "-sbcio-4000" in BUILD_ROM_PATH.stem


def _is_k6802_4000_build() -> bool:
    if os.environ.get("MONITOR_PROFILE") == "k6802_4000":
        return True
    return "-k6802-4000" in BUILD_ROM_PATH.stem


def _is_sbcio_build() -> bool:
    if os.environ.get("BOARD_IO") in ("none", "sbcio"):
        return os.environ["BOARD_IO"] == "sbcio"
    return (
        "-sbcio" in BUILD_ROM_PATH.stem
        or "-k6802-vdg" in BUILD_ROM_PATH.stem
        or _is_sbcio_4000_build()
        or _is_k6802_4000_build()
        or os.environ.get("MONITOR_PROFILE") in ("sbcio", "sbcio_vdg", "k6802_vdg", "sbcio_4000", "k6802_4000")
    )


def _is_vdg_build() -> bool:
    if os.environ.get("FEATURE_VDG") in ("0", "1"):
        return os.environ["FEATURE_VDG"] == "1"
    return (
        "-sbcio-vdg" in BUILD_ROM_PATH.stem
        or "-k6802-vdg" in BUILD_ROM_PATH.stem
        or os.environ.get("MONITOR_PROFILE") in ("sbcio_vdg", "k6802_vdg")
    )


def _is_k6802_vdg_build() -> bool:
    if os.environ.get("MEMORY_CONFIG") == "ram64_a000_work" and os.environ.get("FEATURE_VDG") == "1":
        return os.environ.get("VDG_VRAM_CONFIG", "c000") == "c000"
    return "-k6802-vdg" in BUILD_ROM_PATH.stem or os.environ.get("MONITOR_PROFILE") == "k6802_vdg"


def _is_ram64_4000_work_build() -> bool:
    if os.environ.get("MEMORY_CONFIG") == "ram64_4000_work":
        return True
    return _is_sbcio_4000_build() or _is_k6802_4000_build() or "-ram64_4000_work-" in BUILD_ROM_PATH.stem


def _is_sd_build() -> bool:
    if os.environ.get("FEATURE_SD") in ("0", "1"):
        return os.environ["FEATURE_SD"] == "1"
    profile = os.environ.get("MONITOR_PROFILE")
    if profile in ("sbcio_vdg", "k6802_vdg", "sbcio_4000", "k6802_4000"):
        return True
    if profile in ("base", "sbcio"):
        return False
    stem = BUILD_ROM_PATH.stem
    return "-sbcio-vdg" in stem or "-k6802-vdg" in stem or "-sbcio-4000" in stem or "-k6802-4000" in stem or "-sd1-" in stem


def _is_fat_build() -> bool:
    if os.environ.get("FEATURE_FAT") in ("0", "1"):
        return os.environ["FEATURE_FAT"] == "1"
    return False


def _is_s1_boot_build() -> bool:
    return _is_sd_build()


def _run_emu_with_sd(input_text: str, sd_image: bytes, max_cycles: int = 30_000_000) -> tuple[str, str, int]:
    if not BUILD_ROM_PATH.exists() or not BUILD_LST_PATH.exists():
        raise AssertionError("build output missing; run `make bin` first")

    input_bytes = input_text.encode("ascii")
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as input_file:
        input_file.write(input_bytes)
        input_path = Path(input_file.name)
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as sd_file:
        sd_file.write(sd_image)
        sd_path = Path(sd_file.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(EMU_PATH),
                str(BUILD_ROM_PATH),
                "--input",
                str(input_path),
                "--max-cycles",
                str(max_cycles),
                "--sd",
                str(sd_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            cwd=PROJECT_ROOT,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        return exc.stdout or "", (exc.stderr or "") + "[TIMEOUT]", -1
    finally:
        input_path.unlink(missing_ok=True)
        sd_path.unlink(missing_ok=True)


def _hex_bytes(values: list[int]) -> str:
    return "\r".join(f"{value:02X}" for value in values)


def _parse_dump_bytes(stdout: str, address: int) -> list[int]:
    values: list[int] = []
    current = address
    while True:
        try:
            line = _dump_line(stdout, current)
        except AssertionError:
            break
        fields = line.split()
        line_values: list[int] = []
        for field in fields[1:17]:
            try:
                line_values.append(int(field, 16))
            except ValueError:
                break
        if not line_values:
            break
        values.extend(line_values)
        current += len(line_values)
    return values


def _dump_line(stdout: str, address: int) -> str:
    marker = f"{address:04X}"
    for line in stdout.splitlines():
        if line.lstrip().startswith(marker):
            return line
    raise AssertionError(f"missing dump line {marker}: {stdout!r}")


def test_mbr_fat32_fixture_layout() -> None:
    image = build_fat32_image(with_mbr=True)
    mbr = sector(image, 0)
    assert mbr[510:512] == b"\x55\xAA", "missing MBR signature"
    assert mbr[450] == 0x0C, "partition type must be FAT32 LBA"
    assert u32(mbr, 454) == PARTITION_START_LBA, "partition start LBA mismatch"
    assert_common_bpb(image, PARTITION_START_LBA)
    assert_root_directory(image, with_mbr=True)
    print("[PASS] test_mbr_fat32_fixture_layout")


def test_superfloppy_fat32_fixture_layout() -> None:
    image = build_fat32_image(with_mbr=False)
    assert_common_bpb(image, 0)
    assert_root_directory(image, with_mbr=False)
    print("[PASS] test_superfloppy_fat32_fixture_layout")


def test_chained_root_fat32_fixture_layout() -> None:
    image = build_fat32_image(with_mbr=True, root_chain=True)
    assert_common_bpb(image, PARTITION_START_LBA)
    assert_chained_root_directory(image, with_mbr=True)
    print("[PASS] test_chained_root_fat32_fixture_layout")


def test_multisector_cluster_fixture_layout() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    layout = layout_for_image(with_mbr=True, sectors_per_cluster=6)
    assert_common_bpb(image, PARTITION_START_LBA, sectors_per_cluster=6)
    assert layout.cluster_lba(MULTI_CLUSTER_1) == layout.data_start_lba + (MULTI_CLUSTER_1 - 2) * 6
    assert sector(image, layout.cluster_lba(TEST_S_CLUSTER)).startswith(TEST_S_CONTENT)
    assert sector(image, layout.cluster_lba(MULTI_CLUSTER_1)).startswith(MULTI_CLUSTER_1_PREFIX)
    assert sector(image, layout.cluster_lba(MULTI_CLUSTER_1) + 1).startswith(MULTI_CLUSTER_2_PREFIX)
    assert sector(image, layout.cluster_lba(BIG_S_CLUSTER_1)).startswith(BIG_S_CONTENT[:16])
    assert sector(image, layout.cluster_lba(BIG_S_CLUSTER_1) + 1).startswith(BIG_S_CONTENT[SECTOR_SIZE:SECTOR_SIZE + 16])
    print("[PASS] test_multisector_cluster_fixture_layout")


def test_sdcard_command_sequence_reads_known_sector() -> None:
    image = build_fat32_image(with_mbr=True)
    layout = layout_for_image(with_mbr=True)
    card = SDCard(image)
    assert sd_command(card, 0, 0, 0x95) == [0x01], "CMD0 response mismatch"
    assert sd_command(card, 8, 0x000001AA, 0x87, extra=4) == [0x01, 0x00, 0x00, 0x01, 0xAA]
    assert sd_command(card, 55) == [0x01], "CMD55 response mismatch"
    assert sd_command(card, 41, 0x40000000) == [0x00], "ACMD41 response mismatch"
    assert sd_command(card, 58, extra=4) == [0x00, 0x40, 0x00, 0x00, 0x00]
    assert sd_read_sector(card, layout.cluster_lba(MULTI_CLUSTER_1)).startswith(MULTI_CLUSTER_1_PREFIX)
    print("[PASS] test_sdcard_command_sequence_reads_known_sector")


def test_sdcard_cs_release_discards_pending_response() -> None:
    image = build_fat32_image(with_mbr=True)
    card = SDCard(image)
    frame = [0x40, 0x00, 0x00, 0x00, 0x00, 0x95]
    for byte in frame:
        card.transfer_byte(byte)
    card.transfer_byte(0xFF, selected=False)
    assert card.transfer_byte(0xFF) == 0xFF, "CS release should discard pending CMD0 response"
    print("[PASS] test_sdcard_cs_release_discards_pending_response")


def test_pia_bitbang_reads_known_sector() -> None:
    image = build_fat32_image(with_mbr=True)
    layout = layout_for_image(with_mbr=True)
    pia = PIA(SDCard(image))
    pia_setup(pia)
    pia_select(pia)
    assert pia_command(pia, 0, 0, 0x95) == [0x01], "PIA CMD0 response mismatch"
    assert pia_command(pia, 8, 0x000001AA, 0x87, extra=4) == [0x01, 0x00, 0x00, 0x01, 0xAA]
    assert pia_command(pia, 55) == [0x01], "PIA CMD55 response mismatch"
    assert pia_command(pia, 41, 0x40000000) == [0x00], "PIA ACMD41 response mismatch"
    assert pia_command(pia, 58, extra=4) == [0x00, 0x40, 0x00, 0x00, 0x00]
    assert pia_read_sector(pia, layout.cluster_lba(MULTI_CLUSTER_2)).startswith(MULTI_CLUSTER_2_PREFIX)
    pia_deselect(pia)
    print("[PASS] test_pia_bitbang_reads_known_sector")


def test_rom_sd_read_sector_reads_known_fixture_sector() -> None:
    if not _is_sd_build():
        print("[SKIP] test_rom_sd_read_sector_reads_known_fixture_sector")
        return

    image = build_fat32_image(with_mbr=True)
    layout = layout_for_image(with_mbr=True)
    symbols = _load_symbol_addresses(
        "SD_INIT",
        "SD_READ_SECTOR",
        "SD_LBA0",
        "SD_LBA1",
        "SD_LBA2",
        "SD_LBA3",
        "SD_SECTOR_BUF",
    )
    lba = layout.cluster_lba(MULTI_CLUSTER_1)
    harness_addr = 0x0100
    fail_offset = 0x1B
    harness = [
        0xBD, (symbols["SD_INIT"] >> 8) & 0xFF, symbols["SD_INIT"] & 0xFF,
        0x25, fail_offset,
        0x86, (lba >> 24) & 0xFF, 0xB7, (symbols["SD_LBA0"] >> 8) & 0xFF, symbols["SD_LBA0"] & 0xFF,
        0x86, (lba >> 16) & 0xFF, 0xB7, (symbols["SD_LBA1"] >> 8) & 0xFF, symbols["SD_LBA1"] & 0xFF,
        0x86, (lba >> 8) & 0xFF, 0xB7, (symbols["SD_LBA2"] >> 8) & 0xFF, symbols["SD_LBA2"] & 0xFF,
        0x86, lba & 0xFF, 0xB7, (symbols["SD_LBA3"] >> 8) & 0xFF, symbols["SD_LBA3"] & 0xFF,
        0xCE, (symbols["SD_SECTOR_BUF"] >> 8) & 0xFF, symbols["SD_SECTOR_BUF"] & 0xFF,
        0xBD, (symbols["SD_READ_SECTOR"] >> 8) & 0xFF, symbols["SD_READ_SECTOR"] & 0xFF,
        0x3F,
        0x3F,
    ]
    input_text = (
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{symbols['SD_SECTOR_BUF']:04X}-{symbols['SD_SECTOR_BUF'] + 0x0F:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(input_text, image)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    line = _dump_line(stdout, symbols["SD_SECTOR_BUF"])
    expected = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_1_PREFIX[:16])
    assert expected in line, f"sector prefix mismatch: {line!r}\nstdout={stdout!r}"
    print("[PASS] test_rom_sd_read_sector_reads_known_fixture_sector")


def test_rom_profile_memory_layout() -> None:
    names = [
        "MONITOR_FEATURE_SD",
        "MONITOR_FEATURE_FAT",
        "MONITOR_RAM_BASE",
        "USER_RAM_END",
        "WORK_RAM_START",
        "WORK_RAM_END",
        "MONITOR_FEATURE_VDG",
    ]
    if _is_sd_build():
        names.extend(["SD_SECTOR_BUF", "FAT_SECTOR_IN_CLUS"])
    if _is_vdg_build():
        names.extend(["VDG_CTL", "VDG_VRAM_START", "VDG_VRAM_END"])
    symbols = _load_symbol_addresses(*names)
    if _is_ram64_4000_work_build():
        expected_sector_buf = 0xA000 if (_is_k6802_4000_build() or (_is_vdg_build() and os.environ.get("VDG_VRAM_CONFIG", "a000") == "c000")) else 0xC000
        expected_monitor_base = 0x4200
        expected_user_ram_end = 0x3FFF
        expected_work_start = 0x4000
        expected_work_end = 0x7FFF
    elif _is_k6802_vdg_build():
        expected_sector_buf = 0xA000
        expected_monitor_base = 0xA200
        expected_user_ram_end = 0x7FFF
        expected_work_start = 0xA000
        expected_work_end = 0xBFFF
    elif _is_sbcio_build():
        expected_sector_buf = 0xC000
        expected_monitor_base = 0xC200
        expected_user_ram_end = 0x7FFF
        expected_work_start = 0xC000
        expected_work_end = 0xDFFF
    else:
        expected_sector_buf = 0x1C00
        expected_monitor_base = 0x1E00
        expected_user_ram_end = 0x1FFF
        expected_work_start = 0x1C00
        expected_work_end = 0x1FFF

    assert symbols["MONITOR_FEATURE_SD"] == (1 if _is_sd_build() else 0), "SD feature flag mismatch"
    assert symbols["MONITOR_FEATURE_FAT"] == (1 if _is_fat_build() else 0), "FAT feature flag mismatch"
    if _is_sd_build():
        assert symbols["SD_SECTOR_BUF"] == expected_sector_buf, (
            f"SD_SECTOR_BUF mismatch: got={symbols['SD_SECTOR_BUF']:04X} "
            f"expected={expected_sector_buf:04X}"
        )
    assert symbols["MONITOR_RAM_BASE"] == expected_monitor_base, (
        f"MONITOR_RAM_BASE mismatch: got={symbols['MONITOR_RAM_BASE']:04X} "
        f"expected={expected_monitor_base:04X}"
    )
    assert symbols["USER_RAM_END"] == expected_user_ram_end, (
        f"USER_RAM_END mismatch: got={symbols['USER_RAM_END']:04X} "
        f"expected={expected_user_ram_end:04X}"
    )
    assert symbols["WORK_RAM_START"] == expected_work_start, (
        f"WORK_RAM_START mismatch: got={symbols['WORK_RAM_START']:04X} "
        f"expected={expected_work_start:04X}"
    )
    assert symbols["WORK_RAM_END"] == expected_work_end, (
        f"WORK_RAM_END mismatch: got={symbols['WORK_RAM_END']:04X} "
        f"expected={expected_work_end:04X}"
    )
    if _is_sd_build():
        assert symbols["WORK_RAM_START"] <= symbols["SD_SECTOR_BUF"] <= symbols["WORK_RAM_END"]
    assert symbols["WORK_RAM_START"] <= symbols["MONITOR_RAM_BASE"] <= symbols["WORK_RAM_END"]
    if _is_sd_build():
        assert symbols["SD_SECTOR_BUF"] + SECTOR_SIZE <= symbols["MONITOR_RAM_BASE"], (
            "SD sector buffer must not overlap monitor work area"
        )
    if _is_vdg_build():
        expected_vram_start = 0xC000 if _is_k6802_vdg_build() else 0xA000
        expected_vram_end = 0xDFFF if _is_k6802_vdg_build() else 0xBFFF
        assert symbols["MONITOR_FEATURE_VDG"] == 1, "VDG profiles must enable VDG feature"
        assert symbols["VDG_CTL"] == 0x8110, "VDG control register must use K68-VDG address"
        assert symbols["VDG_VRAM_START"] == expected_vram_start, (
            f"K68-VDG VRAM start mismatch: got={symbols['VDG_VRAM_START']:04X} "
            f"expected={expected_vram_start:04X}"
        )
        assert symbols["VDG_VRAM_END"] == expected_vram_end, (
            f"K68-VDG VRAM end mismatch: got={symbols['VDG_VRAM_END']:04X} "
            f"expected={expected_vram_end:04X}"
        )
        assert (
            symbols["VDG_VRAM_END"] < symbols["WORK_RAM_START"]
            or symbols["WORK_RAM_END"] < symbols["VDG_VRAM_START"]
        ), (
            "K68-VDG VRAM must not overlap SBC-IO work RAM"
        )
    else:
        assert symbols["MONITOR_FEATURE_VDG"] == 0, "non-VDG profiles must keep VDG disabled"
    if _is_sd_build():
        assert symbols["FAT_SECTOR_IN_CLUS"] <= symbols["WORK_RAM_END"], (
            "SD work variables must stay under WORK_RAM_END"
        )
    print("[PASS] test_rom_profile_memory_layout")


def test_rom_map_command_matches_profile_symbols() -> None:
    names = [
        "RAM_START",
        "RAM_END",
        "USER_RAM_END",
        "WORK_RAM_START",
        "WORK_RAM_END",
        "MONITOR_RAM_BASE",
        "MIKBUG_VAR_BASE",
        "STACK_TOP",
        "ROM_BASE",
        "ROM_END",
    ]
    if _is_sd_build():
        names.append("SD_SECTOR_BUF")
    if _is_vdg_build():
        names.extend(["VDG_VRAM_START", "VDG_VRAM_END"])
    symbols = _load_symbol_addresses(*names)
    stdout, stderr, rc = _run_emu_with_sd("MAP\r\r", build_fat32_image(with_mbr=True))
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if _is_k6802_4000_build():
        profile = "K6802 4000"
    elif _is_sbcio_4000_build():
        profile = "SBCIO 4000"
    elif _is_k6802_vdg_build():
        profile = "K6802 VDG"
    elif _is_vdg_build():
        profile = "SBCIO VDG"
    elif _is_sbcio_build():
        profile = "SBCIO"
    else:
        profile = "BASE"
    expected_lines = [
        f"MAP {profile}",
        f"RAM {symbols['RAM_START']:04X}-{symbols['RAM_END']:04X}",
        f"USER {symbols['RAM_START']:04X}-{symbols['USER_RAM_END']:04X}",
        f"WORK {symbols['WORK_RAM_START']:04X}-{symbols['WORK_RAM_END']:04X}",
        f"MON {symbols['MONITOR_RAM_BASE']:04X}",
        f"MIK {symbols['MIKBUG_VAR_BASE']:04X}",
        f"STK {symbols['STACK_TOP']:04X}",
        f"ROM {symbols['ROM_BASE']:04X}-{symbols['ROM_END']:04X}",
    ]
    if _is_sd_build():
        expected_lines.insert(4, f"SD {symbols['SD_SECTOR_BUF']:04X}")
    if _is_vdg_build():
        expected_lines.insert(-1, f"VRAM {symbols['VDG_VRAM_START']:04X}-{symbols['VDG_VRAM_END']:04X}")
        expected_lines.insert(-1, "VDG 8110")
    for line in expected_lines:
        assert line in stdout, f"missing MAP line {line!r}: {stdout!r}"
    print("[PASS] test_rom_map_command_matches_profile_symbols")


def test_rom_sd_commands_disabled_without_feature() -> None:
    if _is_sd_build():
        print("[SKIP] test_rom_sd_commands_disabled_without_feature")
        return

    stdout, stderr, rc = _run_emu_with_sd("DIR\rLF TEST.S\rMAP\r\r", build_fat32_image(with_mbr=True))
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert stdout.count("?") >= 2, f"SD commands should be rejected when FEATURE_SD=0: {stdout!r}"
    assert "SD 1C00" not in stdout and "SD C000" not in stdout and "SD A000" not in stdout, (
        f"MAP should not show SD line when FEATURE_SD=0: {stdout!r}"
    )
    print("[PASS] test_rom_sd_commands_disabled_without_feature")


def assert_rom_fat32_mount_layout(with_mbr: bool) -> None:
    image = build_fat32_image(with_mbr=with_mbr)
    layout = layout_for_image(with_mbr=with_mbr)
    symbols = _load_symbol_addresses(
        "FAT32_MOUNT",
        "FAT_ERROR",
        "FAT_VOLUME_LBA0",
        "FAT_FAT_LBA0",
        "FAT_DATA_LBA0",
        "FAT_ROOT_CLUS0",
        "FAT_SEC_PER_CLUS",
        "FAT_RSVD_HI",
        "FAT_RSVD_LO",
        "FAT_NUM_FATS",
        "FAT_FATSZ0",
    )
    harness_addr = 0x0100
    harness = [
        0xBD, (symbols["FAT32_MOUNT"] >> 8) & 0xFF, symbols["FAT32_MOUNT"] & 0xFF,
        0x3F,
    ]
    first_addr = symbols["FAT_ERROR"]
    last_addr = symbols["FAT_FATSZ0"] + 3
    input_text = (
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{first_addr:04X}-{last_addr:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(input_text, image)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"

    values = _parse_dump_bytes(stdout, first_addr)
    expected = [
        0x00,
        *layout.volume_start_lba.to_bytes(4, "big"),
        *layout.fat_lba.to_bytes(4, "big"),
        *layout.data_start_lba.to_bytes(4, "big"),
        *ROOT_CLUSTER.to_bytes(4, "big"),
        0x01,
        0x00, 0x04,
        0x02,
        0x00, 0x00, 0x00, 0x01,
    ]
    assert values[:len(expected)] == expected, (
        f"FAT32 mount layout mismatch with_mbr={with_mbr}: "
        f"got={values[:len(expected)]!r} expected={expected!r}\nstdout={stdout!r}"
    )


def test_rom_fat32_mount_reads_mbr_bpb_layout() -> None:
    assert_rom_fat32_mount_layout(with_mbr=True)
    print("[PASS] test_rom_fat32_mount_reads_mbr_bpb_layout")


def test_rom_fat32_mount_reads_superfloppy_bpb_layout() -> None:
    assert_rom_fat32_mount_layout(with_mbr=False)
    print("[PASS] test_rom_fat32_mount_reads_superfloppy_bpb_layout")


def run_rom_find_and_read_file(file_name: bytes, image: bytes, dump_end: int) -> tuple[str, dict[str, int]]:
    assert len(file_name) == 11
    symbols = _load_symbol_addresses(
        "FAT32_MOUNT",
        "FAT32_FIND_83",
        "FAT32_READ_FILE",
        "FAT_FILE_CLUS0",
        "FAT_FILE_SIZE0",
    )
    name_addr = 0x0180
    harness_addr = 0x0100
    dest_addr = 0x0200
    harness = [
        0xBD, (symbols["FAT32_MOUNT"] >> 8) & 0xFF, symbols["FAT32_MOUNT"] & 0xFF,
        0xCE, (name_addr >> 8) & 0xFF, name_addr & 0xFF,
        0xBD, (symbols["FAT32_FIND_83"] >> 8) & 0xFF, symbols["FAT32_FIND_83"] & 0xFF,
        0xCE, (dest_addr >> 8) & 0xFF, dest_addr & 0xFF,
        0xBD, (symbols["FAT32_READ_FILE"] >> 8) & 0xFF, symbols["FAT32_READ_FILE"] & 0xFF,
        0x3F,
    ]
    input_text = (
        f"M{name_addr:04X}\r"
        f"{_hex_bytes(list(file_name))}\r.\r"
        f"M{harness_addr:04X}\r"
        f"{_hex_bytes(harness)}\r.\r"
        f"G{harness_addr:04X}\r"
        f"D{dest_addr:04X}-{dump_end:04X}\r"
        f"D{symbols['FAT_FILE_CLUS0']:04X}-{symbols['FAT_FILE_SIZE0'] + 3:04X}\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(input_text, image, max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    return stdout, symbols


def test_rom_fat32_find_and_read_multicluster_file() -> None:
    image = build_fat32_image(with_mbr=True)
    stdout, _symbols = run_rom_find_and_read_file(b"MULTI   BIN", image, 0x040F)
    line0 = _dump_line(stdout, 0x0200)
    line1 = _dump_line(stdout, 0x0400)
    expected0 = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_1_PREFIX)
    expected1 = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_2_PREFIX)
    assert expected0 in line0, f"missing first cluster prefix: {line0!r}"
    assert expected1 in line1, f"missing second cluster prefix: {line1!r}"
    print("[PASS] test_rom_fat32_find_and_read_multicluster_file")


def test_rom_fat32_find_and_read_multisector_cluster_file() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    stdout, _symbols = run_rom_find_and_read_file(b"MULTI   BIN", image, 0x040F)
    line0 = _dump_line(stdout, 0x0200)
    line1 = _dump_line(stdout, 0x0400)
    expected0 = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_1_PREFIX)
    expected1 = " ".join(f"{value:02X}" for value in MULTI_CLUSTER_2_PREFIX)
    assert expected0 in line0, f"missing first sector prefix: {line0!r}"
    assert expected1 in line1, f"missing second sector prefix: {line1!r}"
    print("[PASS] test_rom_fat32_find_and_read_multisector_cluster_file")


def test_rom_fat32_find_and_read_multisector_cluster_chain_file() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=2)
    stdout, _symbols = run_rom_find_and_read_file(b"BIGSREC S  ", image, 0x08FF)
    for offset in (0, SECTOR_SIZE, SECTOR_SIZE * 2):
        line = _dump_line(stdout, 0x0200 + offset)
        expected = " ".join(f"{value:02X}" for value in BIG_S_CONTENT[offset:offset + 16])
        assert expected in line, f"missing BIGSREC data at offset {offset}: {line!r}"
    print("[PASS] test_rom_fat32_find_and_read_multisector_cluster_chain_file")


def test_rom_fat32_find_respects_file_size() -> None:
    image = build_fat32_image(with_mbr=True)
    stdout, _symbols = run_rom_find_and_read_file(b"TEST    S  ", image, 0x022F)
    data = _parse_dump_bytes(stdout, 0x0200)
    assert bytes(data[:len(TEST_S_CONTENT)]) == TEST_S_CONTENT
    assert data[len(TEST_S_CONTENT)] == 0x00, "read should stop at file size before padding"
    print("[PASS] test_rom_fat32_find_respects_file_size")


def test_rom_fat32_find_chained_root_entry() -> None:
    image = build_fat32_image(with_mbr=True, root_chain=True)
    stdout, symbols = run_rom_find_and_read_file(b"LATE    BIN", image, 0x020F)
    line = _dump_line(stdout, 0x0200)
    expected = " ".join(f"{value:02X}" for value in LATE_BIN_CONTENT[:16])
    assert expected in line, f"missing chained root file data: {line!r}"
    meta = _parse_dump_bytes(stdout, symbols["FAT_FILE_CLUS0"])
    assert meta[:4] == list(LATE_BIN_CLUSTER.to_bytes(4, "big"))
    assert meta[4:8] == list(len(LATE_BIN_CONTENT).to_bytes(4, "big"))
    print("[PASS] test_rom_fat32_find_chained_root_entry")


def test_rom_dir_command_lists_root_files() -> None:
    image = build_fat32_image(with_mbr=True)
    stdout, stderr, rc = _run_emu_with_sd("DIR\r\r", image, max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "TEST.S A 0000001E" in stdout, f"missing TEST.S DIR entry: {stdout!r}"
    assert "TEST.HEX A 00000020" in stdout, f"missing TEST.HEX DIR entry: {stdout!r}"
    assert "MULTI.BIN A 00000400" in stdout, f"missing MULTI.BIN DIR entry: {stdout!r}"
    assert "SKIP" not in stdout, f"volume/subdirectory-like entries should be skipped: {stdout!r}"
    print("[PASS] test_rom_dir_command_lists_root_files")


def test_rom_dir_keeps_dump_command() -> None:
    image = build_fat32_image(with_mbr=True)
    stdout, stderr, rc = _run_emu_with_sd("D0100\r\r", image)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "0100" in stdout, f"dump command should still work: {stdout!r}"
    print("[PASS] test_rom_dir_keeps_dump_command")


def test_rom_boot_loads_fixed_lba_stage1_and_jumps() -> None:
    if not _is_s1_boot_build():
        print("[SKIP] test_rom_boot_loads_fixed_lba_stage1_and_jumps")
        return

    symbols = _load_symbol_addresses("S1_BASE")
    result_addr = symbols["S1_BASE"] + 0x0300
    image = _build_boot_stage1_image(_make_boot_stage1_stub(symbols["S1_BASE"], result_addr))
    stdout, stderr, rc = _run_emu_with_sd(
        f"BOOT\rD{result_addr:04X}-{result_addr:04X}\r\r",
        image,
        max_cycles=120_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    line = _dump_line(stdout, result_addr)
    assert re.search(rf"{result_addr:04X}\s+42\b", line), f"BOOT did not jump to stage1: {stdout!r}"
    print("[PASS] test_rom_boot_loads_fixed_lba_stage1_and_jumps")


def test_rom_boot_rejects_invalid_stage1_headers() -> None:
    if not _is_s1_boot_build():
        print("[SKIP] test_rom_boot_rejects_invalid_stage1_headers")
        return

    symbols = _load_symbol_addresses("S1_BASE")
    result_addr = symbols["S1_BASE"] + 0x0300
    cases = [
        lambda data: data.__setitem__(0, ord("X")),
        lambda data: data.__setitem__(slice(10, 12), b"\x00\x00"),
        lambda data: data.__setitem__(slice(12, 14), b"\x00\x00"),
        lambda data: data.__setitem__(slice(12, 14), b"\x20\x00"),
    ]
    for mutate in cases:
        stage1 = bytearray(_make_boot_stage1_stub(symbols["S1_BASE"], result_addr))
        mutate(stage1)
        image = _build_boot_stage1_image(bytes(stage1))
        stdout, stderr, rc = _run_emu_with_sd(
            f"BOOT\rD{result_addr:04X}-{result_addr:04X}\r\r",
            image,
            max_cycles=120_000_000,
        )
        assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
        assert "?" in stdout, f"BOOT should reject invalid stage1: {stdout!r}"
        line = _dump_line(stdout, result_addr)
        assert not re.search(rf"{result_addr:04X}\s+42\b", line), (
            f"BOOT jumped despite invalid stage1: {stdout!r}"
        )
    print("[PASS] test_rom_boot_rejects_invalid_stage1_headers")


def test_rom_boot_returns_prompt_on_stage1_read_failure() -> None:
    if not _is_s1_boot_build():
        print("[SKIP] test_rom_boot_returns_prompt_on_stage1_read_failure")
        return

    symbols = _load_symbol_addresses("S1_BASE")
    result_addr = symbols["S1_BASE"] + 0x0300
    stdout, stderr, rc = _run_emu_with_sd(
        f"BOOT\rD{result_addr:04X}-{result_addr:04X}\r\r",
        bytes(SECTOR_SIZE * 17),
        max_cycles=120_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "?" in stdout, f"BOOT read failure should return an error prompt: {stdout!r}"
    assert f"{result_addr:04X}" in stdout, f"monitor did not continue after BOOT failure: {stdout!r}"
    print("[PASS] test_rom_boot_returns_prompt_on_stage1_read_failure")


def test_rom_fat_commands_disabled_without_feature_fat() -> None:
    if not _is_sd_build() or _is_fat_build():
        print("[SKIP] test_rom_fat_commands_disabled_without_feature_fat")
        return

    stdout, stderr, rc = _run_emu_with_sd("DIR\rLF TEST.S\r\r", build_fat32_image(with_mbr=True))
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert stdout.count("?") >= 2, f"DIR/LF should be disabled when FEATURE_FAT=0: {stdout!r}"
    assert "TEST.S A" not in stdout, f"DIR should not list FAT root when FEATURE_FAT=0: {stdout!r}"
    assert "OK" not in stdout, f"LF should not load when FEATURE_FAT=0: {stdout!r}"
    print("[PASS] test_rom_fat_commands_disabled_without_feature_fat")


def test_rom_fat_feature_help_policy() -> None:
    if not _is_sd_build():
        print("[SKIP] test_rom_fat_feature_help_policy")
        return

    stdout, stderr, rc = _run_emu_with_sd("H\r\r", build_fat32_image(with_mbr=True))
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if _is_fat_build():
        expected = "D DIR M MAP RAMTEST G L LF BOOT B C R U H F"
        assert expected in stdout, f"FEATURE_FAT=1 help should include DIR/LF/BOOT: {stdout!r}"
    elif _is_vdg_build():
        expected = "D M MAP RAMTEST G L BOOT B C R U H F"
        assert expected in stdout, f"FEATURE_FAT=0 VDG help should keep BOOT only: {stdout!r}"
    else:
        expected = "D M MAP RAMTEST G L BOOT B C R U H F"
        assert expected in stdout, f"FEATURE_FAT=0 help should keep BOOT only: {stdout!r}"
    print("[PASS] test_rom_fat_feature_help_policy")


def test_rom_lf_command_opens_83_files_only() -> None:
    image = build_fat32_image(with_mbr=True)
    input_text = (
        "LF TEST.S\r"
        "D0200-0202\r"
        "LF   test.hex   \r"
        "D0300-0302\r"
        "LF NOFILE.S\r"
        "V\r"
        "\r"
    )
    stdout, stderr, rc = _run_emu_with_sd(input_text, image, max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert stdout.count("OK") >= 2, f"LF should load existing files: {stdout!r}"
    assert "0200 01 02 03" in stdout, f"missing S-Record loaded bytes: {stdout!r}"
    assert "0300 AA BB CC" in stdout, f"missing Intel HEX loaded bytes: {stdout!r}"
    assert stdout.count("?") >= 2, f"missing LF not found / V errors: {stdout!r}"
    print("[PASS] test_rom_lf_command_opens_83_files_only")


def test_rom_lf_file_eof_does_not_wait_for_acia() -> None:
    image = bytearray(build_fat32_image(with_mbr=True))
    layout = layout_for_image(with_mbr=True)
    root_offset = layout.root_dir_lba * SECTOR_SIZE
    image[root_offset + 28:root_offset + 32] = len(b"S1060200010203F1\r\n").to_bytes(4, "little")
    stdout, stderr, rc = _run_emu_with_sd("LF TEST.S\r\r", bytes(image), max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator should not hang at file EOF: {stderr!r}"
    assert "?S" in stdout or "?" in stdout, f"truncated file should report loader error: {stdout!r}"
    print("[PASS] test_rom_lf_file_eof_does_not_wait_for_acia")


def test_rom_lf_reads_small_file_from_multisector_cluster() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    stdout, stderr, rc = _run_emu_with_sd("LF TEST.S\rD0200-0202\r\r", image, max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "OK" in stdout, f"LF should load small file from SecPerClus > 1 image: {stdout!r}"
    assert "0200 01 02 03" in stdout, f"missing S-Record loaded bytes: {stdout!r}"
    print("[PASS] test_rom_lf_reads_small_file_from_multisector_cluster")


def test_rom_lf_reads_file_across_sector_inside_cluster() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    stdout, stderr, rc = _run_emu_with_sd(
        "F0500-079F 00\rLF BIGSREC.S\rD0500-050F\rD0720-072F\r\r",
        image,
        max_cycles=160_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "OK" in stdout, f"LF should load S-Record beyond first sector: {stdout!r}"
    assert "0500 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F" in stdout, (
        f"missing first loaded S-Record bytes: {stdout!r}"
    )
    assert "0720 20 21 22 23 24 25 26 27 28 29 2A 2B 2C 2D 2E 2F" in stdout, (
        f"missing bytes loaded after sector boundary: {stdout!r}"
    )
    print("[PASS] test_rom_lf_reads_file_across_sector_inside_cluster")


def test_rom_lf_reads_file_across_cluster_boundary_multisector_cluster() -> None:
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=2)
    stdout, stderr, rc = _run_emu_with_sd(
        "F0500-079F 00\rLF BIGSREC.S\rD0500-050F\rD0720-072F\r\r",
        image,
        max_cycles=160_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "OK" in stdout, f"LF should load S-Record across cluster boundary: {stdout!r}"
    assert "0500 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F" in stdout, (
        f"missing first loaded S-Record bytes: {stdout!r}"
    )
    assert "0720 20 21 22 23 24 25 26 27 28 29 2A 2B 2C 2D 2E 2F" in stdout, (
        f"missing bytes loaded after cluster boundary: {stdout!r}"
    )
    print("[PASS] test_rom_lf_reads_file_across_cluster_boundary_multisector_cluster")


def test_sbcio_sd_fat_ignores_old_low_ram_work_area() -> None:
    if not _is_fat_build():
        print("[SKIP] test_sbcio_sd_fat_ignores_old_low_ram_work_area")
        return

    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    stdout, stderr, rc = _run_emu_with_sd(
        "F1C00-1EFF A5\rDIR\rLF TEST.S\rD0200-0202\r\r",
        image,
        max_cycles=160_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "TEST.S A 0000001E" in stdout, f"DIR should work after old work area fill: {stdout!r}"
    assert "OK" in stdout, f"LF should work after old work area fill: {stdout!r}"
    assert "0200 01 02 03" in stdout, f"missing S-Record loaded bytes: {stdout!r}"
    print("[PASS] test_sbcio_sd_fat_ignores_old_low_ram_work_area")


def test_sbcio_ramtest_preserves_sd_fat_work_area() -> None:
    if not _is_fat_build():
        print("[SKIP] test_sbcio_ramtest_preserves_sd_fat_work_area")
        return

    work_range = "A000-BFFF" if _is_k6802_vdg_build() else "C000-DFFF"
    image = build_fat32_image(with_mbr=True, sectors_per_cluster=6)
    stdout, stderr, rc = _run_emu_with_sd(
        f"RAMTEST {work_range}\rDIR\rLF TEST.S\rD0200-0202\r\r",
        image,
        max_cycles=200_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert f"RAMTEST {work_range}" in stdout, f"RAMTEST should echo tested range: {stdout!r}"
    assert "OK" in stdout, f"RAMTEST/LF should report OK: {stdout!r}"
    assert "NG" not in stdout, f"RAMTEST should not fail in emulator: {stdout!r}"
    assert "TEST.S A 0000001E" in stdout, f"DIR should work after RAMTEST: {stdout!r}"
    assert "0200 01 02 03" in stdout, f"LF should work after RAMTEST: {stdout!r}"
    print("[PASS] test_sbcio_ramtest_preserves_sd_fat_work_area")


def _make_boot_stage1_stub(s1_base: int, result_addr: int) -> bytes:
    entry = s1_base + 16
    code = bytes([
        0x86, 0x42,
        0xB7, (result_addr >> 8) & 0xFF, result_addr & 0xFF,
        0x3F,
    ])
    data = bytearray(512)
    data[0:7] = b"S1API68"
    data[7] = 1
    data[8] = 6
    data[9] = 0
    data[10:12] = entry.to_bytes(2, "big")
    data[12:14] = (16 + len(code)).to_bytes(2, "big")
    data[16:16 + len(code)] = code
    return bytes(data)


def _build_boot_stage1_image(stage1: bytes) -> bytes:
    return build_sdfs_image(
        stage1_data=stage1,
        sdfs_data=b"SDFS68\x01\x10\x00\x00\x00\x10" + bytes(4),
        extra_files=[],
        total_volume_sectors=64,
    )


def main() -> None:
    print("=" * 50)
    print("SD/PIA fixture tests")
    print("=" * 50)

    tests = [
        test_mbr_fat32_fixture_layout,
        test_superfloppy_fat32_fixture_layout,
        test_chained_root_fat32_fixture_layout,
        test_multisector_cluster_fixture_layout,
        test_sdcard_command_sequence_reads_known_sector,
        test_sdcard_cs_release_discards_pending_response,
        test_pia_bitbang_reads_known_sector,
        test_rom_profile_memory_layout,
        test_rom_map_command_matches_profile_symbols,
    ]
    if _is_sd_build():
        tests.extend([
            test_rom_sd_read_sector_reads_known_fixture_sector,
            test_rom_boot_loads_fixed_lba_stage1_and_jumps,
            test_rom_boot_rejects_invalid_stage1_headers,
            test_rom_boot_returns_prompt_on_stage1_read_failure,
            test_rom_fat_commands_disabled_without_feature_fat,
            test_rom_fat_feature_help_policy,
        ])
    if _is_fat_build():
        tests.extend([
            test_rom_fat32_mount_reads_mbr_bpb_layout,
            test_rom_fat32_mount_reads_superfloppy_bpb_layout,
            test_rom_fat32_find_and_read_multicluster_file,
            test_rom_fat32_find_and_read_multisector_cluster_file,
            test_rom_fat32_find_and_read_multisector_cluster_chain_file,
            test_rom_fat32_find_respects_file_size,
            test_rom_fat32_find_chained_root_entry,
            test_rom_dir_command_lists_root_files,
            test_rom_dir_keeps_dump_command,
            test_rom_lf_command_opens_83_files_only,
            test_rom_lf_file_eof_does_not_wait_for_acia,
            test_rom_lf_reads_small_file_from_multisector_cluster,
            test_rom_lf_reads_file_across_sector_inside_cluster,
            test_rom_lf_reads_file_across_cluster_boundary_multisector_cluster,
            test_sbcio_sd_fat_ignores_old_low_ram_work_area,
            test_sbcio_ramtest_preserves_sd_fat_work_area,
        ])
    if not _is_sd_build():
        tests.append(test_rom_sd_commands_disabled_without_feature)

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
