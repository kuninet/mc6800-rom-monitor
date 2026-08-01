# Issue #256 SDFS/68 v3 ROM command dispatch / resident API入口設計

## 対象

- 親Issue: #254
- 前提Issue: #255
- 本Issue: #256
- 関連Issue: #257、#259、#261

## 背景

SDFS/68 v3 では、PC-8001 SD-DOS が N-BASIC 側のコマンド入口に乗る構造を参考にする。
ただし MC6800 ROMモニタはBASICではないため、BASIC風の構文処理や高水準行編集をROMへ載せるのではなく、既存の `] ` プロンプト、`READ_LINE`、コマンドdispatchを薄く拡張する。

現行ROMモニタは、`MAIN_LOOP` で1行を読み、先頭文字を中心に `D`、`M`、`G`、`L`、`B`、`R`、`C`、`U`、`H`、`F` などへ分岐する。
現行SDFS/68は、`SDFS> ` で独自に行入力、コマンド解釈、`DIR`、`LOAD`、`RUN`、`.COM` 判定、エラー表示を持つ。

v3 phase 1 の目標は、v2のUI互換ではなく機能互換である。
ROMモニタ側に置くのは、SDFS resident を呼ぶための薄いコマンド入口とし、FAT本体、directory walk、SAVE/write本体はROMへ戻さない。

## 現行ROM空きの目安

2026-08-01 の現行ソースでlisting上の最終実コード直後から `$FFF7` までを数えた。
`make bin` の `.bin` サイズはベクタを含むため全profileで近い値になり、追加余地の判断にはlisting終端を見る。

| 構成 | 最終コード直後 | `$FFF7` までの空き |
| --- | ---: | ---: |
| `base` | `$EF36` | 4290 bytes |
| `sbcio` | `$EF76` | 4226 bytes |
| `sbcio_vdg` | `$F535` | 2755 bytes |
| `k6802_vdg` | `$F543` | 2741 bytes |
| `sbcio + SD + FAT` 互換 | `$FBF2` | 1030 bytes |
| `sbcio + VDG + SD + FAT` 互換 | `$FE22` | 470 bytes |

標準のSDFS本線に近い `sbcio_vdg` / `k6802_vdg` では約2.7KBの余地がある。
これは command gateway、resident検出、API呼び出し口、最小エラー処理には使えるが、FAT本体やSAVE/writeをROMへ戻す余地ではない。

## ROM側が担う範囲

ROM側の責務は次に限定する。

- 既存 `READ_LINE` による1行入力。
- 先頭トークンの最小判定。
- SDFS resident が存在するかの検出。
- resident APIへの引数渡し。
- API失敗時の共通 `?` 表示、またはresidentが出したエラーをそのまま受ける。
- residentがない場合にROMモニタへ安全に戻る。

ROM側は次を担わない。

- FAT mount / directory walk / file open / file read / file write本体。
- 8.3 path parserの詳細。
- S-Record / Intel HEX loaderのSD入力処理。
- BASIC処理系固有のSAVE/LOAD変換。
- `.COM` ABIの詳細処理。
- v2 `SDFS> ` シェル互換。

## コマンド入口案

### 案A: `CMD <subcommand>` 単一gateway

```text
] CMD DIR
] CMD TYPE README.TXT
] CMD LOAD SRC/HELLO.S
] CMD RUN SRC/HELLO.S
] CMD COM BIN/HELLO.COM ARG
```

ROMは `CMD` だけをSDFS系の明示入口として認識し、`CMD` 以降のtailをresidentへ渡す。
resident側が `DIR`、`TYPE`、`LOAD`、`RUN`、`.COM` 相当を解釈する。

良い点:

- ROM側の追加コードが最小になる。
- 既存ROMコマンドとの衝突が少ない。
- phase 1 の機能互換確認に向く。
- 後続でresident側parserを差し替えやすい。

懸念:

- v2の見た目とは離れる。
- `FILES`、`LOAD`、`SAVE` のような直接コマンドより手数が多い。

### 案B: 直接コマンド

```text
] DIR
] TYPE README.TXT
] LOAD SRC/HELLO.S
] RUN SRC/HELLO.S
] FILES
```

ROMが `DIR`、`TYPE`、`LOAD`、`RUN`、`FILES` などを直接認識し、対応するAPI番号またはtailをresidentへ渡す。

良い点:

- 利用者から見て自然。
- SD-DOSの `FILES` などに近い操作感を作りやすい。

懸念:

- ROM側parserが増える。
- 既存 `D` dump、`L` serial load、`R` resume/RAMTEST、`F` fill などと衝突しやすい。
- `LOAD` をROMのシリアル `L` とどう分けるか、`RUN addr` と既存 `G addr` をどう扱うかが曖昧になりやすい。

衝突は、現行ROMの `DIR` / `MAP` / `BOOT` / `RAMTEST` と同じく、長いコマンドを先に判定してから1文字コマンドへ落とす方式で避けられる可能性がある。
たとえば `DIR` は `D` dumpより先、`LOAD ` は `L` serial loadより先、`RUN ` は `R` resumeより先、`FILES` は `F` fillより先に判定する。

### 案C: hybrid

内部ABIは単一のdispatch入口に寄せる。
最小ROM実装では `CMD` gatewayを先に使い、直接コマンドはサイズ確認しながら1本ずつ追加するalias候補として評価する。

```text
] DIR              ; 直接入口候補
] FILES            ; 直接入口候補
] LOAD SRC/HELLO.S ; 直接入口候補
] RUN HELLO.S      ; 直接入口候補
] CMD DIR          ; fallback / 診断用gateway候補
] CMD RUN HELLO.S  ; fallback / 診断用gateway候補
```

本Issueでは案Cを採用候補にする。
実装Issueでは、まず `CMD` gatewayでROMからresidentへtailを渡す経路を確認し、直接コマンドはROMサイズと既存コマンド衝突を見て後続で判断する。
`CMD` gatewayは、直接aliasをすべて入れられない構成でもv2機能互換を確認できる最小入口として扱う。

## resident API呼び出し口案

#259でresident API全体を設計するため、本IssueではROM command dispatchから見える最小入口の要求だけを定義する。

ROMはresident headerを検出し、command dispatch用の1つの入口を呼べればよい。
API slotの最終配置、command id、破壊規約、詳細エラー規約は #259 で決める。
ROM dispatchから見た仮の要求は次に留める。

### `SDFS_CMD_DISPATCH`

目的:

- ROMモニタからSDFS residentへ、ユーザーが入力したSDFS系コマンドを渡す。
- v3 phase 1 の機能互換を最小のROM追加で確認する。

入力:

| レジスタ / 変数 | 内容 |
| --- | --- |
| `A` | command id候補。最小gatewayでは「text tail」相当を渡せればよい |
| `B` | command tail length |
| `X` | command tail pointer。通常は `LINE_BUF` 内のコマンド名直後または `CMD ` 直後 |
| `LINE_BUF` | ROM `READ_LINE` が読んだ元入力行 |

戻り:

| 状態 | 意味 |
| --- | --- |
| carry clear | 正常終了。ROMは次の `] ` プロンプトへ戻る |
| carry set | 失敗。ROMは共通 `?` を出すか、resident側が表示済みであることを示す規約に従う |

破壊:

- `A`、`B`、`X` の破壊規約は #259 で確定する。
- direct page work は #259 でresident側の使用範囲を定義する。

最小gatewayでは、ROMは `CMD` 以降のtext tailをresidentへ渡すだけでよい。
直接aliasを追加する場合は、aliasごとのcommand idを #259 のAPI表に追加する。
ROMサイズが厳しい構成では、text tailだけでv2相当機能を通す縮退を許容する。

## 引数とエラー表示の方針

### 引数

ROMは詳細なpath parserを持たない。
直接入口では、ROMはコマンド名と直後の空白だけを判定し、残りをtailとしてresidentへ渡す。
`CMD` gatewayでは、`CMD` の後ろの空白を1つ以上読み飛ばし、その残りをtailとしてresidentへ渡す。
tail内の大小文字、path、`.COM` 引数、`RUN addr` 判定はresident側が扱う。

空tailはresidentへ渡してもよいが、初期実装ではROM側で `?` を返す方が小さい場合は許容する。
どちらにするかは実装時のサイズで決める。

### エラー

ROM側の共通エラーは既存 `SHOW_ERROR` の `?` + CR を基本にする。
residentが詳細エラーを出す場合は、戻り値で「表示済み」を示すフラグが必要になる。
このフラグ形式は #259 で決める。

エラー分類の候補:

| `A` | 意味 |
| ---: | --- |
| 0 | error none |
| 1 | resident missing |
| 2 | bad command |
| 3 | bad argument |
| 4 | file not found |
| 5 | I/O error |
| `$80` bit | resident側で表示済み |

ROMは、#259で定義される表示済み規約がなければ `SHOW_ERROR` を呼ぶ。
詳細文字列はresident側へ置き、ROM側は肥大化させない。

## resident検出

ROM dispatchは、resident headerのmagic、version、API countを確認してから `SDFS_CMD_DISPATCH` を呼ぶ。
header形式と配置は #259 で決めるが、#256時点では次の制約を置く。

- magicはstage1の `S1API68` とは別名にする。
- versionは破壊的変更時に上げる。
- API countは末尾追加を許す。
- dispatch entryはheaderまたはjump tableから取得し、ROMにresident内部アドレスを直書きしない。

residentが見つからない場合、ROMは `?` を表示して通常の `] ` プロンプトへ戻る。
自動でstage1やsystem loaderを起動するかは #257 の対象にし、本Issueでは決めない。

## ROMサイズへの影響見積もり

内部dispatch入口と最小コマンド入口のROM側追加は、次の範囲に収まることを目標にする。

| 要素 | 概算 |
| --- | ---: |
| `CMD` または直接コマンド判定1本 | 20-50 bytes |
| tail pointer / length作成 | 30-80 bytes |
| resident header検査 | 60-120 bytes |
| jump table経由call | 20-40 bytes |
| error handling | 20-60 bytes |
| 最小合計 | 約150-350 bytes |

直接aliasを追加する場合は、aliasごとに文字列判定とcommand id設定が増える。
初期実装では、標準 `sbcio_vdg` / `k6802_vdg` の約2.7KB空きを使い切らないよう、ROM側追加を500 bytes未満に抑えることを目安にする。

ROM常駐FATを含む互換構成では空きが約1KB以下になるため、v3 command dispatchは `FEATURE_FAT=0` の本線構成を優先して設計する。
`FEATURE_FAT=1` 互換構成でv3 dispatchを同時に有効にするかは、実装時のサイズ確認で決める。

## 採用する初期判断

- ROMからresidentへの入口は、単一のcommand dispatch呼び出し口へ寄せる。
- 最小ROM実装は `CMD <tail>` gatewayを本線にする。
- `DIR`、`FILES`、`LOAD`、`RUN` などの直接コマンドは、ROMサイズを確認しながら1本ずつ追加するalias候補にする。
- ROM側はtailをresidentへ渡し、詳細なpathやファイル形式判定はresident側に置く。
- ROM側はresident headerを検出してjump table経由で呼ぶ。resident内部アドレスは直書きしない。
- ROMはFAT本体、SAVE/write本体、BASIC固有処理を持たない。
- error詳細文字列はresident側へ置き、ROM側は共通 `?` 表示を基本にする。

## 後続実装Issueへの分割案

実装Issueは、#259 のresident APIと #257 の導入方式が固まってから分割する。
仮stubを先行実装する場合も、長期ABIではなくテスト用stubであることを明記する。

分割候補:

1. resident header / command dispatch stubの設計確定後、ROMからの呼び出しでOK/NGを返す最小PoCを作る。
2. ROM側にresident検出と `CMD <tail>` gatewayを追加する。
3. `CMD DIR` 相当でdirectory表示を確認する。
4. `CMD TYPE` / `CMD LOAD` / `CMD RUN` をv2機能互換として段階的に接続する。
5. `.COM` 相当実行をv3 dispatch経由で接続する。
6. `DIR` / `FILES` / `LOAD` / `RUN` などの直接aliasをサイズ確認後に1本ずつ追加するか判断する。

## 対象外

- ROM command dispatch実装。
- resident API全体の最終仕様。
- FAT read/write実装。
- BASIC本体の改造。
- 固定LBA system loaderの実装。
- 直接aliasの採否確定。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前には `make test` を実行し、既存v2系とROMモニタの挙動が壊れていないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #255: v3責務境界とv2互換性方針。
- #257: 固定LBA system image形式と1発ロード方式。
- #259: resident API最小セット。
- #261: BASIC SAVE/LOAD連携方式。
- #177: ROM空き容量の過去整理。
