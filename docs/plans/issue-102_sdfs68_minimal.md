# Issue #102 SDFS/68最小本体とboot services接続

## 背景

#111 でstage1 loaderがFAT rootの `SDFS.BIN` を読み、SDFS/68 header確認後にentryへ制御を渡せるようになった。#102では、後続 #130 のHEX/S-record loaderを載せるための最小SDFS/68本体を追加する。

## 方針

- SDFS/68本体は `SDFS_LOAD_BASE` を `org` とするRAMロード用バイナリとして生成する。
- 先頭16 bytesは `SDFS68` header、version、header size、entry address、image size、reservedとする。
- 起動時に固定 `S1_BASE` の `S1API68` header、API version、API countを確認する。
- SDFS/68側にはstage1 boot services jump tableを呼ぶ薄いラッパを置く。
- v1最小本体では起動メッセージと `SDFS> ` プロンプトまでに留め、HEX/S-record loaderは #130 に分離する。
- `S1_LOAD_FILE_83` はロード先が `SDFS_LOAD_BASE` 固定であり、起動後のSDFS/68本体から呼ぶと自己上書きになる。そのため #102 ではラッパの接続確認までに留め、#130 では `.S` / `.HEX` 読み込み用に別バッファへ読む手段、または `S1_READ_SECTOR` / `S1_FIND_83` を使ったストリーム処理を設計する。

## 対象外

- HEX/S-record loader本体。
- `DIR`、`TYPE`、AUTOEXEC。
- FAT write、subdirectory、LFN、direct read API。
- stage1 loader本体の追加変更。
- 起動後のSDFS/68から安全に使える汎用ファイルロードAPIの確定。

## 検証方針

- `make sdfs` で `sbcio_vdg` / `k6802_vdg` のSDFS/68バイナリを生成できることを確認する。
- 生成バイナリの `SDFS68` header、entry、image size、`SDFS_LOAD_LIMIT` 内サイズを検査する。
- `mk-sdfs` 生成相当のSDイメージで、ROM `BOOT` → stage1 → SDFS/68 起動メッセージまでをエミュレータで確認する。
- stage1 boot services headerが存在しない場合に `S1?` を表示して停止することを確認する。
- stage1 boot services headerのversion不一致、API count不足を拒否することを確認する。
- SDFS/68側のboot servicesラッパが固定offsetのstage1 jump tableを呼ぶ形で生成されることを確認する。

## 後続

- #130 でSDFS/68のHEX/S-record loaderを実装する。
- #128 でSDFS/68移行後のROM常駐FAT `DIR` / `LF` を整理する。
