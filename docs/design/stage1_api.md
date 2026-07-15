# stage1 API 仕様 (V2 提案)

## 位置付け

ROM モニタが SDFS/68 を起動するために fixed LBA (16) から `S1_BASE` へ読み込む stage1 loader は、boot 後もそのまま resident に残り、SDFS/68 本体に対して FAT32 プリミティブを **jump table 経由の API** として提供する。

`S1_BASE` (`$A400` on k6802_vdg / `$C400` on sbcio) の先頭は header + jump table で始まり、後段に実装ロジックが続く 3 KB モジュール (`S1_LIMIT-S1_BASE+1 = $0C00`) である。

本ドキュメントは V1 の実測仕様と、Issue #245 で計画している V2 の API 拡張案をまとめる。

## V1 (現行、`S1_API_VERSION=1`)

### Header レイアウト (`S1_BASE+0..+15`)

| Offset | Size | 内容 |
| --- | --- | --- |
| `+0`  | 7 B | `"S1API68"` magic |
| `+7`  | 1 B | `S1_API_VERSION` = 1 |
| `+8`  | 1 B | `S1_API_COUNT` = 6 |
| `+9`  | 1 B | `S1_FLAG_NONE` = 0 (予約) |
| `+10` | 2 B | boot entry ptr (`S1_BOOT_SDFS`) |
| `+12` | 2 B | stage1 image size |
| `+14` | 2 B | 予約 (0) |

### Jump Table (`S1_BASE+16..+33`)

各 slot は 3 B (`jmp abs`)。`S1_BASE + 16 + n*3` を JSR することで n 番目 API を呼ぶ。

| Slot | Address | API | 役割 |
| --- | --- | --- | --- |
| 0 | `S1_BASE+16` | `S1_INIT` | SD 初期化 |
| 1 | `S1_BASE+19` | `S1_READ_SECTOR` | LBA 指定 sector 読み |
| 2 | `S1_BASE+22` | `S1_MOUNT` | FAT32 mount |
| 3 | `S1_BASE+25` | `S1_FIND_83` | root 8.3 ファイル検索 |
| 4 | `S1_BASE+28` | `S1_LOAD_FILE_83` | 検索 + 一括 load |
| 5 | `S1_BASE+31` | `S1_GET_ERROR` | `FAT_ERROR` 参照 |

### 呼び出し規約

- 引数 / 戻り値の register は各 API で個別に定義。すべての API は A/B/X を破壊すると仮定する
- carry で成否を通知 (0=成功、1=失敗)。詳細エラーは `FAT_ERROR` (S1 API `S1_GET_ERROR` で参照)
- `S1_BASE` 上の header と jump table 内容は boot 後も変更しない

### version 判定 (SDFS/68 側)

`SDFS_CHECK_S1` (`src/sdfs68.asm:873`) は以下を検査:

1. magic `"S1API68"` 完全一致
2. `S1_API_VERSION == 1` (完全一致)
3. `S1_API_COUNT >= 6` (blo で fail)

いずれか外れると SDFS/68 は `TXT_S1_ERROR` (`S1?`) を出して SWI する。

## V2 提案 (VERSION 据置 / COUNT 拡張)

### 変更概要

streaming primitives を stage1 API として公開し、SDFS/68 内の同等コード (現 `SDFS_STREAM_OPEN` / `SDFS_STREAM_GETC` / `SDFS_NEXT_CLUSTER` など) を削除する。バグ (#243 = cluster ≥ 64 で FAT chain 誤動作) の修正は stage1 側 (`FAT32_NEXT_CLUSTER` / `FAT_NEXT_OFFSET_PREP`) に閉じ込め、SDFS/68 側から自動的に恩恵を受けさせる。

### Header (変更)

| Offset | V1 | V2 |
| --- | --- | --- |
| `+7` `S1_API_VERSION` | 1 | **1** (据置) |
| `+8` `S1_API_COUNT` | 6 | **9** |

`+9..+15` は既存互換のまま (`S1_FLAG_NONE = 0`、boot entry、size、reserved)。

VERSION は破壊的変更時のみ bump する運用にする。今回は既存 slot の semantics を維持したまま末尾に slot を追加する非破壊拡張なので COUNT のみ bump し VERSION は据え置く。将来 slot 順序変更や semantics 変更が必要なら VERSION を 2 に上げる。

### Jump Table 拡張

| Slot | Address | API | V1/V2 | 役割 |
| --- | --- | --- | --- | --- |
| 0 | `S1_BASE+16` | `S1_INIT` | V1 | SD 初期化 |
| 1 | `S1_BASE+19` | `S1_READ_SECTOR` | V1 | LBA 指定 sector 読み |
| 2 | `S1_BASE+22` | `S1_MOUNT` | V1 | FAT32 mount |
| 3 | `S1_BASE+25` | `S1_FIND_83` | V1 | root 8.3 ファイル検索 |
| 4 | `S1_BASE+28` | `S1_LOAD_FILE_83` | V1 | 検索 + 一括 load |
| 5 | `S1_BASE+31` | `S1_GET_ERROR` | V1 | `FAT_ERROR` 参照 |
| 6 | `S1_BASE+34` | `S1_STREAM_OPEN` | **V2** | find 済 file を stream モードで開く |
| 7 | `S1_BASE+37` | `S1_STREAM_GETC` | **V2** | 1 byte 読む (sector 境界内包) |
| 8 | `S1_BASE+40` | `S1_STREAM_BYTES_REMAIN` | **V2** | 残バイトあり判定 |

V1 slot 0-5 の semantics は完全維持。V2 は末尾に 3 slot 追加 (`+9` byte)。

### V2 API 詳細

すべて既存 `src/fat32.asm` の `FAT32_STREAM_OPEN` (line 430)、`FAT32_STREAM_GETC` (line 443)、`FAT_BYTES_REMAIN` (line 761) をそのまま jump table に露出する。

#### `S1_STREAM_OPEN`

**前提**: `S1_FIND_83` または `S1_LOAD_FILE_83` の前段相当で `FAT_FILE_*` (CLUS / SIZE) が有効に設定済であること。

**動作**:
- `FAT_CUR_CLUS` ← `FAT_FILE_CLUS`
- `FAT_BYTES_REM` ← `FAT_FILE_SIZE`
- `FAT_COPY_COUNT` ← 0、`FAT_SECTOR_IN_CLUS` ← 0
- `FAT_ENTRY_PTR` ← `SD_SECTOR_BUF` (sector 未読み込み状態)
- `FAT_ERROR` ← `FAT_ERR_NONE`

**戻り**: A = `FAT_ERR_NONE`、carry = 0

**破壊**: A/B/X

#### `S1_STREAM_GETC`

**動作**:
- 残バイトがなければ carry=1 で戻る (EOF)
- 現 sector に copy 分がなければ `FAT_STREAM_LOAD_SECTOR` (内部) で次 sector を読み込み
- 次 sector が別 cluster にまたがる場合は `FAT_ADVANCE_FILE_SECTOR` → `FAT32_NEXT_CLUSTER` を経由
- `SD_SECTOR_BUF` 内の現在位置 (`FAT_ENTRY_PTR`) から 1 byte を取り、pointer と counters を更新

**戻り**: A = 読んだ byte、carry = 0
**EOF / SD error**: carry = 1 (`FAT_ERROR` に詳細)

**破壊**: A/B/X

#### `S1_STREAM_BYTES_REMAIN`

**動作**: `FAT_BYTES_REM` の 4 バイトを OR して 0 でなければ「残りあり」判定。副作用なし。

**戻り**: carry = 1 で残あり、carry = 0 で EOF

**破壊**: A

### #243 (cluster ≥ 64 バグ) との関係

`FAT32_NEXT_CLUSTER` / `FAT_NEXT_OFFSET_PREP` (`src/fat32.asm:689-742`) の修正は Step 2 (#247) で行う。SDFS/68 側から `S1_STREAM_GETC` を経由すれば同じ fix を利用できるため、SDFS/68 の重複コード (`SDFS_NEXT_CLUSTER` 他) の削除と組み合わせて **バグ修正箇所を 1 つにまとめる**のが本 refactor の主目的。

### version / count 判定の変更 (SDFS/68 側)

V2 stage1 header は VERSION=1 据置 (`cmpa #1 / bne fail` 完全一致は成立)、COUNT=9 (`blo #9 fail` で失敗)。
V2 SDFS/68 は新 API slot 6-8 を呼ぶ必要があるため、`SDFS_CHECK_S1` の期待値を更新する:

```
        ldaa    7,x                 ; S1_API_VERSION
        cmpa    #SDFS_S1_VERSION     ; 現状 1、変更なし
        bne     SDFS_CHECK_S1_FAIL
        ldaa    8,x                 ; S1_API_COUNT
        cmpa    #SDFS_S1_COUNT       ; 6 → 9 に更新
        blo     SDFS_CHECK_S1_FAIL   ; 既存の "count >= expected" 判定を流用
```

つまり SDFS/68 側は `SDFS_S1_COUNT` を 6 → 9 に上げるだけ。`SDFS_S1_VERSION` は 1 のまま。

### 互換性まとめ

| stage1 | SDFS.BIN | 動作 |
| --- | --- | --- |
| V1 (count=6) | V1 (要求 count=6) | 従来通り |
| V1 (count=6) | V2 (要求 count=9) | `S1?` fail (SDFS 側 count check reject) |
| V2 (count=9) | V1 (要求 count=6) | **動く**。V1 SDFS.BIN は新 slot 6-8 を呼ばない。V1 の API slot 0-5 は semantics 維持なので既存挙動 |
| V2 (count=9) | V2 (要求 count=9) | 正常運用 |

V2 stage1 + V1 SDFS.BIN の組合わせは backward compat として動作する。V2 SDFS/68 は V2 stage1 を必須要求する。実運用としては V2 stage1 + V2 SDFS.BIN のペア配布とする。

## 実装上の見込みサイズ影響

### stage1 (`build/stage1-k6802-vdg.bin`)

- 現在: **2514 B / 3072 B** (余り 558 B)
- V2 追加コスト: jump slot 3 × 3 = **9 B** (ただし `FAT32_STREAM_*` は既に stage1 に compile 済みなので追加は jump 分のみ)
- #247 の cluster ≥ 64 修正: **+30..80 B** 見込み (16bit シフト + LBA 加算)
- 合計: 現在 + 40..90 B → **2554..2604 B**、余り 470..518 B 確保

### SDFS/68 (`build/SDFS-k6802-vdg.BIN`)

- 現在: **3714 B / 3840 B** (余り 126 B、診断 patch 込み)
- V2 refactor で削除される重複コード (#248 対象):
  - `SDFS_STREAM_OPEN` / `SDFS_STREAM_GETC` / `SDFS_STREAM_LOAD_SECTOR`
  - `SDFS_SECTOR_TO_SD_LBA` / `SDFS_CLUSTER_TO_SD_LBA`
  - `SDFS_INC_SD_LBA` / `SDFS_ADVANCE_FILE_SECTOR`
  - `SDFS_NEXT_CLUSTER` / `SDFS_COPY_NEXT_TO_CUR`
  - `SDFS_BYTES_REMAIN` / `SDFS_PREP_COPY_COUNT`
  - `SDFS_DEC_BYTES_REM_ONE`
- 見込み削減: **-250..-400 B** → 余り 376..526 B 確保

## テスト方針

### stage1 単体 (`tests/test_stage1_build.py` 等)

- header の VERSION=2 / COUNT=9 assertion 追加
- 新 jump slot が命令 `jmp abs` で埋まっているか確認
- fixture 追加: `sd_fixtures.py` に「SDFS.BIN を cluster 3 に置く現行構成」に加え、「cluster 100」「cluster 200」の layout を追加し、`FAT32_STREAM_GETC` 経由の read が cluster 境界を跨いで正しく動作することを確認する

### SDFS/68 build (`tests/test_sdfs68_build.py`)

- `SDFS_S1_VERSION=2` / `SDFS_S1_COUNT=9` に追従
- 高 cluster fixture で `.COM` load / SREC LOAD / IHEX LOAD が通ることを確認
- SDFS/68 バイナリサイズの縮小を asserted (upper bound として 3700 B 以下、など)

### 統合

- fresh SD (`mk_sdfs_image`) での BOOT / `.COM` 実行が引き続き通ること
- 実機で BASIC (DBS.COM) 動作継続を手動確認

## Refs

- Parent: #245
- Child steps: #246 (本 doc), #247 (実装 + #243 close), #248 (SDFS 側 refactor), #249 (統合)
- 関連: #243 (cluster ≥ 64 バグ)、#244 (S1_BOOT_DONE silent runaway, 独立修正)、#219 (loader dedup 解析)
