# Issue #101 ROM固定LBA stage1 BOOT

## 関連リンク

- Issue #101: https://github.com/kuninet/mc6800-rom-monitor/issues/101
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #125: https://github.com/kuninet/mc6800-rom-monitor/issues/125

## 方針

ROM側 `BOOT` はFATを読まず、固定 physical LBA `16` からstage1 loaderを `S1_BASE` へ読む。FAT rootの `SDFS.BIN` 検索とSDFS/68起動はstage1側の責務にする。

8KB ROM内でVDG + KKBD-USB + BOOTを優先するため、`FEATURE_SD` をraw SD機能、`FEATURE_FAT` をROM常駐FATコマンドとして分離する。当時は `sbcio` profileに従来の `DIR` / `LF` を残す方針だったが、#177 で標準profileからは外し、直接指定互換構成でだけ確認する方針に更新した。

## 実装内容

- `BOOT` コマンドを追加する。
- `BOOT` は `SD_INIT` と `SD_READ_SECTOR` だけを使い、LBA `16` 以降からstage1領域全体を連続ロードする。
- stage1 headerの `S1API68` signature、API version、boot entry、image sizeを検査する。
- boot entryが `S1_BASE` からimage size内にあることを確認する。
- 正常時はstage1 boot entryへ `jmp` する。
- 失敗時は `?` を出して既存monitorへ戻る。

## 対象外

- ROM側FAT mount、root directory探索、8.3検索。
- ROM側からの `SDFS.BIN` 直接ロード。
- SDFS/68本体実装。
- 512 byte超のSDFS/68ロードやFAT chain対応。これはstage1側の後続Issueで扱う。

## 検証方針

- 固定LBAに正しいstage1 stubがある場合、`BOOT` でentryへジャンプすることをエミュレータで確認する。
- signature、entry、size不正でハングせずmonitorへ戻ることを確認する。
- stage1読み込み途中のSD read失敗でmonitorへ戻ることを確認する。
- ROM常駐FATテストは直接指定互換構成で維持し、標準profileではFATコマンドを期待しない。
