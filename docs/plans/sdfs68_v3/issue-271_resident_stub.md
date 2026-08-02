# Issue #271 SDFS/68 v3 resident API stub とビルド基盤

## 背景

#255-#261 で SDFS/68 v3 の設計判断を整理した。
実装の最初のPRでは、既存v2の `src/sdfs68.asm`、stage1、`SDFS.BIN` 生成経路を壊さず、v3 residentを別成果物としてビルドできる足場を作る。

## 採用方針

- v3 residentのソースは `src/sdfs68_v3/` に分ける。
- 既存の `make sdfs` はv2用として変更しない。
- v3 residentは `make sdfs3` で `build/SDFS3*.BIN` を生成する。
- 最初のstubは `SDFS3API` headerと最小jump tableのみを持つ。
- API slotは #259 のslot番号に合わせ、slot 0-6をjump tableに置く。
- `GET_INFO`、`GET_ERROR` 以外は未実装エラーを返すだけにし、ROM dispatchやFAT処理は後続Issueへ分ける。

## 初期stubのheader

`SDFS3API` headerは #259 のresident header案に合わせ、次を持つ。

| Offset | 項目 | 初期値 |
| ---: | --- | --- |
| `$00` | magic | `SDFS3API` |
| `$08` | api major | `1` |
| `$09` | api minor | `0` |
| `$0A` | api count | `7` |
| `$0B` | flags | `0` |
| `$0C` | jump table address | `SDFS3_JUMP_TABLE` |
| `$0E` | work base | `SDFS_LOAD_BASE` |
| `$10` | work end | `SDFS3_END-1` |
| `$12` | memtop | `USER_RAM_END` |
| `$14` | scratch min | `0` |
| `$16` | reserved | `0` |

## 検証方針

- `tests/test_sdfs68_v3_build.py` で `make sdfs3` を実行する。
- `sbcio_4000` と `k6802_4000` で `SDFS3*.BIN` が生成されることを確認する。
- listingから `SDFS_LOAD_BASE`、`SDFS_LOAD_LIMIT`、`USER_RAM_END`、API symbolを取得し、binary headerとjump tableが #259 のslot番号と一致することを確認する。
- `GET_INFO` が `A=api_major`、`B=flags`、`X=resident API header address`、carry clearを返す命令列であることを確認する。
- `base` profileでは `sdfs3` が失敗することを確認する。
- コード変更なのでPR前に `make test` を実行する。

## 対象外

- ROMモニタからv3 residentを検出/呼び出す実装。
- `CMD <tail>` gatewayのROM側実装。
- 固定LBA `SDFS3SYS` loader実装。
- FAT/SD処理との接続。
- BASIC SAVE/LOAD実装。
- FAT write実装。

## 関連

- #271: 対応Issue。
- #272: v3 phase 1 実装epic。
- #254: v3全体親Issue。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
