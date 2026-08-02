# SDFS/68 `RUN filename` 実装計画

## 対象

- Issue: #150
- 親Issue: #140
- 関連: #137, #136, #130, #82

## 背景

`RUN addr` により、SDFS/68から指定アドレスへ直接ジャンプできるようになった。
次はDOSらしい入口として `RUN filename` を追加する。

ただし、Intel HEXは仕様上 start address record を持てるものの、手元のアセンブラが実行アドレスを出さない。
ここでIntel HEXの独自解釈を増やすと、SDFS/68 V1.2としては仕様と実装が重くなる。

## 方針

- `RUN filename` はS-Record専用とする。
- S-Recordの `S9` / `S8` entry recordから16bit entry addressを取得する。
- entry recordが取れた場合だけ、ロード後にそのアドレスへジャンプする。
- Intel HEXは `RUN filename` の対象外とし、`LOAD filename` と `RUN addr` の組み合わせで実行する。
- 壊れたS-Record、entryなし、ファイルなし、Intel HEX指定では `?` を表示して `SDFS> ` へ戻る。
- `LOAD filename` / `L filename` は従来通りロードのみで、自動実行しない。

## 実装メモ

既存のloaderはS-RecordとIntel HEXを同じ入口で読み、終端recordを読むと `A=1` を返している。
今回、S-Recordの `S8` / `S9` を読んだ時だけ `LOADER_ENTRY` と `LOADER_ENTRY_SET` を更新する。

`RUN` は次の順で解釈する。

1. `RUN ` で始まらなければ `?`。
2. 引数が4桁hexなら `RUN addr` として直接ジャンプ。
3. それ以外はファイル名としてロードする。
4. loader modeがS-Recordで、entryが取れていればジャンプ。
5. それ以外は `?`。

## 検証方針

- `RUN HELLO.S` でS-Recordをロードし、entry addressから `HELLO, WORLD` を実行できること。
- Intel HEXを `RUN HELLO.HEX` しても実行せず `?` で戻ること。
- entryなしまたは壊れたS-Recordでハングせず `?` で戻ること。
- `LOAD filename` は従来通り `OK` を出してロードのみであること。
- `RUN addr`、`DIR`、`EXIT` の回帰テストを維持すること。

## 対象外

- Intel HEX start address record対応
- 独自実行ファイル形式
- `FOO` 入力で `FOO.COM` を探すトランジェントコマンド
- ユーザープログラム終了後にSDFS/68へ戻る仕組み
