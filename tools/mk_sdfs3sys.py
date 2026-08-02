#!/usr/bin/env python3
"""Create and validate a SDFS/68 v3 fixed-LBA system image."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"SDFS3SYS"
HEADER_VERSION = 1
HEADER_SIZE = 32
FLAG_CHECKSUM16 = 0x01
MAX_IMAGE_SIZE = 16 * 1024
CHECKSUM_OFFSET = 0x18


@dataclass(frozen=True)
class Sdfs3SysHeader:
    header_version: int
    abi_major: int
    abi_minor: int
    flags: int
    load_address: int
    image_size: int
    entry_offset: int
    api_table_offset: int
    work_min: int
    bank_window_hint: int
    checksum: int
    header_size: int


def build_sdfs3sys_image(
    *,
    resident_data: bytes,
    load_address: int,
    load_limit: int | None,
    entry_address: int,
    api_table_address: int,
    abi_major: int = 1,
    abi_minor: int = 0,
    flags: int = FLAG_CHECKSUM16,
    work_min: int = 0,
    bank_window_hint: int = 0,
) -> bytes:
    if not resident_data:
        raise ValueError("resident payload must not be empty")
    if load_limit is not None and load_address + len(resident_data) - 1 > load_limit:
        raise ValueError("resident payload exceeds SDFS load range")
    image_size = HEADER_SIZE + len(resident_data)
    if image_size > MAX_IMAGE_SIZE:
        raise ValueError(f"SDFS3SYS image exceeds {MAX_IMAGE_SIZE} bytes")
    entry_offset = _offset_from_load(load_address, entry_address, "entry")
    api_table_offset = _offset_from_load(load_address, api_table_address, "API table")
    header = bytearray(HEADER_SIZE)
    header[0:8] = MAGIC
    header[0x08] = _byte(HEADER_VERSION, "header version")
    header[0x09] = _byte(abi_major, "ABI major")
    header[0x0A] = _byte(abi_minor, "ABI minor")
    header[0x0B] = _byte(flags, "flags")
    _put_u16be(header, 0x0C, load_address)
    _put_u16be(header, 0x0E, image_size)
    _put_u16be(header, 0x10, entry_offset)
    _put_u16be(header, 0x12, api_table_offset)
    _put_u16be(header, 0x14, work_min)
    _put_u16be(header, 0x16, bank_window_hint)
    _put_u16be(header, CHECKSUM_OFFSET, 0)
    _put_u16be(header, 0x1A, HEADER_SIZE)
    image = bytes(header) + resident_data
    checksum = checksum16(image)
    mutable = bytearray(image)
    _put_u16be(mutable, CHECKSUM_OFFSET, checksum)
    return bytes(mutable)


def parse_sdfs3sys_header(image: bytes) -> Sdfs3SysHeader:
    if len(image) < HEADER_SIZE:
        raise ValueError("SDFS3SYS image is shorter than the fixed header")
    if image[0:8] != MAGIC:
        raise ValueError("SDFS3SYS magic mismatch")
    header = Sdfs3SysHeader(
        header_version=image[0x08],
        abi_major=image[0x09],
        abi_minor=image[0x0A],
        flags=image[0x0B],
        load_address=_u16be(image, 0x0C),
        image_size=_u16be(image, 0x0E),
        entry_offset=_u16be(image, 0x10),
        api_table_offset=_u16be(image, 0x12),
        work_min=_u16be(image, 0x14),
        bank_window_hint=_u16be(image, 0x16),
        checksum=_u16be(image, CHECKSUM_OFFSET),
        header_size=_u16be(image, 0x1A),
    )
    if header.header_version != HEADER_VERSION:
        raise ValueError("unsupported SDFS3SYS header version")
    if header.header_size < HEADER_SIZE:
        raise ValueError("SDFS3SYS header size is too small")
    if header.image_size != len(image):
        raise ValueError("SDFS3SYS image size mismatch")
    if header.image_size > MAX_IMAGE_SIZE:
        raise ValueError(f"SDFS3SYS image exceeds {MAX_IMAGE_SIZE} bytes")
    if header.entry_offset >= len(image) - HEADER_SIZE:
        raise ValueError("SDFS3SYS entry offset points outside payload")
    if header.api_table_offset >= len(image) - HEADER_SIZE:
        raise ValueError("SDFS3SYS API header offset points outside payload")
    if header.flags & FLAG_CHECKSUM16:
        actual = checksum16(image)
        if actual != header.checksum:
            raise ValueError("SDFS3SYS checksum mismatch")
    return header


def checksum16(image: bytes) -> int:
    data = bytearray(image)
    if len(data) > CHECKSUM_OFFSET + 1:
        data[CHECKSUM_OFFSET] = 0
        data[CHECKSUM_OFFSET + 1] = 0
    return sum(data) & 0xFFFF


def load_symbols(path: Path, *names: str) -> dict[str, int]:
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
            raise ValueError(f"missing symbol in listing: {name}")
    return result


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a SDFS/68 v3 SDFS3SYS image from a resident binary.",
    )
    parser.add_argument("--input", required=True, type=Path, help="SDFS3 resident binary")
    parser.add_argument("--listing", required=True, type=Path, help="SDFS3 resident listing")
    parser.add_argument("--output", required=True, type=Path, help="output SDFS3SYS image")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        symbols = load_symbols(
            args.listing,
            "SDFS3_LOAD_BASE",
            "SDFS3_LOAD_LIMIT",
            "SDFS3_GET_INFO",
            "SDFS3_JUMP_TABLE",
        )
        image = build_sdfs3sys_image(
            resident_data=args.input.read_bytes(),
            load_address=symbols["SDFS3_LOAD_BASE"],
            load_limit=symbols["SDFS3_LOAD_LIMIT"],
            entry_address=symbols["SDFS3_GET_INFO"],
            api_table_address=symbols["SDFS3_JUMP_TABLE"],
        )
        parse_sdfs3sys_header(image)
        args.output.write_bytes(image)
    except OSError as exc:
        print(f"mk-sdfs3sys: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"mk-sdfs3sys: {exc}", file=sys.stderr)
        return 2
    return 0


def _offset_from_load(load_address: int, address: int, label: str) -> int:
    if address < load_address:
        raise ValueError(f"{label} address is below load address")
    return _u16(address - load_address, f"{label} offset")


def _byte(value: int, label: str) -> int:
    if value < 0 or value > 0xFF:
        raise ValueError(f"{label} does not fit in 8 bits")
    return value


def _u16(value: int, label: str) -> int:
    if value < 0 or value > 0xFFFF:
        raise ValueError(f"{label} does not fit in 16 bits")
    return value


def _put_u16be(data: bytearray, offset: int, value: int) -> None:
    value = _u16(value, "u16 value")
    data[offset] = (value >> 8) & 0xFF
    data[offset + 1] = value & 0xFF


def _u16be(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


if __name__ == "__main__":
    sys.exit(main())
