# Issue #291 SDFS/68 v3 resident検出アドレス分離

## 背景

ROM側 `CMD` gateway は、v3 resident API header `SDFS3API` を `SDFS_LOAD_BASE` で検出していた。

`SDFS_LOAD_BASE` は本来、v2 SDFS/68本体をstage1がロードする位置である。`k6802_vdg` では `$B000`、`k6802_4000` では `$5000` になる。

このため、K6802-SBC + VDG の既存v2環境で `BOOT` し、v2からv3 residentを `$5000` へロードして `CMD` で確認する経路が取れなかった。

## 方針

- v2用の `SDFS_LOAD_BASE` / `SDFS_LOAD_LIMIT` はそのまま維持する。
- v3用に `SDFS3_LOAD_BASE` / `SDFS3_LOAD_LIMIT` を追加する。
- 未指定時は既存互換として `SDFS3_LOAD_BASE=SDFS_LOAD_BASE`、`SDFS3_LOAD_LIMIT=SDFS_LOAD_LIMIT` とする。
- ROM側 `SDFS3_FIND_API` は `SDFS3_LOAD_BASE` を見る。
- v3 resident の `org` と header内work baseは `SDFS3_LOAD_BASE` を使う。
- `SDFS3SYS` 生成も `SDFS3_LOAD_*` を使う。

## 確認用構成

K6802-SBC + VDG で既存v2 system SDを使い、v3 residentだけ `$5000` に置く確認用構成は次の軸指定で作る。

```powershell
make rombin MONITOR_PROFILE=k6802_vdg ROM_KIND=W27C512 SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
make sdfs3 sdfs-tools MONITOR_PROFILE=k6802_vdg SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
```

この構成では、v2 SDFS/68本体のロード先は `$B000` のまま、v3 resident検出先だけ `$5000` になる。

## 検証方針

- 既存の `sbcio_4000` / `k6802_4000` v3 resident / SDFS3SYS テストを維持する。
- `k6802_vdg` + `SDFS3_LOAD_BASE=0x5000` のビルドで、`SDFS_LOAD_BASE=$B000` と `SDFS3_LOAD_BASE=$5000` が分離されることをテストする。
- K6802-SBC実機手順は `docs/testing/k6802_sdfs3_via_v2_bringup.md` に反映する。

