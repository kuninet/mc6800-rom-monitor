# Issue #75 RAMTESTコマンド

## 関連リンク

- Issue #75: https://github.com/kuninet/mc6800-rom-monitor/issues/75
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- Issue #72: https://github.com/kuninet/mc6800-rom-monitor/issues/72
- Issue #74: https://github.com/kuninet/mc6800-rom-monitor/issues/74
- PR #73: https://github.com/kuninet/mc6800-rom-monitor/pull/73

## 背景

Issue #72 で `base` / `sbcio` のビルドプロファイルを分け、`sbcio` では SD sector buffer と monitor/FAT work を `$C000-$DFFF` へ移した。
Issue #74 では `MAP` により、ビルド時の想定メモリ配置を表示できるようにした。

次の段階として、実機SBC-IOで `$C000-$DFFF` のRAMが期待どおり使えるか確認するため、破壊系の `RAMTEST` コマンドを追加する。

## 採用方針

- 初期実装で受け付ける構文は、安全側で選んだ明示範囲だけに限定する。
- `base` profile では `RAMTEST 0000-1BFF` だけを許可する。
- `sbcio` profile では `RAMTEST 0000-1BFF`、`RAMTEST 2000-7FFF`、`RAMTEST C000-DFFF` を許可する。
- `$1C00-$1FFF` はbaseのSD buffer、monitor work、MIKBUG互換work、stackに近いため拒否する。
- `$A000-$BFFF` は K68-VDG VRAM 候補なので触らない。
- ROM、I/O、任意範囲、RAM自動検出、長時間バーンインは扱わない。
- `R` は既存の breakpoint resume なので、`RAMTEST` 完全一致を先に判定し、それ以外の `R` は従来どおり `CMD_RESUME` へ渡す。

## 実装メモ

`RAMTEST C000-DFFF` は、実行中に monitor work が置かれている `$C000-$DFFF` 自体を検査する。
そのため、テストループ本体は monitor work 変数に依存せず、Xレジスタ、Aレジスタ、スタックだけで進める。

各アドレスでは次の順で確認する。

1. 元値をスタックへ保存する。
2. `$55` を書き込み、同じ値が読めるか確認する。
3. `$AA` を書き込み、同じ値が読めるか確認する。
4. 元値を復元する。

成功時は `OK`、失敗時は `NG xxxx` と失敗アドレスを表示する。
電源断やリセットが途中で発生した場合の内容保持は保証しない。

## 検証方針

- `base` で `RAMTEST 0000-1BFF` が `OK` を返し、`RAMTEST 2000-7FFF` と `RAMTEST C000-DFFF` が `?` を返すこと。
- `sbcio` で `RAMTEST 0000-1BFF`、`RAMTEST 2000-7FFF`、`RAMTEST C000-DFFF` が `OK` を返すこと。
- `RAMTEST` 無引数、`RAMTEST 1C00-1FFF`、`RAMTEST A000-BFFF`、`RAMTEST E000-FFFF`、`RAMTEST 8000-80FF` が拒否されること。
- `R` 単独が既存どおり `CMD_RESUME` として扱われること。
- `sbcio` で `RAMTEST C000-DFFF` 後に `DIR` と `LF TEST.S` が動き、monitor/SD/FAT work が復帰していること。

## 対象外

- RAM容量自動検出。
- 任意範囲RAMTEST。
- 長時間バーンイン。
- `base` profileでの `$C000-$DFFF` RAM前提動作。
- K68-VDG、2nd ACIA、PTM、RTC、BOOT、SAVE/write。
