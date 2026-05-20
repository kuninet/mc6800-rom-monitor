# Issue #121 stage1 SDFS.BIN 1-sector loader

## 関連リンク

- Issue #121: https://github.com/kuninet/mc6800-rom-monitor/issues/121
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #119: https://github.com/kuninet/mc6800-rom-monitor/issues/119

## 方針

#119 でstage1 boot servicesはFAT32 mountとroot 8.3検索まで対応した。次の `S1_LOAD_FILE_83` では、既存の汎用 `FAT32_READ_FILE` をそのままstage1へ入れない。現状のstage1は約1865 bytesで、汎用file APIを含めると2KB枠を超えるためである。

このIssueでは、v1の最小loaderとして **1 sector / 512 byte以下の8.3ファイルだけ** を `SDFS_LOAD_BASE` へ読む。512 byte超、0 byte、cluster chainをたどるロードは後続Issueで扱う。

## 実装内容

- `S1_LOAD_FILE_83` を実装する。
- 入力は `X` が11 byteのFAT 8.3名を指す。
- 内部で `FAT32_FIND_83` を呼ぶ。
- file size が `1..512` byte の場合だけ、開始clusterの先頭sectorを `SDFS_LOAD_BASE` へ読む。
- file size が `0` または `512` byte超の場合は `FAT_ERR_SIZE` で失敗する。
- `FAT32_READ_FILE`、`FAT32_STREAM_*`、汎用file copy APIはstage1へ含めない。

## 対象外

- 512 byte超の `SDFS.BIN` 対応。
- cluster内複数sector対応。
- FAT chainをたどるfile load。
- SDFS/68 header検査。
- SDFS/68 entry jump。
- ROM `BOOT` 実装。

## 検証方針

- stage1 binaryが `S1_LIMIT` を超えないことを確認する。
- stage1 binaryをRAMへロードし、root上の `TEST.S` を `SDFS_LOAD_BASE` へ読めることを確認する。
- `MULTI.BIN` のような512 byte超ファイルは失敗することを確認する。
- 存在しない8.3名で失敗し、ハングしないことを確認する。
