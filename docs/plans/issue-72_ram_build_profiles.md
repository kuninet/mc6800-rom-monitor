# Issue #72 RAM整理とビルドプロファイル分離

## 関連リンク

- Issue #72: https://github.com/kuninet/mc6800-rom-monitor/issues/72
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- PR #71: https://github.com/kuninet/mc6800-rom-monitor/pull/71
- SD/FAT実機PoC Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54

## 背景

Issue #70 では、SD/FAT read-only LOAD が実機で動いた後の次期方針として、RAM整理とビルド分離を最初に進める判断を残した。

現行の8KB互換ROMは、SD sector buffer を `$1C00-$1DFF`、モニタ/FATワークを `$1E00` 付近に置いている。この配置は既存構成では動くが、電大版BASICのように低RAMを広く使うプログラムや、メモリサイズスキャンで低RAMを壊すソフトと共存しにくい。

今回の目的は、既定の8KB互換ROMを壊さず、SBC-IO拡張RAM前提のROMを別ビルドとして作れるようにすることである。

## 採用方針

- 既定の `make bin` は現行互換の `base` プロファイルとして維持する。
- `make bin MONITOR_PROFILE=sbcio` でSBC-IO拡張RAM前提のROMを作る。
- `base` の出力名は `build/mc6800-monitor.bin` / `.lst` のままにする。
- `sbcio` の出力名は `build/mc6800-monitor-sbcio.bin` / `.lst` に分ける。
- ASL のコマンドライン define には依存せず、Makefile が `build/monitor_profile.inc` を生成し、`include/hardware.inc` から読み込む。

## メモリ配置

### base

既存の8KB互換配置を維持する。

- `RAM_START=$0000`
- `RAM_END=$1FFF`
- `USER_RAM_END=$1FFF`
- `WORK_RAM_START=$1C00`
- `WORK_RAM_END=$1FFF`
- `SD_SECTOR_BUF=$1C00`
- `MONITOR_RAM_BASE=$1E00`
- `MIKBUG_VAR_BASE=$1F00`
- `STACK_TOP=$1F42`

### sbcio

SD/FATワークを `$C000-$DFFF` 側へ逃がす。

- `RAM_START=$0000`
- `RAM_END=$7FFF`
- `USER_RAM_END=$7FFF`
- `WORK_RAM_START=$C000`
- `WORK_RAM_END=$DFFF`
- `SD_SECTOR_BUF=$C000`
- `MONITOR_RAM_BASE=$C200`
- `MIKBUG_VAR_BASE=$1F00`
- `STACK_TOP=$1F42`

`RAM_END` は従来互換の汎用RAM終端として残し、`USER_RAM_END` はユーザー/BASIC向け低RAMの終端、`WORK_RAM_START` / `WORK_RAM_END` はモニタ内部ワーク候補範囲として扱う。`sbcio` ではユーザー領域とモニタワーク領域を分けて読み取れるようにする。

`MIKBUG_VAR_BASE` と `STACK_TOP` は、今回は低RAMに残す。BASIC互換性をさらに上げるためのスタック移動やMIKBUG互換ワーク退避は、影響が大きいため別Issueで扱う。

`$A000-$BFFF` はK68-VDG VRAM候補として予約し、今回の汎用RAM領域にはしない。

## 対象外

- `MAP` / `RAMTEST` コマンド追加。
- 実機SBC-IOの `$C000-$DFFF` RAM確認。
- K68-VDG、2nd ACIA、PTM、RTC、AUTOEXEC、SAVE/write。
- SD/FATの仕様変更。

## 検証方針

- `base` と `sbcio` の両方で smoke test と SD fixture test を実行する。
- listing から `SD_SECTOR_BUF` と `MONITOR_RAM_BASE` を読み、プロファイルごとの期待値と一致することを確認する。
- `sbcio` では旧低RAMワーク候補 `$1C00-$1EFF` を破壊してから `DIR` / `LF` を実行し、SD/FAT操作が低RAM旧配置に依存していないことを確認する。
