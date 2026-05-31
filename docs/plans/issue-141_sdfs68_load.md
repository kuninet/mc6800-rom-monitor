# Issue #141 SDFS/68 LOAD 正式化

## 背景

SDFS/68 v1の `L filename` は、S-Record / Intel HEXをロードするための最小入口として実装した。
v2では通常実行を `RUN` へ寄せ、ロードだけ行う操作は開発補助コマンドとして整理する。

## 採用仕様

- `SDFS> LOAD filename` を正式名として追加する。
- 既存の `SDFS> L filename` は `LOAD filename` の短縮エイリアスとして維持する。
- `LOAD` はロードだけを行い、自動実行しない。
- `LOAD` と `L` は同じ内部ロード処理を呼ぶ。
- `LOAD filename` はコマンド名とファイル名の間に空白を要求する。
- `LOADHELLO.S` のような曖昧な入力は `?` として扱う。

## 実装判断

`LOAD` はSDFS/68本体のshell commandであり、stage1 APIは増やさない。
既存の `L` 実装を `SDFS_K_LOAD_FILE` として共通化し、`SDFS_CMD_LOAD_LONG` と `SDFS_CMD_LOAD_ALIAS` の両方から呼ぶ。

表示上のbuild番号は元Issue番号に合わせ、起動メッセージは `SDFS/68 V1.2 #141` とする。
SDFS.BIN headerのformat versionはstage1互換のため `1` のまま変更しない。

## 確認内容

- `LOAD HELLO.S` でS-Recordをロードできること。
- `L HELLO.HEX` で既存aliasが動くこと。
- `LOAD EOF.HEX` でIntel HEX EOF終端を処理できること。
- `LOAD MISSING.S`、`LOADHELLO.S`、壊れたHEX、終端recordなしS-Recordで `?` を出してプロンプトへ戻ること。

## 実機確認手順

1. 新しい `SDFS.BIN` をsystem SDのrootへコピーする。
2. `] BOOT` でSDFS/68を起動する。
3. `SDFS> LOAD HELLO.S` を実行する。
4. `SDFS> D0100` などでロード済みであることを確認する。
5. `SDFS> L HELLO.S` も同じように動くことを確認する。

## 対象外

- `RUN` の実装。
- 実行ファイル形式の追加。
- ロード先メモリ保護。
