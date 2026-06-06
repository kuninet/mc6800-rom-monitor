# Issue #192 SDFS/68 .COMトランジェントコマンド実装メモ

## 対象

- Issue: #192
- 親Issue: #190
- 設計: [SDFS/68 .COM トランジェントコマンドABI](../design/sdfs68_com_abi.md)

## 実装判断

- `FOO.COM` のように拡張子 `.COM` まで明示された入力だけを外部コマンド候補にする。
- `FOO` から `FOO.COM` を補完探索する処理は、設計どおり後続Issueへ残す。
- `.COM` は raw binary として `$0100` へ固定ロードし、`JSR $0100` 相当で起動する。
- `.COM` 側は `RTS` で SDFS/68 へ戻る。`RUN addr` と `RUN filename` は従来どおり `JMP` 実行のまま変更しない。
- 引数テールは `X` に先頭ポインタ、`B` に長さ、`A=0` で渡す。引数文字列は `LINE_BUF` 上の一時データとして扱う。
- `$0100` から `USER_RAM_END` までに収まらない `.COM` と、0 byte の `.COM` は `?` で拒否する。

## コマンド解釈

内蔵コマンドを優先しつつ、未定義コマンド経路で `.COM` 候補を判定する。
ただし `DUMP.COM`、`READ.COM`、`LIST.COM`、`LOAD.COM` のように先頭文字や `LOAD` prefix が内蔵コマンド判定に入る名前でも、内蔵コマンドとして成立しなければ `.COM` として再判定する。

## 検証

- `python3 tests/test_sdfs68_build.py`
  - `21 passed, 0 failed`
- `build/SDFS-sbcio-vdg.BIN`: 3115 byte
- `build/SDFS-k6802-vdg.BIN`: 3115 byte

テストでは、通常の `.COM` 実行、引数渡し、内蔵コマンド名との衝突、ネストした `JSR` / `RTS` を使う `.COM`、存在しない `.COM`、0 byte `.COM`、サイズ超過 `.COM`、`.COM` ではない未定義入力を確認した。

## 残課題

- `FOO` から `FOO.COM` を探す本格トランジェントコマンド探索。
- `.COM` から呼び出す SDFS/68 API の整理。
- path 対応後の `.COM` 探索範囲の再設計。
