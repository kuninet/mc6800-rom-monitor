#!/usr/bin/env python3
"""mk-sdfs image generation tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from fat32_image import DEFAULT_PARTITION_START_LBA, EOC, SECTOR_SIZE, sector  # noqa: E402
from mk_sdfs_image import DEFAULT_STAGE1_LBA, build_sdfs_image, fat83_from_path, fat83_parent_from_path  # noqa: E402


def u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 2], "little")


def u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 4], "little")


def fat_entry(fat: bytes, cluster: int) -> int:
    return u32(fat, cluster * 4) & 0x0FFFFFFF


def entry_cluster(entry: bytes) -> int:
    return (u16(entry, 20) << 16) | u16(entry, 26)


def test_fat83_from_path_accepts_uppercase_83() -> None:
    assert fat83_from_path(Path("HELLO.S")) == b"HELLO   S  "
    assert fat83_from_path(Path("big.bin")) == b"BIG     BIN"
    assert fat83_from_path(Path("A-B.S")) == b"A-B     S  "
    assert fat83_from_path(Path("A!B#.DAT")) == b"A!B#    DAT"
    print("[PASS] test_fat83_from_path_accepts_uppercase_83")


def test_fat83_from_path_rejects_non_83() -> None:
    for name in ("TOO-LONG-NAME.S", "HELLO.LONG", "A.B.C", "日本.S"):
        try:
            fat83_from_path(Path(name))
        except ValueError:
            continue
        raise AssertionError(f"expected invalid 8.3 filename: {name}")
    print("[PASS] test_fat83_from_path_rejects_non_83")


def test_fat83_parent_from_path_rejects_absolute_path() -> None:
    try:
        fat83_parent_from_path(Path("/tmp/SRC/HELLO.S"))
    except ValueError:
        print("[PASS] test_fat83_parent_from_path_rejects_absolute_path")
        return
    raise AssertionError("expected absolute image path to be rejected")


def test_build_sdfs_image_places_stage1_and_root_files() -> None:
    stage1 = b"S1API68" + bytes(range(32))
    sdfs = b"SDFS68" + bytes(range(250)) * 3
    hello = b"S1060200010203F1\r\nS9030000FC\r\n"
    image = build_sdfs_image(
        stage1_data=stage1,
        sdfs_data=sdfs,
        extra_files=[
            _file("HELLO.S", hello),
            _file("DATA.BIN", b"DATA" * 200),
        ],
    )

    assert image == build_sdfs_image(
        stage1_data=stage1,
        sdfs_data=sdfs,
        extra_files=[
            _file("HELLO.S", hello),
            _file("DATA.BIN", b"DATA" * 200),
        ],
    ), "same input must generate identical image bytes"

    mbr = sector(image, 0)
    assert mbr[510:512] == b"\x55\xAA"
    assert mbr[450] == 0x0C
    assert u32(mbr, 454) == DEFAULT_PARTITION_START_LBA

    boot_area = sector(image, DEFAULT_STAGE1_LBA)
    assert boot_area.startswith(stage1)
    assert boot_area[len(stage1):] == bytes(SECTOR_SIZE - len(stage1))

    bpb = sector(image, DEFAULT_PARTITION_START_LBA)
    assert bpb[510:512] == b"\x55\xAA"
    assert u16(bpb, 11) == SECTOR_SIZE
    assert bpb[13] == 1
    assert u16(bpb, 14) == 4
    assert bpb[16] == 2
    assert u32(bpb, 44) == 2
    assert bpb[82:90] == b"FAT32   "
    fat_size = u32(bpb, 36)
    total_volume_sectors = u32(bpb, 32)
    data_clusters = (total_volume_sectors - u16(bpb, 14) - bpb[16] * fat_size) // bpb[13]
    assert data_clusters >= 65525

    fat_lba = DEFAULT_PARTITION_START_LBA + u16(bpb, 14)
    data_start_lba = fat_lba + bpb[16] * fat_size
    root = sector(image, data_start_lba)
    assert root[0:11] == b"SDFS    BIN"
    assert root[32:43] == b"HELLO   S  "
    assert root[64:75] == b"DATA    BIN"
    assert u32(root, 28) == len(sdfs)
    assert u32(root, 32 + 28) == len(hello)

    fat = sector(image, fat_lba)
    sdfs_cluster = entry_cluster(root[0:32])
    data_cluster = entry_cluster(root[64:96])
    assert sdfs_cluster == 3
    assert fat_entry(fat, 2) == EOC
    assert fat_entry(fat, sdfs_cluster) == 4
    assert fat_entry(fat, 4) == EOC
    assert fat_entry(fat, data_cluster) == 7
    assert fat_entry(fat, 7) == EOC
    assert sector(image, data_start_lba + (sdfs_cluster - 2)).startswith(sdfs[:SECTOR_SIZE])
    assert sector(image, data_start_lba + (data_cluster - 2)).startswith((b"DATA" * 200)[:SECTOR_SIZE])
    print("[PASS] test_build_sdfs_image_places_stage1_and_root_files")


def test_build_sdfs_image_places_subdirectory_files() -> None:
    stage1 = b"S1API68"
    sdfs = b"SDFS68" + bytes(range(250)) * 3
    hello = b"S1060200010203F1\r\nS9030000FC\r\n"
    hello_com = b"\x39"
    image = build_sdfs_image(
        stage1_data=stage1,
        sdfs_data=sdfs,
        extra_files=[
            _file("HELLO.S", hello, path=("SRC",)),
            _file("HELLO.COM", hello_com, path=("BIN",)),
        ],
    )

    bpb = sector(image, DEFAULT_PARTITION_START_LBA)
    fat_lba = DEFAULT_PARTITION_START_LBA + u16(bpb, 14)
    data_start_lba = fat_lba + bpb[16] * u32(bpb, 36)
    root = sector(image, data_start_lba)
    assert root[0:11] == b"SDFS    BIN"
    assert root[32:43] == b"SRC        "
    assert root[32 + 11] == 0x10
    assert root[64:75] == b"BIN        "
    assert root[64 + 11] == 0x10

    fat = sector(image, fat_lba)
    src_cluster = entry_cluster(root[32:64])
    bin_cluster = entry_cluster(root[64:96])
    assert fat_entry(fat, src_cluster) == EOC
    assert fat_entry(fat, bin_cluster) == EOC

    src = sector(image, data_start_lba + (src_cluster - 2))
    bin_dir = sector(image, data_start_lba + (bin_cluster - 2))
    assert src[0:11] == b"HELLO   S  "
    assert src[11] == 0x20
    assert u32(src, 28) == len(hello)
    assert bin_dir[0:11] == b"HELLO   COM"
    assert bin_dir[11] == 0x20
    assert u32(bin_dir, 28) == len(hello_com)
    assert sector(image, data_start_lba + (entry_cluster(src[0:32]) - 2)).startswith(hello)
    assert sector(image, data_start_lba + (entry_cluster(bin_dir[0:32]) - 2)).startswith(hello_com)
    print("[PASS] test_build_sdfs_image_places_subdirectory_files")


def test_build_sdfs_image_rejects_bad_inputs() -> None:
    cases = [
        dict(stage1_data=b"", sdfs_data=b"S", extra_files=[]),
        dict(stage1_data=b"S", sdfs_data=b"", extra_files=[]),
        dict(stage1_data=b"S" * (17 * SECTOR_SIZE), sdfs_data=b"S", extra_files=[]),
        dict(stage1_data=b"S", sdfs_data=b"S", extra_files=[_file("SDFS.BIN", b"dup")]),
        dict(
            stage1_data=b"S",
            sdfs_data=b"S",
            extra_files=[
                _file("SRC", b"file"),
                _file("HELLO.S", b"sub", path=("SRC",)),
            ],
        ),
    ]
    for kwargs in cases:
        try:
            build_sdfs_image(**kwargs)
        except ValueError:
            continue
        raise AssertionError(f"expected build_sdfs_image to reject: {kwargs!r}")
    print("[PASS] test_build_sdfs_image_rejects_bad_inputs")


def test_cli_writes_image_and_reports_missing_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage1 = root / "STAGE1.BIN"
        sdfs = root / "SDFS.BIN"
        out = root / "sdfs.img"
        stage1.write_bytes(b"S1API68")
        sdfs.write_bytes(b"SDFS68")
        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "mk_sdfs_image.py"),
                "--stage1",
                str(stage1),
                "--sdfs",
                str(sdfs),
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert out.read_bytes()[DEFAULT_STAGE1_LBA * SECTOR_SIZE:].startswith(b"S1API68")

        missing = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "tools" / "mk_sdfs_image.py"),
                "--stage1",
                str(root / "NOPE.BIN"),
                "--sdfs",
                str(sdfs),
                "--output",
                str(out),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        assert missing.returncode == 1
        assert "mk-sdfs:" in missing.stderr
    print("[PASS] test_cli_writes_image_and_reports_missing_file")


def _file(name: str, data: bytes, path: tuple[str, ...] = ()):
    from fat32_image import Fat32File

    return Fat32File(
        fat83_from_path(Path(name)),
        data,
        path=tuple(fat83_from_path(Path(component)) for component in path),
    )


def main() -> None:
    print("=" * 50)
    print("mk-sdfs image tests")
    print("=" * 50)
    tests = [
        test_fat83_from_path_accepts_uppercase_83,
        test_fat83_from_path_rejects_non_83,
        test_fat83_parent_from_path_rejects_absolute_path,
        test_build_sdfs_image_places_stage1_and_root_files,
        test_build_sdfs_image_places_subdirectory_files,
        test_build_sdfs_image_rejects_bad_inputs,
        test_cli_writes_image_and_reports_missing_file,
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
