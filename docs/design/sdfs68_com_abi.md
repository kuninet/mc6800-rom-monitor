# SDFS/68 .COM トランジェントコマンドABI

## 対象

- Issue: #191
- 親Issue: #190
- 実装Issue: #192
- 関連: #157, #137, #136, #82

この文書は、SDFS/68 から SD 上の `.COM` ファイルをトランジェントコマンドとしてロードし、実行後に SDFS/68 へ戻るための最小ABIを定義する。

## 背景

SDFS/68 V1.2では、`DIR`、`LOAD` / `L`、`RUN addr`、`RUN filename`、`EXIT` までが揃った。
`RUN` はロード済みプログラムや S-Record の entry address へ制御を渡す入口であり、現行実装では `jmp 0,x` で実行先へ飛ぶ。
そのため、実行先が戻ることは前提にしていない。

`.COM` はこれとは別に、SDFS/68 管理下の外部コマンドとして扱う。
SDFS/68 が呼び出し元になり、`.COM` 側は `RTS` で SDFS/68 のプロンプトへ戻る。

## 初期スコープ

初期実装では、次だけを対象にする。

- `SDFS> FOO.COM` のように、拡張子 `.COM` まで明示された入力を外部コマンド候補にする。
- `SDFS> FOO.COM AAA BBB` のような引数テールを渡せるようにする。
- root directory 直下の 8.3 short filename を対象にする。
- `.COM` ファイルは header なしの raw binary とする。
- `.COM` は `$0100` 固定ロード、`$0100` 固定エントリとする。
- SDFS/68 は `.COM` を `JSR $0100` 相当で呼び、`.COM` は `RTS` で戻る。

次は対象外とする。

- `FOO` 入力から `FOO.COM` を補完探索する本格トランジェントコマンド探索。
- path 指定つき `.COM` 実行。ただし #157 の path 対応後に拡張できる設計にする。
- `.COM` から呼び出す SDFS/68 ファイルAPI。
- FAT write、SAVE、delete、rename。
- 複数ファイルopen。

## コマンド解釈

SDFS/68 のコマンド解釈順は、次を基本にする。

1. 既存の内蔵コマンドを優先して判定する。
2. 内蔵コマンドに一致しない場合、入力行の先頭トークンを 8.3 filename として解釈する。
3. 先頭トークンの拡張子が `.COM` の場合だけ、トランジェントコマンドとして扱う。
4. `.COM` として検索、ロード、起動できなければ `?` を表示して `SDFS> ` へ戻る。
5. `.COM` 以外の未定義入力は従来どおり `?` を表示する。

初期実装では `FOO.COM` を明示指定する。
`FOO` だけを入力して `FOO.COM` を探す動作は、検索規則と内蔵コマンド優先順位の仕様が増えるため後続Issueへ分ける。

## ファイル形式

`.COM` ファイルは header なしの raw binary とする。
ファイル先頭byteを `$0100` へロードし、以後ファイルサイズ分だけ連続配置する。

| 項目 | 値 |
| --- | --- |
| 拡張子 | `.COM` |
| ファイル形式 | raw binary |
| ロード先頭 | `$0100` |
| エントリ | `$0100` |
| 終了 | `RTS` |

Macro Assembler AS では、`.COM` 用ソースを `$0100` origin で作る。

```asm
        CPU     6800
        ORG     $0100

START   ; command body
        RTS
        END     START
```

生成は概念的には次の流れにする。

```sh
asl -q -L -o FOO.p FOO.ASM
p2bin FOO.p FOO.bin -q
mv FOO.bin FOO.COM
```

## 起動ABI

SDFS/68 は `.COM` 実行直前にスタックを `STACK_TOP` へ設定し、固定エントリ `$0100` をサブルーチンとして呼ぶ。

エントリ時のレジスタ規約は次とする。

| レジスタ | 意味 |
| --- | --- |
| `X` | 引数テール先頭へのポインタ |
| `B` | 引数テール長 |
| `A` | 0 |

引数がない場合、`B=0` とする。
このとき `X` は有効なアドレスを指すが、`.COM` 側は `B=0` の場合に `X` を参照してはならない。

`.COM` 側は、`A`、`B`、`X` を自由に破壊してよい。
SDFS/68 は `.COM` から戻った後、必要な状態を再設定してプロンプトへ戻る。

`.COM` 側は `RTS` で戻るため、スタック上の戻りアドレスを壊してはならない。
一時的にスタックを使う場合も、`RTS` 前に呼び出し時のスタック深さへ戻す必要がある。

## 引数テール

入力例:

```text
SDFS> FOO.COM AAA BBB
```

SDFS/68 は先頭トークン `FOO.COM` をファイル名として扱い、その後ろを引数テールとする。
先頭トークン直後の空白は区切りとして消費し、引数テール先頭は最初の非空白文字にする。
引数テール内部の空白は保持する。

上の例では、`.COM` エントリ時に次の状態になる。

| 値 | 内容 |
| --- | --- |
| `X` | 文字列 `AAA BBB` の先頭 |
| `B` | 7 |

引数テールは SDFS/68 の行入力バッファ上に残る。
`.COM` 実行中は読み取り専用の一時文字列として扱う。
`.COM` が引数を後で使い続けたい場合は、自分のワーク領域へコピーする。

`LINE_BUF_SIZE` は現状 96 byte である。
そのため初期実装では、コマンド名と空白を含む1行全体がこの制限内に収まる範囲だけを扱う。

## ゼロページを予約しない理由

CP/M 風に `$0080` へコマンドテールを置く案もあるが、初期ABIでは採用しない。

MC6800 では direct addressing のため `$0000-$00FF` の利用価値が高く、既存の小プログラムや移植プログラムが自由に使っている可能性がある。
`.COM` 形式は、既存の RAM 実行プログラムを少し直して使える余地を残したい。

そのため、初期ABIでは `$0000-$00FF` を SDFS/68 固定ABI領域として予約しない。
引数は `X` と `B` で渡し、`.COM` 側が必要に応じて自分でコピーする。

## メモリ配置

SDFS/68 が通常対象にする `sbcio_vdg` と `k6802_vdg` では、低RAM `$0000-$7FFF` がユーザー領域であり、SDFS/68 本体と SD/FAT work は別の work RAM 側に置く。

| profile | ユーザーRAM | work RAM | stage1 | SDFS/68 | stack | VDG VRAM |
| --- | --- | --- | --- | --- | --- | --- |
| `sbcio_vdg` | `$0000-$7FFF` | `$C000-$DFFF` | `$C400-$CFFF` | `$D000-$DEFF` | `$DFFF` | `$A000-$BFFF` |
| `k6802_vdg` | `$0000-$7FFF` | `$A000-$BFFF` | `$A400-$AFFF` | `$B000-$BEFF` | `$BFFF` | `$C000-$DFFF` |

`.COM` の初期ロード範囲は `$0100` から `USER_RAM_END` までの連続領域とする。
許容ファイルサイズは `USER_RAM_END - $0100 + 1` byte で判定する。
現行の SDFS/68 対象profileでは `USER_RAM_END=$7FFF` なので、最大サイズは `$7FFF - $0100 + 1 = $7F00`、つまり 32512 byte である。

ただし `.COM` は自身が使う direct page、スタック、MIKBUG互換ワーク、既存プログラムの作業領域を自分で管理する必要がある。
SDFS/68 は初期実装では `.COM` が低RAM内のどの領域を使うかまでは保護しない。

## SDFS/68本体サイズ

2026-06-05 時点の `main` 由来ビルドでは、`make sdfs MONITOR_PROFILE=sbcio_vdg` と `make sdfs MONITOR_PROFILE=k6802_vdg` の `SDFS.BIN` はどちらも 2714 byte である。

`SDFS_LOAD_BASE` から `SDFS_LOAD_LIMIT` までの枠は 3840 byte なので、現時点の余裕は 1126 byte である。
`.COM` 対応は SDFS/68 本体を肥大化させすぎないよう、初期実装を次に限定する。

- 先頭トークン `.COM` 判定。
- 8.3 root filename 検索。
- raw binary の `$0100` への読み込み。
- `X` / `B` / `A` のエントリレジスタ設定。
- `JSR $0100` と `RTS` 復帰後のプロンプト表示。

## `RUN` との差分

`RUN addr` と `RUN filename` は、従来どおり `JMP` 実行のままにする。
`RUN` は ROM モニタの `G addr` 相当であり、実行先から SDFS/68 へ戻る保証はない。

`.COM` は SDFS/68 のトランジェントコマンドであり、`RTS` で戻ることをABIとして要求する。
戻りたいプログラムは `.COM`、制御を明け渡すプログラムや既存S-Record資産は `RUN`、という分担にする。

`SWI` は ROM モニタのブレーク、非常脱出、デバッグ用途として残す。
`.COM` の正常終了には使わない。

## エラー処理

初期実装では、次の場合に `?` を表示して `SDFS> ` へ戻る。

- 先頭トークンが 8.3 filename として不正。
- 拡張子が `.COM` ではない未定義コマンド。
- `.COM` ファイルが見つからない。
- `.COM` ファイルサイズが 0 byte。
- `.COM` ファイルサイズが `USER_RAM_END - $0100 + 1` byte に収まらない。
- FAT chain 読み込みや SD 読み込みで失敗した。

`.COM` 実行後に `RTS` で戻った場合は、正常復帰として `SDFS> ` プロンプトへ戻る。
`.COM` が `SWI` した場合は ROM モニタ側へ落ちるため、SDFS/68 へ戻る保証はない。

## 実装方針

実装Issue #192 では、既存の `SDFS_COMMAND_ERROR` へ落ちる直前に `.COM` 候補判定を追加する。
内蔵コマンドの優先順位は変えない。

既存の `SDFS_K_LOAD_FILE` は S-Record / Intel HEX parser を通すため、raw binary `.COM` には使わない。
実装では、既存の FAT stream 処理を使い、ファイル内容をそのまま `$0100` 以降へコピーする `.COM` 専用ロード経路を追加する。

`S1_LOAD_FILE_83` は `SDFS_LOAD_BASE` へロードする boot service なので、常駐中の SDFS/68 からは呼ばない。
これは SDFS/68 本体を自己上書きするためである。

## 検証方針

実装Issue #192 では、少なくとも次を確認する。

- `SDFS> HELLO.COM` で `.COM` が実行され、`RTS` で `SDFS> ` へ戻る。
- `SDFS> ARGS.COM AAA BBB` で、`.COM` 側が `X` / `B` から `AAA BBB` を読める。
- 存在しない `NOFILE.COM` で `?` を表示して戻る。
- `.COM` 以外の未定義入力は従来どおり `?` を表示する。
- `RUN HELLO.S`、`RUN addr`、`LOAD filename`、`DIR`、`EXIT` の既存動作を維持する。
- `make sdfs MONITOR_PROFILE=sbcio_vdg` と `make sdfs MONITOR_PROFILE=k6802_vdg` で `SDFS_LOAD_LIMIT` を超えない。

## 関連ドキュメント

- [sdfs68_system_sd.md](../usage/sdfs68_system_sd.md): SDFS/68 の利用方針と現行コマンド。
- [memory_map.md](memory_map.md): RAM / ROM / I/O の基本配置。
- [issue-sdfs68_v2_roadmap.md](../plans/issue-sdfs68_v2_roadmap.md): `RUN` / `LOAD` / `EXIT` までの基本操作ロードマップ。
- [issue-130_sdfs68_loader.md](../plans/issue-130_sdfs68_loader.md): SDFS/68 loader の前提。
- [issue-149_sdfs68_run_addr.md](../plans/issue-149_sdfs68_run_addr.md): `RUN addr`。
- [issue-150_sdfs68_run_file.md](../plans/issue-150_sdfs68_run_file.md): `RUN filename`。
