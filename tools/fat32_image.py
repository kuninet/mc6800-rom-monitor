"""Small deterministic FAT32 image writer used by tests and mk-sdfs."""

from __future__ import annotations

from dataclasses import dataclass


SECTOR_SIZE = 512
EOC = 0x0FFFFFFF
DEFAULT_PARTITION_START_LBA = 32
DEFAULT_RESERVED_SECTORS = 4
DEFAULT_FAT_COUNT = 2
DEFAULT_SECTORS_PER_CLUSTER = 1
DEFAULT_ROOT_CLUSTER = 2
DEFAULT_VOLUME_SERIAL = 0x68004800
DEFAULT_VOLUME_LABEL = b"MC6800 SD  "
MIN_FAT32_DATA_CLUSTERS = 65525


@dataclass(frozen=True)
class Fat32Layout:
    volume_start_lba: int
    fat_lba: int
    root_dir_lba: int
    data_start_lba: int
    total_volume_sectors: int
    reserved_sectors: int = DEFAULT_RESERVED_SECTORS
    fat_count: int = DEFAULT_FAT_COUNT
    fat_size_sectors: int = 1
    sectors_per_cluster: int = DEFAULT_SECTORS_PER_CLUSTER
    root_cluster: int = DEFAULT_ROOT_CLUSTER

    def cluster_lba(self, cluster: int) -> int:
        return self.data_start_lba + (cluster - 2) * self.sectors_per_cluster


@dataclass(frozen=True)
class Fat32File:
    name: bytes
    data: bytes
    attr: int = 0x20

    def __post_init__(self) -> None:
        if len(self.name) != 11:
            raise ValueError("FAT 8.3 directory name must be 11 bytes")


def build_fat32_image_from_files(
    files: list[Fat32File],
    *,
    with_mbr: bool = True,
    partition_start_lba: int = DEFAULT_PARTITION_START_LBA,
    total_volume_sectors: int | None = None,
    reserved_sectors: int = DEFAULT_RESERVED_SECTORS,
    fat_count: int = DEFAULT_FAT_COUNT,
    sectors_per_cluster: int = DEFAULT_SECTORS_PER_CLUSTER,
    root_cluster: int = DEFAULT_ROOT_CLUSTER,
    volume_label: bytes = DEFAULT_VOLUME_LABEL,
) -> tuple[bytes, Fat32Layout]:
    """Build a simple read-only FAT32 image with root-directory files only."""
    if not files:
        raise ValueError("at least one root file is required")
    if len(files) >= entries_per_cluster(sectors_per_cluster):
        raise ValueError("too many root files for a single root directory cluster")
    if len(volume_label) != 11:
        raise ValueError("FAT volume label must be 11 bytes")

    cluster_cursor = root_cluster + 1
    file_clusters: list[tuple[Fat32File, list[int]]] = []
    for file in files:
        clusters_needed = max(1, cluster_count_for_size(len(file.data), sectors_per_cluster))
        clusters = list(range(cluster_cursor, cluster_cursor + clusters_needed))
        cluster_cursor += clusters_needed
        file_clusters.append((file, clusters))

    minimum_data_clusters = cluster_cursor - 2
    if total_volume_sectors is None:
        data_clusters = max(MIN_FAT32_DATA_CLUSTERS, minimum_data_clusters)
        fat_size_sectors = sector_count_for_size((data_clusters + 2) * 4)
        total_volume_sectors = (
            reserved_sectors
            + fat_count * fat_size_sectors
            + data_clusters * sectors_per_cluster
        )
    else:
        fat_size_sectors = fat_size_for_volume(
            total_volume_sectors=total_volume_sectors,
            reserved_sectors=reserved_sectors,
            fat_count=fat_count,
            sectors_per_cluster=sectors_per_cluster,
        )
    minimum_volume_sectors = (
        reserved_sectors
        + fat_count * fat_size_sectors
        + minimum_data_clusters * sectors_per_cluster
    )
    if total_volume_sectors < minimum_volume_sectors:
        raise ValueError("total volume sectors is too small for requested files")

    volume_start = partition_start_lba if with_mbr else 0
    image = bytearray((volume_start + total_volume_sectors) * SECTOR_SIZE)
    layout = layout_for_image(
        with_mbr=with_mbr,
        partition_start_lba=partition_start_lba,
        total_volume_sectors=total_volume_sectors,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size_sectors,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=root_cluster,
    )

    if with_mbr:
        write_mbr(image, volume_start, total_volume_sectors)
    write_vbr(
        image,
        volume_start,
        total_volume_sectors=total_volume_sectors,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size_sectors,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=root_cluster,
        volume_label=volume_label,
    )
    write_fsinfo(image, volume_start + 1)
    _write_generated_fats(image, layout, file_clusters)
    _write_generated_root_dir(image, layout, file_clusters)
    for file, clusters in file_clusters:
        write_file_data(image, layout, tuple(clusters), file.data, 0x00)
    return bytes(image), layout


def layout_for_image(
    *,
    with_mbr: bool,
    partition_start_lba: int = DEFAULT_PARTITION_START_LBA,
    total_volume_sectors: int = 64,
    reserved_sectors: int = DEFAULT_RESERVED_SECTORS,
    fat_count: int = DEFAULT_FAT_COUNT,
    fat_size_sectors: int = 1,
    sectors_per_cluster: int = DEFAULT_SECTORS_PER_CLUSTER,
    root_cluster: int = DEFAULT_ROOT_CLUSTER,
) -> Fat32Layout:
    volume_start = partition_start_lba if with_mbr else 0
    fat_lba = volume_start + reserved_sectors
    data_start = volume_start + reserved_sectors + fat_count * fat_size_sectors
    return Fat32Layout(
        volume_start_lba=volume_start,
        fat_lba=fat_lba,
        root_dir_lba=data_start + (root_cluster - 2) * sectors_per_cluster,
        data_start_lba=data_start,
        total_volume_sectors=total_volume_sectors,
        reserved_sectors=reserved_sectors,
        fat_count=fat_count,
        fat_size_sectors=fat_size_sectors,
        sectors_per_cluster=sectors_per_cluster,
        root_cluster=root_cluster,
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


def write_mbr(image: bytearray, start_lba: int, sector_count: int) -> None:
    mbr = bytearray(SECTOR_SIZE)
    entry = 446
    mbr[entry + 4] = 0x0C
    mbr[entry + 8:entry + 12] = start_lba.to_bytes(4, "little")
    mbr[entry + 12:entry + 16] = sector_count.to_bytes(4, "little")
    mbr[510:512] = b"\x55\xAA"
    write_sector(image, 0, mbr)


def write_vbr(
    image: bytearray,
    lba: int,
    *,
    total_volume_sectors: int,
    reserved_sectors: int,
    fat_count: int,
    fat_size_sectors: int,
    sectors_per_cluster: int,
    root_cluster: int,
    volume_label: bytes = DEFAULT_VOLUME_LABEL,
) -> None:
    if len(volume_label) != 11:
        raise ValueError("FAT volume label must be 11 bytes")
    vbr = bytearray(SECTOR_SIZE)
    vbr[0:3] = b"\xEB\x58\x90"
    vbr[3:11] = b"MSDOS5.0"
    vbr[11:13] = SECTOR_SIZE.to_bytes(2, "little")
    vbr[13] = sectors_per_cluster
    vbr[14:16] = reserved_sectors.to_bytes(2, "little")
    vbr[16] = fat_count
    vbr[17:19] = (0).to_bytes(2, "little")
    vbr[19:21] = (0).to_bytes(2, "little")
    vbr[21] = 0xF8
    vbr[22:24] = (0).to_bytes(2, "little")
    vbr[32:36] = total_volume_sectors.to_bytes(4, "little")
    vbr[36:40] = fat_size_sectors.to_bytes(4, "little")
    vbr[44:48] = root_cluster.to_bytes(4, "little")
    vbr[48:50] = (1).to_bytes(2, "little")
    vbr[50:52] = (0).to_bytes(2, "little")
    vbr[64] = 0x80
    vbr[66] = 0x29
    vbr[67:71] = DEFAULT_VOLUME_SERIAL.to_bytes(4, "little")
    vbr[71:82] = volume_label
    vbr[82:90] = b"FAT32   "
    vbr[510:512] = b"\x55\xAA"
    write_sector(image, lba, vbr)


def write_fsinfo(image: bytearray, lba: int) -> None:
    fsinfo = bytearray(SECTOR_SIZE)
    fsinfo[0:4] = b"RRaA"
    fsinfo[484:488] = b"rrAa"
    fsinfo[488:492] = (0xFFFFFFFF).to_bytes(4, "little")
    fsinfo[492:496] = (0xFFFFFFFF).to_bytes(4, "little")
    fsinfo[510:512] = b"\x55\xAA"
    write_sector(image, lba, fsinfo)


def write_sector(image: bytearray, lba: int, data: bytes | bytearray) -> None:
    if len(data) != SECTOR_SIZE:
        raise ValueError("sector data must be exactly 512 bytes")
    start = lba * SECTOR_SIZE
    image[start:start + SECTOR_SIZE] = data


def write_cluster(image: bytearray, layout: Fat32Layout, cluster: int, data: bytes) -> None:
    if len(data) != SECTOR_SIZE * layout.sectors_per_cluster:
        raise ValueError("cluster data has an unexpected size")
    for sector_index in range(layout.sectors_per_cluster):
        start = sector_index * SECTOR_SIZE
        write_sector(
            image,
            layout.cluster_lba(cluster) + sector_index,
            data[start:start + SECTOR_SIZE],
        )


def write_file_data(
    image: bytearray,
    layout: Fat32Layout,
    clusters: tuple[int, ...],
    data: bytes,
    fill: int,
) -> None:
    sector_count = max(1, sector_count_for_size(len(data)))
    cluster_count = max(1, cluster_count_for_size(len(data), layout.sectors_per_cluster))
    if cluster_count > len(clusters):
        raise ValueError("not enough clusters for file data")
    for sector_index in range(sector_count):
        chunk = data[sector_index * SECTOR_SIZE:(sector_index + 1) * SECTOR_SIZE]
        sector_data = chunk + bytes([fill]) * (SECTOR_SIZE - len(chunk))
        cluster_index = sector_index // layout.sectors_per_cluster
        sector_in_cluster = sector_index % layout.sectors_per_cluster
        lba = layout.cluster_lba(clusters[cluster_index]) + sector_in_cluster
        write_sector(image, lba, sector_data)


def sector_count_for_size(size: int) -> int:
    return (size + SECTOR_SIZE - 1) // SECTOR_SIZE


def cluster_count_for_size(size: int, sectors_per_cluster: int) -> int:
    return (sector_count_for_size(size) + sectors_per_cluster - 1) // sectors_per_cluster


def entries_per_cluster(sectors_per_cluster: int) -> int:
    return SECTOR_SIZE * sectors_per_cluster // 32


def fat_size_for_volume(
    *,
    total_volume_sectors: int,
    reserved_sectors: int,
    fat_count: int,
    sectors_per_cluster: int,
) -> int:
    fat_size = 1
    while True:
        data_sectors = total_volume_sectors - reserved_sectors - fat_count * fat_size
        if data_sectors <= 0:
            raise ValueError("total volume sectors is too small for FAT32 layout")
        data_clusters = data_sectors // sectors_per_cluster
        needed = sector_count_for_size((data_clusters + 2) * 4)
        if needed == fat_size:
            return fat_size
        fat_size = needed


def _write_generated_fats(
    image: bytearray,
    layout: Fat32Layout,
    file_clusters: list[tuple[Fat32File, list[int]]],
) -> None:
    fat = bytearray(SECTOR_SIZE * layout.fat_size_sectors)
    entries = {
        0: 0x0FFFFFF8,
        1: EOC,
        layout.root_cluster: EOC,
    }
    for _file, clusters in file_clusters:
        for index, cluster in enumerate(clusters):
            entries[cluster] = clusters[index + 1] if index + 1 < len(clusters) else EOC
    for cluster, value in entries.items():
        offset = cluster * 4
        fat[offset:offset + 4] = value.to_bytes(4, "little")
    for copy_index in range(layout.fat_count):
        base_lba = layout.fat_lba + copy_index * layout.fat_size_sectors
        for sector_index in range(layout.fat_size_sectors):
            start = sector_index * SECTOR_SIZE
            write_sector(image, base_lba + sector_index, fat[start:start + SECTOR_SIZE])


def _write_generated_root_dir(
    image: bytearray,
    layout: Fat32Layout,
    file_clusters: list[tuple[Fat32File, list[int]]],
) -> None:
    root = bytearray(SECTOR_SIZE * layout.sectors_per_cluster)
    for index, (file, clusters) in enumerate(file_clusters):
        start = index * 32
        root[start:start + 32] = root_entry(file.name, file.attr, clusters[0], len(file.data))
    root[len(file_clusters) * 32] = 0x00
    write_cluster(image, layout, layout.root_cluster, root)
