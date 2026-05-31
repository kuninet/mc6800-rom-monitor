# SDFS/68 `RUN addr` 実装計画

## 対象

- Issue: #149
- 親Issue: #140
- 関連: #137, #136, #130, #82

## 背景

SDFS/68では `LOAD filename` / `L filename` でSD上のS-RecordまたはIntel HEXをロードできるようになった。
ただし実機確認では、ロード後にいったん `EXIT` でROMモニタへ戻り、ROM側の `G addr` で実行する必要がある。

まずは `RUN filename` ではなく、仕様が単純な `RUN addr` を実装する。
`RUN filename` はentry addressの扱い、終端recordが不完全なS-Record、実行後の復帰方針などを別途決める必要があるため、#150で扱う。

## 方針

- `RUN addr` はSDFS/68本体のコマンドとして実装する。
- `addr` は4桁の16bit hexadecimal addressとする。
- parseは既存の `SDFS_PARSE_HEX16` を使う。
- 成功時は `STACK_TOP` を設定し、指定アドレスへ `jmp` する。
- `RUN`、`RUN XYZ`、`RUN 0100 X`、`RUN0100` は `?` を表示して `SDFS> ` へ戻る。
- `RUN filename` は今回実装しない。

## 実装メモ

SDFS/68の内部レイヤは、今回も正式なBIOS/kernel/shell分離までは行わない。
ただしコマンド実装は既存の `SDFS_CMD_*` に置き、文字入力やpromptとは分ける。

今回の `RUN addr` はROMモニタの `G addr` 相当の素朴な入口である。
実行先プログラムがSWIなどでROMモニタへ落ちることはあるが、SDFS/68へ戻る常駐復帰機構は持たない。

## 検証方針

- エミュレータで `LOAD HELLO.S` 後に `RUN 0100` し、`HELLO, WORLD` が表示されることを確認する。
- `RUN`、`RUN XYZ`、`RUN 0100 X`、`RUN0100` が `?` で戻ることを確認する。
- 既存の `DIR`、`LOAD`、`EXIT`、stage1 bootの回帰テストを通す。
- 実機では system SD の `SDFS.BIN` を差し替え、`BOOT` 後に `LOAD HELLO.S`、`RUN 0100` を確認する。

## 対象外

- `RUN filename`
- S-Record / Intel HEX のentry address抽出
- 実行後にSDFS/68へ戻る仕組み
- 低位RAMや高位RAMの新規system予約
