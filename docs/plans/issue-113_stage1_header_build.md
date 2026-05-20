# Issue #113 stage1 header / jump table とビルド基盤

## 関連リンク

- Issue #113: https://github.com/kuninet/mc6800-rom-monitor/issues/113
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #109: https://github.com/kuninet/mc6800-rom-monitor/issues/109

## 方針

#111 のstage1 loader全体実装へ入る前に、stage1 binaryの配置、header、jump table、単体ビルド、検査テストを固定する。このIssueではFAT32処理や `SDFS.BIN` 実ロードは実装しない。

## Stage1 binary

stage1 binaryは `S1_BASE` から始まる。

| offset | 内容 |
| --- | --- |
| `+0` | signature: ASCII `S1API68` |
| `+7` | API version。v1は `1` |
| `+8` | API count。v1は `6` |
| `+9` | flags。v1は `0` |
| `+10` - `+11` | stage1 boot entry address |
| `+12` - `+13` | stage1 image size |
| `+14` - `+15` | reserved。すべて `0` |
| `+16` | jump table開始 |

jump tableはMC6800の3byte `jmp` 命令列にする。

| offset | 内容 |
| --- | --- |
| `+16` | `jmp S1_INIT` |
| `+19` | `jmp S1_READ_SECTOR` |
| `+22` | `jmp S1_MOUNT` |
| `+25` | `jmp S1_FIND_83` |
| `+28` | `jmp S1_LOAD_FILE_83` |
| `+31` | `jmp S1_GET_ERROR` |

このIssueではAPI本体はstubにする。`S1_INIT` は成功、その他は未実装エラーを返す。

## メモリ配置

| profile | `S1_BASE` | `S1_LIMIT` | `SDFS_LOAD_BASE` | `SDFS_LOAD_LIMIT` |
| --- | --- | --- | --- | --- |
| `sbcio_vdg` | `$C400` | `$CFFF` | `$D000` | `$DEFF` |
| `k6802_vdg` | `$A400` | `$AFFF` | `$B000` | `$BEFF` |

`base` profileはstage1非対応とする。

## SDFS/68 最小header

SDFS/68本体 `SDFS.BIN` は、後続Issueで次の最小headerを持つ形式として扱う。

| offset | 内容 |
| --- | --- |
| `+0` | signature: ASCII `SDFS68` |
| `+6` | version。v1は `1` |
| `+7` | header size。v1は `16` |
| `+8` | entry address high |
| `+9` | entry address low |
| `+10` | body/load size high |
| `+11` | body/load size low |
| `+12` - `+15` | reserved |

このIssueでは仕様だけを固定し、stage1による検査とロードは後続で実装する。

## 検証方針

- `sbcio_vdg` と `k6802_vdg` のstage1 binaryを単体生成する。
- binary先頭の `S1API68` headerとjump tableを検査する。
- listingから `S1_BASE`、`S1_LIMIT`、`SDFS_LOAD_BASE` を確認する。
- binaryサイズが `S1_LIMIT - S1_BASE + 1` を超えないことを確認する。
