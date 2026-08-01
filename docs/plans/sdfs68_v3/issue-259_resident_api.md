# Issue #259 SDFS/68 v3 resident API最小セット

## 対象

- 親Issue: #254
- 前提Issue: #256、#257、#258
- 本Issue: #259
- 関連Issue: #260、#261
- 関連Issue: #245

## 背景

SDFS/68 v3では、SDFSを独立シェルではなくRAM residentのSD/FAT serviceとして扱う。
ROMモニタは #256 の方針どおり、行入力、最小dispatch、resident検出、API呼び出しを担う。
resident本体は #257 の固定LBA system imageでRAMへ配置され、#258 のsystem slot更新方式に従って更新される候補である。

v3 phase 1の目標は、v2のUI互換ではなく機能互換である。
そのため、resident APIは最初からPOSIX風の汎用ファイルAPIを広く定義するのではなく、ROM dispatch、system loader、後続のBASIC連携が実際に依存する最小入口に絞る。

## 現行stage1 APIとの関係

現行v2では、`stage1` が `S1API68` headerとjump tableを持つ。
`SDFS.BIN` は `S1_BASE` のmagic、version、API countを確認したうえで、次のようなstage1 APIを直接呼んでいる。

| stage1 API | 現行用途 |
| --- | --- |
| `S1_INIT` | SD初期化 |
| `S1_READ_SECTOR` | raw sector read |
| `S1_MOUNT` | FAT32 mount |
| `S1_FIND_83` | 8.3 filename検索 |
| `S1_LOAD_FILE_83` | `SDFS.BIN` 起動時ロード |
| `S1_GET_ERROR` | エラー取得 |
| `S1_STREAM_OPEN` / `S1_STREAM_GETC` / `S1_STREAM_BYTES_REMAIN` | stream read |
| `S1_CLUSTER_TO_SD_LBA` / `S1_NEXT_CLUSTER` / `S1_COPY_NEXT_TO_CUR` | FAT chain補助 |

v3では、stage1 APIとの外部ABI互換性は不要と判断する。
stage1 APIを長期の外部ABIとしては直接使わない。
stage1 APIはv2互換起動やresident内部の実装部品として残してよいが、ROMモニタ、BASIC連携層、system loaderが依存する入口はSDFS resident APIとして再定義する。
v3 residentが内部で既存stage1実装を再利用する場合も、外部からはSDFS resident APIだけを見せ、stage1 APIとの差分はresident内部adapterで吸収する。

理由:

- stage1 APIはv2 boot loaderの都合を含み、resident常駐後の外部ABIとして粒度が細かすぎる。
- `S1_LOAD_FILE_83` は `SDFS_LOAD_BASE` へ読み込む前提を持ち、resident実行中に外部から呼ぶと自己破壊になりうる。
- FAT chain補助APIを外部へ露出すると、ROM/BASIC側がFAT内部状態へ依存してしまう。
- v3では2GB級FAT目標、bank有無、BASIC SAVE/LOADなどの後続変更をresident内部で吸収したい。

この判断により、v3実装Issueでは `S1API68` のjump table slot番号、破壊規約、`S1_LOAD_FILE_83` のロード先制約を守る必要はない。
互換性を残す対象は、v2の既存起動経路と既存SDFS/68の動作であり、v3 resident APIそのものではない。

## resident header案

resident system image headerとは別に、RAM上のresident API headerを定義する。
ROMモニタとBASIC連携層は、固定アドレスを直接呼ばず、resident headerとjump tableを検査してから呼ぶ。

| Offset | Size | 項目 | 内容 |
| ---: | ---: | --- | --- |
| `$00` | 8 | `magic` | `SDFS3API` |
| `$08` | 1 | `api_major` | 破壊的変更時に上げる |
| `$09` | 1 | `api_minor` | 後方互換のAPI追加時に上げる |
| `$0A` | 1 | `api_count` | jump table entry数 |
| `$0B` | 1 | `flags` | bank対応、write対応、BASIC補助対応など |
| `$0C` | 2 | `jump_table` | resident API jump table address |
| `$0E` | 2 | `work_base` | residentが占有または要求するwork領域開始 |
| `$10` | 2 | `work_end` | residentが占有または要求するwork領域終端 |
| `$12` | 2 | `memtop` | ユーザーが安全に使える上限候補 |
| `$14` | 2 | `scratch_min` | 呼び出し側が一時提供すべきscratch bytes。不要なら0 |
| `$16` | 2 | `reserved` | 将来拡張 |

初期実装では、resident API headerの配置は #260 のメモリマップで決める。
ROM側は `magic`、`api_major`、`api_count` を検査し、必要slotが存在しない場合は `?` を返してROMモニタへ戻る。

検出起点の初期方針は次にする。

- system loaderは、#257のsystem image headerにある `api_table_offset` からresident API headerまたはAPI tableへ辿る。
- resident entryは初期化成功後、#260で決める固定候補アドレスまたはROM work変数へresident API header addressを公開する。
- ROMモニタとBASIC連携層は、公開されたAPI header addressを優先して検査する。
- 公開先が未初期化の場合だけ、#260で決める固定候補アドレスを走査する。

この方針により、API headerの最終配置は #260 で決めつつ、ROM dispatch実装Issueでは検出手順を先に書ける。

## API分類

resident APIは、外部に見せるAPIとresident内部APIを分ける。

| 分類 | 対象 | 方針 |
| --- | --- | --- |
| 外部安定API | ROM command dispatch、system loader、BASIC連携層が呼ぶ入口 | version管理対象 |
| resident内部API | FAT mount、cluster chain、sector cache、path parser | 外部ABIにしない |
| debug / bring-up API | raw sector read、エラー詳細取得、状態dump | 初期PoCでは使ってよいが長期必須ABIにしない |

この分け方により、v3 phase 1で必要な機能互換を保ちながら、後続でFAT write、32bit cluster、bank cacheを追加しやすくする。

## 最小API案

### 外部安定API

| Slot | API | 呼び出し元 | 初期採否 | 目的 |
| ---: | --- | --- | --- | --- |
| 0 | `SDFS3_GET_INFO` | ROM / BASIC | 採用 | resident version、flags、memtop、capability取得 |
| 1 | `SDFS3_CMD_DISPATCH` | ROM | 採用 | #256 の `CMD <tail>` gateway。v2相当機能を文字列tailで呼ぶ |
| 2 | `SDFS3_LOAD_PATH` | ROM / BASIC候補 | 採用候補 | pathを指定してメモリへロード。S-Record/Intel HEX/COMの扱いは引数で指定候補 |
| 3 | `SDFS3_READ_STREAM_OPEN` | BASIC候補 / resident内部候補 | 保留 | BASIC LOADやTYPEで必要なら外部化 |
| 4 | `SDFS3_READ_STREAM_GETC` | BASIC候補 / resident内部候補 | 保留 | 1byte stream read |
| 5 | `SDFS3_READ_STREAM_CLOSE` | BASIC候補 / resident内部候補 | 保留 | stream状態解放 |
| 6 | `SDFS3_GET_ERROR` | ROM / BASIC | 採用 | 直前エラーコード取得 |
| 7 | `SDFS3_GET_MEMTOP` | ROM / BASIC | 採用候補 | resident常駐後のユーザーRAM上限取得 |
| 8 | `SDFS3_GET_CAPS` | ROM / BASIC | 採用候補 | bank有無、write可否、2GB FAT目標などのcapability bit取得 |
| 9 | `SDFS3_SYS_UPDATE` | resident更新コマンド候補 | 後続 | #258 のsystem slot更新 |
| 10 | `SDFS3_WRITE_OPEN` | BASIC SAVE候補 | 後続 | FAT write / SAVEが固まるまで保留 |
| 11 | `SDFS3_WRITE_DATA` | BASIC SAVE候補 | 後続 | 同上 |
| 12 | `SDFS3_WRITE_CLOSE` | BASIC SAVE候補 | 後続 | 同上 |

phase 1で必須にするのは、`GET_INFO`、`CMD_DISPATCH`、`GET_ERROR` を最小とする。
`LOAD_PATH`、`GET_MEMTOP`、`GET_CAPS` は早期に欲しいが、最初のstubでは未実装を返してよい。
stream readはBASIC連携やTYPE実装の方式次第で外部化する。
write系とsystem updateはAPI番号の予約だけに留め、初期実装では未実装を返す。

### resident内部に隠すAPI

次は外部安定APIにしない。

- FAT32 mount。
- FAT32 open / find 8.3 / path parser。
- raw SD sector read/write。
- FAT cluster to LBA計算。
- FAT next cluster取得。
- sector cache操作。
- stage1 API wrapper。

ROM側はこれらを直接呼ばない。
BASIC連携層も、ファイル単位またはstream単位のresident APIへ依存し、FAT内部状態へ依存しない。

## 呼び出し規約案

MC6800で小さく実装するため、初期規約は単純にする。

### 共通

| 項目 | 規約 |
| --- | --- |
| 成功 | carry clear |
| 失敗 | carry set |
| エラー詳細 | `A` に短いエラーコード、必要なら `SDFS3_GET_ERROR` で詳細取得 |
| 破壊レジスタ | 原則 `A`、`B`、`X` は破壊可 |
| stack | 呼び出し元stackを使う。深い再帰や大きい退避はしない |
| direct page | residentが使う範囲は #260 で定義し、呼び出し側へ明示する |
| 再入性 | なし。同時呼び出し、割り込み中呼び出し、nested callは非対応 |

ROMモニタからの呼び出しでは、`LINE_BUF` とtail pointerを渡す。
resident側はtailを必要なら自分のworkへコピーしてよい。
呼び出し後、ROMは常に `] ` プロンプトへ戻れることを前提にする。

### `SDFS3_CMD_DISPATCH`

目的:

- ROMモニタの `CMD <tail>` gatewayからv3 residentへコマンド文字列を渡す。
- phase 1のv2機能互換を最小ROM追加で確認する。

入力:

| レジスタ / 変数 | 内容 |
| --- | --- |
| `X` | command tail pointer |
| `B` | command tail length |
| `A` | 0。将来、直接aliasからのcommand idに使う候補 |
| `LINE_BUF` | 元入力行。residentが必要なら参照してよい |

戻り:

| 状態 | 内容 |
| --- | --- |
| carry clear | 処理成功 |
| carry set | 失敗。`A` に短いエラーコード |

エラー表示はresident側で詳細を出してもよい。
residentが表示済みの場合、エラーコードの上位bitなどで「表示済み」を示す規約を後続実装で決める。

### `SDFS3_GET_INFO`

目的:

- ROM/BASIC側がresidentのversion、capability、memtopを取得する。

入力:

- なし。

戻り候補:

| レジスタ | 内容 |
| --- | --- |
| `A` | `api_major` |
| `B` | flagsまたはcapability low |
| `X` | resident API header address |

詳細なcapabilityが必要な場合は、`SDFS3_GET_CAPS` を使う。

### `SDFS3_LOAD_PATH`

目的:

- ROMまたはBASIC連携層から、pathで指定したファイルを指定先へロードする。

入力候補:

| レジスタ / 変数 | 内容 |
| --- | --- |
| `X` | path pointer |
| `B` | path length |
| `A` | load mode。raw / S-Record / Intel HEX / COM / auto判定候補 |
| work変数 | load destination、entry取得先などは #260 / 実装Issueで定義 |

初期実装では、既存v2相当の `LOAD` / `RUN` / `.COM` は `CMD_DISPATCH` 内部で処理してよい。
`LOAD_PATH` はBASIC連携や直接aliasを小さくするための候補として予約する。

## memtop / bank / capability

v3ではresident常駐により、ユーザーが使えるRAM上限が構成ごとに変わる。
ROM/BASIC側は固定値を持たず、resident APIから問い合わせる。

capability候補:

| bit | 意味 |
| ---: | --- |
| 0 | FAT read利用可能 |
| 1 | stream read API利用可能 |
| 2 | file load API利用可能 |
| 3 | raw SD read debug API利用可能 |
| 4 | raw SD write / system update候補利用可能 |
| 5 | FAT write利用可能 |
| 6 | bank RAM利用可能 |
| 7 | BASIC SAVE/LOAD補助利用可能 |

2GB級FAT32 partition対応は、現行16bit cluster制約と32KB/cluster前提をドキュメント上の目標にする。
32bit cluster対応や8GB/16GB全域利用は、capability拡張またはAPI major更新を伴う後続Issueで扱う。

## ROMモニタから見た呼び出し

ROMモニタは次だけを知ればよい。

1. resident headerの場所候補。
2. `SDFS3API` magic、`api_major`、`api_count` の検査方法。
3. `CMD_DISPATCH` slot番号。
4. 成功/失敗のcarry規約。
5. resident不在時に `?` を出して `] ` へ戻ること。

ROMはFAT mount、path parser、cluster処理、SAVE/write本体を持たない。
直接aliasを追加する場合も、ROMはalias名を判定してtailまたはcommand idをresidentへ渡すだけにする。

## BASIC連携から見た呼び出し

BASIC連携層は #261 で詳細化する。
#259時点では、BASIC側から見た要求を次に留める。

- phase 1では、BASIC連携層は `SDFS3_GET_INFO`、`SDFS3_GET_MEMTOP`、必要なら `SDFS3_GET_CAPS` を使う。
- BASIC LOAD系は、`SDFS3_LOAD_PATH` で一括ロードするか、`SDFS3_READ_STREAM_OPEN` / `GETC` / `CLOSE` でBASIC側が解釈するかを #261 で選ぶ。
- BASIC SAVE系は、write系API slotを予約するだけで、#259時点では実装前提にしない。
- BASIC SAVE/LOADが必要とするmemtopを問い合わせられること。
- BASICのテキスト/バイナリ形式変換はBASIC連携層またはresident側のどちらに置くか #261 で決めること。
- FAT内部APIではなく、file load、stream read、将来write APIへ依存すること。
- BASIC実行後にSDFS独立シェルへ戻る前提を要求しないこと。

## system loaderから見た呼び出し

system loaderは、residentをRAMへ配置し、system image headerとresident API headerを検査する。
loaderが必要とするAPIは、起動直後のself-testまたは初期化entryに限定する。

初期候補:

- resident entryを呼ぶ。
- resident entryは、#257のsystem image headerの `entry_offset` から呼ぶ初期化入口であり、resident API jump table slotには含めない。
- resident entryは内部初期化後、resident API headerを有効化する。
- loaderは必要なら `GET_INFO` 相当でversionとcapabilityを確認する。
- loaderは通常FAT操作APIを呼ばない。

#258のslot fallbackはloader側の責務であり、resident APIの通常呼び出しとは分ける。
起動後にROM/BASICが使う入口は、resident entryではなく `SDFS3API` headerとjump tableである。

## 後続実装Issueへの分割案

1. resident API headerとjump tableの定数を定義する。
2. `GET_INFO`、`GET_ERROR`、`CMD_DISPATCH` stubを持つresident最小imageを作る。
3. ROM側からresident headerを検出し、`CMD <tail>` でstubを呼ぶ。
4. `CMD DIR`、`CMD TYPE`、`CMD LOAD`、`CMD RUN` を既存v2機能互換として段階的に接続する。
5. `GET_MEMTOP` / `GET_CAPS` を #260 のメモリマップ決定後に実装する。
6. stream read APIを #261 BASIC LOAD/TEXT連携の判断に合わせて外部化する。
7. write系APIと `SYS_UPDATE` は、SD write primitive、FAT write、system slot更新の実装Issueへ分ける。

## 対象外

- resident API実装。
- ROM command dispatch実装。
- FAT write実装。
- BASIC SAVE/LOAD実装。
- メモリマップとdirect page割り当ての最終決定。
- 32bit cluster対応。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前の `make test` は、ドキュメントのみの変更として省略できる。
差分確認では、v3設計文書と目次以外のファイルが混ざっていないこと、改行コードを変更していないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #256: ROMモニタ側command dispatch設計。
- #257: 固定LBA system image形式と1発ロード方式。
- #258: system領域更新方式。
- #260: メモリマップとBank RAM利用方針。
- #261: BASIC SAVE/LOAD連携方式。
- #245: stage1 API拡張とSDFS/68 FATコードdedup。
