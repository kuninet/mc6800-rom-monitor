# Issue #281 SDFS/68 v3 resident CMD_DISPATCH tail parser

## 背景

#276 で ROM 側 `CMD <tail>` gateway から resident API slot 1 `SDFS3_CMD_DISPATCH` を呼び出せるようになった。
#280 / #282 で read-only 系や loader 系の実処理へ接続する前に、resident 側で tail の先頭トークンを分類する必要がある。

## 採用方針

- `SDFS3_CMD_DISPATCH` は `X=tail pointer`、`B=tail length`、`A=0` の #259 規約を受ける。
- 先頭空白を読み飛ばし、最初の空白までを command token として扱う。
- token 判定は大文字小文字非依存にする。
- `DIR`、`TYPE`、`LOAD`、`RUN`、`*.COM` を分類する。
- このIssueでは FAT mount、directory walk、file read、loader 実処理には入らない。
- 分類できた command は、後続Issueで差し替えやすい個別 stub label へ分ける。
- stub は carry set で戻し、`SDFS3_LAST_ERROR` へ command 種別ごとの未実装エラーを保存する。
- 空tail、空白のみ、未知commandは `SDFS3_ERR_BAD_CMD` で戻す。

## 対象外

- `DIR` / `TYPE` の実処理接続。
- `LOAD` / `RUN` / `.COM` の実処理接続。
- path parser、8.3変換、FAT処理。
- ROM側の直接alias追加。
- v2 `SDFS> ` shell の変更。

## 検証方針

- `tests/test_sdfs68_v3_build.py` に resident parser harness を追加する。
- built resident をRAMへロードし、harness から `SDFS3_CMD_DISPATCH` を直接呼ぶ。
- `DIR`、前後空白付き小文字 `dir`、`TYPE`、大小混在 `LOAD`、`RUN`、大文字/小文字 `.COM` が各分類へ入ることを、`GET_ERROR` の未実装エラーコードで確認する。
- 空tail、空白のみ、未知commandが bad command になることを確認する。
- 既存 v3 system image / ROM gateway harness が通ることを確認する。
- 最終確認は `make test` を使う。Windows のローカル実行では `PYTHON=python` と相対 `ASL_INCLUDE_ARG` が必要になる場合がある。

## 関連

- #281: 対応Issue。
- #272: v3 phase 1 実装epic。
- #276: ROM CMD gateway。
- #280: resident DIR / TYPE read-only接続。
- #282: resident LOAD / RUN / .COM接続。
- #259: resident API最小セット。
