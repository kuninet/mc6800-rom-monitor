#!/usr/bin/env python3
"""SBC6800 エミュレータのスモークテスト

ROM モニタを起動して基本コマンドの動作を検証する。
"""

import subprocess
import sys
import os
import tempfile

EMU_PATH = os.path.join(os.path.dirname(__file__), "..", "emu", "sbc6800_emu.py")
ROM_PATH = os.path.join(os.path.dirname(__file__), "..", "build", "mc6800-monitor.bin")


def run_emu(input_text, max_cycles=5_000_000, timeout=10):
    """エミュレータを実行して出力を取得する"""
    # 入力を CR 改行に変換
    input_bytes = input_text.encode("ascii")

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(input_bytes)
        input_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, EMU_PATH, ROM_PATH,
             "--input", input_file,
             "--max-cycles", str(max_cycles)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "[TIMEOUT]", -1
    finally:
        os.unlink(input_file)


def test_boot_prompt():
    """起動時に * と ] プロンプトが出力されるか"""
    # 空行を1つ送ってプロンプトを待つ
    stdout, stderr, rc = run_emu("\r\r")
    assert "*" in stdout, f"起動メッセージ '*' が見つかりません: {stdout!r}"
    assert "]" in stdout, f"プロンプト ']' が見つかりません: {stdout!r}"
    print("✅ test_boot_prompt: PASS")


def test_dump_command():
    """D コマンドでメモリダンプができるか"""
    stdout, stderr, rc = run_emu("D0000\r\r")
    # アドレス表示 "0000" が出ること
    assert "0000" in stdout, f"ダンプ出力にアドレスが見つかりません: {stdout!r}"
    print("✅ test_dump_command: PASS")


def test_modify_and_dump():
    """M コマンドで値を書き込んで D で確認できるか"""
    # M0100 で $AA を書き込み、ピリオドで終了、D0100 で確認
    input_text = "M0100\rAA\r.\rD0100\r\r"
    stdout, stderr, rc = run_emu(input_text)
    # ダンプ結果に AA が含まれるか
    assert "AA" in stdout, f"書き込んだ値 AA がダンプに見つかりません: {stdout!r}"
    print("✅ test_modify_and_dump: PASS")


def test_go_swi_return():
    """G コマンドでプログラムを実行し SWI で復帰できるか"""
    # M0100 から LDAA #$55, STAA $0110, SWI を入力
    # 86 55 B7 01 10 3F
    input_text = "M0100\r86\r55\rB7\r01\r10\r3F\r.\rG0100\rD0110\r\r"
    stdout, stderr, rc = run_emu(input_text, max_cycles=10_000_000)
    # D0110 の結果に 55 が含まれるか
    lines = stdout.split("\n")
    dump_lines = [l for l in lines if "0110" in l and "55" in l]
    assert len(dump_lines) > 0, f"G コマンド実行結果が確認できません: {stdout!r}"
    print("✅ test_go_swi_return: PASS")


def test_srec_load():
    """L コマンドで S-Record を読み込めるか"""
    # S-Record: $0200 に 01 02 03 を書き込み
    # S1 レコード: S1 09 0200 010203 チェックサム
    # バイト数=09 ではなく正しく計算
    # アドレス: 02 00, データ: 01 02 03 → 合計5バイト+1(チェックサム)=6
    # S1 06 0200 010203 xx
    # sum = 06 + 02 + 00 + 01 + 02 + 03 = 0E → ~0E = F1
    srec_data = "S1060200010203F1\r"
    srec_eof = "S9030000FC\r"
    input_text = f"L\r{srec_data}{srec_eof}D0200\r\r"
    stdout, stderr, rc = run_emu(input_text, max_cycles=10_000_000)
    assert "OK" in stdout, f"S-Record ロードの OK が見つかりません: {stdout!r}"
    print("✅ test_srec_load: PASS")


def test_ihex_load():
    """L コマンドで Intel HEX を読み込めるか"""
    # Intel HEX: $0300 に AA BB CC を書き込み
    # :03 0300 00 AABBCC xx
    # sum = 03 + 03 + 00 + 00 + AA + BB + CC = 03+03+00+00+AA+BB+CC
    # = 03+03+AA+BB+CC = 03+03+AA+BB+CC
    # 0x03+0x03+0xAA+0xBB+0xCC = 0x03+0x03=0x06, +0xAA=0xB0, +0xBB=0x6B, +0xCC=0x37
    # → 0x137 → low byte 0x37 → two's complement: 0xC9
    # Wait: sum = 03+03+00+00+AA+BB+CC
    # 03+03 = 06
    # 06+00 = 06
    # 06+00 = 06
    # 06+AA = B0
    # B0+BB = 16B → 6B
    # 6B+CC = 137 → 37
    # checksum = (~0x37 + 1) & 0xFF = 0xC9
    ihex_data = ":03030000AABBCCC9\r"
    ihex_eof = ":00000001FF\r"
    input_text = f"L\r{ihex_data}{ihex_eof}D0300\r\r"
    stdout, stderr, rc = run_emu(input_text, max_cycles=10_000_000)
    assert "OK" in stdout, f"Intel HEX ロードの OK が見つかりません: {stdout!r}"
    print("✅ test_ihex_load: PASS")


def test_error_display():
    """不正なコマンドで ? エラーが表示されるか"""
    stdout, stderr, rc = run_emu("X\r\r")
    assert "?" in stdout, f"エラー表示 '?' が見つかりません: {stdout!r}"
    print("✅ test_error_display: PASS")


def main():
    print("=" * 50)
    print("SBC6800 エミュレータ スモークテスト")
    print("=" * 50)

    if not os.path.exists(ROM_PATH):
        print(f"❌ ROM バイナリが見つかりません: {ROM_PATH}")
        print("   先に make bin を実行してください。")
        sys.exit(1)

    tests = [
        test_boot_prompt,
        test_dump_command,
        test_modify_and_dump,
        test_go_swi_return,
        test_srec_load,
        test_ihex_load,
        test_error_display,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: FAIL - {e}")
            failed += 1
        except Exception as e:
            print(f"❌ {test.__name__}: ERROR - {e}")
            failed += 1

    print()
    print(f"結果: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
