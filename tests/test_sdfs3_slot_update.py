#!/usr/bin/env python3
"""PC 側の system slot 更新ツール(tools/sdfs3_slot_update.py、#302)のテスト。

前半は Python だけで検査・選択・書き込み範囲・CLI を確かめる。後半はツールで更新した SD イメージを
ROM のエミュレータで BOOT3 し、ツールが「今起動する」と判断した slot と ROM の BB_SLOT_LBA が
一致することを、更新前・更新後・途中失敗のあと・marker が壊れたあとの各状態で確かめる。
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
TOOL = PROJECT_ROOT / "tools" / "sdfs3_slot_update.py"
TEMP_ROOT = PROJECT_ROOT / "build" / "tmp"

import sdfs3_slot_update as su  # noqa: E402
import test_sdfs68_v3_build as v3  # noqa: E402
from mk_sdfs3sys import build_sdfs3sys_image  # noqa: E402

SECTOR = su.SECTOR_SIZE
SLOT_BYTES = su.SLOT_MAX_SECTORS * SECTOR


# ---------------------------------------------------------------------------
# 補助
# ---------------------------------------------------------------------------


class MemDevice(su.SectorDevice):
    """bytearray の上の SectorDevice(fsync しない)。"""

    def __init__(self, image: bytes) -> None:
        super().__init__(io.BytesIO(bytearray(image)), len(image) // SECTOR)

    def flush(self) -> None:
        pass

    @property
    def data(self) -> bytes:
        return self.handle.getvalue()


class TornSlotDevice(MemDevice):
    """slot への書き込みで、先頭 keep セクタだけ書いて止まる(電源断相当)。"""

    def __init__(self, image: bytes, keep: int) -> None:
        super().__init__(image)
        self.keep = keep

    def write(self, lba: int, data: bytes) -> None:
        if lba in su.SLOT_LBAS:
            super().write(lba, data[: self.keep * SECTOR])
            raise OSError("simulated power loss while writing the slot")
        super().write(lba, data)


class FlipOnWriteDevice(MemDevice):
    """slot に書いた内容の 1 バイトが化ける(読み戻しで見つかるはず)。"""

    def write(self, lba: int, data: bytes) -> None:
        if lba in su.SLOT_LBAS:
            data = bytearray(data)
            data[0x300] ^= 0x01
            data = bytes(data)
        super().write(lba, data)


class TornMarkerDevice(MemDevice):
    """marker の書き込みで先頭 16 バイトだけ書けて止まる。"""

    def write(self, lba: int, data: bytes) -> None:
        if lba == su.MARKER_LBA:
            sector = bytearray(self.read(lba, 1))
            sector[:16] = data[:16]
            super().write(lba, bytes(sector))
            raise OSError("simulated power loss while writing the marker")
        super().write(lba, data)


def synthetic_system(*, tag: int = 0, abi_major: int = 2) -> bytes:
    """CCP 1KB(先頭が入口表)+ 核(先頭に SDFS3API、major 2)の小さな SDFS3SYS。load = $6400。"""
    ccp = bytearray(0x400)
    ccp[-1] = tag
    core = bytearray(b"SDFS3API" + bytes([2, 0]) + bytes(0x200))
    return build_sdfs3sys_image(
        resident_data=bytes(ccp + core),
        load_address=0x6400,
        load_limit=0x7FFF,
        entry_address=0x6400,
        api_table_address=0x6800,
        abi_major=abi_major,
    )


def with_generation(image: bytes, generation: int) -> bytes:
    return su.prepare_image(image, generation)


def sd_image(slot_a: bytes | None = None, slot_b: bytes | None = None, marker: bytes | None = None) -> bytes:
    """MBR + FAT32(LBA 128)の SD。marker・slot は渡したものだけ置く。"""
    image = bytearray(v3._build_sdfs3sys_fat_sd_image(b"", [v3._file("README.TXT", b"HI\r\n")]))
    for lba, data in ((su.MARKER_LBA, marker), (su.SLOT_A_LBA, slot_a), (su.SLOT_B_LBA, slot_b)):
        if data is not None:
            image[lba * SECTOR : lba * SECTOR + len(data)] = data
    return bytes(image)


def state(data: bytes) -> tuple[su.Marker | None, tuple[su.SlotInfo, su.SlotInfo], int | None]:
    marker, slots = su.read_state(MemDevice(data))
    return marker, slots, su.select_boot_slot(marker, slots)


def update(data: bytes, system: bytes, device_cls=MemDevice, **kwargs) -> tuple[bytes, su.UpdatePlan, Exception | None]:
    device = device_cls(data, **kwargs)
    plan = su.plan_update(device, system)
    error: Exception | None = None
    try:
        su.apply_update(device, system, plan)
    except (OSError, su.SlotUpdateError) as exc:
        error = exc
    return device.data, plan, error


def changed_ranges(before: bytes, after: bytes) -> set[int]:
    """変わったセクタの LBA。"""
    assert len(before) == len(after)
    return {i // SECTOR for i in range(0, len(before), SECTOR) if before[i : i + SECTOR] != after[i : i + SECTOR]}


def allowed_sectors(target: int) -> set[int]:
    base = su.SLOT_LBAS[target]
    return {su.MARKER_LBA, *range(base, base + su.SLOT_MAX_SECTORS)}


def run_tool(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True, cwd=PROJECT_ROOT)


def temp_file(data: bytes, suffix: str = ".img") -> Path:
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    path = TEMP_ROOT / f"slot302-{uuid4().hex}{suffix}"
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# 単体(Python だけ)
# ---------------------------------------------------------------------------


def test_validate_system_matches_rom_conditions() -> None:
    """新しいイメージ・読み戻し・既存 slot の判定に使う検査が、ROM と同じ条件で落とす。"""
    good = synthetic_system()
    assert su.validate_system(good) == len(good)

    def broken(mutate, *, fix_sum: bool = True) -> bytes:
        data = bytearray(good)
        mutate(data)
        if fix_sum:
            data[0x18:0x1A] = b"\0\0"
            total = sum(data) & 0xFFFF
            data[0x18:0x1A] = bytes([total >> 8, total & 0xFF])
        return bytes(data)

    def put(offset: int, value: int):
        def mutate(data: bytearray) -> None:
            data[offset : offset + 2] = bytes([value >> 8, value & 0xFF])
        return mutate

    def setb(offset: int, value: int):
        def mutate(data: bytearray) -> None:
            data[offset] = value
        return mutate

    payload = len(good) - 32
    cases = [
        ("magic", setb(0, ord("X")), "magic"),
        ("header version", setb(8, 2), "version"),
        ("API major 1", setb(9, 1), "API major"),
        ("flags 0", setb(0x0B, 0), "flags"),
        ("flags 3", setb(0x0B, 3), "flags"),
        ("header size 33", put(0x1A, 33), "header size"),
        ("image size > 16384", put(0x0E, 16385), "image size"),
        ("image size 32", put(0x0E, 32), "image size"),
        ("image size > file", put(0x0E, len(good) + 1), "shorter"),
        ("load below $4000", put(0x0C, 0x3FFF), "load range"),
        ("load + payload > $8000", put(0x0C, 0x8000 - payload + 1), "load range"),
        ("+$12 = 0", put(0x12, 0), "+$12"),
        ("+$12 outside", put(0x12, payload), "+$12"),
        ("+$10 = +$12", put(0x10, 0x400), "+$10"),
        ("+$10 beyond +$12", put(0x10, 0x500), "+$10"),
        ("SDFS3API does not fit", put(0x12, payload - 8), "does not fit"),
        ("SDFS3API signature", setb(32 + 0x400, ord("X")), "signature"),
        ("SDFS3API major 1", setb(32 + 0x408, 1), "SDFS3API major"),
        ("checksum", setb(32 + 5, 0x55), "checksum"),
    ]
    for label, mutate, needle in cases:
        data = broken(mutate, fix_sum=label != "checksum")
        try:
            su.validate_system(data)
        except ValueError as exc:
            assert needle in str(exc), f"{label}: unexpected reason {exc}"
        else:
            raise AssertionError(f"{label}: should be rejected")
    # load + payload = $8000 ちょうどは通る(ROM の境界)
    edge = broken(put(0x0C, 0x8000 - payload))
    assert su.validate_system(edge) == len(good)
    print("[PASS] test_validate_system_matches_rom_conditions")


def test_marker_round_trip_and_validity() -> None:
    """build_marker が #300 の形式どおりで、テスト側(#301)の _marker と同じバイトになる。"""
    for active in (0, 1):
        for generation in (1, 7, 0xFFFF):
            sector = su.build_marker(active, generation)
            assert sector == v3._marker(active, generation=generation), f"marker {active}/{generation}"
            assert su.parse_marker(sector) == su.Marker(active, generation)
    assert su.parse_marker(v3._marker(0, size=512)) == su.Marker(0, 1)
    for fields in ({"magic": b"SDFS3MRX"}, {"version": 2}, {"active": 2}, {"slot_count": 3}, {"flags": 2},
                   {"slot_max": 33}, {"slot_a": 65}, {"slot_b": 0x0160}, {"size": 31}, {"size": 513},
                   {"fix_sum": False}):
        marker = v3._marker(**{"active": 0, **fields})
        if fields == {"fix_sum": False}:
            marker = bytearray(marker)
            marker[0x18] ^= 1
            marker = bytes(marker)
        assert su.parse_marker(marker) is None, f"marker {fields} should be invalid"
    assert su.parse_marker(bytes(SECTOR)) is None
    print("[PASS] test_marker_round_trip_and_validity")


def test_select_boot_slot_follows_rom_rules() -> None:
    """#301 の「#300 の選択規則と同じ結果になる理由」の表のとおりに選ぶ。"""
    def slot(lba: int, valid: bool, gen: int) -> su.SlotInfo:
        return su.SlotInfo(lba, valid, gen, "")

    A, B = su.SLOT_A_LBA, su.SLOT_B_LBA
    m_a, m_b = su.Marker(0, 1), su.Marker(1, 1)
    cases = [
        (m_a, slot(A, True, 1), slot(B, True, 9), 0),
        (m_b, slot(A, True, 9), slot(B, True, 1), 1),
        (m_a, slot(A, False, 9), slot(B, True, 1), 1),
        (m_b, slot(A, True, 1), slot(B, False, 9), 0),
        (None, slot(A, True, 3), slot(B, True, 4), 1),
        (None, slot(A, True, 4), slot(B, True, 3), 0),
        (None, slot(A, True, 0), slot(B, True, 5), 0),
        (None, slot(A, True, 5), slot(B, True, 5), 0),
        (None, slot(A, True, 0xFFFF), slot(B, True, 1), 0),
        (None, slot(A, False, 9), slot(B, True, 1), 1),
        (None, slot(A, True, 1), slot(B, False, 9), 0),
        (None, slot(A, False, 1), slot(B, False, 1), None),
        (m_a, slot(A, False, 1), slot(B, False, 1), None),
    ]
    for marker, a, b, want in cases:
        assert su.select_boot_slot(marker, (a, b)) == want, f"{marker} {a} {b}"
    print("[PASS] test_select_boot_slot_follows_rom_rules")


def test_update_lifecycle_and_write_range() -> None:
    """開発用イメージ(marker なし、A だけ、世代 0)→ B に世代 1 → A に世代 2。書き換えるのは
    更新先の slot と marker だけ。"""
    new = synthetic_system(tag=0x11)
    before = sd_image(slot_a=synthetic_system())
    after, plan, error = update(before, new)
    assert error is None, error
    assert (plan.current, plan.target, plan.slot_generation, plan.marker_generation) == (0, 1, 1, 1)
    assert changed_ranges(before, after) <= allowed_sectors(1)
    marker, slots, current = state(after)
    assert marker == su.Marker(1, 1) and current == 1 and slots[1].generation == 1
    assert after[su.SLOT_B_LBA * SECTOR : su.SLOT_B_LBA * SECTOR + len(new)] == with_generation(new, 1)
    assert after[su.SLOT_B_LBA * SECTOR + len(new) : (su.SLOT_B_LBA + 32) * SECTOR] == bytes(SLOT_BYTES - len(new))

    again, plan, error = update(after, synthetic_system(tag=0x22))
    assert error is None, error
    assert (plan.current, plan.target, plan.slot_generation, plan.marker_generation) == (1, 0, 2, 2)
    assert changed_ranges(after, again) <= allowed_sectors(0)
    marker, slots, current = state(again)
    assert marker == su.Marker(0, 2) and current == 0 and [s.generation for s in slots] == [2, 1]
    print("[PASS] test_update_lifecycle_and_write_range")


def test_update_targets_slot_rom_does_not_boot() -> None:
    """marker が A を指していても A が壊れていて ROM が B で起動するなら、更新先は A。
    両方無効なら A に書く(初回の導入)。"""
    broken_a = bytearray(with_generation(synthetic_system(), 5))
    broken_a[100] ^= 1
    before = sd_image(slot_a=bytes(broken_a), slot_b=with_generation(synthetic_system(), 2),
                      marker=su.build_marker(0, 4))
    after, plan, error = update(before, synthetic_system(tag=3))
    assert error is None and plan.current == 1 and plan.target == 0
    assert plan.slot_generation == 3, "the broken slot's generation must not count"
    assert changed_ranges(before, after) <= allowed_sectors(0)
    assert state(after)[0] == su.Marker(0, 5)

    blank, plan, error = update(sd_image(), synthetic_system())
    assert error is None and plan.current is None and plan.target == 0 and plan.slot_generation == 1
    assert state(blank)[2] == 0
    print("[PASS] test_update_targets_slot_rom_does_not_boot")


def test_failures_leave_marker_unchanged() -> None:
    """slot の書き込みの途中で止まる・読み戻しが違う、のどちらでも marker は書かない。
    marker の書き込みが途中で止まると marker 不正になり、ROM の規則では世代で選ぶ。"""
    old = sd_image(slot_a=with_generation(synthetic_system(), 2), slot_b=with_generation(synthetic_system(tag=1), 1),
                   marker=su.build_marker(0, 2))
    new = synthetic_system(tag=9)

    after, _plan, error = update(old, new, TornSlotDevice, keep=1)
    assert isinstance(error, OSError)
    assert changed_ranges(old, after) == {su.SLOT_B_LBA}, "only the first sector of B was written"
    marker, slots, current = state(after)
    assert marker == su.Marker(0, 2) and current == 0 and not slots[1].valid

    after, _plan, error = update(old, new, FlipOnWriteDevice)
    assert isinstance(error, su.SlotUpdateError) and error.stage == "slot", error
    assert after[su.MARKER_LBA * SECTOR : (su.MARKER_LBA + 1) * SECTOR] == su.build_marker(0, 2)
    assert state(after)[2] == 0

    after, _plan, error = update(old, new, TornMarkerDevice)
    assert isinstance(error, OSError)
    marker, slots, current = state(after)
    assert marker is None and [s.generation for s in slots] == [2, 3] and current == 1
    print("[PASS] test_failures_leave_marker_unchanged")


def test_rejects_bad_input_without_writing() -> None:
    """新しいイメージの不正・重なり・MBR の署名なし・短いイメージ・世代 $FFFF は書く前に止める。"""
    base = sd_image(slot_a=synthetic_system())
    bad_sum = bytearray(synthetic_system())
    bad_sum[40] ^= 1
    too_big = synthetic_system() + bytes(16384)
    cases = [
        ("checksum", base, bytes(bad_sum), "checksum"),
        ("abi 1", base, synthetic_system(abi_major=1), "API major"),
        ("trailing bytes", base, synthetic_system() + b"\0", "header says"),
        ("too big", base, too_big, None),
    ]
    overlap = bytearray(base)
    overlap[446 + 8 : 446 + 12] = (64).to_bytes(4, "little")
    cases.append(("partition at 64", bytes(overlap), synthetic_system(), "overlapping"))
    no_sig = bytearray(base)
    no_sig[510:512] = b"\0\0"
    cases.append(("no 55AA", bytes(no_sig), synthetic_system(), "55AA"))
    cases.append(("short image", base[: 100 * SECTOR], synthetic_system(), "shorter than 128"))
    top = sd_image(slot_a=with_generation(synthetic_system(), 0xFFFF))
    cases.append(("generation $FFFF", top, synthetic_system(), "$FFFF"))
    for label, image, system, needle in cases:
        device = MemDevice(image)
        try:
            plan = su.plan_update(device, system)
            su.apply_update(device, system, plan)
        except su.SlotUpdateError as exc:
            assert needle is None or needle in str(exc), f"{label}: {exc}"
        else:
            raise AssertionError(f"{label}: should be refused")
        assert device.data == image, f"{label}: image must not change"
    # 書き込みは marker と slot の範囲の外を拒む(最後の砦)
    device = MemDevice(base)
    for lba, count in ((0, 1), (47, 1), (127, 2), (2048, 1)):
        try:
            device.write(lba, bytes(count * SECTOR))
        except su.SlotUpdateError:
            pass
        else:
            raise AssertionError(f"write to LBA {lba} should be refused")
    assert device.data == base
    print("[PASS] test_rejects_bad_input_without_writing")


def test_cli_dry_run_update_and_refuses_devices() -> None:
    """CLI: --dry-run は書かない。通常の実行で更新する。デバイスと、デバイスへの symlink は拒む。"""
    image = sd_image(slot_a=synthetic_system())
    img = temp_file(image)
    system = temp_file(synthetic_system(tag=5), ".bin")
    link = TEMP_ROOT / f"slot302-{uuid4().hex}.lnk"
    try:
        result = run_tool("--image", str(img), "--system", str(system), "--dry-run")
        assert result.returncode == 0, result.stderr
        assert "update: slot B (LBA 96) generation=1" in result.stdout and "nothing written" in result.stdout
        assert img.read_bytes() == image

        result = run_tool("--image", str(img), "--system", str(system))
        assert result.returncode == 0 and "done" in result.stdout, result.stderr
        assert state(img.read_bytes())[0] == su.Marker(1, 1)

        os.symlink("/dev/null", link)
        for target in ("/dev/null", str(link)):
            result = run_tool("--image", target, "--system", str(system))
            assert result.returncode == 2 and "not a regular file" in result.stderr, (target, result.stderr)
        result = run_tool("--image", str(TEMP_ROOT / "missing.img"), "--system", str(system))
        assert result.returncode == 1, result.stderr
    finally:
        for path in (img, system, link):
            path.unlink(missing_ok=True)
    print("[PASS] test_cli_dry_run_update_and_refuses_devices")


# ---------------------------------------------------------------------------
# エミュレータ(ROM の BOOT3 と突き合わせる)
# ---------------------------------------------------------------------------


def _boot(config: dict, image: bytes, label: str) -> int:
    """BOOT3 し、ツールの選択と ROM の BB_SLOT_LBA が一致することを確かめて、起動した slot を返す。"""
    _marker, _slots, want = state(image)
    assert want is not None, f"{label}: the tool says nothing boots"
    raw, _log, reads, lba = v3._boot3_slot(config, image)
    assert v3.PROMPT in raw, f"{config['profile']} {label}: BOOT3 did not reach DOS: {raw[-300:]!r}"
    assert lba == su.SLOT_LBAS[want], f"{config['profile']} {label}: ROM booted LBA {lba}, tool expects {su.SLOT_LBAS[want]}"
    sectors = v3._system_sectors(config, lba)["all"]
    assert reads[-len(sectors) :] == sectors, f"{config['profile']} {label}: reads {reads}"
    return want


def test_rom_boots_updated_slot() -> None:
    """開発用イメージをツールで更新すると、ROM は新しい slot から起動する(2 回続けて A/B を往復)。"""
    for profile in v3.V3_PROFILES:
        config = v3._v3(profile)
        system = config["sdfs3sys"]
        dev = v3._wboot_sd_image(config)
        assert _boot(config, dev, "dev image") == 0
        once, plan, error = update(dev, system)
        assert error is None and plan.target == 1
        assert _boot(config, once, "after update 1") == 1
        twice, plan, error = update(once, v3._slot_image(config, 0, tag=v3.SLOT_TAG))
        assert error is None and plan.target == 0 and plan.slot_generation == 2
        assert _boot(config, twice, "after update 2") == 0
    print("[PASS] test_rom_boots_updated_slot")


def test_rom_boots_old_slot_after_failed_update() -> None:
    """slot の書き込みが途中で止まる・読み戻しが違うと、ROM は元の slot から起動する。marker が
    無く、途中まで書いた slot の世代が大きいときは、ROM はそちらを先に試して和で落ち、元へ戻る。"""
    for profile in v3.V3_PROFILES:
        config = v3._v3(profile)
        system = config["sdfs3sys"]
        # A 世代 2(active)、B 世代 1 の上に、3 回目の更新(B へ)を書きかける
        old, _plan, error = update(update(v3._wboot_sd_image(config), system)[0], system)
        assert error is None and state(old)[0] == su.Marker(0, 2)
        torn, _plan, error = update(old, v3._slot_image(config, 0, tag=v3.SLOT_TAG), TornSlotDevice, keep=3)
        assert isinstance(error, OSError)
        assert _boot(config, torn, "torn slot, marker A") == 0
        flipped, _plan, error = update(old, system, FlipOnWriteDevice)
        assert isinstance(error, su.SlotUpdateError) and error.stage == "slot"
        assert _boot(config, flipped, "readback mismatch") == 0

        # marker なし、A 世代 1 の上で B へ書きかける: B の先頭(世代 2)だけが書けている
        no_marker = v3._slots_sd_image(config, v3._slot_image(config, 1), None, None)
        torn, _plan, error = update(no_marker, system, TornSlotDevice, keep=3)
        assert isinstance(error, OSError)
        marker, slots, _ = state(torn)
        assert marker is None and slots[1].generation == 2 and not slots[1].valid
        raw, _log, reads, lba = v3._boot3_slot(config, torn)
        b_head = v3._system_sectors(config, su.SLOT_B_LBA)["all"]
        assert lba == su.SLOT_A_LBA and v3.PROMPT in raw
        assert reads[:3 + len(b_head)] == [su.MARKER_LBA, su.SLOT_A_LBA, su.SLOT_B_LBA, *b_head], (
            f"{profile}: ROM should try the torn B first: {reads}"
        )
    print("[PASS] test_rom_boots_old_slot_after_failed_update")


def test_rom_after_torn_marker() -> None:
    """marker の書き込みが途中で止まると、ROM は世代で選ぶ。両方の世代が 0 以外なら新しい slot、
    旧 slot が世代 0(開発用イメージから最初の更新)なら旧 slot A から起動する。"""
    for profile in v3.V3_PROFILES:
        config = v3._v3(profile)
        system = config["sdfs3sys"]
        dev = v3._wboot_sd_image(config)
        first, _plan, error = update(dev, system, TornMarkerDevice)
        assert isinstance(error, OSError) and state(first)[0] is None
        assert _boot(config, first, "torn marker, old generation 0") == 0

        old, _plan, error = update(dev, system)  # A 0 / B 1、marker B
        old, _plan, error = update(old, system)  # A 2 / B 1、marker A
        assert error is None
        torn, _plan, error = update(old, v3._slot_image(config, 0, tag=v3.SLOT_TAG), TornMarkerDevice)
        assert isinstance(error, OSError)
        marker, slots, _ = state(torn)
        assert marker is None and [s.generation for s in slots] == [2, 3]
        assert _boot(config, torn, "torn marker, generations 2/3") == 1
    print("[PASS] test_rom_after_torn_marker")


def main() -> None:
    print("=" * 50)
    print("SDFS/68 v3 system slot update tool tests")
    print("=" * 50)
    tests = [
        test_validate_system_matches_rom_conditions,
        test_marker_round_trip_and_validity,
        test_select_boot_slot_follows_rom_rules,
        test_update_lifecycle_and_write_range,
        test_update_targets_slot_rom_does_not_boot,
        test_failures_leave_marker_unchanged,
        test_rejects_bad_input_without_writing,
        test_cli_dry_run_update_and_refuses_devices,
        test_rom_boots_updated_slot,
        test_rom_boots_old_slot_after_failed_update,
        test_rom_after_torn_marker,
    ]
    if os.environ.get("SLOT302_SKIP_EMU"):
        tests = tests[:8]
    passed = failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as exc:
            print(f"[FAIL] {test.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"[ERROR] {test.__name__}: {type(exc).__name__}: {exc}")
            failed += 1
    print()
    print(f"Result: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
