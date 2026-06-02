# Issue #137 SDFS/68 v2 第2段DOS基本操作ロードマップ

## 背景

SDFS/68 v1は、`BOOT -> stage1 -> SDFS.BIN -> L filename` まで完了した。v2では、SDFS/68をROMモニタの延長ではなく、小さい第2段DOSとして通常運用できる基本操作へ進める。

責務境界は #136 の方針に従う。

## v2の本線

- `DIR`: root directoryを表示する。
- `TYPE filename`: root上のテキストファイルを表示する。
- `RUN filename`: S-Recordファイルをロードし、entry recordが取れれば実行する。
- `RUN addr`: 指定アドレスへジャンプする。
- `LOAD filename`: ロードのみを行う開発補助コマンド。
- `L filename`: `LOAD filename` の短縮エイリアス。
- `EXIT`: ROMモニタへ戻る。

`RUN` を通常実行の本線にし、`LOAD` / `L` はロード確認やデバッグ用の補助として扱う。

## 実装順序

| 順番 | Issue | 内容 |
| --- | --- | --- |
| 1 | #138 | `DIR` でroot directoryを表示する |
| 2 | #141 | `LOAD` を開発補助コマンドとして整理する |
| 3 | #142 | `EXIT` でROMモニタへ戻る |
| 4 | #149 | `RUN addr` で指定アドレスを実行する |
| 5 | #150 | `RUN filename` でロード後に実行する |
| 6 | #139 | `TYPE` でテキストファイルを表示する |

## 対象外

- subdirectory、LFN、wildcard。
- FAT write、SAVE。
- direct read API。
- I2C、RTC、OLED、VDG高機能。
- `FOO` 入力で `FOO.COM` を探す本格トランジェントコマンド。
- ユーザープログラム終了後にSDFS/68へ戻るABI。

## 検証方針

- `DIR` はroot上の8.3通常ファイルを表示する。
- `TYPE` は短いテキストファイルを表示し、存在しないファイルでプロンプトへ戻る。
- `RUN addr` は指定アドレスへジャンプする。
- `RUN filename` はentry recordありS-Recordファイルをロードして実行する。
- Intel HEXは `RUN filename` の対象外とし、`LOAD filename` と `RUN addr` の組み合わせで実行する。
- `LOAD` / `L` は同じロード結果になる。
- `EXIT` 後にROMモニタの `] ` プロンプトへ戻り、再度 `BOOT` できる。
- 既存の `make bin`、`make stage1`、`make sdfs`、`test_sdfs68_build.py`、`test_mk_sdfs_image.py`、`test_sd_fixture.py` を維持する。

## 既存Issueの位置づけ

- #104 はv4以降のdirect read API設計として残す。
- #105 はv3以降のsubdirectory設計として残す。
- #177 の方針どおり、`sbcio` はSD/FATなしprofile、`sbcio_vdg` / `k6802_vdg` は `BOOT + SDFS/68` 本線profileとして扱う。ROM常駐FATは直接指定互換構成でだけ確認する。
