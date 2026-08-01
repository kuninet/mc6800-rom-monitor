# Issue #257 SDFS/68 v3 固定LBA system image形式と1発ロード方式

## 対象

- 親Issue: #254
- 前提Issue: #255、#256
- 本Issue: #257
- 関連Issue: #258、#259、#260

## 背景

現行SDFS/68 v2は、ROMモニタの `BOOT` が固定LBAから `stage1` を読み、`stage1` がFAT rootの `SDFS.BIN` を探してRAMへロードする2段構成である。
この方式は、PC上でFATへ `SDFS.BIN` を置き換えれば更新できるため扱いやすい。
一方で、v3ではROMモニタ側command dispatchからSDFS resident APIを呼ぶ構成へ寄せるため、起動直後に「resident本体とAPI tableが既知の形でRAMに存在する」ことが重要になる。

v3 phase 1 はv2のUI互換ではなく機能互換を目標にする。
そのため、`BOOT -> stage1 -> SDFS.BIN -> SDFS> ` の見た目を維持することより、ROMモニタからresidentを検出し、`DIR`、`TYPE`、`LOAD`、`RUN`、`.COM` 相当を段階的に呼べる導入方式を優先して評価する。

## 比較対象

### 案A: 現行2段ロード継続

```text
ROM BOOT
  -> fixed LBA stage1
    -> FAT root SDFS.BIN
      -> SDFS resident / v2 shell
```

良い点:

- 既存の `stage1`、`mk_sdfs_image.py`、FAT root更新運用を活かせる。
- `SDFS.BIN` をFAT上で差し替えればよく、SD全体の再作成を避けやすい。
- 既存v2の起動経路と近く、移行時の比較がしやすい。

懸念:

- 起動時に `stage1` とSDFS本体の2種類の形式/API互換を管理する必要がある。
- `stage1` がFAT rootを読むため、residentを呼ぶ前からFAT処理の一部へ依存する。
- system本体のheader/API tableをROMが直接検出する構成と噛み合わせるには、`stage1` がv3 headerを正しく配置する責務を追加で持つ。
- 起動失敗箇所が `stage1` 読み込み、FAT mount、root検索、`SDFS.BIN` 読み込み、header検査に分散する。

### 案B: 固定LBA system image一発ロード

```text
ROM BOOT
  -> fixed LBA system image
    -> header検査
      -> SDFS resident entry
```

良い点:

- ROMから見た導入対象が1つのsystem imageにまとまる。
- FAT mount前にresidentを配置できるため、system loaderと通常FAT処理の依存を切りやすい。
- headerにload address、size、entry、API table offsetを持たせることで、ROM側resident検出と起動検査を単純化できる。
- #258のsystem領域更新で、固定sectorだけを書き換える運用へ発展させやすい。

懸念:

- PC側のSDイメージ生成ツールと実機更新手順を作り直す必要がある。
- 固定sector破損時はFAT上の `SDFS.BIN` より人間が目視しにくい。
- system imageの最大sector数、世代管理、更新中断時の復旧設計が必要になる。
- 現行v2の `stage1` をすぐ置き換えると、比較対象と復旧経路を失う。

### 案C: 移行期hybrid

固定LBA system imageをv3本線候補にしつつ、現行2段ロードはv2互換および移行期の比較経路として残す。

```text
v2互換:
  ROM BOOT -> stage1 -> FAT root SDFS.BIN

v3候補:
  ROM BOOTV3 または BOOT拡張
    -> fixed LBA system image
    -> resident header / API table検査
```

本Issueでは案Cを採用候補にする。
実装Issueでは、まず固定LBA system imageを読んでheader検査後にentryへ飛ぶ最小loaderを作り、現行stage1経路は撤去しない。
v3が安定してから、`BOOT` の既定動作を切り替えるか、`BOOT` と別名コマンドにするかを判断する。

### stage1を残す場合と廃止する場合

Issue #257 の判断軸として、stage1の扱いは次のように分ける。

| 方針 | 利点 | リスク |
| --- | --- | --- |
| stage1を残す | v2互換の起動経路を維持できる。FAT上の `SDFS.BIN` 差し替え運用を残せる。固定LBA system imageの実装中も比較と復旧がしやすい。 | `stage1` APIとv3 resident APIの二重管理が残る。起動失敗箇所が増える。ROM dispatchが見るresident headerを `stage1` が正しく配置する責務を追加する必要がある。 |
| stage1を廃止する | ROM loaderからsystem imageへの導入経路が単純になる。FAT mount前にresidentを載せられ、system導入と通常FAT処理を分離しやすい。header/API table検査を一本化できる。 | v2互換の復旧経路を失いやすい。固定sector破損時の復旧とsystem領域更新の設計が必須になる。PC側ツールとSDイメージ作成手順の変更が大きい。 |
| 移行期は残し、後で判断する | 既存v2を壊さずにv3 loaderを検証できる。`BOOT` の既定動作変更を後回しにできる。 | 一時的に起動方式が2系統になり、文書、テスト、SD image fixtureの管理が増える。 |

初期判断では、stage1をすぐ廃止しない。
固定LBA system image loaderを別経路または明示的なv3経路として追加し、v3 resident APIとsystem更新方式が固まった後にstage1廃止可否を再評価する。

## system image形式案

system imageは、先頭sectorの先頭からheaderを置き、その後ろにresident本体を続ける。
ROM loaderは、固定LBAから最小sector数を読んでheaderを検査し、`size` に応じて残りsectorをRAMへ読む。

### header案

| Offset | Size | 項目 | 内容 |
| ---: | ---: | --- | --- |
| `$00` | 8 | `magic` | `SDFS3SYS` |
| `$08` | 1 | `header_version` | header形式のversion。初期値は1 |
| `$09` | 1 | `abi_major` | resident APIの破壊的version |
| `$0A` | 1 | `abi_minor` | resident APIの後方互換追加version |
| `$0B` | 1 | `flags` | checksum方式、圧縮有無、bank利用有無など |
| `$0C` | 2 | `load_address` | resident本体のロード先 |
| `$0E` | 2 | `image_size` | headerを含むbyte数 |
| `$10` | 2 | `entry_offset` | `load_address` からの起動entry offset |
| `$12` | 2 | `api_table_offset` | `load_address` からのAPI table offset |
| `$14` | 2 | `work_min` | residentが最低限要求するwork RAM bytes |
| `$16` | 2 | `bank_window_hint` | bank利用時のwindow開始候補。未使用時は0 |
| `$18` | 2 | `checksum` | headerのchecksum欄を0として計算する16bit checksum候補 |
| `$1A` | 2 | `header_size` | header拡張に備えたbyte数。初期値は32以上 |
| `$1C` | 4 | `reserved` | 将来拡張用。初期値0 |

16bit値はMC6800側の扱いやすさを優先し、上位byte、下位byteの順に固定する。
headerは初期32 bytesを最小とし、`header_size` により将来の拡張を許す。

### checksum方針

初期実装は単純な16bit加算checksumを候補にする。
目的は転送漏れ、sector数間違い、明らかな破損の検出であり、暗号学的な完全性確認ではない。
ROM容量が厳しい場合は、headerのみchecksumから始め、system全体checksumはresident側検査または後続Issueへ回す。
ただし、headerに `image_size` を含める以上、少なくとも「読んだsector数がimage全体を覆うこと」はROM loader側で検査する。

## 固定LBA配置案

固定LBAの具体値は実装Issueで最終決定するが、次の制約を置く。

- LBA 0のMBR有無に依存しない領域にsystem imageを置く。
- FAT partition内の通常ファイル領域とは重ねない。
- PC側ツールが「system領域」と「FATデータ領域」を明示的に分けて生成できるようにする。
- 既存v2の `stage1` 固定LBAと衝突させる場合は、v2互換imageとv3 imageを同時に使えなくなるため、移行期は別LBAを優先する。

初期候補:

| 項目 | 候補 |
| --- | --- |
| `stage1`互換領域 | 現行v2の固定LBAを維持 |
| v3 system image開始 | v2 `stage1` と異なる固定LBA |
| 最大sector数 | 32 sectors / 16KBを初期上限候補 |
| ROM loader最小読み込み | 1 sectorでheader検査後、必要sectorを追加読み込み |

16KB上限は、#260の `$4000-$7FFF` 16KB resident/window案と対応しやすい。
ただし、v3 phase 1で必ず16KBを使い切る前提にはしない。
resident常駐部は小さく保ち、bank RAMやcacheを使う拡張はheader `flags` と #260 のメモリマップ設計で分ける。

## 起動失敗時の復帰経路

ROM loaderは、失敗時にRAM上の不完全residentへ飛ばず、必ずROMモニタの `] ` プロンプトへ戻る。
失敗時は共通 `?` 表示を基本にし、詳細コードはデバッグ用途としてAレジスタまたは直前エラー変数へ残す案を検討する。

失敗分類:

| 分類 | 例 | 復帰 |
| --- | --- | --- |
| SD/sector read失敗 | cardなし、SPI timeout、read error | `?` 表示後 `] ` へ戻る |
| header不正 | magic不一致、header_version非対応 | `?` 表示後 `] ` へ戻る |
| size不正 | 0 bytes、最大sector超過、load範囲外 | `?` 表示後 `] ` へ戻る |
| checksum不一致 | header破損。system全体checksumをROMで実装する場合はimage破損も含む | `?` 表示後 `] ` へ戻る |
| API不整合 | abi_major非対応、api table offset不正 | `?` 表示後 `] ` へ戻る |

ROM loaderがresidentを途中までRAMへ読んだ場合でも、header検査とchecksumが通るまではresident有効フラグを立てない。
ROM command dispatchは、#256の方針どおりresident headerを検出してからjump table経由で呼ぶ。

## PC側ツールへの影響

固定LBA system imageを採る場合、PC側ツールには少なくとも次が必要になる。

- resident binaryからsystem image headerを付与する処理。
- 固定LBAへsystem imageを配置するSD image生成処理。
- FAT領域とsystem領域が重ならないことの検査。
- 実機更新用に、system領域だけを書き換えるデータ生成またはsector書き込み手順。

既存の `mk_sdfs_image.py` を直接拡張するか、v3用ツールを分けるかは実装Issueで決める。
v2互換image生成を壊さないため、初期実装ではv3用のオプションまたは別コマンドとして追加する方が安全である。

## 採用する初期判断

- v3本線候補は固定LBA system image一発ロードとする。
- 現行2段ロードは、v2互換および移行期の比較経路として残す。
- system imageには、magic、version、load address、size、entry、API table offset、checksumを持つheaderを置く。
- 初期最大サイズは16KB相当を候補にし、#260のメモリマップ判断で見直す。
- ROM loaderはFATを読まず、固定LBA sector readとheader検査だけを担当する。
- 起動失敗時はROMモニタへ戻り、不完全residentを有効扱いしない。
- system領域更新、二重化、世代管理、書き込み失敗時復旧は #258 で扱う。

## 後続実装Issueへの分割案

設計が固まった後、次の実装Issueへ分ける。

1. v3 system image header定義とPC側image生成の最小実装。
2. 固定LBA system imageを読むROM loader stubの実装。
3. header検査、size検査、checksum検査の追加。
4. resident header/API table検出を #259 の仕様へ接続する。
5. `CMD <tail>` gatewayから、読み込んだresidentのdispatch stubを呼ぶPoC。
6. system領域更新方式を #258 の設計に従って追加する。

## 対象外

- ROM loader実装。
- `mk_sdfs_image.py` またはv3用image生成ツールの実装。
- 既存stage1の撤去。
- 固定LBAの最終値決定。
- system領域更新、二重化、世代管理の最終仕様。
- resident API最小セットの最終仕様。
- メモリマップとBank RAM利用方針の最終決定。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前の `make test` は、ドキュメントのみの変更として省略できる。
差分確認では、v3設計文書と目次以外のファイルが混ざっていないこと、改行コードを変更していないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #255: v3責務境界とv2互換性方針。
- #256: ROMモニタ側command dispatch設計。
- #258: system領域更新方式。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
- #244: SDFS/68 v2後続検討。
