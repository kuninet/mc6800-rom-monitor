# Issue #103 mk-sdfs システムSDイメージ生成ツール

## 関連リンク

- Issue #103: https://github.com/kuninet/mc6800-rom-monitor/issues/103
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #109: https://github.com/kuninet/mc6800-rom-monitor/issues/109

## 方針

`mk-sdfs` は SDFS/68 用のシステムSDイメージをPC上で生成するツールである。実SDデバイスへ直接書き込まず、Mac / Windows / Linux で同じ Python コードを使って FAT32 イメージファイルを作る。

固定 boot area は FAT32 reserved sector ではなく、partition開始前の physical LBA `16` 以降に置く。FAT32 partition は既存SD fixtureと同じ physical LBA `32` から開始する。stage1 loader と root の `SDFS.BIN` は別内容であり、同一コピーとして扱わない。

## 実装内容

- `tools/mk_sdfs_image.py` を追加する。
- CLI は `--stage1 STAGE1.BIN --sdfs SDFS.BIN --output IMAGE.img [files...]` を最小形にする。
- stage1 loader は physical LBA `16` 以降へ sector padding 付きで連続配置する。
- FAT root には `SDFS.BIN` と追加ファイルを 8.3 short filename で配置する。
- 既定出力はホストOSがFAT32として扱えるクラスタ数にする。小型fixtureはテストで明示指定する。
- 既存 `tests/sd_fixtures.py` の低層FAT32生成処理を `tools/fat32_image.py` に切り出し、fixtureと `mk-sdfs` の両方で使う。

## エラー条件

- stage1 loader が空。
- `SDFS.BIN` が空。
- stage1 boot area が MBR または FAT32 partition と衝突する。
- 追加ファイル名が 8.3 short filename として扱えない。
- root内で8.3名が重複する。
- 入力ファイルが存在しない、または読めない。

## 対象外

- 実SDデバイスへの直接書き込み。
- 既存FATカードへの追記。
- LFN、subdirectory、FAT write。
- stage1 loader本体の実装。これは #111 で扱う。
- ROM `BOOT` の実装。これは #101 で扱う。
- SDFS/68 本体の実装。これは #102 で扱う。

## 検証方針

- 同一入力から同一bytesのイメージを生成できることを確認する。
- MBR、FAT32 BPB、FSInfo、FAT、root directoryを検査する。
- 既定出力のdata cluster数がFAT32判定の下限を満たすことを確認する。
- physical LBA `16` にstage1 loaderが配置されることを確認する。
- rootの `SDFS.BIN` と追加ファイルのcluster chain、file size、内容を検査する。
- 異常入力でエラー終了することを確認する。
- 既存 `test_sd_fixture.py` を維持し、共通writer化で既存fixtureが壊れていないことを確認する。
