# Issue #138 SDFS/68 v2 DIR 実装

## 背景

SDFS/68 v1 では `L filename` で root directory の8.3ファイルを読み、S-Record / Intel HEXをロードできるようになった。
ただし、system SD に何が入っているかをSDFS/68側から確認する手段がなく、実機確認ではホストPCでSDカードを見てから `L` する必要があった。

Issue #138 では、SDFS/68 v2に向けた最初の通常操作として `DIR` を追加する。
ただし、まだメジャーバージョンを変えるほどのアーキテクチャ変更ではないため、実機ログでの起動メッセージは `SDFS/68 V1.2 #138` とする。
`#138` は、この実装の元Issue番号をbuild番号相当として表示する。
SDFS.BIN headerのversion byteはstage1が検査するバイナリ形式versionなので、互換性のため `1` のまま残す。

## 採用仕様

- `SDFS> DIR` で FAT root の8.3 short filename通常ファイルを一覧表示する。
- コマンドは `DIR` 完全一致を基本にし、余分な引数はエラーにする。
- `Dhhhh` の1 byte dumpとは、`DIR` 判定を先に行って分岐する。
- 表示形式はROM側 `DIR` 相当に寄せる。

```text
SDFS> DIR
SDFS.BIN A 0000092F
HELLO.S A 0000004A
HELLO.HEX A 00000022
```

表示対象:

| entry | 扱い |
| --- | --- |
| 8.3通常ファイル | 表示する |
| LFN entry | 表示しない |
| volume label | 表示しない |
| directory | 表示しない |
| deleted entry | 表示しない |
| empty entry | root directory終端として扱う |

エラーやroot chain終端ではハングせず、SDFS/68プロンプトへ戻る。

## stage1 APIを増やさない判断

`DIR` はstage1/BIOS側APIとして追加しない。
stage1はSDFS/68を起動するためのboot servicesであり、ユーザー向けのDOS機能を持たせない。

今回の `DIR` は、SDFS/68本体が既存のstage1 jump tableを使って実装する。

- `SDFS_API_MOUNT`
- `SDFS_API_READ_SECTOR`

ROM側 `CMD_DIR` も呼ばない。
ROM常駐FATの `DIR` / `LF` は `sbcio` profileの互換機能であり、SDFS/68本線の機能はSDFS/68側へ寄せる。

## 内部レイヤ整理

8kB RAM制約があるため、v2では正式なBIOS/kernel/shell分離や別ABI化までは行わない。
ただし、今後の肥大化を避けるため、ラベル名と呼び出し方向だけ軽く整理する。

| prefix | 役割 |
| --- | --- |
| `SDFS_API_*` | stage1 jump table wrapper |
| `SDFS_K_*` | root走査、entry判定、entry表示などのkernel相当helper |
| `SDFS_CMD_*` | shell command本体 |
| `SDFS_LOOP` / prompt周辺 | shell dispatch |

呼び出し方向は、おおむね `shell -> command -> kernel helper -> stage1 API wrapper` とする。
v3以降で必要になったら、ここを起点にもう少しきれいに分ける。

## 実機確認手順

1. `MONITOR_PROFILE=sbcio_vdg make stage1 sdfs`
2. `python3 tools/mk_sdfs_image.py --stage1 build/stage1-sbcio-vdg.bin --sdfs build/SDFS-sbcio-vdg.BIN --output build/sdfs-sbcio-vdg.img HELLO.S HELLO.HEX`
3. system SDを書き込む。
4. CPUボード + SBC-IO RAM構成で `RAMTEST C000-DFFF` が `OK` になることを確認する。
5. `] BOOT` でSDFS/68を起動する。
6. `SDFS> DIR` で `SDFS.BIN`、`HELLO.S`、`HELLO.HEX` などが見えることを確認する。
7. `SDFS> L HELLO.S` と `SDFS> D0100` が既存通り動くことを確認する。

## 確認内容

- `make bin`
- `MONITOR_PROFILE=sbcio_vdg make stage1 sdfs`
- `MONITOR_PROFILE=k6802_vdg make stage1 sdfs`
- `python3 tests/test_sdfs68_build.py`

テストでは次を確認する。

- `DIR` がroot上の8.3通常ファイルを表示する。
- LFN、volume label、directory、deleted entryを表示しない。
- root chainの後続clusterにあるentryも表示する。
- 空の後続root clusterでもタイムアウトせずプロンプトへ戻る。

## 対象外

- subdirectory
- LFN表示
- wildcard
- FAT write
- `TYPE`
- `RUN`
- `LOAD` 正式化
- `EXIT`
- 低位RAM `$7000-$7FFF` などの新規予約
