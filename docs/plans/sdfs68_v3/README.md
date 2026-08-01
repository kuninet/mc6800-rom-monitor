# SDFS/68 v3 設計メモ

このディレクトリは、親Issue #254 配下の SDFS/68 v3 設計Issueをまとめる。

v3 は、現行の `BOOT -> stage1 -> SDFS.BIN -> SDFS> ` 方式を単純に拡張するのではなく、ROMモニタをコマンド入口、SDFS/68をRAM residentのSD/FAT serviceとして再整理する検討線である。
設計が固まるまでは実装Issueをここへ混ぜず、責務境界、API、system image、メモリマップ、BASIC連携を分けて記録する。

## 設計Issue

| Issue | 文書 | 内容 |
| --- | --- | --- |
| #255 | [issue-255_boundary.md](issue-255_boundary.md) | 責務境界とv2互換性方針 |
| #256 | [issue-256_rom_dispatch.md](issue-256_rom_dispatch.md) | ROMモニタ側command dispatchとSDFS API呼び出し口 |
| #257 | [issue-257_system_image.md](issue-257_system_image.md) | 固定LBA system image形式と1発ロード方式 |
| #258 | [issue-258_system_update.md](issue-258_system_update.md) | system領域更新方式 |
| #259 | [issue-259_resident_api.md](issue-259_resident_api.md) | resident API最小セット |
| #260 | [issue-260_memory_bankram.md](issue-260_memory_bankram.md) | メモリマップとBank RAM利用方針 |
| #261 | [issue-261_basic_save_load.md](issue-261_basic_save_load.md) | BASIC SAVE/LOAD連携方式 |

## 運用

- v3設計文書はこのディレクトリに置く。
- 実装Issueは、#256から#261の設計が固まってから分割する。
- v2系の既存文書、テスト、`SDFS.BIN`、stage1は、v3検討中も旧系統として壊さない。

## 実装Issue

| Issue | 文書 | 内容 |
| --- | --- | --- |
| #271 | [issue-271_resident_stub.md](issue-271_resident_stub.md) | resident API stub とビルド基盤 |
| #275 | [issue-275_resident_detect.md](issue-275_resident_detect.md) | ROM側resident header検出 |
| #279 | [issue-279_memtop_caps.md](issue-279_memtop_caps.md) | GET_MEMTOP / GET_CAPS API |
