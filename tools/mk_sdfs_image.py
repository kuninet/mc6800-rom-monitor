#!/usr/bin/env python3
"""Create a deterministic SDFS/68 system SD image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fat32_image import (
    DEFAULT_PARTITION_START_LBA,
    SECTOR_SIZE,
    Fat32File,
    build_fat32_image_from_files,
    sector_count_for_size,
)


DEFAULT_STAGE1_LBA = 16
SDFS_NAME_83 = b"SDFS    BIN"
FAT83_EXTRA_CHARS = "$%'-_@~`!(){}^#&"


def build_sdfs_image(
    *,
    stage1_data: bytes,
    sdfs_data: bytes,
    extra_files: list[Fat32File],
    stage1_lba: int = DEFAULT_STAGE1_LBA,
    partition_start_lba: int = DEFAULT_PARTITION_START_LBA,
    total_volume_sectors: int | None = None,
) -> bytes:
    if not stage1_data:
        raise ValueError("stage1 loader must not be empty")
    if not sdfs_data:
        raise ValueError("SDFS.BIN must not be empty")
    stage1_sectors = sector_count_for_size(len(stage1_data))
    if stage1_lba <= 0:
        raise ValueError("stage1 LBA must not overlap the MBR")
    if stage1_lba + stage1_sectors > partition_start_lba:
        raise ValueError("stage1 boot area overlaps the FAT32 partition")

    root_files = [Fat32File(SDFS_NAME_83, sdfs_data), *extra_files]
    names = [file.name for file in root_files]
    if len(names) != len(set(names)):
        raise ValueError("duplicate FAT 8.3 root filename")

    image, _layout = build_fat32_image_from_files(
        root_files,
        with_mbr=True,
        partition_start_lba=partition_start_lba,
        total_volume_sectors=total_volume_sectors,
    )
    mutable = bytearray(image)
    start = stage1_lba * SECTOR_SIZE
    padded_len = stage1_sectors * SECTOR_SIZE
    mutable[start:start + padded_len] = stage1_data + bytes(padded_len - len(stage1_data))
    return bytes(mutable)


def fat83_from_path(path: Path) -> bytes:
    name = path.name
    if name in ("", ".", ".."):
        raise ValueError(f"invalid filename: {name!r}")
    if name.count(".") > 1:
        raise ValueError(f"filename is not 8.3: {name}")
    stem, dot, ext = name.partition(".")
    if not stem or len(stem) > 8 or len(ext) > 3:
        raise ValueError(f"filename is not 8.3: {name}")
    stem = stem.upper()
    ext = ext.upper() if dot else ""
    if not _is_valid_83_part(stem) or not _is_valid_83_part(ext):
        raise ValueError(f"filename contains unsupported FAT 8.3 characters: {name}")
    return stem.encode("ascii").ljust(8, b" ") + ext.encode("ascii").ljust(3, b" ")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a SDFS/68 FAT32 SD image with fixed-LBA stage1.",
    )
    parser.add_argument("--stage1", required=True, type=Path, help="stage1 loader binary")
    parser.add_argument("--sdfs", required=True, type=Path, help="SDFS.BIN body")
    parser.add_argument("--output", required=True, type=Path, help="output image path")
    parser.add_argument(
        "--stage1-lba",
        type=int,
        default=DEFAULT_STAGE1_LBA,
        help=f"physical LBA for stage1 boot area, default {DEFAULT_STAGE1_LBA}",
    )
    parser.add_argument(
        "--partition-start-lba",
        type=int,
        default=DEFAULT_PARTITION_START_LBA,
        help=f"FAT32 partition start LBA, default {DEFAULT_PARTITION_START_LBA}",
    )
    parser.add_argument(
        "--total-volume-sectors",
        type=int,
        default=None,
        help="FAT32 volume sector count; defaults to a host-compatible FAT32 image",
    )
    parser.add_argument("files", nargs="*", type=Path, help="additional root files")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        extra_files = [
            Fat32File(fat83_from_path(path), _read_file(path), 0x20)
            for path in args.files
        ]
        image = build_sdfs_image(
            stage1_data=_read_file(args.stage1),
            sdfs_data=_read_file(args.sdfs),
            extra_files=extra_files,
            stage1_lba=args.stage1_lba,
            partition_start_lba=args.partition_start_lba,
            total_volume_sectors=args.total_volume_sectors,
        )
        args.output.write_bytes(image)
    except OSError as exc:
        print(f"mk-sdfs: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mk-sdfs: {exc}", file=sys.stderr)
        return 2
    return 0


def _read_file(path: Path) -> bytes:
    return path.read_bytes()


def _is_valid_83_part(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return all(char.isalnum() or char in FAT83_EXTRA_CHARS for char in value)


if __name__ == "__main__":
    sys.exit(main())
