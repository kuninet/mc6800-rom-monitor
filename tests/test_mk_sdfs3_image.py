#!/usr/bin/env python3
"""mk_sdfs3_image(v3 の system SD イメージ。#299)の単体テスト。エミュレータは使わない。

生成したイメージで BOOT3 から DOS のコマンドが通ることは tests/test_sdfs68_v3_build.py の
test_sd_image_tool_* で確かめる。"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from fat32_image import SECTOR_SIZE, sector  # noqa: E402
from mk_sdfs3sys import CHECKSUM_OFFSET, build_sdfs3sys_image, checksum16  # noqa: E402
from mk_sdfs3_image import (  # noqa: E402
    DEFAULT_FAT_START_LBA,
    MARKER_LBA,
    SLOT_A_LBA,
    SLOT_B_LBA,
    SYSTEM_AREA_END_LBA,
    build_marker,
    build_sdfs3_image,
    file_from_spec,
    validate_system,
    verify_layout,
)
from mk_sdfs_image import fat83_from_name  # noqa: E402

TOOL = PROJECT_ROOT / "tools" / "mk_sdfs3_image.py"
SMALL_VOLUME = 256  # FAT32 の最小構成(ホストでは読めないが、テストを速くする)
LOAD = 0x6C00
CORE = 0x7000


def _system(*, size: int = 0x1100, major: int = 2, load: int = LOAD) -> bytes:
    """CCP($6C00〜)と核($7000〜、先頭に SDFS3API と major)を持つ SDFS3SYS。"""
    payload = bytearray(size)
    payload[CORE - LOAD : CORE - LOAD + 9] = b"SDFS3API" + bytes([major])
    return build_sdfs3sys_image(
        resident_data=bytes(payload),
        load_address=load,
        load_limit=None,
        entry_address=load,
        api_table_address=load + (CORE - LOAD),
        abi_major=major,
    )


def _too_big() -> bytes:
    """16384B のイメージに 1 バイト足し、image_size と和を付け直したもの(slot に収まらない)。"""
    data = bytearray(_system(load=0x4000, size=16384 - 32) + b"\0")
    data[0x0E:0x10] = bytes([len(data) >> 8, len(data) & 0xFF])
    data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] = b"\0\0"
    total = checksum16(bytes(data))
    data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] = bytes([total >> 8, total & 0xFF])
    return bytes(data)


def _files() -> list:
    return [file_from_spec(f"HELLO.TXT={_tmp_file(b'HELLO')}")]


_TMP = tempfile.TemporaryDirectory()


def _tmp_file(data: bytes, name: str = "in.bin") -> Path:
    path = Path(_TMP.name) / name
    path.write_bytes(data)
    return path


def _u32le(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], "little")


def _u16(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def test_layout_marker_and_slot_a() -> None:
    """marker(48)は active=A・世代 1、slot A(64)は世代 1 で和が合い、stage1 領域と slot B は 0。"""
    system = _system()
    for fat_start in (DEFAULT_FAT_START_LBA, SYSTEM_AREA_END_LBA):
        image = build_sdfs3_image(
            system=system, files=_files(), fat_start_lba=fat_start, total_volume_sectors=SMALL_VOLUME
        )
        mbr = sector(image, 0)
        assert mbr[510:512] == b"\x55\xAA" and mbr[446 + 4] == 0x0C
        assert _u32le(mbr, 446 + 8) == fat_start and _u32le(mbr, 446 + 12) == SMALL_VOLUME
        assert len(image) == (fat_start + SMALL_VOLUME) * SECTOR_SIZE
        assert sector(image, fat_start)[82:90] == b"FAT32   "
        marker = sector(image, MARKER_LBA)
        assert marker == build_marker(0, 1)
        assert marker[0:8] == b"SDFS3MRK" and marker[8:12] == bytes([1, 0, 2, 1])
        assert [_u16(marker, o) for o in (0x0C, 0x0E, 0x10, 0x12, 0x1A)] == [1, 32, 64, 96, 32]
        check = bytearray(marker)
        check[0x18:0x1A] = b"\0\0"
        assert sum(check) & 0xFFFF == _u16(marker, 0x18)
        assert not any(marker[32:])
        slot = image[SLOT_A_LBA * SECTOR_SIZE : SLOT_A_LBA * SECTOR_SIZE + len(system)]
        assert _u16(slot, 0x1C) == 1, "slot A generation must be 1"
        assert checksum16(slot) == _u16(slot, CHECKSUM_OFFSET)
        assert validate_system(slot) == len(system)
        # 世代と和以外は入力と同じ
        diff = [i for i in range(len(system)) if slot[i] != system[i]]
        assert set(diff) <= {0x18, 0x19, 0x1C, 0x1D}, diff
        assert not any(image[SLOT_A_LBA * SECTOR_SIZE + len(system) : SYSTEM_AREA_END_LBA * SECTOR_SIZE])
        assert not any(image[SECTOR_SIZE : MARKER_LBA * SECTOR_SIZE]), "LBA 1-47 must stay zero"
        assert not any(image[SYSTEM_AREA_END_LBA * SECTOR_SIZE : fat_start * SECTOR_SIZE])
    print("[PASS] test_layout_marker_and_slot_a")


def test_default_image_is_host_fat32_and_deterministic() -> None:
    """既定(2048、ホストが FAT32 と見なす大きさ)のイメージは、同じ入力から同じバイト列になる。"""
    system = _system()
    first = build_sdfs3_image(system=system, files=_files())
    assert first == build_sdfs3_image(system=system, files=_files())
    bpb = sector(first, DEFAULT_FAT_START_LBA)
    total = _u32le(bpb, 32)
    fat_size = _u32le(bpb, 36)
    clusters = (total - int.from_bytes(bpb[14:16], "little") - bpb[16] * fat_size) // bpb[13]
    assert clusters >= 65525, clusters
    assert _u32le(sector(first, 0), 446 + 8) == DEFAULT_FAT_START_LBA
    print("[PASS] test_default_image_is_host_fat32_and_deterministic")


def test_rejects_fat_overlapping_system_area() -> None:
    """FAT32 の開始が 128 未満(MBR・stage1・marker・slot と重なる)なら、関数も CLI も拒否する。"""
    system = _system()
    for fat_start in (0, 1, 16, 47, 48, 64, 95, 96, 127):
        try:
            build_sdfs3_image(system=system, files=_files(), fat_start_lba=fat_start, total_volume_sectors=SMALL_VOLUME)
        except ValueError as exc:
            assert "overlaps the system area" in str(exc), exc
        else:
            raise AssertionError(f"FAT start {fat_start} must be rejected")
    system_path = _tmp_file(system, "SDFS3SYS.BIN")
    hello = _tmp_file(b"HELLO", "HELLO.TXT")
    for fat_start, expected in ((127, 2), (16, 2), (128, 0)):
        output = Path(_TMP.name) / f"out-{fat_start}.img"
        output.unlink(missing_ok=True)
        result = _cli(
            "--system", system_path, "--output", output, "--fat-start", fat_start,
            "--total-volume-sectors", SMALL_VOLUME, f"HELLO.TXT={hello}",
        )
        assert result.returncode == expected, (fat_start, result.stderr)
        if expected:
            assert "overlaps the system area" in result.stderr and not output.exists(), result.stderr
        else:
            assert _u32le(output.read_bytes(), 446 + 8) == 128
    print("[PASS] test_rejects_fat_overlapping_system_area")


def test_rejects_bad_system_images() -> None:
    """ROM の BOOT3 が `?` にするイメージは PC 側で止める。"""
    good = _system()

    def mutated(offset: int, value: int, *, fix_sum: bool = True) -> bytes:
        data = bytearray(good)
        data[offset] = value
        if fix_sum:
            data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] = b"\0\0"
            total = checksum16(bytes(data))
            data[CHECKSUM_OFFSET : CHECKSUM_OFFSET + 2] = bytes([total >> 8, total & 0xFF])
        return bytes(data)

    cases = {
        "magic": mutated(0, ord("X")),
        "checksum": mutated(0x40, 0x55, fix_sum=False),
        "header version": mutated(0x08, 2),
        "API major 1": _system(major=1),
        "flags": mutated(0x0B, 0x03),
        "load below $4000": _system(load=0x3F00),
        "load past $7FFF": _system(load=0x7000, size=0x1001),
        "too big": _too_big(),
        "core magic": mutated(32 + CORE - LOAD, ord("X")),
        "truncated": good[:-1],
    }
    for name, data in cases.items():
        try:
            build_sdfs3_image(system=data, files=_files(), total_volume_sectors=SMALL_VOLUME)
        except ValueError:
            continue
        raise AssertionError(f"{name}: must be rejected")
    biggest = _system(load=0x4000, size=16384 - 32)
    image = build_sdfs3_image(system=biggest, files=_files(), total_volume_sectors=SMALL_VOLUME)
    assert validate_system(image[SLOT_A_LBA * SECTOR_SIZE : SLOT_B_LBA * SECTOR_SIZE]) == 16384
    print("[PASS] test_rejects_bad_system_images")


def test_file_specs_and_tools_dir() -> None:
    """`カード上のパス=ホスト` と、--tools-dir の 3 本が /BIN に入る。なければエラー。"""
    host = _tmp_file(b"DATA", "data.bin")
    spec = file_from_spec(f"/src/hello.s={host}")
    assert spec.name == fat83_from_name("HELLO.S") and spec.path == (fat83_from_name("SRC"),)
    assert spec.data == b"DATA"
    tools = Path(_TMP.name) / "tools"
    tools.mkdir(exist_ok=True)
    system_path = _tmp_file(_system(), "SDFS3SYS.BIN")
    output = Path(_TMP.name) / "tools.img"
    for name in ("LOAD.COM", "RUN.COM"):
        (tools / name).write_bytes(b"\x39")
    missing = _cli("--system", system_path, "--output", output, "--tools-dir", tools, "--total-volume-sectors", SMALL_VOLUME)
    assert missing.returncode == 2 and "XLDR.OVL" in missing.stderr, missing.stderr
    (tools / "XLDR.OVL").write_bytes(b"\x7e\x68\x00XLDR")
    ok = _cli("--system", system_path, "--output", output, "--tools-dir", tools, "--total-volume-sectors", SMALL_VOLUME)
    assert ok.returncode == 0, ok.stderr
    image = output.read_bytes()
    data_lba = 2048 + 4 + 2 * _u32le(sector(image, 2048), 36)
    root = sector(image, data_lba)
    assert root[0:11] == fat83_from_name("BIN") and root[11] == 0x10
    bin_cluster = (int.from_bytes(root[20:22], "little") << 16) | int.from_bytes(root[26:28], "little")
    bin_dir = sector(image, data_lba + bin_cluster - 2)
    assert [bin_dir[i * 32 : i * 32 + 11] for i in range(3)] == [fat83_from_name(n) for n in ("LOAD.COM", "RUN.COM", "XLDR.OVL")]
    empty = _cli("--system", system_path, "--output", output)
    assert empty.returncode == 2 and "no files" in empty.stderr
    print("[PASS] test_file_specs_and_tools_dir")


def test_verify_layout_rejects_broken_images() -> None:
    """組み立てのあとの読み直し(verify_layout)は、区画が system 領域に入るイメージや、
    marker・slot A・slot B・stage1 領域が置いたとおりでないイメージを拒否する。"""
    system = _system()
    image = build_sdfs3_image(system=system, files=_files(), total_volume_sectors=SMALL_VOLUME)
    slot_a = image[SLOT_A_LBA * SECTOR_SIZE : SLOT_A_LBA * SECTOR_SIZE + len(system)]
    marker = build_marker(0, 1)
    verify_layout(image, slot_a, marker)

    def broken(offset: int, value: bytes) -> bytes:
        data = bytearray(image)
        data[offset : offset + len(value)] = value
        return bytes(data)

    cases = {
        "partition at 64": broken(446 + 8, (64).to_bytes(4, "little")),
        "partition past the end": broken(446 + 12, (SMALL_VOLUME + 1).to_bytes(4, "little")),
        "no 55AA": broken(510, b"\0\0"),
        "marker": broken(MARKER_LBA * SECTOR_SIZE + 40, b"\1"),
        "slot A": broken(SLOT_A_LBA * SECTOR_SIZE + 100, b"\xAA"),
        "slot A tail": broken(SLOT_A_LBA * SECTOR_SIZE + len(system), b"\1"),
        "slot B": broken(SLOT_B_LBA * SECTOR_SIZE + 5, b"\1"),
        "stage1 area": broken(16 * SECTOR_SIZE, b"\1"),
    }
    for name, data in cases.items():
        try:
            verify_layout(data, slot_a, marker)
        except ValueError:
            continue
        raise AssertionError(f"{name}: must be rejected")
    print("[PASS] test_verify_layout_rejects_broken_images")


def _cli(*args) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *(str(a) for a in args)],
        capture_output=True,
        text=True,
        timeout=60,
    )


def main() -> None:
    tests = [
        test_layout_marker_and_slot_a,
        test_default_image_is_host_fat32_and_deterministic,
        test_rejects_fat_overlapping_system_area,
        test_rejects_bad_system_images,
        test_file_specs_and_tools_dir,
        test_verify_layout_rejects_broken_images,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] {test.__name__}: {exc!r}")
            failed += 1
    print(f"Result: {len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
