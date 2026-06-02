# Issue #168 VDG console行制御

## 背景

#167 でROMモニタの通常出力を K68-VDG のVRAMへ複製できるようになった。
ただし、その時点のVDG consoleは最小実装であり、`LF` は無視、`CR` は32桁境界まで進むだけ、画面下端ではVRAM先頭へ巻き戻る挙動だった。

#168 では、ROMモニタや SDFS/68 の複数行出力をVDG画面で追えるように、行制御をコンソールとして最低限読める状態へ整える。

## 採用方針

- 対象は `FEATURE_VDG=1` のROMだけにする。
- UART出力とMIKBUG互換入口は維持し、VDG側の画面表示だけを改善する。
- VDGテキスト領域は既存定義どおり 32桁 x 16行、`VDG_TEXT_END` までの512 byteとして扱う。
- `CR` は次行先頭へ移動する。
- `LF` 単独は改行として扱う。ただし直前が `CR` の場合は、CRLFの二重改行を避けて無視する。
- 通常文字が行末を越えた場合は次行先頭へ進める。
- 画面下端を越える場合は、VRAMの2行目以降を1行上へコピーし、最終行を `$60` でクリアする簡易スクロールにする。
- `BS` / `DEL` は1文字戻して、戻った位置を `$60` で消す。
- `READ_LINE_BACKSPACE` の `BS SPACE BS` は `MON_OUTEEE` 経由で出し、UARTとVDGの見え方を揃える。

## カーソル表示

カーソル表示は #168 に含める。
既存の個別Issueはなく、親Issue #165 では「スクロール、BS、CR/LF、カーソルは段階的に入れる」とだけ整理されていた。
行編集とスクロールを整えた直後に現在位置が分からないとVDG consoleとして使いにくいため、点滅なしの静的カーソルを同じPRで入れる。

- カーソル位置には `_` 相当のVDG文字を表示する。
- 出力前にカーソル下の元文字を復元し、出力後に新しいカーソル位置の元文字を保存してからカーソルを描く。
- カーソル下文字と直前CR状態は `MIKBUG_VAR_BASE` 直前のVDG専用ワークに置き、`MIKBUG_VAR_BASE` 自体やSD/FAT、stage1、SDFS/68のワーク配置は動かさない。
- 点滅、タイマ連動、反転表示、カーソル形状の高度化は対象外にする。

## Dコマンド狭幅表示の分離

現行 `D` コマンドは16 byte/行で、アドレス、HEX 16個、ASCII欄を含めると約70文字/行になる。
VDGの32桁画面では読みづらいが、これはVDG consoleの行制御ではなくDコマンドの出力フォーマット変更である。

そのため、Dコマンド狭幅表示は #168 には含めず、#165 配下の sub-issue #179 として分離した。
#168 のPRでは、Dコマンドの幅切り替えは実装しない。

## 検証方針

- `make bin`
- `MONITOR_PROFILE=sbcio_vdg make bin`
- `MONITOR_PROFILE=k6802_vdg make bin`
- `REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `MONITOR_PROFILE=sbcio_vdg REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `MONITOR_PROFILE=k6802_vdg REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`

VDG有効profileでは、起動メッセージ、`D`、`M` の既存ミラー確認に加え、CRLF抑止、BSでの画面消去、画面下端スクロールをVRAM dumpで固定する。

## 対象外

- 2nd ACIAキーボード入力統合。これは #169 で扱う。
- SDFS/68をVDG+keyboard経由で操作する統合確認。これは #170 で扱う。
- Dコマンド狭幅表示。これは #179 で扱う。
- UARTなしのスタンドアロン化。
