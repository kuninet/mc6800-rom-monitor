#!/usr/bin/env python3
"""SDFS/68 v3(案 B)の system SD イメージを作る(#299)。

配置は #300(docs/plans/sdfs68_v3/issue-300_system_slot_layout.md)に従う。

    LBA 0        MBR(区画 1 = FAT32、開始は --fat-start。既定 2048)
    LBA 16-47    0(v2 の stage1 用に予約。FAT には割り当てない)
    LBA 48       active marker(active=A、marker 世代 1)
    LBA 64-95    slot A = SDFS3SYS(slot 世代 1 を入れて和を付け直す)
    LBA 96-127   0(slot B。PC 側の slot 更新 #302 の最初の書き込み先)
    --fat-start  FAT32(/BIN の LOAD.COM・RUN.COM・XLDR.OVL とサンプル)

slot A を世代 1 にして marker を書いておくと、最初の更新(slot B に世代 2)の途中で marker が
壊れても、ROM は世代を比べて新しい slot B を選ぶ(#302 の残件)。実 SD カードへは書かない。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fat32_image import SECTOR_SIZE, Fat32File, build_fat32_image_from_files, sector_count_for_size
from mk_sdfs3sys import CHECKSUM_OFFSET, HEADER_SIZE, MAGIC, MAX_IMAGE_SIZE, checksum16
from mk_sdfs_image import fat83_from_name, fat83_from_path, fat83_parent_from_path


# #300 の配置。名前は PC 側の slot 更新(#302 の tools/sdfs3_slot_update.py)とそろえる
STAGE1_LBA = 16
MARKER_LBA = 48
SLOT_A_LBA = 64
SLOT_B_LBA = 96
SLOT_MAX_SECTORS = 32
SYSTEM_AREA_END_LBA = 128  # FAT32 区画はここ以降(#300 の重なり検出条件)
DEFAULT_FAT_START_LBA = 2048  # #300 の既定。128 は今のカードの配置(#310 の決定 12)

MARKER_MAGIC = b"SDFS3MRK"
MARKER_VERSION = 1
MARKER_SIZE = 32
MARKER_FLAG_CHECKSUM16 = 0x01
INITIAL_GENERATION = 1

API_MAGIC = b"SDFS3API"
API_MAJOR = 2
HEADER_VERSION = 1
HEADER_FLAGS = 0x01  # ROM は flags == 1 を求める(BOOT3_CHECK_HEADER)
GENERATION_OFFSET = 0x1C
RAM_FLOOR = 0x4000  # SDFS3_RAM_FLOOR
RAM_END = 0x7FFF  # USER_RAM_END

# LOAD・RUN の .COM と本体(#316)。/BIN に入れる
TOOL_FILES = ("LOAD.COM", "RUN.COM", "XLDR.OVL")
BIN_DIR = "BIN"

assert STAGE1_LBA + 32 <= MARKER_LBA < SLOT_A_LBA
assert SLOT_A_LBA + SLOT_MAX_SECTORS <= SLOT_B_LBA
assert SLOT_B_LBA + SLOT_MAX_SECTORS <= SYSTEM_AREA_END_LBA
assert SLOT_MAX_SECTORS * SECTOR_SIZE == MAX_IMAGE_SIZE


def validate_system(data: bytes) -> int:
    """SDFS3SYS を ROM の BOOT3 と同じ条件で検査する(#300 の slot 有効条件、#310 の 1-5)。
    満たさなければ ValueError。"""
    if len(data) < HEADER_SIZE:
        raise ValueError("SDFS3SYS is shorter than its header")
    if data[0:8] != MAGIC:
        raise ValueError("SDFS3SYS magic mismatch")
    if data[0x08] != HEADER_VERSION:
        raise ValueError("SDFS3SYS header version is not 1")
    if data[0x09] != API_MAJOR:
        raise ValueError(f"SDFS3SYS API major is {data[0x09]}, not {API_MAJOR}")
    if data[0x0B] != HEADER_FLAGS:
        raise ValueError("SDFS3SYS flags must be $01 (checksum16)")
    if _u16(data, 0x1A) != HEADER_SIZE:
        raise ValueError("SDFS3SYS header size is not $0020")
    image_size = _u16(data, 0x0E)
    if image_size != len(data):
        raise ValueError(f"SDFS3SYS file is {len(data)} bytes but its header says {image_size}")
    if image_size < HEADER_SIZE + 1 or image_size > MAX_IMAGE_SIZE:
        raise ValueError(f"SDFS3SYS image size {image_size} does not fit in a slot (max {MAX_IMAGE_SIZE})")
    payload = image_size - HEADER_SIZE
    load = _u16(data, 0x0C)
    if load < RAM_FLOOR or load + payload > RAM_END + 1:
        raise ValueError(f"SDFS3SYS load range ${load:04X}+{payload} is outside ${RAM_FLOOR:04X}-${RAM_END:04X}")
    entry = _u16(data, 0x10)
    api = _u16(data, 0x12)
    if not 0 < api < payload:
        raise ValueError("SDFS3SYS +$12 (core / SDFS3API) points outside the image")
    if entry >= api:
        raise ValueError("SDFS3SYS +$10 (CCP vectors) must be inside the CCP, below +$12")
    if api + 9 > payload:
        raise ValueError("SDFS3API header does not fit in the image")
    core = HEADER_SIZE + api
    if data[core : core + 8] != API_MAGIC:
        raise ValueError("SDFS3API signature not found at +$12")
    if data[core + 8] != API_MAJOR:
        raise ValueError(f"SDFS3API major is {data[core + 8]}, not {API_MAJOR}")
    if checksum16(data) != _u16(data, CHECKSUM_OFFSET):
        raise ValueError("SDFS3SYS checksum mismatch")
    return image_size


def prepare_slot_image(system: bytes, generation: int = INITIAL_GENERATION) -> bytes:
    """slot 世代(+$1C)を入れて和を付け直した SDFS3SYS。入れる前と後の両方で検査する。"""
    validate_system(system)
    if not 1 <= generation <= 0xFFFF:
        raise ValueError("slot generation must be 1..$FFFF")
    data = bytearray(system)
    _put_u16(data, GENERATION_OFFSET, generation)
    _put_u16(data, CHECKSUM_OFFSET, 0)
    _put_u16(data, CHECKSUM_OFFSET, checksum16(bytes(data)))
    validate_system(bytes(data))
    return bytes(data)


def build_marker(active_slot: int, generation: int) -> bytes:
    """#300 の active marker の 512B。和は「+$18 を 0 にした 512B の 16bit 加算」。"""
    if active_slot not in (0, 1):
        raise ValueError("active slot must be 0 (A) or 1 (B)")
    if not 1 <= generation <= 0xFFFF:
        raise ValueError("marker generation must be 1..$FFFF")
    sector = bytearray(SECTOR_SIZE)
    sector[0:8] = MARKER_MAGIC
    sector[0x08:0x0C] = bytes([MARKER_VERSION, active_slot, 2, MARKER_FLAG_CHECKSUM16])
    _put_u16(sector, 0x0C, generation)
    _put_u16(sector, 0x0E, SLOT_MAX_SECTORS)
    _put_u16(sector, 0x10, SLOT_A_LBA)
    _put_u16(sector, 0x12, SLOT_B_LBA)
    _put_u16(sector, 0x1A, MARKER_SIZE)
    _put_u16(sector, 0x18, sum(sector) & 0xFFFF)
    return bytes(sector)


def check_fat_start(fat_start_lba: int) -> None:
    """FAT32 の区画が system 領域(MBR・stage1・marker・slot A/B、LBA 0〜127)に重ならない。"""
    if fat_start_lba < SYSTEM_AREA_END_LBA:
        raise ValueError(
            f"FAT32 start LBA {fat_start_lba} overlaps the system area "
            f"(LBA 0-{SYSTEM_AREA_END_LBA - 1}: MBR, stage1 {STAGE1_LBA}-{MARKER_LBA - 1}, "
            f"marker {MARKER_LBA}, slot A {SLOT_A_LBA}-{SLOT_B_LBA - 1}, "
            f"slot B {SLOT_B_LBA}-{SYSTEM_AREA_END_LBA - 1})"
        )


def build_sdfs3_image(
    *,
    system: bytes,
    files: list[Fat32File],
    fat_start_lba: int = DEFAULT_FAT_START_LBA,
    total_volume_sectors: int | None = None,
) -> bytes:
    """system 領域と FAT32 を 1 枚にしたイメージ。files は FAT に入れるファイル(1 本以上)。"""
    check_fat_start(fat_start_lba)
    slot_a = prepare_slot_image(system)
    marker = build_marker(0, INITIAL_GENERATION)
    image, _layout = build_fat32_image_from_files(
        files,
        with_mbr=True,
        partition_start_lba=fat_start_lba,
        total_volume_sectors=total_volume_sectors,
    )
    mutable = bytearray(image)
    if any(mutable[SECTOR_SIZE : fat_start_lba * SECTOR_SIZE]):
        raise ValueError("FAT32 builder wrote below the partition start")
    _put_sector(mutable, MARKER_LBA, marker)
    _put_sector(mutable, SLOT_A_LBA, slot_a)
    result = bytes(mutable)
    verify_layout(result, slot_a, marker)
    return result


def verify_layout(image: bytes, slot_a: bytes, marker: bytes) -> None:
    """組み立てたイメージを読み直し、#300 の重なり検出条件と置いた中身を確かめる。"""
    mbr = image[0:SECTOR_SIZE]
    if mbr[510:512] != b"\x55\xAA":
        raise ValueError("MBR signature 55AA not found")
    for index in range(4):
        entry = mbr[446 + index * 16 : 446 + (index + 1) * 16]
        start = int.from_bytes(entry[8:12], "little")
        count = int.from_bytes(entry[12:16], "little")
        if entry[4] == 0 or count == 0:
            continue
        check_fat_start(start)
        if (start + count) * SECTOR_SIZE > len(image):
            raise ValueError(f"partition {index + 1} runs past the end of the image")
    if image[MARKER_LBA * SECTOR_SIZE : (MARKER_LBA + 1) * SECTOR_SIZE] != marker:
        raise ValueError("marker sector was overwritten")
    slot_start = SLOT_A_LBA * SECTOR_SIZE
    slot_end = SLOT_B_LBA * SECTOR_SIZE
    if image[slot_start : slot_start + len(slot_a)] != slot_a or any(image[slot_start + len(slot_a) : slot_end]):
        raise ValueError("slot A was overwritten")
    if any(image[slot_end : SYSTEM_AREA_END_LBA * SECTOR_SIZE]):
        raise ValueError("slot B must be empty in a new image")
    if any(image[STAGE1_LBA * SECTOR_SIZE : MARKER_LBA * SECTOR_SIZE]):
        raise ValueError("stage1 area must be empty in a v3 image")


def file_from_spec(spec: str) -> Fat32File:
    """`[カード上のパス=]ホストのパス`。`=` がなければホストの相対パスをそのまま使う。"""
    if "=" in spec:
        dest, host = spec.split("=", 1)
        dest_path = Path(dest.replace("\\", "/").lstrip("/"))
        if not dest or dest_path.name in ("", ".", ".."):
            raise ValueError(f"invalid image path: {spec!r}")
    else:
        host = spec
        dest_path = Path(spec)
    data = Path(host).read_bytes()
    return Fat32File(fat83_from_path(dest_path), data, 0x20, fat83_parent_from_path(dest_path))


def tool_files(tools_dir: Path) -> list[Fat32File]:
    """`tools_dir` の LOAD.COM・RUN.COM・XLDR.OVL を /BIN に入れる。"""
    bin_dir = (fat83_from_name(BIN_DIR),)
    files = []
    for name in TOOL_FILES:
        path = tools_dir / name
        if not path.is_file():
            raise ValueError(f"{path} not found (run make sdfs-tools)")
        files.append(Fat32File(fat83_from_name(name), path.read_bytes(), 0x20, bin_dir))
    return files


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an SDFS/68 v3 system SD image: active marker at LBA 48, "
        "SDFS3SYS in slot A (LBA 64) and a FAT32 partition.",
    )
    parser.add_argument("--system", required=True, type=Path, help="SDFS3SYS image (make sdfs3sys)")
    parser.add_argument("--output", required=True, type=Path, help="output image path")
    parser.add_argument(
        "--fat-start",
        type=int,
        default=DEFAULT_FAT_START_LBA,
        help=f"FAT32 partition start LBA, default {DEFAULT_FAT_START_LBA} "
        f"(128 or more; 128 matches the earlier cards)",
    )
    parser.add_argument(
        "--tools-dir",
        type=Path,
        default=None,
        help="directory holding LOAD.COM, RUN.COM and XLDR.OVL; they go into /BIN",
    )
    parser.add_argument(
        "--total-volume-sectors",
        type=int,
        default=None,
        help="FAT32 volume sector count; defaults to a host-compatible FAT32 image",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="files for the FAT32 volume: [IMAGE/PATH=]HOST_PATH (without '=', the relative host path is used)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        files = [file_from_spec(spec) for spec in args.files]
        if args.tools_dir is not None:
            files += tool_files(args.tools_dir)
        if not files:
            raise ValueError("no files for the FAT32 volume (use --tools-dir and/or file arguments)")
        image = build_sdfs3_image(
            system=args.system.read_bytes(),
            files=files,
            fat_start_lba=args.fat_start,
            total_volume_sectors=args.total_volume_sectors,
        )
        args.output.write_bytes(image)
    except OSError as exc:
        print(f"mk-sdfs3-image: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mk-sdfs3-image: {exc}", file=sys.stderr)
        return 2
    return 0


def _put_sector(image: bytearray, lba: int, data: bytes) -> None:
    sectors = sector_count_for_size(len(data))
    start = lba * SECTOR_SIZE
    image[start : start + sectors * SECTOR_SIZE] = data + bytes(sectors * SECTOR_SIZE - len(data))


def _u16(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset] = (value >> 8) & 0xFF
    data[offset + 1] = value & 0xFF


if __name__ == "__main__":
    sys.exit(main())
