#!/usr/bin/env python3
"""SBC6800 emulator smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EMU_PATH = PROJECT_ROOT / "emu" / "sbc6800_emu.py"
BUILD_ROM_PATH = PROJECT_ROOT / "build" / "mc6800-monitor.bin"
FIXTURE_ROM_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mc6800-monitor.bin"
DATAPACK_DIR = PROJECT_ROOT / "third_party" / "sbc6800_datapack"


def rom_path() -> Path:
    if BUILD_ROM_PATH.exists():
        return BUILD_ROM_PATH
    if os.environ.get("REQUIRE_BUILD_ROM") == "1":
        return BUILD_ROM_PATH
    return FIXTURE_ROM_PATH


def run_emu(input_text: str, max_cycles: int = 5_000_000, timeout: int = 10):
    input_bytes = input_text.encode("ascii")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(input_bytes)
        input_file = f.name

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(EMU_PATH),
                str(rom_path()),
                "--input",
                input_file,
                "--max-cycles",
                str(max_cycles),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=PROJECT_ROOT,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        return exc.stdout or "", (exc.stderr or "") + "[TIMEOUT]", -1
    finally:
        os.unlink(input_file)


def datapack_srec_script(filename: str, entry: str = "0100") -> str:
    path = DATAPACK_DIR / filename
    lines = [line.strip() for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith("S9")]
    lines.append(f"S903{entry}FB")
    return "L\r" + "\r".join(lines) + f"\rG{entry}\r\r"


def test_boot_prompt():
    stdout, stderr, rc = run_emu("\r\r")
    assert "*" in stdout, f"missing boot marker: {stdout!r}"
    assert "]" in stdout, f"missing prompt: {stdout!r}"
    print("[PASS] test_boot_prompt")


def test_dump_command():
    stdout, stderr, rc = run_emu("D0000\r\r")
    assert "0000" in stdout, f"missing dump line: {stdout!r}"
    print("[PASS] test_dump_command")


def test_modify_and_dump():
    stdout, stderr, rc = run_emu("M0100\rAA\r.\rD0100\r\r")
    assert "0100 AA" in stdout or " AA " in stdout, f"missing modified value: {stdout!r}"
    print("[PASS] test_modify_and_dump")


def test_go_swi_return():
    input_text = "M0100\r86\r55\rB7\r01\r10\r3F\r.\rG0100\rD0110\r\r"
    stdout, stderr, rc = run_emu(input_text, max_cycles=10_000_000)
    dump_lines = [line for line in stdout.splitlines() if "0110" in line and "55" in line]
    assert dump_lines, f"missing SWI return dump: {stdout!r}"
    print("[PASS] test_go_swi_return")


def test_srec_load():
    srec_data = "S1060200010203F1\r"
    srec_eof = "S9030000FC\r"
    stdout, stderr, rc = run_emu(f"L\r{srec_data}{srec_eof}D0200\r\r", max_cycles=10_000_000)
    assert "OK" in stdout, f"missing SREC OK: {stdout!r}"
    assert "0200 01 02 03" in stdout or "01 02 03" in stdout, f"missing loaded SREC bytes: {stdout!r}"
    print("[PASS] test_srec_load")


def test_ihex_load():
    ihex_data = ":03030000AABBCCC9\r"
    ihex_eof = ":00000001FF\r"
    stdout, stderr, rc = run_emu(f"L\r{ihex_data}{ihex_eof}D0300\r\r", max_cycles=10_000_000)
    assert "OK" in stdout, f"missing IHEX OK: {stdout!r}"
    assert "0300 AA BB CC" in stdout or "AA BB CC" in stdout, f"missing loaded IHEX bytes: {stdout!r}"
    print("[PASS] test_ihex_load")


def test_error_display():
    stdout, stderr, rc = run_emu("X\r\r")
    assert "?" in stdout, f"missing error marker: {stdout!r}"
    print("[PASS] test_error_display")


def test_datapack_hello():
    stdout, stderr, rc = run_emu(datapack_srec_script("HELLO.S"), max_cycles=2_000_000)
    assert "OK" in stdout, f"missing datapack HELLO load OK: {stdout!r}"
    assert "HELLO, WORLD" in stdout, f"missing datapack HELLO output: {stdout!r}"
    print("[PASS] test_datapack_hello")


def test_datapack_micbas13_boot():
    stdout, stderr, rc = run_emu(datapack_srec_script("MICBAS13.S"), max_cycles=20_000_000)
    assert "OK" in stdout, f"missing MICBAS13 load OK: {stdout!r}"
    assert "READY" in stdout, f"missing MICBAS13 READY output: {stdout!r}"
    print("[PASS] test_datapack_micbas13_boot")


def main():
    print("=" * 50)
    print("SBC6800 emulator smoke tests")
    print("=" * 50)

    rom = rom_path()
    if not rom.exists():
        print(f"[FAIL] ROM binary not found: {rom}")
        if os.environ.get("REQUIRE_BUILD_ROM") == "1":
            print("       CI requires a freshly built build/mc6800-monitor.bin.")
        else:
            print("       Run `make bin` first, or provide tests/fixtures/mc6800-monitor.bin.")
        sys.exit(1)

    tests = [
        test_boot_prompt,
        test_dump_command,
        test_modify_and_dump,
        test_go_swi_return,
        test_srec_load,
        test_ihex_load,
        test_error_display,
        test_datapack_hello,
        test_datapack_micbas13_boot,
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
        except Exception as exc:  # pragma: no cover - smoke script fallback
            print(f"[ERROR] {test.__name__}: {exc}")
            failed += 1

    print()
    print(f"Result: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
