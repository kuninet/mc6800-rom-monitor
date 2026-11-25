#!/usr/bin/env python3
"""SDFS/68 v3 の SD イメージで、起動していない側の system slot に新しい SDFS3SYS を書き、
検証に通ってから active marker を切り替える(#302)。

レイアウト・marker の形式・有効条件・選択規則は #300(docs/plans/sdfs68_v3/issue-300_system_slot_layout.md)、
ヘッダの範囲検査と API major は #310 の 1-5 に従う。ROM(src/main.asm の BOOT3)と同じ厳しさで
検査し、「今起動する slot」も ROM と同じ規則で決める。書き込み先はイメージファイルだけ。
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from mk_sdfs3sys import CHECKSUM_OFFSET, HEADER_SIZE, MAGIC, MAX_IMAGE_SIZE, checksum16


SECTOR_SIZE = 512
STAGE1_LBA = 16
MARKER_LBA = 48
SLOT_A_LBA = 64
SLOT_B_LBA = 96
SLOT_LBAS = (SLOT_A_LBA, SLOT_B_LBA)
SLOT_MAX_SECTORS = 32
SYSTEM_AREA_END_LBA = 128  # FAT32 区画はここ以降(#300 の重なり検出条件)

MARKER_MAGIC = b"SDFS3MRK"
MARKER_VERSION = 1
MARKER_SIZE = 32
MARKER_FLAG_CHECKSUM16 = 0x01

API_MAGIC = b"SDFS3API"
API_MAJOR = 2
HEADER_VERSION = 1
HEADER_FLAGS = 0x01  # ROM は flags == 1 を求める(BOOT3_CHECK_HEADER)
GENERATION_OFFSET = 0x1C
RAM_FLOOR = 0x4000  # SDFS3_RAM_FLOOR
RAM_END = 0x7FFF  # USER_RAM_END

assert SLOT_A_LBA + SLOT_MAX_SECTORS <= SLOT_B_LBA
assert STAGE1_LBA + 32 <= MARKER_LBA < SLOT_A_LBA
assert SLOT_B_LBA + SLOT_MAX_SECTORS <= SYSTEM_AREA_END_LBA
assert SLOT_MAX_SECTORS * SECTOR_SIZE == MAX_IMAGE_SIZE


class SlotUpdateError(Exception):
    """更新を止めた理由。止めた時点までに marker は書き換えていない(stage で区別する)。"""

    def __init__(self, message: str, *, stage: str = "check") -> None:
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True)
class Marker:
    active_slot: int
    generation: int


@dataclass(frozen=True)
class SlotInfo:
    lba: int
    valid: bool
    generation: int  # 生の +$1C(無効でも読めた値。読めなければ 0)
    reason: str


@dataclass(frozen=True)
class UpdatePlan:
    marker: Marker | None
    slots: tuple[SlotInfo, SlotInfo]
    current: int | None  # ROM が今起動する slot(0=A、1=B)。どちらも無効なら None
    target: int
    slot_generation: int
    marker_generation: int


# ---------------------------------------------------------------------------
# 検査
# ---------------------------------------------------------------------------


def validate_system(data: bytes) -> int:
    """SDFS3SYS(ちょうど image_size バイト、または slot の中身)を ROM と同じ条件で検査し、
    image_size を返す。満たさなければ ValueError。"""
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
    if image_size < HEADER_SIZE + 1 or image_size > MAX_IMAGE_SIZE:
        raise ValueError(f"SDFS3SYS image size {image_size} is out of range")
    if len(data) < image_size:
        raise ValueError("SDFS3SYS is shorter than its image size")
    payload = image_size - HEADER_SIZE
    load = _u16(data, 0x0C)
    if load < RAM_FLOOR or load + payload > RAM_END + 1:
        raise ValueError(f"SDFS3SYS load range ${load:04X}+{payload} is outside ${RAM_FLOOR:04X}-${RAM_END:04X}")
    entry = _u16(data, 0x10)
    api = _u16(data, 0x12)
    # CCP 入口表は [load, core)、核の先頭は (load, load+payload-1](BB_CHECK_VALID)
    if not 0 < api < payload:
        raise ValueError("SDFS3SYS +$12 (core / SDFS3API) points outside the image")
    if entry >= api:
        raise ValueError("SDFS3SYS +$10 (CCP vectors) must be inside the CCP, below +$12")
    # SDFS3API の署名と major の 9 バイトがイメージに収まる(BB_CHECK_API)
    if api + 9 > payload:
        raise ValueError("SDFS3API header does not fit in the image")
    core = HEADER_SIZE + api
    if data[core : core + 8] != API_MAGIC:
        raise ValueError("SDFS3API signature not found at +$12")
    if data[core + 8] != API_MAJOR:
        raise ValueError(f"SDFS3API major is {data[core + 8]}, not {API_MAJOR}")
    if checksum16(data[:image_size]) != _u16(data, CHECKSUM_OFFSET):
        raise ValueError("SDFS3SYS checksum mismatch")
    return image_size


def parse_marker(sector: bytes) -> Marker | None:
    """#300 の marker 有効条件を全部満たせば Marker、そうでなければ None。"""
    if len(sector) != SECTOR_SIZE:
        return None
    if sector[0:8] != MARKER_MAGIC or sector[0x08] != MARKER_VERSION:
        return None
    size = _u16(sector, 0x1A)
    if not MARKER_SIZE <= size <= SECTOR_SIZE:
        return None
    if not sector[0x0B] & MARKER_FLAG_CHECKSUM16:
        return None
    if _marker_checksum(sector) != _u16(sector, 0x18):
        return None
    if sector[0x09] not in (0, 1) or sector[0x0A] != 2:
        return None
    if (_u16(sector, 0x0E), _u16(sector, 0x10), _u16(sector, 0x12)) != (SLOT_MAX_SECTORS, SLOT_A_LBA, SLOT_B_LBA):
        return None
    return Marker(active_slot=sector[0x09], generation=_u16(sector, 0x0C))


def build_marker(active_slot: int, generation: int) -> bytes:
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
    _put_u16(sector, 0x18, _marker_checksum(sector))
    return bytes(sector)


def slot_info(lba: int, data: bytes) -> SlotInfo:
    generation = _u16(data, GENERATION_OFFSET) if len(data) >= HEADER_SIZE else 0
    try:
        validate_system(data)
    except ValueError as exc:
        return SlotInfo(lba, False, generation, str(exc))
    return SlotInfo(lba, True, generation, "ok")


def select_boot_slot(marker: Marker | None, slots: tuple[SlotInfo, SlotInfo]) -> int | None:
    """ROM の BOOT3 が起動する slot(#300 の選択規則、#301 の実装と同じ結果)。"""
    if marker is not None and slots[marker.active_slot].valid:
        return marker.active_slot
    a, b = slots
    if marker is None and a.valid and b.valid and a.generation and b.generation and b.generation > a.generation:
        return 1
    if a.valid:
        return 0
    if b.valid:
        return 1
    return None


def next_generation(slots: tuple[SlotInfo, SlotInfo]) -> int:
    """有効な slot の世代の最大 + 1。$FFFF からは上げない(#300 が作らないとした $FFFF と 1 の
    並びになるため)。"""
    current = max((s.generation for s in slots if s.valid), default=0)
    if current >= 0xFFFF:
        raise SlotUpdateError("slot generation is already $FFFF; refusing to wrap to 1")
    return current + 1


def check_layout(device: "SectorDevice") -> None:
    """#300 の重なり検出条件。MBR の区画が system 領域(LBA 0〜127)に重ならないこと。"""
    if device.sector_count < SYSTEM_AREA_END_LBA:
        raise SlotUpdateError(f"image is shorter than {SYSTEM_AREA_END_LBA} sectors")
    mbr = device.read(0, 1)
    if mbr[510:512] != b"\x55\xAA":
        raise SlotUpdateError("MBR signature 55AA not found; cannot prove the partitions avoid the system area")
    for index in range(4):
        entry = mbr[446 + index * 16 : 446 + (index + 1) * 16]
        ptype = entry[4]
        start = int.from_bytes(entry[8:12], "little")
        count = int.from_bytes(entry[12:16], "little")
        if ptype == 0 or count == 0:
            continue
        if start < SYSTEM_AREA_END_LBA:
            raise SlotUpdateError(
                f"partition {index + 1} starts at LBA {start}, overlapping the system area (LBA 0-{SYSTEM_AREA_END_LBA - 1})"
            )


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------


class SectorDevice:
    """セクタ単位の読み書き。テストはこれを差し替えて失敗を注入する。"""

    def __init__(self, handle, sector_count: int) -> None:
        self.handle = handle
        self.sector_count = sector_count

    def read(self, lba: int, count: int) -> bytes:
        self.handle.seek(lba * SECTOR_SIZE)
        data = self.handle.read(count * SECTOR_SIZE)
        if len(data) != count * SECTOR_SIZE:
            raise SlotUpdateError(f"short read at LBA {lba}", stage="io")
        return data

    def write(self, lba: int, data: bytes) -> None:
        assert len(data) % SECTOR_SIZE == 0
        if lba < MARKER_LBA or lba + len(data) // SECTOR_SIZE > SYSTEM_AREA_END_LBA:
            raise SlotUpdateError(f"refusing to write outside LBA {MARKER_LBA}-{SYSTEM_AREA_END_LBA - 1}")
        self.handle.seek(lba * SECTOR_SIZE)
        self.handle.write(data)

    def flush(self) -> None:
        self.handle.flush()
        os.fsync(self.handle.fileno())


def prepare_image(new_image: bytes, generation: int) -> bytes:
    """世代を入れて和を付け直した SDFS3SYS。入れる前と後の両方で検査する。"""
    size = validate_system(new_image)
    if size != len(new_image):
        raise ValueError(f"SDFS3SYS file is {len(new_image)} bytes but its header says {size}")
    data = bytearray(new_image)
    _put_u16(data, GENERATION_OFFSET, generation)
    _put_u16(data, CHECKSUM_OFFSET, 0)
    _put_u16(data, CHECKSUM_OFFSET, checksum16(bytes(data)))
    validate_system(bytes(data))
    return bytes(data)


def read_state(device: SectorDevice) -> tuple[Marker | None, tuple[SlotInfo, SlotInfo]]:
    marker = parse_marker(device.read(MARKER_LBA, 1))
    slots = tuple(slot_info(lba, device.read(lba, SLOT_MAX_SECTORS)) for lba in SLOT_LBAS)
    return marker, slots  # type: ignore[return-value]


def plan_update(device: SectorDevice, new_image: bytes) -> UpdatePlan:
    try:
        prepare_image(new_image, 1)
    except ValueError as exc:
        raise SlotUpdateError(f"new SDFS3SYS is invalid: {exc}") from exc
    check_layout(device)
    marker, slots = read_state(device)
    current = select_boot_slot(marker, slots)
    target = 0 if current is None else 1 - current
    marker_generation = 1 if marker is None else marker.generation % 0xFFFF + 1
    return UpdatePlan(marker, slots, current, target, next_generation(slots), marker_generation)


def apply_update(device: SectorDevice, new_image: bytes, plan: UpdatePlan) -> None:
    """slot を書いて読み戻しで確かめ、通ったときだけ marker を書く(#300 の更新時の規約)。"""
    try:
        image = prepare_image(new_image, plan.slot_generation)
    except ValueError as exc:
        raise SlotUpdateError(f"new SDFS3SYS is invalid: {exc}") from exc
    lba = SLOT_LBAS[plan.target]
    slot_data = image + bytes(SLOT_MAX_SECTORS * SECTOR_SIZE - len(image))
    device.write(lba, slot_data)
    device.flush()
    readback = device.read(lba, SLOT_MAX_SECTORS)
    if readback != slot_data:
        raise SlotUpdateError(f"slot readback at LBA {lba} does not match; marker left unchanged", stage="slot")
    try:
        validate_system(readback)
    except ValueError as exc:
        raise SlotUpdateError(f"slot readback is invalid ({exc}); marker left unchanged", stage="slot") from exc

    marker = build_marker(plan.target, plan.marker_generation)
    device.write(MARKER_LBA, marker)
    device.flush()
    after_marker, after_slots = read_state(device)
    if after_marker != Marker(plan.target, plan.marker_generation):
        raise SlotUpdateError("marker readback is invalid", stage="marker")
    if select_boot_slot(after_marker, after_slots) != plan.target:
        raise SlotUpdateError("after the update BOOT3 would not pick the new slot", stage="marker")


def open_image(path: Path, *, writable: bool):
    """通常ファイルだけを開く。判定は開いた fd で行う(symlink 経由のデバイスも弾く)。"""
    handle = open(path, "r+b" if writable else "rb")
    try:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise SlotUpdateError(f"{path} is not a regular file; only SD image files are supported")
        if info.st_size % SECTOR_SIZE:
            raise SlotUpdateError(f"{path} size is not a multiple of {SECTOR_SIZE}")
    except BaseException:
        handle.close()
        raise
    return handle, info.st_size // SECTOR_SIZE


def describe(plan: UpdatePlan) -> str:
    names = "AB"
    lines = []
    if plan.marker is None:
        lines.append("marker: invalid or absent")
    else:
        lines.append(f"marker: active={names[plan.marker.active_slot]} generation={plan.marker.generation}")
    for name, slot in zip(names, plan.slots):
        state = "valid" if slot.valid else f"invalid ({slot.reason})"
        lines.append(f"slot {name} (LBA {slot.lba}): generation={slot.generation} {state}")
    lines.append(f"boots now: {'none' if plan.current is None else names[plan.current]}")
    lines.append(
        f"update: slot {names[plan.target]} (LBA {SLOT_LBAS[plan.target]}) generation={plan.slot_generation}, "
        f"marker generation={plan.marker_generation}"
    )
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write SDFS3SYS to the inactive system slot of an SDFS/68 v3 SD image file, "
        "verify it, then switch the active marker.",
    )
    parser.add_argument("--image", required=True, type=Path, help="SD image file (block devices are refused)")
    parser.add_argument("--system", required=True, type=Path, help="new SDFS3SYS image")
    parser.add_argument("--dry-run", action="store_true", help="report the plan without writing")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        new_image = args.system.read_bytes()
        handle, sectors = open_image(args.image, writable=not args.dry_run)
        with handle:
            device = SectorDevice(handle, sectors)
            plan = plan_update(device, new_image)
            print(describe(plan))
            if args.dry_run:
                print("dry run: nothing written")
                return 0
            apply_update(device, new_image, plan)
        print("done")
    except OSError as exc:
        print(f"sdfs3-slot-update: {exc}", file=sys.stderr)
        return 1
    except SlotUpdateError as exc:
        print(f"sdfs3-slot-update: {exc}", file=sys.stderr)
        return 2
    return 0


def _marker_checksum(sector: bytes) -> int:
    data = bytearray(sector)
    data[0x18] = 0
    data[0x19] = 0
    return sum(data) & 0xFFFF


def _u16(data: bytes, offset: int) -> int:
    return (data[offset] << 8) | data[offset + 1]


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset] = (value >> 8) & 0xFF
    data[offset + 1] = value & 0xFF


if __name__ == "__main__":
    sys.exit(main())
