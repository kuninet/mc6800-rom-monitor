# Issue #129 SDFS/68 v1移行とROM FAT整理ロードマップ

## 背景

PR #127 で #101 のROM固定LBA stage1 `BOOT` は完了した。ROMはFATを読まず、固定 physical LBA `16` からstage1 loaderをRAMへ読み込む方針になった。

この後の作業は、stage1、SDFS/68本体、ROM FAT整理の責務が混ざりやすい。中断後も迷わないよう、#129 を親ロードマップIssueとして扱い、実装順序をこの文書に固定する。

## 実装順序

| 順番 | Issue | 役割 | 完了条件 |
| --- | --- | --- | --- |
| 完了済み | #101 / PR #127 | ROM固定LBA stage1 `BOOT` | ROMが固定LBAからstage1を読み、`S1API68` header確認後にjumpする |
| 1 | #111 | stage1 loader完成 | stage1がFAT rootの `SDFS.BIN` を512 byte超も含めて読み、SDFS/68 entryへjumpする |
| 2 | #102 | SDFS/68最小本体 | `SDFS.BIN` として起動し、stage1 boot servicesを呼べる |
| 3 | #130 | SDFS/68 HEX/S-record loader | SDFS/68からroot上の `.S` / `.HEX` をRAMへロードできる |
| 4 | #128 | ROM FAT整理 | SDFS/68移行後のROM常駐FAT `DIR` / `LF` の扱いをprofile、docs、testsで整理する |

## Issue単位の責務

### #111 stage1 loader

#111 はstage1側で閉じる。FAT32 read-only最小mount、root 8.3検索、`SDFS.BIN` のFAT chain読み込み、SDFS/68 header検査、entry jump、boot servicesエラーコードを扱う。

SDFS/68本体のシェルやHEX/S-record loaderは含めない。

### #102 SDFS/68最小本体

#102 は `SDFS.BIN` として起動する最小本体に絞る。`SDFS68` header、entry、最小プロンプト、stage1 boot servicesの検出と呼び出し口を実装する。

旧 #102 の本文に含まれていたHEX/S-record loaderは #130 に分離した。

### #130 HEX/S-record loader

#130 はSDFS/68上のロード機能を扱う。stage1 boot services経由でroot上の8.3ファイルを読み、S-RecordまたはIntel HEXとしてRAMへ展開する。

このIssueが完了すると、ROM側 `LF` 相当の主用途をSDFS/68側へ移せる。

### #128 ROM FAT整理

#128 は #130 完了後に実施する。`sbcio_vdg` / `k6802_vdg` は `BOOT + SDFS/68` 本線として固め、`sbcio` のROM FAT `DIR` / `LF` は互換扱いとして残すか、別profile化するかを判断する。
#177 ではこの判断を一段進め、`sbcio` 標準profileからSD/FATを外し、ROM FATは直接指定互換構成でだけ使う方針にした。

## profile方針

- `sbcio_vdg` / `k6802_vdg` は `FEATURE_SD=1` / `FEATURE_FAT=0` の `BOOT + SDFS/68` 本線に寄せる。
- `sbcio` は `FEATURE_SD=0` / `FEATURE_FAT=0` とし、SBC-IO RAM拡張 + 2nd ACIAキーボードprofileとして扱う。
- ROM FATを使う場合は、profileではなく直接構成軸で `FEATURE_SD=1 FEATURE_FAT=1` を指定する。

## 対象外

- I2C / RTC / OLED / VDG高機能。
- SDFS/68 v2の `DIR`、`TYPE`、AUTOEXEC、subdirectory、direct read API。
- FAT write、LFN、複数open、seek。

## テスト方針

- #111 では stage1 build、`mk-sdfs` 生成イメージ、SD fixtureで `SDFS.BIN` 起動まで確認する。
- #102 では `SDFS.BIN` 単体ビルドと、stage1から最小SDFS/68へ制御が渡ることを確認する。
- #130 では `.S` / `.HEX` 正常ロードと、壊れたHEX、終端なし、存在しないファイルの異常系を確認する。
- #128 では `FEATURE_FAT=0/1` の `DIR` / `LF` / `BOOT` / help表示とprofile別ROMサイズを確認する。
