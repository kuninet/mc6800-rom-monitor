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
