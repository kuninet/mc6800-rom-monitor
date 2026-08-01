# Issue #278 SDFS/68 v3 SDFS3SYS system image生成

## 背景

#257では、v3 residentを固定LBA system imageから1発ロードする案を採用候補にした。
#271以降で `SDFS3API` resident stub、ROM側resident検出、`CMD <tail>` gatewayが入ったため、次はPC側/ビルド側でresident binaryをROM loaderが扱えるsystem image形式へ包む必要がある。

このIssueでは、ROMから固定LBAを読む実装には入らず、`SDFS3SYS` header付きimageの生成と検査に絞る。

## 採用方針

- v3用toolは `tools/mk_sdfs3sys.py` として既存v2の `tools/mk_sdfs_image.py` から分ける。
- `make sdfs3sys` で `build/SDFS3SYS*.BIN` を生成する。
- headerは #257 の初期案どおり32 bytes固定で始める。
- 16bit値はMC6800側で扱いやすいbig-endianにする。
- `load_address` は listing の `SDFS_LOAD_BASE` を使う。
- payloadが listing の `SDFS_LOAD_BASE..SDFS_LOAD_LIMIT` を超える場合は生成時に拒否する。
- `entry_offset` は現stubで安全に呼べる `SDFS3_GET_INFO - SDFS_LOAD_BASE` とする。
- `api_table_offset` はresident API jump table位置である `SDFS3_JUMP_TABLE - SDFS_LOAD_BASE` とする。
- ROM側resident検出で使う `SDFS3API` headerは、現stubではpayload先頭の `SDFS_LOAD_BASE` に置く前提とする。
- checksumはchecksum欄 `$18-$19` だけを0として、header+payload全体の16bit加算で計算する。
- 初期最大image sizeは #257 の16KB級方針に合わせて16KBとする。

## Header

| Offset | Size | 項目 | 初期値 |
| ---: | ---: | --- | --- |
| `$00` | 8 | magic | `SDFS3SYS` |
| `$08` | 1 | header version | `1` |
| `$09` | 1 | ABI major | `1` |
| `$0A` | 1 | ABI minor | `0` |
| `$0B` | 1 | flags | bit0: checksum16あり |
| `$0C` | 2 | load address | `SDFS_LOAD_BASE` |
| `$0E` | 2 | image size | header + payload bytes |
| `$10` | 2 | entry offset | `SDFS3_GET_INFO - SDFS_LOAD_BASE` |
| `$12` | 2 | API table offset | `SDFS3_JUMP_TABLE - SDFS_LOAD_BASE` |
| `$14` | 2 | work min | `0` |
| `$16` | 2 | bank window hint | `0` |
| `$18` | 2 | checksum | checksum欄を0として計算した16bit加算 |
| `$1A` | 2 | header size | `32` |
| `$1C` | 4 | reserved | `0` |

## 検証方針

- `tests/test_sdfs68_v3_build.py` で `sbcio_4000` と `k6802_4000` の `make sdfs3sys` を実行する。
- headerのload address、image size、entry offset、API table offset、checksum、payload境界を確認する。
- payloadが `SDFS_LOAD_LIMIT` を超える場合に生成を拒否することを確認する。
- bad magicとbad checksumを `parse_sdfs3sys_header` が拒否することを確認する。
- listingに必要symbolがないCLI失敗を確認する。
- 既存v2 image生成経路を壊していないことを `make test` で確認する。

## 対象外

- ROMから固定LBAを読む実装。
- system領域slot A/B更新。
- active marker形式。
- FAT write。
- residentの `DIR` / `TYPE` / `LOAD` / `RUN` 実装。

## 関連

- #278: 対応Issue。
- #272: v3 phase 1 実装epic。
- #257: 固定LBA system image形式と1発ロード方式。
- #258: system領域更新方式。
- #271: resident API stub とビルド基盤。
