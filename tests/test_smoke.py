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
FIXTURE_ROM_PATH = PROJECT_ROOT / "tests" / "fixtures" / "mc6800-monitor.bin"
DATAPACK_DIR = PROJECT_ROOT / "third_party" / "sbc6800_datapack"


def _default_build_rom_path() -> Path:
    suffix_by_profile = {
        "base": "",
        "sbcio": "-sbcio",
        "sbcio_vdg": "-sbcio-vdg",
        "k6802_vdg": "-k6802-vdg",
    }
    suffix = suffix_by_profile.get(os.environ.get("MONITOR_PROFILE", "base"), "")
    return PROJECT_ROOT / "build" / f"mc6800-monitor{suffix}.bin"


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if not value:
        return default
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


BUILD_ROM_PATH = _path_from_env("MONITOR_ROM_PATH", _default_build_rom_path())


def rom_path() -> Path:
    if BUILD_ROM_PATH.exists():
        return BUILD_ROM_PATH
    if os.environ.get("REQUIRE_BUILD_ROM") == "1":
        return BUILD_ROM_PATH
    return FIXTURE_ROM_PATH


def run_emu(input_text: str, max_cycles: int = 5_000_000, timeout: int = 10, key_input: str | None = None):
    input_bytes = input_text.encode("ascii")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(input_bytes)
        input_file = f.name
    key_input_file = None
    if key_input is not None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(key_input.encode("ascii"))
            key_input_file = f.name

    try:
        cmd = [
            sys.executable,
            str(EMU_PATH),
            str(rom_path()),
            "--input",
            input_file,
            "--max-cycles",
            str(max_cycles),
        ]
        if key_input_file is not None:
            cmd.extend(["--key-input", key_input_file])
        result = subprocess.run(
            cmd,
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
        if key_input_file is not None:
            os.unlink(key_input_file)


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
    if is_vdg_build() and is_keyboard_build():
        expected = "D DIR M MAP RAMTEST VDGTEST KEYTEST G L LF B C R U H F"
    elif is_vdg_build():
        expected = "D DIR M MAP RAMTEST VDGTEST G L LF B C R U H F"
    elif is_keyboard_build():
        expected = "D DIR M MAP RAMTEST KEYTEST G L LF B C R U H F"
    else:
        expected = "D DIR M MAP RAMTEST G L LF B C R U H F"
    assert expected in stdout, f"missing help command list: {stdout!r}"
    print("[PASS] test_help_command")


def is_sbcio_build() -> bool:
    return (
        "-sbcio" in BUILD_ROM_PATH.stem
        or "-k6802-vdg" in BUILD_ROM_PATH.stem
        or os.environ.get("MONITOR_PROFILE") in ("sbcio", "sbcio_vdg", "k6802_vdg")
    )


def is_vdg_build() -> bool:
    return (
        "-sbcio-vdg" in BUILD_ROM_PATH.stem
        or "-k6802-vdg" in BUILD_ROM_PATH.stem
        or os.environ.get("MONITOR_PROFILE") in ("sbcio_vdg", "k6802_vdg")
    )


def is_k6802_vdg_build() -> bool:
    return "-k6802-vdg" in BUILD_ROM_PATH.stem or os.environ.get("MONITOR_PROFILE") == "k6802_vdg"


def is_keyboard_build() -> bool:
    return is_sbcio_build()


def test_map_command():
    stdout, stderr, rc = run_emu("F0100-0103 5A\rMAP\rD0100-0103\r\r", max_cycles=5_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if is_k6802_vdg_build():
        expected = [
            "MAP K6802 VDG",
            "RAM 0000-7FFF",
            "USER 0000-7FFF",
            "WORK A000-BFFF",
            "SD A000",
            "MON A200",
            "MIK A300",
            "STK BFFF",
            "VRAM C000-DFFF",
            "VDG 8110",
            "KEY 8094-8095",
        ]
    elif is_vdg_build():
        expected = [
            "MAP SBCIO VDG",
            "RAM 0000-7FFF",
            "USER 0000-7FFF",
            "WORK C000-DFFF",
            "SD C000",
            "MON C200",
            "MIK C300",
            "STK DFFF",
            "VRAM A000-BFFF",
            "VDG 8110",
            "KEY 8094-8095",
        ]
    elif is_sbcio_build():
        expected = [
            "MAP SBCIO",
            "RAM 0000-7FFF",
            "USER 0000-7FFF",
            "WORK C000-DFFF",
            "SD C000",
            "MON C200",
            "MIK C300",
            "STK DFFF",
            "KEY 8094-8095",
        ]
    else:
        expected = [
            "MAP BASE",
            "RAM 0000-1FFF",
            "USER 0000-1FFF",
            "WORK 1C00-1FFF",
            "SD 1C00",
            "MON 1E00",
            "MIK 1F00",
            "STK 1F42",
        ]
    expected.append("ROM E000-FFFF")
    for text in expected:
        assert text in stdout, f"missing MAP output {text!r}: {stdout!r}"
    assert "0100 5A 5A 5A 5A" in stdout, f"MAP should not modify user RAM: {stdout!r}"
    print("[PASS] test_map_command")


def test_vdgtest_command():
    vram_start = "C000" if is_k6802_vdg_build() else "A000"
    vram_dump_end = "C017" if is_k6802_vdg_build() else "A017"
    vram_next = "C010" if is_k6802_vdg_build() else "A010"
    stdout, stderr, rc = run_emu(
        f"F8110-8110 5A\rVDGTEST\rD8110-8110\rD{vram_start}-{vram_dump_end}\r\r",
        max_cycles=10_000_000,
    )
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if is_vdg_build():
        assert "OK" in stdout, f"VDGTEST should report OK: {stdout!r}"
        assert "8110 00" in stdout, f"VDGTEST should write VDG mode to 8110: {stdout!r}"
        assert f"{vram_start} 4D 43 36 38 30 30 20 4D 4F 4E 49 54 4F 52 20 4B" in stdout, (
            f"VDGTEST should write message at {vram_start}: {stdout!r}"
        )
        assert f"{vram_next} 36 38 2D 56 44 47 60 60" in stdout, (
            f"VDGTEST should leave cleared screen bytes after message: {stdout!r}"
        )
    else:
        assert "?" in stdout, f"non-VDG builds should reject VDGTEST: {stdout!r}"
    print("[PASS] test_vdgtest_command")


def test_keytest_command():
    stdout, stderr, rc = run_emu("KEYTEST\r\r", key_input="A", max_cycles=10_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if is_keyboard_build():
        assert "KEY 41 A" in stdout, f"KEYTEST should report keyboard byte: {stdout!r}"
    else:
        assert "?" in stdout, f"base should reject KEYTEST: {stdout!r}"

    stdout, stderr, rc = run_emu("KEYTEST\r\r", key_input="\r", max_cycles=10_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if is_keyboard_build():
        assert "KEY 0D ." in stdout, f"KEYTEST should show control byte as dot: {stdout!r}"
    print("[PASS] test_keytest_command")


def test_ramtest_command():
    input_text = (
        "RAMTEST\r"
        "RAMTEST C000\r"
        "RAMTEST C000-\r"
        "RAMTEST -DFFF\r"
        "RAMTEST 02000-03FFF\r"
        "RAMTEST DFFF-C000\r"
        "RAMTEST 2000-3FFF X\r"
        "RAMTEST 0000-00FF\r"
        "RAMTEST 0000-1BFF\r"
        "RAMTEST 00F0-0100\r"
        "RAMTEST A000-BFFF\r"
        "RAMTEST E000-FFFF\r"
        "RAMTEST 8000-80FF\r"
        "RAMTEST 1C00-1FFF\r"
        "RAMTEST 7FFF-C000\r"
        "RAMTEST BFFF-C000\r"
        "RAMTEST DFFF-E000\r"
        "RAMTEST 2000-DFFF\r"
        "RAMTEST 0100-1BFF\r"
        "RAMTEST 0100-01FF\r"
        "RAMTEST 1BFF-2000\r"
        "RAMTEST 0100-7FFF\r"
        "RAMTEST 2000-7FFF\r"
        "RAMTEST 2000-3FFF\r"
        "RAMTEST 4000-7FFF\r"
        "RAMTEST C000-DFFF\r"
        "RAMTEST C200-C2FF\r"
        "R\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=80_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    if is_k6802_vdg_build():
        assert "RAMTEST 0100-1BFF" in stdout, f"missing low RAMTEST range echo: {stdout!r}"
        assert "RAMTEST 0100-01FF" in stdout, f"missing low subrange echo: {stdout!r}"
        assert "RAMTEST 1BFF-2000" in stdout, f"missing low boundary-crossing RAM echo: {stdout!r}"
        assert "RAMTEST 0100-7FFF" in stdout, f"missing low full RAM range echo: {stdout!r}"
        assert "RAMTEST 2000-7FFF" in stdout, f"missing extended RAMTEST range echo: {stdout!r}"
        assert "RAMTEST 2000-3FFF" in stdout, f"missing extended subrange echo: {stdout!r}"
        assert "RAMTEST 4000-7FFF" in stdout, f"missing upper extended subrange echo: {stdout!r}"
        assert "RAMTEST A000-BFFF" in stdout, f"missing K6802 work RAMTEST range echo: {stdout!r}"
        assert "RAMTEST C000-DFFF\nOK" not in stdout, f"K6802 VRAM range must be rejected: {stdout!r}"
        assert "RAMTEST C200-C2FF\nOK" not in stdout, f"K6802 VRAM subrange must be rejected: {stdout!r}"
        assert stdout.count("OK") >= 8, f"K6802 RAMTEST ranges should pass in emulator: {stdout!r}"
        assert "NG" not in stdout, f"K6802 RAMTEST should not report NG: {stdout!r}"
        assert stdout.count("?") >= 15, f"invalid RAMTEST forms and VRAM ranges should be rejected: {stdout!r}"
    elif is_sbcio_build():
        assert "RAMTEST 0100-1BFF" in stdout, f"missing low RAMTEST range echo: {stdout!r}"
        assert "RAMTEST 0100-01FF" in stdout, f"missing low subrange echo: {stdout!r}"
        assert "RAMTEST 1BFF-2000" in stdout, f"missing low boundary-crossing RAM echo: {stdout!r}"
        assert "RAMTEST 0100-7FFF" in stdout, f"missing low full RAM range echo: {stdout!r}"
        assert "RAMTEST 2000-7FFF" in stdout, f"missing extended RAMTEST range echo: {stdout!r}"
        assert "RAMTEST 2000-3FFF" in stdout, f"missing extended subrange echo: {stdout!r}"
        assert "RAMTEST 4000-7FFF" in stdout, f"missing upper extended subrange echo: {stdout!r}"
        assert "RAMTEST C000-DFFF" in stdout, f"missing high RAMTEST range echo: {stdout!r}"
        assert "RAMTEST C200-C2FF" in stdout, f"missing high subrange echo: {stdout!r}"
        assert stdout.count("OK") >= 8, f"SBCIO RAMTEST ranges should pass in emulator: {stdout!r}"
        assert "NG" not in stdout, f"SBCIO RAMTEST should not report NG: {stdout!r}"
        assert stdout.count("?") >= 14, f"invalid RAMTEST forms and bare R should be rejected: {stdout!r}"
    else:
        assert "RAMTEST 0100-1BFF" in stdout, f"base should allow low RAMTEST range: {stdout!r}"
        assert "RAMTEST 0100-01FF" in stdout, f"base should allow low subrange: {stdout!r}"
        assert stdout.count("OK") == 2, f"base should only run low RAMTEST ranges: {stdout!r}"
        assert stdout.count("?") >= 22, f"base invalid/unsafe ranges should be rejected: {stdout!r}"
    print("[PASS] test_ramtest_command")


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


def test_ramtest_does_not_break_resume_state():
    work_range = "A000-BFFF" if is_k6802_vdg_build() else "C000-DFFF"
    input_text = (
        "M0100\r"
        "86\r42\rB7\r01\r20\r86\r99\rB7\r01\r21\r3F\r.\r"
        "B0105\r"
        "G0100\r"
        f"RAMTEST {work_range}\r"
        "R\r"
        "D0120-0121\r"
        "\r"
    )
    stdout, stderr, rc = run_emu(input_text, max_cycles=40_000_000)
    assert rc == 0 and "[TIMEOUT]" not in stderr, f"emulator failed: rc={rc} stderr={stderr!r}"
    assert "BRK 0105" in stdout, f"missing breakpoint hit: {stdout!r}"
    if is_sbcio_build():
        assert f"RAMTEST {work_range}" in stdout and "OK" in stdout, f"SBCIO RAMTEST should run: {stdout!r}"
    else:
        assert "OK" not in stdout, f"base should reject C000-DFFF RAMTEST: {stdout!r}"
    assert "0120 42 99" in stdout, f"resume state was broken by RAMTEST handling: {stdout!r}"
    print("[PASS] test_ramtest_does_not_break_resume_state")


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
            print(f"       CI requires a freshly built ROM binary: {rom}")
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
        test_map_command,
        test_vdgtest_command,
        test_keytest_command,
        test_ramtest_command,
        test_breakpoint_query,
        test_breakpoint_resume_and_clear,
        test_resume_requires_active_breakpoint,
        test_breakpoint_resume_restores_registers,
        test_breakpoint_resume_restores_user_sp,
        test_ramtest_does_not_break_resume_state,
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
