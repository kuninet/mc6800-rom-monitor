# K6802-SBC VDG環境でSDFS/68 v2からv3 residentを確認する手順

## 目的

K6802-SBC + K68-VDG実機で、SDFS/68 v3 resident の `CMD` 経由動作を確認する。
PH2の `BOOT3` 実装後は fixed LBA `64` の `SDFS3SYS` から直接residentをロードできる。v2経由の `LOAD SDFS3.S` 手順は比較・退避用として残す。

この手順では、既存のv2 system SDをそのまま使う。ROMは `k6802_vdg` ベースにし、v2 SDFS/68のロード先 `$B000` は維持したまま、v3 residentの検出先だけ `$5000` にする。

```text
]BOOT
  -> SDFS/68 v2 起動
SDFS> LOAD SDFS3.S
  -> v3 residentを $5000 へロード
SDFS> EXIT
  -> ROM monitorへ戻る
]CMD DIR
  -> $5000 の v3 residentを使う
```

## 前提

- ROMは `k6802_vdg` ベースで作る。
- `SDFS3_LOAD_BASE=0x5000`、`SDFS3_LOAD_LIMIT=0x7EFF` を指定する。
- v2 system SDの `SDFS.BIN` は既存の `k6802_vdg` 用を使う。
- `k6802_4000` 用に生成した `$5000` 配置のv2 `SDFS.BIN` は、この手順では使わない。

この構成では、v2とv3の配置は次のように分離される。

```text
v2 SDFS.BIN:      $B000-
v3 resident:      $5000-
K68-VDG VRAM:     $C000-$DFFF
SD/FAT work:      $A000-$BFFF
```

## ビルド

Windows PowerShell例。

```powershell
make rombin MONITOR_PROFILE=k6802_vdg ROM_KIND=W27C512 SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
make sdfs3 sdfs3sys sdfs-tools MONITOR_PROFILE=k6802_vdg SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
```

主な生成物:

```text
build/mc6800-monitor-k6802-vdg-sdfs3-5000-W27C512.bin
build/SDFS3-k6802-vdg-sdfs3-5000.BIN
build/SDFS3SYS-k6802-vdg-sdfs3-5000.BIN
build/SDFS3-k6802-vdg-sdfs3-5000.p
build/HELLO.S
build/HELLO.COM
build/ARGS.COM
```

SDに置くS-recordを作る。

```powershell
p2hex build\SDFS3-k6802-vdg-sdfs3-5000.p build\SDFS3.S -q -F Moto -M 2
```

## SDカード準備

`BOOT3` を使う場合は、physical LBA `64` に `build/SDFS3SYS-k6802-vdg-sdfs3-5000.BIN` を配置し、FAT32 partitionを physical LBA `128` 以降へ置く。
v2経由の比較も行う場合は、既存v2のsystem SDとして起動できるカードを用意する。FAT32 rootに、最低限次を置く。

```text
SDFS.BIN
SDFS3.S
README.TXT
HELLO.S
HELLO.COM
ARGS.COM
```

`SDFS.BIN` は既存v2環境のものを使う。`SDFS3.S` は上記の `SDFS3-k6802-vdg-sdfs3-5000.p` から作ったものを置く。

ファイル名は8.3 short nameで扱えるようにする。まずはサブディレクトリ、長いファイル名、日本語ファイル名、exFATは避ける。

## 実機手順

1. `build/mc6800-monitor-k6802-vdg-sdfs3-5000-W27C512.bin` をW27C512へ焼いて起動する。

```text
]
```

2. VDG画面とシリアルの両方でmonitor表示が出ることを確認する。

3. `BOOT3` でv3 residentをロードする。

```text
]BOOT3
OK
]
```

4. v3 residentがROM `CMD` から使えることを確認する。

```text
]CMD DIR
]CMD TYPE README.TXT
]CMD LOAD HELLO.S
]D0200-020F
]CMD RUN HELLO.S
]CMD HELLO.COM
]CMD ARGS.COM AAA BBB
```

期待値:

| コマンド | 期待結果 |
| --- | --- |
| `CMD DIR` | FAT32 rootの8.3通常ファイルが表示される |
| `CMD TYPE README.TXT` | テキスト内容が表示される |
| `CMD LOAD HELLO.S` | `OK` が表示される |
| `CMD RUN HELLO.S` | `HELLO SREC` が表示され、SWIでmonitorに戻る |
| `CMD HELLO.COM` | `HELLO COM` が表示され、monitorに戻る |
| `CMD ARGS.COM AAA BBB` | `ARGS AAA BBB` が表示され、monitorに戻る |

## v2経由の比較手順

1. v2 SDFS/68を起動する。

```text
]BOOT
SDFS>
```

2. v2側でSD rootが見えることを確認する。

```text
SDFS> DIR
```

`SDFS3.S`、`HELLO.S`、`HELLO.COM`、`ARGS.COM` が見えることを確認する。

3. v3 residentを `$5000` へロードする。

```text
SDFS> LOAD SDFS3.S
OK
```

4. ROM monitorへ戻る。

```text
SDFS> EXIT
]
```

5. v3 residentがROM `CMD` から使えることを確認する。

```text
]CMD DIR
]CMD TYPE README.TXT
]CMD LOAD HELLO.S
]D0200-020F
]CMD RUN HELLO.S
]CMD HELLO.COM
]CMD ARGS.COM AAA BBB
```

期待値:

| コマンド | 期待結果 |
| --- | --- |
| `CMD DIR` | FAT32 rootの8.3通常ファイルが表示される |
| `CMD TYPE README.TXT` | テキスト内容が表示される |
| `CMD LOAD HELLO.S` | `OK` が表示される |
| `CMD RUN HELLO.S` | `HELLO SREC` が表示され、SWIでmonitorに戻る |
| `CMD HELLO.COM` | `HELLO COM` が表示され、monitorに戻る |
| `CMD ARGS.COM AAA BBB` | `ARGS AAA BBB` が表示され、monitorに戻る |

## v2へ戻る

v2へ戻りたい場合は、ROM monitorから再度 `BOOT` する。

```text
]BOOT
SDFS>
```

これはRAM上に残っているv2へ復帰するのではなく、SDからv2を再ロードする動作である。

## 切り分け

| 症状 | 見る場所 |
| --- | --- |
| `BOOT` でSDFSに入れない | ROM、stage1、system SD、`SDFS.BIN` |
| `SDFS> LOAD SDFS3.S` が失敗する | FAT32 root、8.3名、ファイル破損 |
| `BOOT3` が `?` | LBA64の `SDFS3SYS`、checksum、ROMとresidentの `SDFS3_LOAD_BASE` |
| `CMD DIR` が `?` | `BOOT3` または `LOAD SDFS3.S` でresidentがロード済みか、ROMとresidentの `SDFS3_LOAD_BASE` が一致しているか |
| `CMD DIR` が固まる | SD SPI配線、PIAアドレス、カード相性 |
| `CMD TYPE` / `CMD LOAD` だけ失敗 | FAT32 entry、file size、cluster chain |
