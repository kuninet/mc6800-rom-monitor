# SDFS/68 `DIR` / `RUN` 表示改善計画

## 対象

- Issue: #153
- 親Issue: #137
- 関連: #138, #149, #150, #136, #130, #82

## 背景

SDFS/68 V1.2で `DIR`、`LOAD`、`RUN addr`、`RUN filename`、`EXIT` が揃い、通常操作がDOSらしくなってきた。
一方で実機確認中、MacでSDカード上のファイルを触ったあとにAppleDouble風の副産物が `DIR` に見えた。
また `RUN KHELL` のような存在しないファイル指定で、実機ログ上は `?` が見えないように見えた。

`TYPE` を追加する前に、既存コマンドの表示対象とエラー復帰を整える。

## 方針

- `DIR` は通常ユーザーファイルだけを表示する。
- hidden / system / volume label / directory / LFN / deleted entry は表示しない。
- ファイル名に制御文字や非ASCIIが混じるentryは表示しない。
- Mac由来のAppleDouble風entryはhidden属性付きの短縮名として見えることがあるため、hidden除外で非表示にする。
- `_` 始まりの通常ファイルを無条件には隠さない。FAT属性上の通常ファイルなら表示対象に残す。
- `RUN` の失敗経路は `?` を表示して `SDFS> ` に戻ることをテストで固定する。

## 検証方針

- `DIR` に `SDFS.BIN`、`HELLO.S`、`HELLO2.S` などの通常ファイルが出ること。
- `DIR` に hidden、system、volume label、directory、LFN、deleted entryが出ないこと。
- `DIR` にAppleDouble風の `_SDF~*.BIN`、`_HELL~*.S` が出ないこと。
- `DIR` に制御文字や非ASCIIを含む名前entryが出ないこと。
- `RUN KHELL`、`RUN HELLO.HEX`、entryなし/壊れたS-Recordで `?` を表示し、プロンプトへ戻ること。
- 既存の `RUN HELLO.S`、`RUN 0100`、`LOAD`、`EXIT` の回帰を維持すること。

## 対象外

- `TYPE filename`
- FAT write / delete / rename
- subdirectory対応
- AppleDoubleファイル自体をSDから削除する機能
