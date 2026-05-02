# Issue #50 FAT32 BPB/MBR解析 実装計画

## 関連リンク

- Issue #50: https://github.com/kuninet/mc6800-rom-monitor/issues/50
- Issue #49: https://github.com/kuninet/mc6800-rom-monitor/issues/49
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 方針

Issue #50では、FAT32 read-only実装の入口として、SD上のvolume位置とBPBを読むところまでを実装する。
公開モニタコマンドは追加しない。後続Issueが呼び出す内部APIとして `FAT32_MOUNT` を追加する。

今回の境界は、MBRあり/なしの判定、BPB validation、RootClus取得、FAT先頭LBAとdata先頭LBAの計算までとする。
FAT chain追跡、8.3ファイル検索、root directory走査、`DIR`、`LF` は #51 以降の対象なので入れない。

## 実装範囲

- `src/fat32.asm` を追加し、`FAT32_MOUNT` を実装する。
- `FAT32_MOUNT` は `SD_INIT` と `SD_READ_SECTOR` を使い、LBA0を読む。
- LBA0がFAT32 BPBならsuperfloppyとして扱い、volume start LBAを0にする。
- LBA0がMBRならpartition entry 0のFAT32 LBA partitionを見て、その開始LBAをvolume start LBAにする。
- BPBから次を取得する。
  - `BytesPerSec=512`
  - `SecPerClus`
  - `RsvdSecCnt`
  - `NumFATs`
  - `FATSz32`
  - `RootClus`
- 次を計算してRAM変数に保持する。
  - volume start LBA
  - FAT start LBA = volume start LBA + reserved sectors
  - data start LBA = FAT start LBA + NumFATs * FATSz32
  - RootClus

## 対象外

- FAT chain追跡
- root directory sectorの読み取りやdirectory entry解釈
- 8.3 filename検索
- `DIR` / `LF filename` コマンド統合
- S-Record/Intel HEX LOAD連携
- SAVE/write対応
- 実機SBC-IOアドレスの最終決定

## 確認方針

`tests/test_sd_fixture.py` にROM統合テストを追加する。

- MBRありfixtureとsuperfloppy fixtureの両方を使う。
- listingから `FAT32_MOUNT` と計算結果変数のアドレスを取得する。
- モニタの `M` コマンドで `JSR FAT32_MOUNT` と `SWI` だけの小さなハーネスをRAMへ注入する。
- 実行後、`D` コマンドでRAM上の結果変数をdumpし、期待値と一致することを確認する。

## Issue #51へ踏み込まないための確認

- root directory LBAはdata start LBAとRootClusから後続で求められるが、今回のROMコードではroot directory sectorを読まない。
- FAT entryを読まない。
- cluster chainをたどらない。
- 8.3名、属性、ファイルサイズは見ない。
- `TEST.S`、`TEST.HEX`、`MULTI.BIN` のentry確認は既存fixtureテストだけに残し、ROM側の#50統合テストでは使わない。
