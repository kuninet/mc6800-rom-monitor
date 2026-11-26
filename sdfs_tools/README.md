# SDFS/68 ツールサンプル

このディレクトリには、SDFS/68 から実行する小さなツールのサンプルを置く。
目的は、従来の S-Record 実行と `.COM` トランジェントコマンド実行の作り分けを Makefile 上で確認できるようにすることである。

## 生成ターゲット

```sh
make sdfs-tools-srec
make sdfs-tools-com
make sdfs-tools
```

生成物は `build/` に出力する。

| 生成物 | 入力ソース | 用途 |
| --- | --- | --- |
| `build/HELLO.S` | `HELLO_S.ASM` | 従来の `RUN HELLO.S` 確認用S-Record |
| `build/HELLO.COM` | `HELLO_COM.ASM` | `.COM` トランジェントコマンドの最小確認 |
| `build/ARGS.COM` | `ARGS_COM.ASM` | `.COM` 引数ABIの確認 |
| `build/LOAD.COM` | `LOAD_COM.ASM`（`XLDR_STUB.INC`） | v3 の `LOAD`。`/BIN` に置く（#316） |
| `build/RUN.COM` | `RUN_COM.ASM`（`XLDR_STUB.INC`） | v3 の `RUN`。`/BIN` に置く（#316） |
| `build/XLDR.OVL` | `XLDR.ASM` | v3 の `LOAD`・`RUN` の本体。`/BIN` に置く（#316） |

`make sdfs-tools-com` は上の `.COM` と `XLDR.OVL` をまとめて作る。どれもプロファイルによらない（`hardware.inc` を使わず、ROM の固定番地と API だけで動く）。

## 形式差分

S-Record サンプルは現行 SDFS/68 の `RUN filename` 用である。
`ORG $0200` で配置し、終了は `SWI` で ROM モニタへ落ちる。

`.COM` サンプルは SDFS/68 のトランジェントコマンド用である。
`ORG $0100` で配置し、終了は `RTS` で SDFS/68 へ戻る。
引数付き `.COM` では、SDFS/68 が `X=引数テール先頭`, `B=引数テール長`, `A=0` で起動する前提にする。

## 実行例

現行の SDFS/68 では、S-Record は次のように実行する。

```text
SDFS> RUN HELLO.S
```

`.COM` は #192 の実装後に次のように実行する想定である。

```text
SDFS> HELLO.COM
SDFS> ARGS.COM AAA BBB
```

## v3 の LOAD・RUN（#316）

v3（`SDFS3> `）では LOAD と RUN は CCP の内蔵ではなく、`/BIN` の `.COM` である。拡張子なしで `LOAD HELLO.S` と打てば、CCP が `LOAD.COM` をルート → `/BIN` の順に探して起動する。

```text
SDFS3> LOAD HELLO.S
OK
SDFS3> RUN HELLO.S
SDFS3> RUN 0200
```

| 部品 | 番地 | 大きさ | 役割 |
| --- | --- | ---: | --- |
| `LOAD.COM`・`RUN.COM` | `$0100-$0188` | 137B | 入口。`BIOS_GET_API` で API を探し、核の `LOAD_PATH` で `/BIN/XLDR.OVL`（なければルートの `XLDR.OVL`）を `$6800` から `GET_MEMTOP` までに読み、署名 `XLDR` を確かめて、A = 1（LOAD）／2（RUN）、X・B = 引数のままで本体へ飛ぶ |
| `XLDR.OVL` | `$6800-$6BBE`（変数は `$6BD8` まで） | 959B | 本体。S-record（S1／S2、S9／S8）と Intel HEX（00／01）を `READ_STREAM_*` で 1 バイトずつ読み、`$0000-$67FF` にだけ書く。`RUN addr` の 16 進の解析も持つ |

- 形式の見分け方: ファイルの最初のレコードの先頭の文字が `S` なら S-record、`:` なら Intel HEX。拡張子は見ないので、拡張子を間違えても読める。途中で形式が変わるファイルは `?`
- 書き込みの範囲: 1 バイトごとに、書く直前に番地の上位バイトが `$68` 未満かを確かめる。`$6800` 以上（本体、CCP、核、窓、I/O、ROM）へのレコードは書かずに `?`。それより前のバイトは書かれたまま残る
- 失敗はどれも `?` を出して `RTS` し、ROM の WBOOT を通って `SDFS3> ` に戻る。本体は `$6C00` の手前に収まるので、通常のイメージでは CCP も核も読み直さない
- 入口は `$0100-$0188` を使うので、`LOAD` してから `RUN addr` で起動するプログラムはこの範囲にかからないように置く（`HELLO.S` の `$0200` は壊れない）。かかるものは `RUN file` で起動するか、`EXIT` してモニタの `G` を使う（#310 の決定 6）
