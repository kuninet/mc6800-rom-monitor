# Issue #115 stage1 S1_INIT / S1_READ_SECTOR

## 関連リンク

- Issue #115: https://github.com/kuninet/mc6800-rom-monitor/issues/115
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #113: https://github.com/kuninet/mc6800-rom-monitor/issues/113

## 方針

#113 で固定したstage1 header / jump tableを維持したまま、stage1 boot servicesの最初の実体としてSD初期化とraw sector readだけを接続する。このIssueではFAT32 mountや `SDFS.BIN` ロードは実装しない。

## 実装内容

- `src/stage1.asm` から既存 `src/sdcard.asm` をincludeする。
- `S1_INIT` は `SD_INIT` へ接続する。
- `S1_READ_SECTOR` は `SD_READ_SECTOR` へ接続する。
- `S1_GET_ERROR` は `SD_ERROR` を返す。
- `S1_MOUNT`、`S1_FIND_83`、`S1_LOAD_FILE_83` は未実装stubのまま残す。
- `Makefile` のstage1依存に `src/sdcard.asm` を追加する。

## API前提

`S1_READ_SECTOR` は既存 `SD_READ_SECTOR` と同じ低層APIを踏襲する。

- 入力: `SD_LBA0..3` に読み出しLBA、`X` に転送先アドレス。
- 成功: carry clear、`SD_ERROR=0`。
- 失敗: carry set、`SD_ERROR` に既存SDエラーコード。

## 対象外

- FAT32 mount。
- root 8.3検索。
- `SDFS.BIN` 実ロード。
- ROM `BOOT` 実装。
- SDFS/68本体実装。

## 検証方針

- `sbcio_vdg` stage1 binaryをRAMへロードする。
- RAM上の小ハーネスから `S1_INIT`、`S1_READ_SECTOR` を呼ぶ。
- 既存SD fixtureの既知sectorを `SDFS_LOAD_BASE` へ読み、先頭bytesが期待値と一致することを確認する。
- stage1 binaryが `S1_LIMIT` を超えないことを維持する。
