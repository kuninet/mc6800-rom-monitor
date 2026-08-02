# Issue #261 SDFS/68 v3 BASIC SAVE/LOAD連携方式

## 背景

SDFS/68 v3では、ROMモニタをコマンド入口、SDFS/68をRAM residentのSD/FAT serviceとして扱う。
v2互換機能の最初のゴールは `DIR`、`TYPE`、`LOAD`、`RUN`、`.COM` 相当までであり、BASIC SAVE/LOADとFAT writeはその後の拡張である。

一方で、BASIC連携を後回しにしすぎると、resident API、メモリマップ、FAT writeの境界を誤って固定してしまう。
このIssueでは、BASIC本体改造、ROMモニタコマンド経由、SDFS resident API経由を比較し、最初に実装検討するBASIC候補と機能範囲を決める。

## 前提

- v3 resident APIはstage1 APIとの外部ABI互換を不要とする。
- phase 1の本線は、16KB固定resident frame、または8KB固定resident + 16KB bank window候補で検討する。
- resident本体は8KB以内に抑えることを目標にするが、FAT write、BASIC SAVE、system update実機コマンドまで同居させる前提にはしない。
- system領域更新は固定sector/raw sector writeで扱い、通常のBASIC SAVEやメモリ範囲SAVEとは別機能にする。
- BASIC実装ごとに内部形式、行入力、LIST出力、メモリ上限、I/O入口が異なるため、BASIC固有処理をSDFS resident本体へ混ぜない。

## 既存BASIC候補の状況

| 候補 | 既存判断 | SAVE/LOAD連携上の見立て |
| --- | --- | --- |
| 電大版Tiny BASIC | 最初のBASICソースLOAD候補。`D-BASIC-SBC6800.ASM` があり、MIKBUG互換 `INEEE` / `OUTEEE` を使う | `LOAD` はコンソール入力からテキスト行を読む構造。最初の実装候補にする |
| SWTPC MicroBasic 1.3 | 比較対象に残すが、最初の本線候補ではない | `LIST` はあるが `LOAD` / `SAVE` が見当たらない。共通テキストストリーム支援の確認用に回す |
| MITS Altair 680 BASIC | 浮動小数点BASICの最有力候補 | 低RAMを広く使うため、まずはSDFS/68から起動して制御を渡し切るアプリケーションとして扱う |
| Robert Uiterwyk 4K/8K BASIC | 浮動小数点候補として残す | 入手性、権利、実体ファイル確認が先。v3初期実装対象にはしない |
| Microsoft BASIC-68 / TSC BASIC系 | FLEX依存の整理が先 | FLEX互換または別DOS構想へ回す候補。v3初期実装対象にはしない |

最初に実装検討するBASIC候補は、電大版Tiny BASICにする。
理由は、ローカルにソースがあり、現行ROMモニタのMIKBUG互換I/O入口と相性がよく、`LOAD` がテキスト入力として観察しやすいためである。

候補ごとのI/O入口、メモリ配置、hook可否は次のように整理する。

| 候補 | 根拠文書 | I/O入口 | メモリ/起動位置 | hook/patch可否 |
| --- | --- | --- | --- | --- |
| 電大版Tiny BASIC | `docs/plans/issue-207_dendai_basic_sdfs.md` | `INEEE=$E1AC`、`OUTEEE=$E1D1`。`POLCAA` は `ACIACS=$8018` を直接参照 | `ORG $0100`。BASICプログラム領域 `$0980-$1EFF`、stack `$1F47` / `$1F80` 付近 | `LOAD` が行入力へ入るため、入力stream差し替えadapterの最初の対象にできる。`SAVE` コマンドは見当たらない |
| SWTPC MicroBasic 1.3 | `docs/plans/issue-208_microbasic13_sdfs.md` | `INEEE=$E1AC`、`OUTEEE=$E1D1`。`BREAK` は `PIAD=$8004` 依存 | `ORG $0100`。`MEMEND=$0FFF`、`XSTACK=$1F7F` | `PAT` はROMモニタ復帰入口として使える可能性があるが、`LOAD` / `SAVE` が見当たらないため最初のadapter対象にはしない |
| MITS Altair 680 BASIC | `docs/plans/issue-209_altair680_basic_sdfs.md` | Altair 680B monitor ROM前提に由来し、ローカル資産はSBC6800 MIKBUG向けpatch付き | S-Recordは `$0000` 起点。patch recordは `$1F80` 付近。起動時 `MEMORY SIZE?` 指定が必要 | 低RAMを広く使うため、まずは起動確認とmemtop運用確認を優先する。BASIC内hookは後続 |
| Robert Uiterwyk 4K/8K BASIC | `docs/plans/issue-210_uiterwyk_basic.md` | MIKBUG / MP-C interface依存の確認が必要 | ローカルで即実行できる実体と配置が未確定 | 権利、入手性、実体ファイル確認が先。v3初期hook対象にしない |
| Microsoft BASIC-68 / TSC BASIC系 | `docs/plans/issue-206_basic68_tsc_flex.md` | FLEX/DOS call依存の切り分けが必要 | FLEX上のBASIC候補であり単体ロード可否が未確定 | FLEX互換または別DOS構想へ回す。v3初期hook対象にしない |

## 連携方式の比較

| 方式 | 内容 | 利点 | 問題 | 判断 |
| --- | --- | --- | --- | --- |
| BASIC本体改造 | BASICのコマンド表へ `LOAD` / `SAVE` / `FILES` などを追加し、直接SDFS resident APIを呼ぶ | BASIC上の操作感は最もよい。PC-8001 SD-DOSの未定義命令hookに近い | BASICごとにパッチが必要。8KB resident目標へBASIC固有コードが入り込みやすい | 後続候補。最初から本線にしない |
| ROMモニタコマンド経由 | ROMモニタの `CMD <tail>` からSDFS residentへ処理を投げる | BASICに依存しない。v3 phase 1のv2互換機能と同じ入口を使える | BASIC実行中はROMモニタが入力を握れない。BASIC内コマンドとしての `SAVE` / `LOAD` にはならない | binary `LOAD` / `RUN`、メモリ範囲操作、BASIC起動前後の支援に使う |
| SDFS resident API + BASIC adapter | BASIC固有の小さいadapterまたはpatchが、stream read/writeやmemtop APIを呼ぶ | SDFS本体はFAT/SD serviceに集中できる。BASICごとの内部形式差をadapter側へ隔離できる | adapter ABIと常駐位置の設計が必要。SAVEはwrite API未確定だと完結しない | 採用方針。最初は電大版Tiny BASIC向けLOAD支援から始める |

ROMモニタへ汎用コマンド解釈を寄せる方針は筋がよい。
ただし、ROMモニタだけではBASIC実行中の未定義命令hookにはならない。
BASIC内から `LOAD "file"` のように扱うには、BASIC側のコマンド入口またはI/O入口に小さいadapterを置き、SDFS resident APIへ橋渡しする必要がある。

## 機能ごとの扱い

| 機能 | 初期方針 | FAT write要否 | 補足 |
| --- | --- | --- | --- |
| binary `LOAD` / `RUN` | v3 phase 1のv2互換機能としてROMモニタ `CMD` 経由で扱う | 不要 | BASIC連携ではなく汎用loader機能 |
| BASIC本体のロード/起動 | SDFS/68からS-Record等でロードし、BASICへ制御を渡し切る | 不要 | 電大版Tiny BASICとAltair 680 BASICの確認はこの線から始める |
| BASICテキストLOAD | 電大版Tiny BASIC向けに、SD上テキストをBASIC行入力相当へ供給するadapterを検討する | 不要 | `SDFS3_READ_STREAM_OPEN` / `GETC` / `CLOSE` の外部化候補 |
| BASICテキストSAVE | `LIST` 出力を捕まえてSD上ファイルへ書く設計にする | 必要 | 通常のFATファイルへ保存するなら #83 のFAT writeが前提 |
| BASIC内部形式SAVE/LOAD | 初期対象外 | LOADのみなら不要、SAVEは必要 | BASICごとの内部表現に強く依存するため後回し |
| メモリ範囲SAVE | 後続でROMモニタコマンドとして検討する | 通常ファイルなら必要 | raw scratch領域ならFAT write不要だが、通常のユーザーファイルとは別物 |
| system領域更新 | #258の固定slot更新として扱う | FAT write不要 | BASIC SAVEやメモリ範囲SAVEとは共有しない |

通常のユーザー機能としての `SAVE` は、FAT writeなしでは完結しない。
固定sectorへ一時退避する方式はデバッグ用途としては成立するが、FAT上の名前付きファイルにならないため、BASIC SAVEの最初の到達点にはしない。

## 採用方針

v3のBASIC連携は、SDFS resident API + BASIC adapterを本線にする。

採用する理由:

- ROMモニタはコマンド解釈とresident呼び出しに集中できる。
- SDFS residentはSD/FAT serviceとして共通化でき、BASIC内部形式を知らずに済む。
- BASICごとの差分はadapterへ閉じ込められる。
- 電大版Tiny BASICの `LOAD` のようなテキスト入力型BASICと相性がよい。
- 将来、Altair 680 BASICやMicroBasicを試す場合も、adapter差し替えで評価できる。

最初の実装検討対象:

1. 電大版Tiny BASICをSDFS/68 v3からロードして起動する。
2. SD上のBASICテキストファイルを、電大版Tiny BASICの行入力へ供給する。
3. `SAVE` は実装しないが、`LIST` 出力を将来のwrite streamへ流す設計境界を残す。

## resident APIへの要求

#259のAPI案に対して、BASIC LOAD支援では次を優先する。

| API | 用途 | #261時点の扱い |
| --- | --- | --- |
| `SDFS3_GET_INFO` | resident有無、version、memtop確認 | 必須 |
| `SDFS3_GET_MEMTOP` | BASICへ渡すRAM上限の確認 | 採用候補から必須寄りへ上げる |
| `SDFS3_GET_CAPS` | stream read、write、bank有無などの確認 | 必須寄り |
| `SDFS3_READ_STREAM_OPEN` | BASICテキストファイルを開く | BASIC LOAD実装時に外部化する |
| `SDFS3_READ_STREAM_GETC` | BASIC行入力へ1 byteずつ渡す | BASIC LOAD実装時に外部化する |
| `SDFS3_READ_STREAM_CLOSE` | stream状態を閉じる | BASIC LOAD実装時に外部化する |
| `SDFS3_WRITE_OPEN` / `WRITE_DATA` / `WRITE_CLOSE` | BASIC SAVE / メモリ範囲SAVE | #83のFAT write設計後まで予約に留める |

`SDFS3_LOAD_PATH` は、BASIC本体やbinary fileの一括ロードには有効である。
一方、BASICテキストLOADでは、residentがBASIC行形式を知らない方がよいため、stream read APIをadapterへ渡す構成を優先する。

## メモリ配置への要求

電大版Tiny BASICの既存調査では、BASICプログラム領域は `$0980-$1EFF`、スタックは `$1F47` / `$1F80` 付近である。
v3 residentを `$4000-$7FFF`、`$A000-$BFFF`、`$C000-$DFFF` のいずれに置く場合でも、BASIC側の低RAM範囲と衝突しないことを最初の確認項目にする。

ただし、BASICが `MEMORY SIZE?` 相当の上限指定を持つ場合や、低RAMを広く使うAltair 680 BASICでは、residentのmemtopをそのまま使えない。
`SDFS3_GET_MEMTOP` は「residentが守ってほしい上限」を返すが、BASIC adapter側でBASIC固有の安全上限へ丸める余地を残す。

Bank RAMはBASIC LOADの必須条件にしない。
BASICテキストLOADは小さいstream bufferで成立させ、bank windowはFAT cache、directory cache、SAVE staging、将来のwrite耐性改善に使う。

## 後続Issue案

設計が固まった後、実装Issueは次の単位へ分ける。

1. v3: 電大版Tiny BASICをresident構成からロード/起動する。
2. v3: `SDFS3_READ_STREAM_*` APIを外部化する。
3. v3: 電大版Tiny BASIC向けテキストLOAD adapterを作る。
4. v3: BASIC `LIST` 出力を捕まえるSAVE adapter境界を設計する。
5. v3: FAT write最小実装を #83 から分割する。
6. v3: メモリ範囲SAVEコマンドをROMモニタ経由で実装する。
7. v3: Altair 680 BASIC向けLOAD/SAVE適合性を電大版Tiny BASIC adapterと比較する。

## 判断

v3初期のBASIC SAVE/LOAD連携は、機能互換のphase 1には含めない。
ただし、phase 1のresident APIには、後続BASIC LOADで使う `GET_MEMTOP`、`GET_CAPS`、stream read APIを自然に外部化できる余地を残す。

最初の実装検討は、電大版Tiny BASICのテキストLOAD支援に絞る。
SAVEはFAT write設計が固まるまで通常ファイル保存としては実装しない。
メモリ範囲SAVEもBASIC SAVEとは分け、ROMモニタコマンドとFAT writeの後続Issueとして扱う。

## 対象外

- BASIC本体の移植パッチ実装。
- 電大版Tiny BASIC adapterの実装。
- FAT write実装。
- メモリ範囲SAVE実装。
- Altair 680 BASICやMicroBasic向けadapter実装。

## 関連

- #254: SDFS/68 v3親Issue。
- #255: v3責務境界とv2互換性方針。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
- #205: BASIC候補の整理。
- #83: SAVE/write検討。
