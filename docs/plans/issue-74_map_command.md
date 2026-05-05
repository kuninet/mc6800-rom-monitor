# Issue #74 MAP表示

## 関連リンク

- Issue #74: https://github.com/kuninet/mc6800-rom-monitor/issues/74
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- Issue #72: https://github.com/kuninet/mc6800-rom-monitor/issues/72
- PR #73: https://github.com/kuninet/mc6800-rom-monitor/pull/73

## 背景

Issue #72 で `base` / `sbcio` のビルドプロファイルを分け、`sbcio` ではSD/FATワークを `$C000-$DFFF` へ移せるようにした。次の確認段階として、実機やエミュレータ上で現在のビルドが想定している主要メモリ配置を短く表示できるようにする。

## 採用方針

- 新規コマンドは `MAP` とする。
- `M` は既存のメモリ変更コマンドなので、`MAP` 完全一致を先に判定し、`MAP` 以外は従来どおり `CMD_MOD` へ渡す。
- `MAP` は表示専用で、RAM確認や破壊テストはしない。
- 表示値は実行時検出ではなく、ビルド時の profile 定義をそのまま表示する。

## 表示仕様

`MAP` は次のような固定形式で表示する。

```text
MAP BASE
RAM 0000-1FFF
USER 0000-1FFF
WORK 1C00-1FFF
SD 1C00
MON 1E00
MIK 1F00
STK 1F42
ROM E000-FFFF
```

`sbcio` profileでは `MAP SBCIO`、`RAM 0000-7FFF`、`WORK C000-DFFF`、`SD C000`、`MON C200` になる。

## 対象外

- Issue #75 の `RAMTEST`。
- 実機上でRAMが存在するかの確認。
- RAM容量自動検出。
- K68-VDG、2nd ACIA、PTM、RTC、BOOT、SAVE/write。

## 検証方針

- `base` / `sbcio` の両方で `MAP` 出力が profile 定義と一致することを smoke test で確認する。
- `MAP` 後にユーザーRAM内容が変化しないことを、`F` と `D` を使って確認する。
- 既存の `M0100` などメモリ変更コマンドが壊れていないことを既存テストで維持する。
