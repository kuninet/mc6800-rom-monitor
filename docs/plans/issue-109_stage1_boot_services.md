# Issue #109 SDFS/68 stage1 boot services設計

## 関連リンク

- Issue #109: https://github.com/kuninet/mc6800-rom-monitor/issues/109
- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #101: https://github.com/kuninet/mc6800-rom-monitor/issues/101
- Issue #102: https://github.com/kuninet/mc6800-rom-monitor/issues/102
- Issue #103: https://github.com/kuninet/mc6800-rom-monitor/issues/103
- Issue #107: https://github.com/kuninet/mc6800-rom-monitor/issues/107

## 方針

固定LBA boot area には `SDFS.BIN` 本体ではなく **stage1 loader** を置く。ROM はFATを読まず、固定LBAからstage1をRAMへ読み込んで起動する。stage1 はFAT32 read-only の最小実装を持ち、FAT root の `SDFS.BIN` を読み込んで SDFS/68 本体へ制御を渡す。

stage1 は SDFS/68 起動後もRAMに常駐し、固定baseの header + jump table を `boot services` として公開する。SDFS/68 はこの boot services を使って、stage1 の SD/FAT 低層処理を再利用できる。

この方針により、ROMからFAT I/Oを外しつつ、stage1を使い捨てにしない。

## 起動の流れ

1. ROM `BOOT` が SD を初期化する。
2. ROM `BOOT` が固定LBAからstage1を `S1_BASE` へ読み込む。
3. ROM `BOOT` が `S1API68` header、API version、entryを確認する。
4. ROM `BOOT` がstage1 entryへジャンプする。
5. stage1 がFAT32を最小mountする。
6. stage1 がroot directoryから8.3名 `SDFS    BIN` を探す。
7. stage1 が `SDFS.BIN` を `SDFS_LOAD_BASE` へロードする。
8. stage1 がSDFS/68 headerを確認し、SDFS/68 entryへジャンプする。
9. SDFS/68 は必要に応じてstage1 boot servicesを呼び出す。

## Stage1 API

stage1 header は `S1_BASE` から始まる。

| offset | 内容 |
| --- | --- |
| `+0` | signature: ASCII `S1API68` |
| `+7` | API version。v1は `1` |
| `+8` | API count |
| `+9` | flags |
| `+10` - `+15` | reserved |
| `+16` | jump table開始 |

MC6800には便利な間接 `JSR` がないため、APIはポインタ列ではなく固定offsetの `jmp` 命令列にする。

| offset | 命令 | 用途 |
| --- | --- | --- |
| `+16` | `jmp S1_INIT` | stage1再初期化または状態確認 |
| `+19` | `jmp S1_READ_SECTOR` | LBA指定の1 sector read |
| `+22` | `jmp S1_MOUNT` | FAT32最小mount |
| `+25` | `jmp S1_FIND_83` | root 8.3名検索 |
| `+28` | `jmp S1_LOAD_FILE_83` | 8.3名ファイルを指定RAMへロード |
| `+31` | `jmp S1_GET_ERROR` | stage1エラー取得 |

v1のAPIは boot services に限定する。汎用DOS API、複数open、seek、write、subdirectory、LFNは扱わない。

## メモリ配置

stage1配置はprofile別に分ける。

| profile | sector buffer | monitor / stage1 work予約 | stage1候補 | SDFS/68候補 | stack余白 | VDG VRAM |
| --- | --- | --- | --- | --- | --- |
| `sbcio_vdg` | `$C000-$C1FF` | `$C200-$C3FF` | `$C400-$CFFF` | `$D000-$DEFF` | `$DF00-$DFFF` | `$A000-$BFFF` |
| `k6802_vdg` | `$A000-$A1FF` | `$A200-$A3FF` | `$A400-$AFFF` | `$B000-$BEFF` | `$BF00-$BFFF` | `$C000-$DFFF` |

実装Issueでは `S1_BASE`、`S1_LIMIT`、`SDFS_LOAD_BASE`、`SDFS_LOAD_LIMIT` をprofile別定数として追加し、stack、VRAM、monitor workと衝突しないことをlistingとテストで確認する。`$DF00-$DFFF` / `$BF00-$BFFF` は当面stack余白として扱う。

## Issueへの影響

- #82 は、SDFS/68ブート構想の親Issueとして、ROM直FAT方式ではなく stage1方式を現方針として扱う。
- #101 は、ROMからFAT rootの `SDFS.BIN` を読むIssueではなく、固定LBAからstage1を読むROM `BOOT` Issueへ再定義する。
- #103 は、FAT32 rootファイル配置だけでなく、固定LBA boot areaへ `STAGE1.BIN` 相当を書き込むツールIssueへ拡張する。
- #107 は、固定LBAにSDFS/68本体を置く評価ではなく、stage1 loaderを置く評価として読み替える。

## 後続実装分割

- ROM stage1 loader: ROMに `BOOT` を追加し、固定LBAからstage1を `S1_BASE` へロードする。
- stage1 FAT loader: stage1に最小FAT32 readerと `SDFS.BIN` ロード処理を実装する。
- `mk-sdfs`: 固定LBA boot areaへstage1を書き込み、FAT rootへ `SDFS.BIN` とデータファイルを配置する。
- SDFS/68 v1: stage1 boot servicesを利用し、HEX/S-recordロードを提供する。

## 検証方針

このIssueでは設計整理を成果物とする。後続実装では次を確認する。

- ROM `BOOT` が固定LBAからstage1を読める。
- stage1 signature不一致、read失敗、size不正、entry不正でmonitorへ戻る。
- stage1がroot `SDFS.BIN` をロードできる。
- `SDFS.BIN` 未検出、壊れたFAT、壊れたSDFS headerでハングしない。
- SDFS/68起動後にstage1 header / jump tableを確認できる。
