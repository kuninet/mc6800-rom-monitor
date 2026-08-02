# Issue #280 SDFS/68 v3 resident DIR / TYPE read-only接続

## 背景

#281 で resident 側 `SDFS3_CMD_DISPATCH` が `DIR` / `TYPE` / `LOAD` / `RUN` / `*.COM` を分類できるようになった。
このIssueでは、read-only系の `DIR` と `TYPE` を実処理へ接続する。

## 採用方針

- ROM側の `CMD` gatewayは変更しない。
- `DIR` / `TYPE` の切り分けと実処理はRAM resident側に置く。
- v3 residentは phase 1 の実装部品として `sdcard.asm` と `fat32.asm` を直接 include する。
- 外部ABIとしてstage1 APIには依存しない。
- `FAT32_MOUNT` はSD初期化込みで呼び、各 `CMD DIR` / `CMD TYPE` ごとにmountする。
- `CMD DIR` はroot directoryを表示する。
- `CMD DIR <path>` は既存v2相当の8.3 path parserでdirectoryを解決して表示する。
- `CMD TYPE <path>` はfileを解決し、`FAT32_STREAM_OPEN` / `FAT32_STREAM_GETC` で内容を出力する。
- hidden / system / volume label / LFN / AppleDouble系のskip判定は既存v2の `DIR` 表示方針を踏襲する。
- `LOAD` / `RUN` / `.COM` は引き続き未実装stubのまま残す。

## 実装上の注意

- residentが1 sectorを超えるため、既存の固定LBA loader harnessを複数sector対応へ更新する。
- system imageのchecksum検査も `image_size` 全体を対象にする。
- テスト用のv3 SD imageは、`SDFS3SYS` を固定LBA 64へ置き、FAT partitionはLBA 128以降へ置いてsystem領域と重ねない。
- `TYPE` のEOFは `FAT_BYTES_REMAIN` で判定し、残byteがなければ正常終了とする。

## 対象外

- `LOAD` / `RUN` / `.COM` の接続。
- FAT write。
- BASIC SAVE/LOAD。
- 32bit cluster拡張。
- ROM側の直接 `DIR` / `TYPE` alias。
- command hook vector方式の導入。

## 検証方針

- `tests/test_sdfs68_v3_build.py` に `CMD DIR` / `CMD TYPE` のSD fixture実行テストを追加する。
- 固定LBA loader harnessでresidentをRAMへロードした後、ROM promptから次を確認する。
  - `CMD DIR` がrootの既知fileとdirectoryを表示する。
  - `CMD DIR DOCS` がsubdirectory内のfileを表示する。
  - `CMD TYPE README.TXT` がroot file内容を表示する。
  - `CMD TYPE DOCS/NOTE.TXT` がsubdirectory file内容を表示する。
  - missing fileでROM monitorへ `?` 復帰する。
- 既存v3 header / parser / SDFS3SYS / loader harnessテストも通す。
- PR前に `make test` 相当を確認する。WindowsローカルではPOSIX形式の環境変数指定に注意する。

## 関連

- #280: 対応Issue。
- #272: v3 phase 1 実装epic。
- #281: resident CMD_DISPATCH parser。
- #282: resident LOAD / RUN / .COM接続。
- #257: 固定LBA system image。
- #259: resident API最小セット。
