# #184 stage1 / SDFS/68生成条件の構成軸整理

## 背景

`make stage1` / `make sdfs` は、これまで `MONITOR_PROFILE=sbcio_vdg` または `MONITOR_PROFILE=k6802_vdg` の場合だけ許可していた。
一方で、SDFS/68 の起動に必要なのはVDGそのものではなく、ROM側のraw SD sector read / `BOOT`、SBC-IO、stage1を置けるワークRAM配置である。

標準 `sbcio` profileは引き続き `FEATURE_SD=0` のSBC-IO RAM拡張 + 2nd ACIAキーボード構成として残す。
ただし、VDGなしSBC-IOでSDFS/68を試す場合は、profile名を増やさず構成軸の直接指定で扱えるようにする。

## 採用方針

- `stage1` / `sdfs` の生成可否をprofile名ではなく構成軸で判断する。
- 許可条件は `FEATURE_SD=1`、`BOARD_IO=sbcio`、`MEMORY_CONFIG=ram64_c000_work` または `ram64_a000_work` とする。
- `FEATURE_FAT` は条件に含めない。SDFS/68本線では `FEATURE_FAT=0` を推奨するが、ROM常駐FAT互換構成の確認は別軸として残す。
- VDGなしSBC-IOのSDFS/68構成は、次のように直接指定する。

```sh
MONITOR_PROFILE=sbcio FEATURE_SD=1 FEATURE_FAT=0 BUILD_CONFIG_NAME=sbcio-sdfs make bin stage1 sdfs
```

## 生成物名

`BUILD_CONFIG_NAME=sbcio-sdfs` を使うと、次の生成物名になる。

- `build/mc6800-monitor-sbcio-sdfs.bin`
- `build/stage1-sbcio-sdfs.bin`
- `build/SDFS-sbcio-sdfs.BIN`

SDへ置くときは、他のSDFS/68構成と同じく `stage1` はfixed boot areaへ、SDFS/68本体はrootの `SDFS.BIN` として格納する。

## 検証方針

- `base` profileの `make stage1` / `make sdfs` は引き続き失敗することを確認する。
- `sbcio FEATURE_SD=1 FEATURE_FAT=0 BUILD_CONFIG_NAME=sbcio-sdfs` でROM、stage1、SDFS/68本体を生成できることを確認する。
- 生成したVDGなしSBC-IO構成のROM、stage1、SDFS/68本体で、エミュレータ上の `BOOT` がSDFS/68プロンプトへ到達することを確認する。
- 既存の `sbcio_vdg` / `k6802_vdg` のstage1 / SDFS/68テストを維持する。
