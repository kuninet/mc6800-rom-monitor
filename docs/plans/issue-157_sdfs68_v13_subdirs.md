# Issue #157 SDFS/68 V1.3 サブディレクトリ対応

## 対象

- 親Issue: #157
- 子Issue: #158, #160, #161, #162

## 採用方針

SDFS/68 V1.3では、root起点の明示path指定だけを扱う。
`CD`、`PWD`、カレントディレクトリ、相対path、`.`、`..` は実装しない。

受け付けるpathは `/SRC/HELLO.S` または `SRC/HELLO.S` のような8.3 short filename component列である。
どちらもroot directoryを起点に解決する。
末尾 `/`、空component、`//`、path内空白、wildcard、LFNは対象外として `?` を返す。

## 実装判断

- `DIR [path]` は通常ファイルと通常ディレクトリを表示する。
- 属性欄は通常ファイルを `A`、ディレクトリを `D` として表示する。
- hidden、system、volume label、LFN、deleted、不正名、`.`、`..` は表示しない。
- `LOAD path/file` と `RUN path/file` は共通path resolverで最後の通常ファイルentryを解決し、既存stream loaderへ渡す。
- `.COM` は `/BIN/HELLO.COM` と `/BIN/ARGS.COM AAA BBB` のようなpath指定に対応する。
- `.COM` の引数tailはpath解析で壊さないように専用一時領域へ退避し、実行直前に既存ABIの `ARG2_PTR` / `ARG2_LEN` へ戻す。

## サイズ確認

実装前の `SDFS-sbcio-vdg.BIN` は 3115 bytes。
V1.3実装後の `SDFS-sbcio-vdg.BIN` は 3614 bytesで、現行 `SDFS_LOAD_LIMIT=$DEFF` 内に収まる。

`.COM` path対応込みで収まったため、後続Issueへの分離は不要と判断した。
今後さらに機能を足す場合は、同じく `SDFS_END-1 > SDFS_LOAD_LIMIT` のアセンブル時チェックと実バイナリサイズを確認する。

## 検証方針

- `DIR` でrootの `SRC D 00000000`、`BIN D 00000000` が表示されること。
- `DIR /SRC` でサブディレクトリ内ファイルが表示されること。
- `LOAD /SRC/HELLO.S` と `L SRC/HELLO.HEX` がロードできること。
- `RUN /SRC/RUN.S` がS-Record entryへジャンプできること。
- `/BIN/HELLO.COM` と `/BIN/ARGS.COM AAA BBB` が実行でき、引数が渡ること。
- 不正pathで `?` を表示し、プロンプトへ戻ること。

## 対象外

- LFN。
- wildcard。
- FAT write。
- 複数open。
- `CD` / `PWD` / カレントディレクトリ。
- `.` / `..`。
- direct read API本体。
