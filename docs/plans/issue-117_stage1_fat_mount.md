# Issue #117 stage1 FAT32 mount

## 関連リンク

- Issue #117: https://github.com/kuninet/mc6800-rom-monitor/issues/117
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #115: https://github.com/kuninet/mc6800-rom-monitor/issues/115

## 方針

#115 でstage1 boot servicesにSD初期化とraw sector readを接続した。次の段階として、`S1_MOUNT` だけを実体化し、FAT32 volumeのBPBと基本LBA情報をstage1上で読める状態にする。

このIssueでは `S1_FIND_83` と `S1_LOAD_FILE_83` には入らない。stage1の2KB枠を守るため、既存 `fat32.asm` のうち mount / BPB解析に必要な範囲だけをstage1へ含める。

## 実装内容

- `S1_MOUNT` を `FAT32_MOUNT` へ接続する。
- `src/fat32.asm` に `FAT32_INCLUDE_FILE_API` を追加し、`FAT32_FIND_83` 以降のfile APIを条件アセンブル対象にする。
- monitor本体では `FAT32_INCLUDE_FILE_API=1` とし、従来どおり `DIR` / `LF` が使うFAT APIを含める。
- stage1では `FAT32_INCLUDE_FILE_API=0` とし、mount / BPB解析だけを含める。
- `S1_GET_ERROR` は `FAT_ERROR` が非0ならそれを返し、そうでなければ `SD_ERROR` を返す。

## 対象外

- root 8.3検索。
- `SDFS.BIN` 読み込み。
- SDFS/68 header検査。
- ROM `BOOT` 実装。
- SDFS/68本体実装。

## 検証方針

- `sbcio_vdg` と `k6802_vdg` のstage1 binaryが `S1_LIMIT` 内に収まることを確認する。
- stage1 binaryをRAMへロードし、MBRありFAT32 fixtureとsuperfloppy FAT32 fixtureで `S1_INIT` -> `S1_MOUNT` が成功することを確認する。
- 不正FAT32 imageで `S1_MOUNT` が失敗し、ハングしないことを確認する。
- 既存monitor側の `DIR` / `LF` 回帰として `test_sd_fixture.py` を維持する。
