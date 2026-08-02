# Issue #119 stage1 root 8.3 find

## 関連リンク

- Issue #119: https://github.com/kuninet/mc6800-rom-monitor/issues/119
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #117: https://github.com/kuninet/mc6800-rom-monitor/issues/117

## 方針

#117 でstage1 boot servicesにFAT32 mountを接続した。次の段階として、`S1_FIND_83` を `FAT32_FIND_83` へ接続し、mount済みFAT32 root directoryから8.3 short filenameを検索できるようにする。

このIssueでは検索だけに絞る。`S1_LOAD_FILE_83`、SDFS/68 header検査、entry jumpは後続Issueに残す。stage1の2KB枠はかなり狭くなっているため、file read / stream APIはまだstage1へ含めない。

## 実装内容

- `S1_FIND_83` を `FAT32_FIND_83` へ接続する。
- `src/fat32.asm` に `FAT32_INCLUDE_FIND_API` を追加する。
- stage1では mount API と find API までを含め、file read / stream APIは除外する。
- monitor本体では従来どおり find API と file API の両方を含める。

## API前提

`S1_FIND_83` は既存 `FAT32_FIND_83` と同じ呼び出し規約を踏襲する。

- 入力: `X` が11 byteのFAT 8.3名を指す。
- 成功: carry clear、`FAT_FILE_CLUS*` と `FAT_FILE_SIZE*` に見つかったentryの情報を保持する。
- 失敗: carry set、`FAT_ERROR` に既存FATエラーコードを保持する。

## 対象外

- `S1_LOAD_FILE_83` の実装。
- `SDFS.BIN` 実ロード。
- SDFS/68 header検査。
- ROM `BOOT` 実装。
- SDFS/68本体実装。

## 検証方針

- stage1 binaryが `S1_LIMIT` を超えないことを確認する。
- stage1 binaryをRAMへロードし、`S1_INIT` -> `S1_MOUNT` -> `S1_FIND_83` でroot上の `TEST.S` を検索できることを確認する。
- root directory cluster chain上の後続entryを検索できることを確認する。
- 存在しない8.3名で `S1_FIND_83` が失敗し、ハングしないことを確認する。
