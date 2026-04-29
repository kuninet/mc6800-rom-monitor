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
    assert "MC6800 MONITOR" in stdout, f"missing welcome message: {stdout!r}"
    assert "]" in stdout, f"missing prompt: {stdout!r}"
    print("[PASS] test_boot_prompt")


def test_dump_command():
    stdout, stderr, rc = run_emu("D0000\r\r")
    assert "0000" in stdout, f"missing dump line: {stdout!r}"
    print("[PASS] test_dump_command")


def test_dump_range_command():
    stdout, stderr, rc = run_emu("D0100\rD0100-011F\rDFFF0\rDFFF0-FFFF\rD0110-0100\rD0100-\r\r")
    assert "0100" in stdout and "0130" in stdout, f"missing 64-byte dump range: {stdout!r}"
    assert "0110" in stdout, f"missing explicit range line: {stdout!r}"
    assert "FFF0" in stdout, f"missing high-end range dump: {stdout!r}"
    assert stdout.count("?") >= 2, f"missing invalid range errors: {stdout!r}"
    print("[PASS] test_dump_range_command")


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


def test_help_command():
    stdout, stderr, rc = run_emu("H\r\r")
    assert "D M G L B C R U H F" in stdout, f"missing help command list: {stdout!r}"
    print("[PASS] test_help_command")


def test_breakpoint_query():
    input_text = (
        "B\r"
        "M0100\r86\r42\r3F\r.\r"
        "B0100\r"
        "B\r"
        "G0100\r"
        "B\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=20_000_000)
    assert "BP NONE" in stdout, f"missing empty breakpoint query: {stdout!r}"
    assert "BP 0100" in stdout, f"missing active breakpoint query: {stdout!r}"
    assert stdout.count("BP NONE") >= 2, f"break hit did not clear breakpoint query: {stdout!r}"
    print("[PASS] test_breakpoint_query")


def test_breakpoint_resume_and_clear():
    input_text = (
        "M0100\r"
        "86\r42\rB7\r01\r20\r86\r99\rB7\r01\r21\r3F\r.\r"
        "B0105\r"
        "G0100\r"
        "D0120-0121\r"
        "R\r"
        "D0120-0121\r"
        "M0140\r86\r55\r3F\r.\r"
        "B0140\rC\rD0140-0140\r"
        "BE200\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=20_000_000)
    assert "BRK 0105" in stdout, f"missing breakpoint hit: {stdout!r}"
    assert "0120 42 00" in stdout, f"breakpoint did not stop before second store: {stdout!r}"
    assert "0120 42 99" in stdout, f"resume did not run restored instruction: {stdout!r}"
    assert "0140 86" in stdout, f"clear did not restore original opcode: {stdout!r}"
    assert "?" in stdout, f"missing ROM breakpoint error: {stdout!r}"
    print("[PASS] test_breakpoint_resume_and_clear")


def test_resume_requires_active_breakpoint():
    stdout, stderr, rc = run_emu("R\r\r", max_cycles=2_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "?" in stdout, f"resume without breakpoint did not report error: {stdout!r}"
    assert "BRK" not in stdout, f"resume without breakpoint should not enter break state: {stdout!r}"
    print("[PASS] test_resume_requires_active_breakpoint")


def test_breakpoint_resume_restores_registers():
    input_text = (
        "M0100\r"
        "86\r12\rC6\r34\rCE\r1A\r2B\r"
        "B7\r01\r20\rF7\r01\r21\rFF\r01\r22\r3F\r.\r"
        "B0107\r"
        "G0100\r"
        "R\r"
        "D0120-0123\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=20_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "BRK 0107" in stdout, f"missing breakpoint hit: {stdout!r}"
    assert "0120 12 34 1A 2B" in stdout, f"resume did not preserve A/B/X: {stdout!r}"
    print("[PASS] test_breakpoint_resume_restores_registers")


def test_breakpoint_resume_restores_user_sp():
    input_text = (
        "M0100\r"
        "8E\r1D\r00\rBF\r01\r30\r3F\r.\r"
        "B0103\r"
        "G0100\r"
        "R\r"
        "D0130-0131\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=20_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "BRK 0103" in stdout, f"missing breakpoint hit: {stdout!r}"
    assert "0130 1D 00" in stdout, f"resume did not restore user SP: {stdout!r}"
    print("[PASS] test_breakpoint_resume_restores_user_sp")


def test_fill_command():
    input_text = (
        "F0100-0103 AA\r"
        "D0100-0103\r"
        "F0100-01FF 00\r"
        "D0100-010F\r"
        "F0103-0100 00\r"
        "F0100-0103\r"
        "F0100-0103 100\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=20_000_000)
    assert "0100 AA AA AA AA" in stdout, f"fill AA range missing: {stdout!r}"
    assert "0100 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00" in stdout, (
        f"fill 00 range missing: {stdout!r}"
    )
    assert stdout.count("?") >= 3, f"missing fill argument errors: {stdout!r}"
    print("[PASS] test_fill_command")


def test_unassemble_command():
    stdout, stderr, rc = run_emu("M0100\r86\r12\rB7\r01\r20\r3F\rFF\r.\rU0100\r\r")
    assert "0100 86 LDAA #$12" in stdout, f"missing LDAA disassembly: {stdout!r}"
    assert "0102 B7 STAA $0120" in stdout, f"missing STAA disassembly: {stdout!r}"
    assert "0105 3F SWI" in stdout, f"missing SWI disassembly: {stdout!r}"
    assert "0106 FF DB $FF" in stdout, f"missing DB fallback: {stdout!r}"
    print("[PASS] test_unassemble_command")


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
        test_dump_range_command,
        test_modify_and_dump,
        test_go_swi_return,
        test_srec_load,
        test_ihex_load,
        test_error_display,
        test_help_command,
        test_breakpoint_query,
        test_breakpoint_resume_and_clear,
        test_resume_requires_active_breakpoint,
        test_breakpoint_resume_restores_registers,
        test_breakpoint_resume_restores_user_sp,
        test_fill_command,
        test_unassemble_command,
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
