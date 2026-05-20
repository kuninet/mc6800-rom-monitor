"""Deterministic FAT32 fixtures for SD/FAT emulator tests."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from fat32_image import (  # noqa: E402
    EOC,
    SECTOR_SIZE,
    Fat32Layout,
    layout_for_image as _layout_for_image,
    root_entry,
    sector,
    write_cluster as _write_cluster_common,
    write_file_data as _write_file_data_common,
    write_fsinfo as _write_fsinfo_common,
    write_mbr as _write_mbr_common,
    write_sector as _write_sector_common,
    write_vbr as _write_vbr_common,
    cluster_count_for_size as _cluster_count_for_size,
    sector_count_for_size as _sector_count_for_size,
)


PARTITION_START_LBA = 32
TOTAL_VOLUME_SECTORS = 64
RESERVED_SECTORS = 4
FAT_COUNT = 2
FAT_SIZE_SECTORS = 1
SECTORS_PER_CLUSTER = 1
ROOT_CLUSTER = 2
TEST_S_CLUSTER = 3
TEST_HEX_CLUSTER = 4
MULTI_CLUSTER_1 = 5
MULTI_CLUSTER_2 = 6
ROOT_EXTRA_CLUSTER = 7
LATE_BIN_CLUSTER = 8
BIG_S_CLUSTER_1 = 9
BIG_S_CLUSTER_2 = 10
BIG_S_CLUSTER_3 = 11
BIG_S_CLUSTER_4 = 12

TEST_S_CONTENT = b"S1060200010203F1\r\nS9030000FC\r\n"
TEST_HEX_CONTENT = b":03030000AABBCCC9\r\n:00000001FF\r\n"
MULTI_CLUSTER_1_PREFIX = b"MULTI-CLUSTER-1"
MULTI_CLUSTER_2_PREFIX = b"MULTI-CLUSTER-2"
LATE_BIN_CONTENT = b"LATE-ROOT-ENTRY\r\n"


def _srec_record(address: int, data: bytes) -> bytes:
    count = len(data) + 3
    total = count + ((address >> 8) & 0xFF) + (address & 0xFF) + sum(data)
    checksum = (~total) & 0xFF
    return f"S1{count:02X}{address:04X}".encode("ascii") + data.hex().upper().encode("ascii") + f"{checksum:02X}\r\n".encode("ascii")


def _make_big_s_content() -> bytes:
    payload = bytes(value & 0xFF for value in range(640))
    records = [
        _srec_record(0x0500 + offset, payload[offset:offset + 16])
        for offset in range(0, len(payload), 16)
    ]
    records.append(b"S9030000FC\r\n")
    return b"".join(records)


BIG_S_CONTENT = _make_big_s_content()
BIG_S_CLUSTERS = (BIG_S_CLUSTER_1, BIG_S_CLUSTER_2, BIG_S_CLUSTER_3, BIG_S_CLUSTER_4)


def build_fat32_image(with_mbr: bool, root_chain: bool = False, sectors_per_cluster: int = SECTORS_PER_CLUSTER) -> bytes:
    volume_start = PARTITION_START_LBA if with_mbr else 0
    total_sectors = volume_start + TOTAL_VOLUME_SECTORS
    image = bytearray(total_sectors * SECTOR_SIZE)
    layout = layout_for_image(with_mbr, sectors_per_cluster=sectors_per_cluster)

    if with_mbr:
        _write_mbr(image, volume_start, TOTAL_VOLUME_SECTORS)

    _write_vbr(image, volume_start, sectors_per_cluster=sectors_per_cluster)
    _write_fsinfo(image, volume_start + 1)
    _write_fats(image, layout, root_chain=root_chain)
    _write_root_dir(image, layout, root_chain=root_chain)
    _write_file_clusters(image, layout, root_chain=root_chain)
    return bytes(image)


def layout_for_image(with_mbr: bool, sectors_per_cluster: int = SECTORS_PER_CLUSTER) -> Fat32Layout:
    return _layout_for_image(
        with_mbr=with_mbr,
        partition_start_lba=PARTITION_START_LBA,
        total_volume_sectors=TOTAL_VOLUME_SECTORS,
        reserved_sectors=RESERVED_SECTORS,
        fat_count=FAT_COUNT,
        fat_size_sectors=FAT_SIZE_SECTORS,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=ROOT_CLUSTER,
    )


def _write_mbr(image: bytearray, start_lba: int, sector_count: int) -> None:
    _write_mbr_common(image, start_lba, sector_count)


def _write_vbr(image: bytearray, lba: int, sectors_per_cluster: int) -> None:
    _write_vbr_common(
        image,
        lba,
        total_volume_sectors=TOTAL_VOLUME_SECTORS,
        reserved_sectors=RESERVED_SECTORS,
        fat_count=FAT_COUNT,
        fat_size_sectors=FAT_SIZE_SECTORS,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=ROOT_CLUSTER,
    )


def _write_fsinfo(image: bytearray, lba: int) -> None:
    _write_fsinfo_common(image, lba)


def _write_fats(image: bytearray, layout: Fat32Layout, root_chain: bool) -> None:
    fat = bytearray(SECTOR_SIZE)
    entries = {
        0: 0x0FFFFFF8,
        1: EOC,
        ROOT_CLUSTER: ROOT_EXTRA_CLUSTER if root_chain else EOC,
        TEST_S_CLUSTER: EOC,
        TEST_HEX_CLUSTER: EOC,
        MULTI_CLUSTER_1: MULTI_CLUSTER_2 if layout.sectors_per_cluster == 1 else EOC,
    }
    if layout.sectors_per_cluster == 1:
        entries[MULTI_CLUSTER_2] = EOC
    if root_chain:
        entries[ROOT_EXTRA_CLUSTER] = EOC
        entries[LATE_BIN_CLUSTER] = EOC
    big_clusters_needed = _cluster_count_for_size(len(BIG_S_CONTENT), layout.sectors_per_cluster)
    for index, cluster in enumerate(BIG_S_CLUSTERS[:big_clusters_needed]):
        if index + 1 < big_clusters_needed:
            entries[cluster] = BIG_S_CLUSTERS[index + 1]
        else:
            entries[cluster] = EOC
    for cluster, value in entries.items():
        offset = cluster * 4
        fat[offset:offset + 4] = value.to_bytes(4, "little")

    for copy_index in range(FAT_COUNT):
        _write_sector(image, layout.fat_lba + copy_index * FAT_SIZE_SECTORS, fat)


def _write_root_dir(image: bytearray, layout: Fat32Layout, root_chain: bool) -> None:
    root = bytearray(SECTOR_SIZE)
    entries = [
        root_entry(b"TEST    S  ", 0x20, TEST_S_CLUSTER, len(TEST_S_CONTENT)),
        root_entry(b"TEST    HEX", 0x20, TEST_HEX_CLUSTER, len(TEST_HEX_CONTENT)),
        root_entry(b"MULTI   BIN", 0x20, MULTI_CLUSTER_1, SECTOR_SIZE * 2),
        root_entry(b"BIGSREC S  ", 0x20, BIG_S_CLUSTER_1, len(BIG_S_CONTENT)),
    ]
    for index, entry in enumerate(entries):
        start = index * 32
        root[start:start + 32] = entry
    if root_chain:
        for index in range(len(entries), 16):
            start = index * 32
            root[start:start + 32] = root_entry(b"SKIP    TMP", 0x08, 0, 0)
    else:
        root[len(entries) * 32] = 0x00
    _write_sector(image, layout.root_dir_lba, root)

    if root_chain:
        extra = bytearray(SECTOR_SIZE)
        extra[0:32] = root_entry(b"LATE    BIN", 0x20, LATE_BIN_CLUSTER, len(LATE_BIN_CONTENT))
        extra[32] = 0x00
        _write_cluster(image, layout, ROOT_EXTRA_CLUSTER, extra)


def _write_file_clusters(image: bytearray, layout: Fat32Layout, root_chain: bool) -> None:
    _write_cluster(image, layout, TEST_S_CLUSTER, _padded(TEST_S_CONTENT, 0x00))
    _write_cluster(image, layout, TEST_HEX_CLUSTER, _padded(TEST_HEX_CONTENT, 0x00))
    _write_cluster(image, layout, MULTI_CLUSTER_1, _padded(MULTI_CLUSTER_1_PREFIX, 0x11))
    if layout.sectors_per_cluster == 1:
        _write_cluster(image, layout, MULTI_CLUSTER_2, _padded(MULTI_CLUSTER_2_PREFIX, 0x22))
    else:
        _write_sector(image, layout.cluster_lba(MULTI_CLUSTER_1) + 1, _padded(MULTI_CLUSTER_2_PREFIX, 0x22))
    _write_file_data(image, layout, BIG_S_CLUSTERS, BIG_S_CONTENT, 0x44)
    if root_chain:
        _write_cluster(image, layout, LATE_BIN_CLUSTER, _padded(LATE_BIN_CONTENT, 0x33))


def _write_cluster(image: bytearray, layout: Fat32Layout, cluster: int, data: bytes) -> None:
    if len(data) == SECTOR_SIZE:
        _write_sector(image, layout.cluster_lba(cluster), data)
        return
    _write_cluster_common(image, layout, cluster, data)


def _write_sector(image: bytearray, lba: int, data: bytes | bytearray) -> None:
    _write_sector_common(image, lba, data)


def _write_file_data(image: bytearray, layout: Fat32Layout, clusters: tuple[int, ...], data: bytes, fill: int) -> None:
    _write_file_data_common(image, layout, clusters, data, fill)


def _padded(prefix: bytes, fill: int) -> bytes:
    return prefix + bytes([fill]) * (SECTOR_SIZE - len(prefix))
