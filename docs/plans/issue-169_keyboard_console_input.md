# Issue #169 2nd ACIAキーボード入力統合

## 背景

#78 で2nd ACIA `$8094/$8095` と KKBD-USB による1文字入力PoCを確認した。
#167 と #168 でVDGへの出力と行制御が入ったため、#169 では入力側もROMモニタの通常操作へ統合する。

## 採用方針

- 外部から見える入力入口は増やさない。
- `INCH` / `INEEE` は従来通り単一のMIKBUG互換入力入口として維持する。
- 外部プログラムやBASICには、入力元が1st ACIAか2nd ACIAかを意識させない。
- `MONITOR_FEATURE_KEYBOARD=1` のときだけ、内部入力ルーチンで2nd ACIAと1st ACIAを多重化する。
- 優先順位は2nd ACIAキーボード優先、1st ACIA UART fallbackとする。
- 2nd ACIAと1st ACIAのステータスをポーリングし、2nd ACIAに受信文字があればそれを返す。
- 2nd ACIAに文字がない場合は1st ACIAを確認し、どちらにも文字がない場合は待つ。
- `MONITOR_FEATURE_KEYBOARD=0` では従来通り1st ACIAのみを待つ。

## 実装方針

- `src/acia6850.asm` に内部用の `CONSOLE_GETC` を追加する。
- `READ_LINE` と `MIKBUG_INEEE_IMPL` は `ACIA_GETC` ではなく `CONSOLE_GETC` を呼ぶ。
- `MIKBUG_INEEE_IMPL` の `LF` 読み飛ばしと echo は維持する。
- `MON_OUTEEE` / `MIKBUG_OUTEEE_IMPL` など出力経路は変更しない。
- ROM常駐 `KEYTEST` は復活させない。診断は引き続きSD上の `diagnostics/KEYTEST.S` を使う。

## エミュレータ方針

`--key-input` は2nd ACIA入力を固定するテスト補助であり、ROMの外部仕様ではない。
ただし、key入力スクリプトが空になった場合にCPU実行を終了するとUART fallbackをテストできないため、2nd ACIA側だけはEOF後も「受信データなし」として扱う。
1st ACIAの `--input` は従来通りEOFでエミュレータ終了に使う。

## 検証方針

- key入力だけで `H` / `MAP` などのROMモニタ操作ができること。
- key入力とUART入力が同時にある場合、key入力が先に処理されること。
- key入力が空または未指定でも、UART入力だけで従来通り操作できること。
- key入力の `BS` / `DEL` / `CR` が `READ_LINE` でUART入力と同じように扱われること。
- `INEEE` の公開契約や固定アドレスを変えないこと。

## 対象外

- 入力元切替コマンドや入力モード表示。
- SBCからKKBD-USBへの制御、LED同期、複数キーボード対応。
- SDFS/68のVDG+keyboard経由の完全操作確認。これは #170 で扱う。
