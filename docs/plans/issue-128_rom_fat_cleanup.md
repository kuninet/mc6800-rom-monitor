# Issue #128 ROM常駐FAT DIR/LF整理

## 背景

#111、#102、#130 により、ROM `BOOT` から固定LBA stage1を読み、stage1が `SDFS.BIN` を起動し、SDFS/68側でS-Record / Intel HEXをロードできるようになった。これにより、ROM常駐FAT `DIR` / `LF` は本線機能ではなく互換機能として扱える。

## 採用方針

- `sbcio_vdg` / `k6802_vdg` は `BOOT + SDFS/68` 本線profileとする。
- `sbcio_vdg` / `k6802_vdg` は `FEATURE_SD=1`、`FEATURE_FAT=0` を維持し、ROMには固定LBA `BOOT` とraw SD sector readを残す。
- ROM常駐FAT `DIR` / `LF` は `sbcio` profileの互換機能として残す。
- `base` profileは引き続きSDなしの最小ROMとする。
- 新しいSDFS/68機能、I2C、RTC、OLED、AUTOEXEC、subdirectory、FAT writeはROMへ戻さず、SDFS/68側の後続Issueで扱う。

## profileの意味

| profile | ROM側の位置づけ | `FEATURE_SD` | `FEATURE_FAT` | `DIR` / `LF` | `BOOT` |
| --- | --- | --- | --- | --- | --- |
| `base` | SBC6800互換の最小ROM | 0 | 0 | なし | なし |
| `sbcio` | ROM常駐FAT互換profile | 1 | 1 | あり | あり |
| `sbcio_vdg` | SBC-IO + KBD + VDG + SDFS/68本線 | 1 | 0 | なし | あり |
| `k6802_vdg` | K6802-SBC + KBD + VDG + SDFS/68本線 | 1 | 0 | なし | あり |

## ROMサイズ確認

`make bin` は固定vector領域を含むROMイメージを生成するため、単純な出力サイズは全profileで同じになる。今回の確認では `ROM_CODE_LIMIT=8192` の上限監視を通した。

| profile | 確認コマンド | 出力サイズ |
| --- | --- | --- |
| `base` | `MONITOR_PROFILE=base make bin` | 8075 / 8192 bytes |
| `sbcio` | `MONITOR_PROFILE=sbcio make bin` | 8075 / 8192 bytes |
| `sbcio_vdg` | `MONITOR_PROFILE=sbcio_vdg make bin` | 8075 / 8192 bytes |
| `k6802_vdg` | `MONITOR_PROFILE=k6802_vdg make bin` | 8075 / 8192 bytes |

## 検証方針

- `FEATURE_FAT=1` ではhelpに `DIR` / `LF` を表示し、ROM `DIR` / `LF` が動作することを確認する。
- `FEATURE_FAT=0` かつ `FEATURE_SD=1` ではhelpに `BOOT` を表示し、`DIR` / `LF` は未対応として `?` を返すことを確認する。
- `FEATURE_SD=0` ではSD行とSD系コマンドを表示しないことを確認する。

## 後続

ROM常駐FAT `DIR` / `LF` を完全削除する判断はしない。`sbcio` profileを互換入口として残し、SDFS/68 v2以降で `DIR`、`TYPE`、AUTOEXEC、subdirectoryなどを育てる。
