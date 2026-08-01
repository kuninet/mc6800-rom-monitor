# SDFS/68 v3 設計メモ

このディレクトリは、親Issue #254 配下の SDFS/68 v3 設計Issueをまとめる。

v3 は、現行の `BOOT -> stage1 -> SDFS.BIN -> SDFS> ` 方式を単純に拡張するのではなく、ROMモニタをコマンド入口、SDFS/68をRAM residentのSD/FAT serviceとして再整理する検討線である。
設計が固まるまでは実装Issueをここへ混ぜず、責務境界、API、system image、メモリマップ、BASIC連携を分けて記録する。

## 設計Issue

| Issue | 文書 | 内容 |
| --- | --- | --- |
| #255 | [issue-255_boundary.md](issue-255_boundary.md) | 責務境界とv2互換性方針 |
| #256 | [issue-256_rom_dispatch.md](issue-256_rom_dispatch.md) | ROMモニタ側command dispatchとSDFS API呼び出し口 |
| #257 | 後続PRで追加 | 固定LBA system image形式と1発ロード方式 |
| #258 | 後続PRで追加 | system領域更新方式 |
| #259 | 後続PRで追加 | resident API最小セット |
| #260 | 後続PRで追加 | メモリマップとBank RAM利用方針 |
| #261 | 後続PRで追加 | BASIC SAVE/LOAD連携方式 |

## 運用

- v3設計文書はこのディレクトリに置く。
- 実装Issueは、#256から#261の設計が固まってから分割する。
- v2系の既存文書、テスト、`SDFS.BIN`、stage1は、v3検討中も旧系統として壊さない。
