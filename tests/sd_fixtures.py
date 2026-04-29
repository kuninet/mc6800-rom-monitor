"""Deterministic FAT32 fixtures for SD/FAT emulator tests."""

from __future__ import annotations

from dataclasses import dataclass


SECTOR_SIZE = 512
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
EOC = 0x0FFFFFFF

TEST_S_CONTENT = b"S1060200010203F1\r\nS9030000FC\r\n"
TEST_HEX_CONTENT = b":03030000AABBCCC9\r\n:00000001FF\r\n"
MULTI_CLUSTER_1_PREFIX = b"MULTI-CLUSTER-1"
MULTI_CLUSTER_2_PREFIX = b"MULTI-CLUSTER-2"


@dataclass(frozen=True)
class Fat32Layout:
    volume_start_lba: int
    fat_lba: int
    root_dir_lba: int
    data_start_lba: int

    def cluster_lba(self, cluster: int) -> int:
        return self.data_start_lba + (cluster - 2) * SECTORS_PER_CLUSTER


def build_fat32_image(with_mbr: bool) -> bytes:
    volume_start = PARTITION_START_LBA if with_mbr else 0
    total_sectors = volume_start + TOTAL_VOLUME_SECTORS
    image = bytearray(total_sectors * SECTOR_SIZE)
    layout = layout_for_image(with_mbr)

    if with_mbr:
        _write_mbr(image, volume_start, TOTAL_VOLUME_SECTORS)

    _write_vbr(image, volume_start)
    _write_fsinfo(image, volume_start + 1)
    _write_fats(image, layout)
    _write_root_dir(image, layout.root_dir_lba)
    _write_file_clusters(image, layout)
    return bytes(image)


def layout_for_image(with_mbr: bool) -> Fat32Layout:
    volume_start = PARTITION_START_LBA if with_mbr else 0
    fat_lba = volume_start + RESERVED_SECTORS
    data_start = volume_start + RESERVED_SECTORS + FAT_COUNT * FAT_SIZE_SECTORS
    return Fat32Layout(
        volume_start_lba=volume_start,
        fat_lba=fat_lba,
        root_dir_lba=data_start,
        data_start_lba=data_start,
    )


def sector(image: bytes, lba: int) -> bytes:
    start = lba * SECTOR_SIZE
    return image[start:start + SECTOR_SIZE]


def root_entry(name: bytes, attr: int, cluster: int, size: int) -> bytes:
    if len(name) != 11:
        raise ValueError("FAT 8.3 directory name must be 11 bytes")
    entry = bytearray(32)
    entry[0:11] = name
    entry[11] = attr
    entry[20:22] = ((cluster >> 16) & 0xFFFF).to_bytes(2, "little")
    entry[26:28] = (cluster & 0xFFFF).to_bytes(2, "little")
    entry[28:32] = size.to_bytes(4, "little")
    return bytes(entry)


def _write_mbr(image: bytearray, start_lba: int, sector_count: int) -> None:
    mbr = bytearray(SECTOR_SIZE)
    entry = 446
    mbr[entry + 4] = 0x0C
    mbr[entry + 8:entry + 12] = start_lba.to_bytes(4, "little")
    mbr[entry + 12:entry + 16] = sector_count.to_bytes(4, "little")
    mbr[510:512] = b"\x55\xAA"
    image[0:SECTOR_SIZE] = mbr


def _write_vbr(image: bytearray, lba: int) -> None:
    vbr = bytearray(SECTOR_SIZE)
    vbr[0:3] = b"\xEB\x58\x90"
    vbr[3:11] = b"MSDOS5.0"
    vbr[11:13] = SECTOR_SIZE.to_bytes(2, "little")
    vbr[13] = SECTORS_PER_CLUSTER
    vbr[14:16] = RESERVED_SECTORS.to_bytes(2, "little")
    vbr[16] = FAT_COUNT
    vbr[17:19] = (0).to_bytes(2, "little")
    vbr[19:21] = (0).to_bytes(2, "little")
    vbr[21] = 0xF8
    vbr[22:24] = (0).to_bytes(2, "little")
    vbr[32:36] = TOTAL_VOLUME_SECTORS.to_bytes(4, "little")
    vbr[36:40] = FAT_SIZE_SECTORS.to_bytes(4, "little")
    vbr[44:48] = ROOT_CLUSTER.to_bytes(4, "little")
    vbr[48:50] = (1).to_bytes(2, "little")
    vbr[50:52] = (0).to_bytes(2, "little")
    vbr[64] = 0x80
    vbr[66] = 0x29
    vbr[67:71] = (0x68004800).to_bytes(4, "little")
    vbr[71:82] = b"MC6800 SD  "
    vbr[82:90] = b"FAT32   "
    vbr[510:512] = b"\x55\xAA"
    _write_sector(image, lba, vbr)


def _write_fsinfo(image: bytearray, lba: int) -> None:
    fsinfo = bytearray(SECTOR_SIZE)
    fsinfo[0:4] = b"RRaA"
    fsinfo[484:488] = b"rrAa"
    fsinfo[488:492] = (0xFFFFFFFF).to_bytes(4, "little")
    fsinfo[492:496] = (0xFFFFFFFF).to_bytes(4, "little")
    fsinfo[510:512] = b"\x55\xAA"
    _write_sector(image, lba, fsinfo)


def _write_fats(image: bytearray, layout: Fat32Layout) -> None:
    fat = bytearray(SECTOR_SIZE)
    entries = {
        0: 0x0FFFFFF8,
        1: EOC,
        ROOT_CLUSTER: EOC,
        TEST_S_CLUSTER: EOC,
        TEST_HEX_CLUSTER: EOC,
        MULTI_CLUSTER_1: MULTI_CLUSTER_2,
        MULTI_CLUSTER_2: EOC,
    }
    for cluster, value in entries.items():
        offset = cluster * 4
        fat[offset:offset + 4] = value.to_bytes(4, "little")

    for copy_index in range(FAT_COUNT):
        _write_sector(image, layout.fat_lba + copy_index * FAT_SIZE_SECTORS, fat)


def _write_root_dir(image: bytearray, lba: int) -> None:
    root = bytearray(SECTOR_SIZE)
    entries = [
        root_entry(b"TEST    S  ", 0x20, TEST_S_CLUSTER, len(TEST_S_CONTENT)),
        root_entry(b"TEST    HEX", 0x20, TEST_HEX_CLUSTER, len(TEST_HEX_CONTENT)),
        root_entry(b"MULTI   BIN", 0x20, MULTI_CLUSTER_1, SECTOR_SIZE * 2),
    ]
    for index, entry in enumerate(entries):
        start = index * 32
        root[start:start + 32] = entry
    root[len(entries) * 32] = 0x00
    _write_sector(image, lba, root)


def _write_file_clusters(image: bytearray, layout: Fat32Layout) -> None:
    _write_cluster(image, layout, TEST_S_CLUSTER, _padded(TEST_S_CONTENT, 0x00))
    _write_cluster(image, layout, TEST_HEX_CLUSTER, _padded(TEST_HEX_CONTENT, 0x00))
    _write_cluster(image, layout, MULTI_CLUSTER_1, _padded(MULTI_CLUSTER_1_PREFIX, 0x11))
    _write_cluster(image, layout, MULTI_CLUSTER_2, _padded(MULTI_CLUSTER_2_PREFIX, 0x22))


def _write_cluster(image: bytearray, layout: Fat32Layout, cluster: int, data: bytes) -> None:
    _write_sector(image, layout.cluster_lba(cluster), data)


def _write_sector(image: bytearray, lba: int, data: bytes | bytearray) -> None:
    if len(data) != SECTOR_SIZE:
        raise ValueError("sector data must be exactly 512 bytes")
    start = lba * SECTOR_SIZE
    image[start:start + SECTOR_SIZE] = data


def _padded(prefix: bytes, fill: int) -> bytes:
    return prefix + bytes([fill]) * (SECTOR_SIZE - len(prefix))

