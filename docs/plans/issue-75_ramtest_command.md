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

次の段階として、実機でRAM拡張の有無や指定範囲の読み書きを確認しやすくするため、破壊系の `RAMTEST` コマンドを追加する。

## 採用方針

- 構文は `RAMTEST ssss-eeee` とする。
- 指定範囲全体が、ビルドプロファイルで有効化された単一の許可領域に完全包含される場合だけ実行する。
- `RAMTEST` 自身の一時ワークはゼロページ `$00F0-$00F5` に置く。
- ゼロページ `$0000-$00FF` は検査対象から外す。
- ゼロページの作業領域と一時スタック領域は指定範囲外でも破壊され得るが、ゼロページは検査対象外なので仕様として許容する。
- `base` profile では `0100-1BFF` だけを許可する。
- `sbcio` profile では `0100-7FFF` と `C000-DFFF` を許可する。
- `$1C00-$1FFF` は base の SD buffer、monitor work、MIKBUG互換work、stackに近いため、`base` では拒否する。
- `$A000-$BFFF` は K68-VDG VRAM 候補なので触らない。
- ROM、I/O、境界をまたぐ範囲、RAM自動検出、長時間バーンインは扱わない。
- `R` は既存の breakpoint resume なので、`RAMTEST ` prefix を先に判定し、それ以外の `R` は従来どおり `CMD_RESUME` へ渡す。

## 実装メモ

`RAMTEST C000-DFFF` は、実行中に monitor work が置かれている `$C000-$DFFF` 自体を検査する。
そのため、パースと許可判定はテスト開始前に済ませ、テストループ中は `$C000-$DFFF` 上の monitor work 変数へ依存しない。
開始・終端アドレスと元スタック位置はゼロページの退避領域へ置き、対象アドレスは X レジスタで進める。
テスト中のスタックもゼロページ直下へ移し、`$0100-$7FFF` 内の既存スタック領域を検査対象にできるようにする。

各アドレスでは次の順で確認する。

1. 元値をスタックへ保存する。
2. `$55` を書き込み、同じ値が読めるか確認する。
3. `$AA` を書き込み、同じ値が読めるか確認する。
4. 元値を復元する。

成功時は `OK`、失敗時は `NG xxxx` と失敗アドレスを表示する。
電源断やリセットが途中で発生した場合の内容保持は保証しない。

## 検証方針

- `base` で `RAMTEST 0100-1BFF` と `RAMTEST 0100-01FF` が `OK` を返すこと。
- `base` で `RAMTEST 2000-3FFF`、`RAMTEST C000-DFFF`、`RAMTEST A000-BFFF` が `?` を返すこと。
- `base` で `RAMTEST 0000-1BFF` と `RAMTEST 1BFF-2000` が拒否されること。
- `sbcio` で `RAMTEST 0100-7FFF`、`RAMTEST 2000-3FFF`、`RAMTEST 4000-7FFF`、`RAMTEST C000-DFFF`、`RAMTEST C200-C2FF` が `OK` を返すこと。
- `sbcio` で `RAMTEST 0000-00FF`、`RAMTEST 7FFF-C000`、`RAMTEST BFFF-C000`、`RAMTEST DFFF-E000`、`RAMTEST A000-BFFF`、`RAMTEST E000-FFFF` が拒否されること。
- `RAMTEST` 無引数、片側欠落、5桁以上、余分な文字、開始 > 終了が拒否されること。
- `R` 単独が既存どおり `CMD_RESUME` として扱われること。
- `sbcio` で `RAMTEST C000-DFFF` 後に `MAP`、`H`、`DIR`、`LF TEST.S` が動き、monitor/SD/FAT work が復帰していること。

## 対象外

- RAM容量自動検出。
- 許可領域外を含む任意範囲RAMTEST。
- 長時間バーンイン。
- `base` profileでの `$C000-$DFFF` RAM前提動作。
- K68-VDG、2nd ACIA、PTM、RTC、BOOT、SAVE/write。
