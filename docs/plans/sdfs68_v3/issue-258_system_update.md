# Issue #258 SDFS/68 v3 system領域更新方式

## 対象

- 親Issue: #254
- 前提Issue: #257
- 本Issue: #258
- 関連Issue: #259、#260

## 背景

#257では、v3の導入方式として固定LBA system image一発ロードを本線候補にした。
この方式では、SDFS resident本体をFAT rootの通常ファイルではなく、SDカード先頭側の予約領域へ固定配置する。
起動時にFAT mountを要求せず、ROM loaderが固定sector readとheader検査だけでresidentを配置できる点が利点である。

一方で、system imageが通常ファイルでなくなるため、更新のために毎回SDカード全体を作り直す運用は重い。
v3では、FAT write本体を実装する前でも、system予約領域だけを書き換える更新方式を検討対象にする。

## 前提

- 現行SD層はSDHC/SDXC block addressing前提であり、旧SDSC 2GBカードは対象外とする。
- v3 phase 1では、4GB以上のSDHCカード上に先頭予約領域と2GB程度のFAT32 partitionを置く構成を目標にする。
- system imageの初期上限は、#257の候補どおり32 sectors / 16KB級とする。
- FAT write本体、directory entry更新、cluster allocationは本Issueの対象外とする。
- system更新は、固定LBA範囲に対するraw sector writeだけで完結できる範囲に限定する。

## 更新方式候補

### 案A: PC側ツールでSD image全体を再生成

PC側でsystem image、FAT partition、利用者ファイルを含むSD imageを生成し、カードへ書き直す。

良い点:

- 実機側に書き込み機能を追加しなくてよい。
- 生成結果をPC上で検証しやすい。
- 更新中断時の実機側破損モードを考えなくてよい。

懸念:

- systemだけ更新したい場合でもカード全体の再書き込みになり、運用が重い。
- 実機だけで更新できない。
- 16GB級カードを使う場合、未使用領域が多くてもイメージ運用が煩雑になる。

### 案B: 単一slotへ固定sector上書き

PCまたは実機から、予約領域内の固定LBAへsystem imageを直接上書きする。

良い点:

- FAT writeなしで実装できる。
- 更新対象が小さく、16KB級なら32 sectors程度で済む。
- PC側ツール、実機側コマンドのどちらにも展開しやすい。

懸念:

- 書き込み途中で電源断するとsystem imageが壊れる。
- 旧imageへ戻る手段がない。
- checksum不一致時の復旧は、外部PCで再書き込みする以外に乏しい。

### 案C: 二重slot + active marker

予約領域にsystem image slotを2つ置き、非active slotへ新imageを書いて検証してからactive markerを切り替える。

```text
reserved area
  slot A: SDFS3SYS image
  slot B: SDFS3SYS image
  active marker / generation
  FAT32 partition
```

良い点:

- 更新途中で失敗しても、旧slotを残せる。
- ROM loaderはactive markerと各slot header/checksumを見て、起動可能なslotを選べる。
- 実機更新でもPC側更新でも同じslot規約を使える。

懸念:

- ROM loaderの検査処理が単一slotより増える。
- 予約領域が2倍以上必要になる。
- active marker更新そのものの失敗に備えた規約が必要になる。

### 案D: FAT上の更新ファイルからsystem slotへinstall

PC側でFAT rootへ `SDFS3.SYS` などを置き、実機側の `INSTALL` / `SYSWRITE` がそれを読んでsystem slotへ書く。

良い点:

- ユーザーはFAT上に更新ファイルを置くだけでよい。
- FAT writeなしでも、FAT readだけで実機更新できる。
- system更新ファイルを通常のPC環境で差し替えやすい。

懸念:

- 実機側にFAT read、system write、検証、slot切り替えをすべて持たせる必要がある。
- 更新対象のresidentを実行中に自分自身のslotへ書く場合、配置とバッファ管理が難しくなる。
- 失敗復旧には案C相当の二重slotがほぼ必要になる。

## 採用する初期判断

v3では、案Cの二重slot + active markerを本線候補にする。
案Aは初期開発と復旧用に残し、案Dは二重slot規約が固まった後の実機更新コマンド候補にする。
案Bの単一slot上書きは実装は小さいが、system領域破損時の復旧性が低いため本線にはしない。

phase 1では、まずPC側ツールで二重slot形式のSD imageを生成し、ROM loaderが有効slotを選ぶところまでを目標にする。
実機側 `INSTALL` / `SYSWRITE` は後続Issueへ分ける。

## slot配置案

固定値は実装Issueで決めるが、初期候補は次の構成にする。

| 項目 | 候補 |
| --- | --- |
| 予約領域 | 先頭1MiB |
| FAT partition開始 | LBA 2048 |
| slot A開始 | 予約領域内の固定LBA |
| slot B開始 | slot Aと重ならない固定LBA |
| slotあたり上限 | 32 sectors / 16KB候補 |
| active marker | 予約領域内の専用sector候補 |

slot内のsystem image headerは #257 の `SDFS3SYS` header案を使う。
active markerは、active slot id、generation、marker checksumを持つ小さいsectorにする候補である。
slotごとのgenerationは、active markerだけでなくslot側にも持たせる。
#257のsystem image header本体へ世代番号を追加するか、slot先頭に小さいslot wrapper headerを置いてから `SDFS3SYS` imageを続けるかは、layout実装Issueで決める。
markerが壊れている場合、ROM loaderはslot A/Bのslot側generation、system header、checksumを見て、generationが新しく検査に通るslotを選ぶ。
slot側generationを持たない形式に縮退する場合は、marker破損時のfallbackをslot A、slot Bの固定順に限定する。

## 更新手順案

二重slotの更新手順は次を基本にする。

1. 現在activeでないslotを選ぶ。
2. 新system imageを非active slotへ全sector書く。
3. 書いたslotを読み戻し、magic、version、size、checksumを検査する。
4. 検査に通った場合だけactive markerを書き換える。
5. active markerを書いた後、markerを読み戻して検査する。
6. 失敗した場合は旧active slotを維持する。

この手順では、system image本体の書き込み失敗はactive marker更新前に検出できる。
active marker更新中に失敗した場合でも、ROM loaderはmarkerだけに依存せずslot A/Bを検査して起動可能slotを選ぶ。

## FAT write本体との関係

system領域更新は、FAT write本体とは独立させる。
固定LBAへraw sector writeできればよく、directory entry更新、FAT chain更新、free cluster探索は不要である。

ただし、FAT上の更新ファイルから実機installする案Dでは、FAT readは必要になる。
この場合でも、実機側がFATへ書き戻す必要はない。
FAT write、BASIC SAVE、メモリ範囲SAVEは、system更新より後の別機能として扱う。

## PC側ツールと実機側の役割

| 役割 | PC側ツール | 実機側 |
| --- | --- | --- |
| 初期SD image生成 | system slot A/B、active marker、FAT partitionを生成する | 不要 |
| system image作成 | resident binaryへheader/checksumを付ける | 原則不要 |
| system更新 | SD imageまたは実カードの非active slotを書き換える | 後続で `INSTALL` / `SYSWRITE` 候補 |
| 検証 | header/checksum/slot重なり/FAT重なりを検査する | 書き込み後の読み戻し検査 |
| 復旧 | 既知良品imageを再書き込みする | 旧active slotまたは有効slotから起動する |

初期実装ではPC側ツールを優先する。
実機側更新コマンドは、SD write primitive、resident API、メモリマップが固まった後に実装Issueへ分ける。

## 失敗時復旧方針

ROM loaderは、active markerだけを信頼しない。
active markerが正しく、指定slotも検査に通る場合はそのslotを使う。
marker不正、指定slot不正、checksum不一致の場合は、slot A/Bを順に検査し、起動可能なslotへfallbackする。
どのslotも起動不能なら `?` を表示してROMモニタへ戻る。

復旧の優先順位:

1. active markerが指すslot。
2. markerが壊れている場合、generationが大きく検査に通るslot。
3. generation比較ができない場合、slot A、slot Bの順。
4. どちらも不正ならROMモニタへ復帰。

## 後続実装Issueへの分割案

1. v3 system image slot layoutとactive marker形式を定義する。
2. PC側ツールで二重slotつきSD imageを生成する。
3. ROM loaderでactive markerとslot header/checksumを検査する。
4. ROM loaderでfallback slot選択を実装する。
5. PC側ツールで非active slotだけ更新するコマンドを追加する。
6. PC側ツールでslot/FAT重なり、slot範囲超過、checksum不一致のfixture検証を追加する。
7. ROM loaderでmarker破損、active slot checksum不一致、非active slot有効、両slot不正のfallback検証を追加する。
8. 実機側 `INSTALL` / `SYSWRITE` を、FAT read + raw sector writeで実装するか判断する。

## 対象外

- system領域書き込み実装。
- SD write primitive実装。
- FAT write実装。
- 実機 `INSTALL` / `SYSWRITE` 実装。
- 固定LBAとmarker形式の最終バイト仕様。
- 実機書き込み確認。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前の `make test` は、ドキュメントのみの変更として省略できる。
差分確認では、v3設計文書と目次以外のファイルが混ざっていないこと、改行コードを変更していないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #257: 固定LBA system image形式と1発ロード方式。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
