# Issue #78 2nd ACIAキーボード入力PoC

## 関連リンク

- Issue #78: https://github.com/kuninet/mc6800-rom-monitor/issues/78
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- KKBD-USB: https://github.com/kuninet/KKBD-USB
- SBC-IO Rev02: https://sbc738827564.wordpress.com/2018/08/11/sbc-io-rev02/

## 確認した事実

- Issue #70では、1st ACIAをPC保守コンソールとして残し、2nd ACIAをキーボード入力候補にする方針を置いている。
- Issue #78では、2nd ACIAのアドレスと初期化方法確認、`KEYTEST` 相当の受信確認、PS/2直結案とUSB+MCU案の比較メモが求められている。
- KKBD-USBはRaspberry Pi PicoでUSBキーボードをASCII化し、UART TXへ単方向送信するプロジェクトである。
- KKBD-USB READMEでは、Phase 1〜6完了により「USBキーボード接続 → ASCII変換 → UART送信」のメイン機能は実機検証済みとされている。
- SBC-IOの2nd ACIAは `$8094/$8095` として扱う。

## 採用方針

- Issue #78ではUSB+MCU案としてKKBD-USBを採用し、PS/2直結案は採用しない比較対象として記録する。
- `base` の既存互換を維持し、キーボードPoCはSBC-IO系profileだけで有効にする。
- 2nd ACIAは `ACIA2_CTRL=$8094`、`ACIA2_DATA=$8095` と定義する。
- 2nd ACIA初期化は既存1st ACIAと同じ制御値を使う。
- 初期PoCのコマンドは `KEYTEST` とし、2nd ACIAから1文字受信して1st ACIAへ `KEY xx c` を表示するだけに限定する。
- 通常のモニタ入力、MIKBUG互換 `INEEE`、BASIC入力の2nd ACIA切替は後続Issueに分ける。

後続の #167 ではROM容量を優先し、ROM常駐 `KEYTEST` は外した。受信確認は `diagnostics/KEYTEST.S` をSDからロードして実行する。

## 検証方針

- エミュレータに2nd ACIA入力 `--key-input` を追加し、1st ACIAの `--input` と独立して扱えることを確認する。
- `base` では `KEYTEST` が `?` を返すことを smoke test で確認する。
- `sbcio` / `sbcio_vdg` / `k6802_vdg` では `KEYTEST` が2nd ACIA入力を受け、`KEY 41 A` のように表示することを smoke test で確認する。
- `MAP` ではSBC-IO系profileに `KEY 8094-8095` が表示されることを確認する。
- 実機依存のKKBD-USB接続確認は `docs/testing/kkbd_usb_keytest.md` の手順に残す。

## 対象外

- フルキーボードドライバ。
- VDG画面との統合入力。
- 通常のモニタ入力やBASIC入力の2nd ACIA切替。
- SBCからKKBD-USBへの制御、LED同期、複数キーボード対応。
- USBホスト実装。
