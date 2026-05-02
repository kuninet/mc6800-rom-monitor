#!/usr/bin/env python3
"""SD/PIA emulator fixture tests."""

from __future__ import annotations

import sys
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
sys.path.insert(0, str(PROJECT_ROOT / "emu"))
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"
BUILD_ROM_PATH = PROJECT_ROOT / "build" / "mc6800-monitor.bin"
BUILD_LST_PATH = PROJECT_ROOT / "build" / "mc6800-monitor.lst"

from sbc6800_emu import PIA, PIA_CRB, PIA_PRB, SDCard, SPI_CS, SPI_MISO, SPI_MOSI, SPI_SCLK
from sd_fixtures import (
    EOC,
    MULTI_CLUSTER_1,
    MULTI_CLUSTER_1_PREFIX,
    MULTI_CLUSTER_2,
    MULTI_CLUSTER_2_PREFIX,
    PARTITION_START_LBA,
    ROOT_CLUSTER,
    SECTOR_SIZE,
    TEST_HEX_CLUSTER,
    TEST_HEX_CONTENT,
    TEST_S_CLUSTER,
    TEST_S_CONTENT,
    build_fat32_image,
    layout_for_image,
    sector,
)


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def fat_entry(fat: bytes, cluster: int) -> int:
    return u32(fat, cluster * 4) & 0x0FFFFFFF


def entry_cluster(entry: bytes) -> int:
    return (u16(entry, 20) << 16) | u16(entry, 26)


def assert_common_bpb(image: bytes, volume_lba: int) -> None:
    bpb = sector(image, volume_lba)
    assert bpb[510:512] == b"\x55\xAA", "missing BPB signature"
    assert u16(bpb, 11) == SECTOR_SIZE, "unexpected bytes per sector"
    assert bpb[13] == 1, "unexpected sectors per cluster"
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
        if pia.read(PIA_PRB) & SPI_MISO:
            read_value |= 1 << bit
        pia.write(PIA_PRB, mosi | SPI_SCLK)
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
    import re

    text = BUILD_LST_PATH.read_text(encoding="utf-8", errors="replace")
    result: dict[str, int] = {}
    wanted = set(names)
    symbol_patterns = {
        name: [
            re.compile(rf"\b{re.escape(name)}\s*:\s*([0-9A-Fa-f]{{1,4}})\b"),
            re.compile(rf":=\$([0-9A-Fa-f]{{1,4}})\s+{re.escape(name)}\s+equ\b"),
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


def main() -> None:
    print("=" * 50)
    print("SD/PIA fixture tests")
    print("=" * 50)

    tests = [
        test_mbr_fat32_fixture_layout,
        test_superfloppy_fat32_fixture_layout,
        test_sdcard_command_sequence_reads_known_sector,
        test_sdcard_cs_release_discards_pending_response,
        test_pia_bitbang_reads_known_sector,
        test_rom_sd_read_sector_reads_known_fixture_sector,
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
