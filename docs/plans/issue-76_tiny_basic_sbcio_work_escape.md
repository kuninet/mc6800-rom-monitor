# Issue #76 電大版BASIC向け sbcio 低RAMワーク退避

## 背景

Issue #72 で `sbcio` profile のSD/FATワークとモニタ主要ワークは `$C000-$DFFF` へ移した。
一方で、MIKBUG互換ワーク予約と通常スタックは `MIKBUG_VAR_BASE=$1F00`、`STACK_TOP=$1F42` のまま低RAMに残していた。

電大版 `MICBAS13` は `$1F08` 付近を使うため、`sbcio` profileでBASICを確認する Issue #76 では低RAM上部をモニタが使い続けない構成にする。

## 採用方針

- `base` profile は従来どおり `MIK 1F00`、`STK 1F42` を維持する。
- `sbcio` profile の `MIKBUG_VAR_BASE` は `$C300` に移す。
- `sbcio` profile の `STACK_TOP` は `$DFFF` に移す。
- MIKBUG互換入口アドレス `$E075`、`$E078`、`$E07E`、`$E0E3`、`$E1AC`、`$E1D1` は変更しない。
- BASIC本体、VDG、キーボード、自動起動は今回の対象外とする。
- `RAMTEST` は一時的にゼロページスタックへ退避する。MC6800 の `TSX` は `SP+1` を返すため、元の `SP` を保存するときは1バイト戻してから保存する。

## 配置

`sbcio` profileでは次の配置にする。

- `SD_SECTOR_BUF=$C000`
- `MONITOR_RAM_BASE=$C200`
- `MIKBUG_VAR_BASE=$C300`
- `STACK_TOP=$DFFF`

`STACK_TOP=$DFFF` は、MC6800 のスタックが下方向へ伸びることを前提に、`C000-C1FF` のSD sector buffer、`C200` から始まるモニタ/FAT変数と十分離すための上端として扱う。

## 検証方針

- `make bin MONITOR_PROFILE=sbcio` でビルドする。
- listing で `STACK_TOP=$DFFF`、`MIKBUG_VAR_BASE=$C300`、`MONITOR_RAM_BASE=$C200`、`FAT_SECTOR_IN_CLUS` が `WORK C000-DFFF` 内にあることを確認する。
- `MONITOR_PROFILE=sbcio REQUIRE_BUILD_ROM=1 python tests/test_smoke.py` を実行し、`MAP`、`RAMTEST`、`MICBAS13.S` 起動確認を通す。
- `MONITOR_PROFILE=sbcio REQUIRE_BUILD_ROM=1 python tests/test_sd_fixture.py` を実行し、SD/FATワーク退避と `MAP` 表示を確認する。
- 実機では `MAP`、`RAMTEST 0100-7FFF`、`RAMTEST C000-DFFF`、`LF MICBAS13.S`、BASIC起動を確認する。
