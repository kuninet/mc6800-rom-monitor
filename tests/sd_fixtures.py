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
ROOT_EXTRA_CLUSTER = 7
LATE_BIN_CLUSTER = 8
BIG_S_CLUSTER_1 = 9
BIG_S_CLUSTER_2 = 10
BIG_S_CLUSTER_3 = 11
BIG_S_CLUSTER_4 = 12
EOC = 0x0FFFFFFF

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


@dataclass(frozen=True)
class Fat32Layout:
    volume_start_lba: int
    fat_lba: int
    root_dir_lba: int
    data_start_lba: int
    sectors_per_cluster: int = SECTORS_PER_CLUSTER

    def cluster_lba(self, cluster: int) -> int:
        return self.data_start_lba + (cluster - 2) * self.sectors_per_cluster


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
    volume_start = PARTITION_START_LBA if with_mbr else 0
    fat_lba = volume_start + RESERVED_SECTORS
    data_start = volume_start + RESERVED_SECTORS + FAT_COUNT * FAT_SIZE_SECTORS
    return Fat32Layout(
        volume_start_lba=volume_start,
        fat_lba=fat_lba,
        root_dir_lba=data_start,
        data_start_lba=data_start,
        sectors_per_cluster=sectors_per_cluster,
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


def _write_vbr(image: bytearray, lba: int, sectors_per_cluster: int) -> None:
    vbr = bytearray(SECTOR_SIZE)
    vbr[0:3] = b"\xEB\x58\x90"
    vbr[3:11] = b"MSDOS5.0"
    vbr[11:13] = SECTOR_SIZE.to_bytes(2, "little")
    vbr[13] = sectors_per_cluster
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
    _write_sector(image, layout.cluster_lba(cluster), data)


def _write_sector(image: bytearray, lba: int, data: bytes | bytearray) -> None:
    if len(data) != SECTOR_SIZE:
        raise ValueError("sector data must be exactly 512 bytes")
    start = lba * SECTOR_SIZE
    image[start:start + SECTOR_SIZE] = data


def _write_file_data(image: bytearray, layout: Fat32Layout, clusters: tuple[int, ...], data: bytes, fill: int) -> None:
    sector_count = _sector_count_for_size(len(data))
    cluster_count = _cluster_count_for_size(len(data), layout.sectors_per_cluster)
    if cluster_count > len(clusters):
        raise ValueError("not enough clusters for file data")
    for sector_index in range(sector_count):
        chunk = data[sector_index * SECTOR_SIZE:(sector_index + 1) * SECTOR_SIZE]
        sector_data = chunk + bytes([fill]) * (SECTOR_SIZE - len(chunk))
        cluster_index = sector_index // layout.sectors_per_cluster
        sector_in_cluster = sector_index % layout.sectors_per_cluster
        lba = layout.cluster_lba(clusters[cluster_index]) + sector_in_cluster
        _write_sector(image, lba, sector_data)


def _sector_count_for_size(size: int) -> int:
    return (size + SECTOR_SIZE - 1) // SECTOR_SIZE


def _cluster_count_for_size(size: int, sectors_per_cluster: int) -> int:
    return (_sector_count_for_size(size) + sectors_per_cluster - 1) // sectors_per_cluster


def _padded(prefix: bytes, fill: int) -> bytes:
    return prefix + bytes([fill]) * (SECTOR_SIZE - len(prefix))
