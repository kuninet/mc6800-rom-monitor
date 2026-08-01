# Issue #255 SDFS/68 v3 責務境界とv2互換性方針

## 対象

- 親Issue: #254
- 本Issue: #255
- 後続設計Issue: #256、#257、#258、#259、#260、#261

## 背景

SDFS/68 v2 では、ROMモニタを救命具と低レベルデバッガとして残し、通常のSDファイル操作を `BOOT -> stage1 -> SDFS.BIN -> SDFS> ` の第2段DOSへ寄せた。
この方針により、`DIR`、`TYPE`、`LOAD`、`RUN`、`EXIT`、`.COM` 実行、V1.3 の明示path指定までを小さいDOSとして整理できた。

一方で、今後 BASIC SAVE/LOAD、メモリ範囲SAVE、FAT write、system領域更新、bank RAM活用などへ進む場合、現行のSDFS/68に独自シェル、コマンド解釈、FAT処理、loader、`.COM`実行をすべて持たせ続ける構成は苦しくなる。
2026-07-15 の #245 後の `make sdfs MONITOR_PROFILE=sbcio_vdg` では、`SDFS.BIN` は 3144 bytes であり、現行の `SDFS_LOAD_LIMIT` 枠 3840 bytes に対する余裕は 696 bytes 程度である。
これは `sbcio_vdg` / `k6802_vdg` / 直接軸指定で常に同じ値になる一般値ではなく、現行8KB級SDFS領域の余裕が小さいことを示す目安として扱う。

PC-8001 SD-DOS は、BASIC側のコマンド入口に乗ることで、DOS側が行入力や汎用コマンド解釈を大きく抱えずにLOAD/SAVEを実現している。
SDFS/68 v3 では、N-BASIC相当の上位入口を MC6800 ROMモニタが担い、SDFS/68をRAM residentのSD/FAT serviceとして扱う構成を検討対象にする。

## v3の位置づけ

SDFS/68 v3 は、v2のコマンドを増やすだけの世代ではなく、ROMモニタとSDFS/68の境界を組み替える互換性破壊を含む設計検討である。

v2までの本線:

```text
] BOOT
ROM reads fixed LBA stage1
stage1 finds FAT root SDFS.BIN
SDFS.BIN starts
SDFS> DIR
SDFS> RUN HELLO.S
SDFS> EXIT
]
```

v3で検討する本線:

```text
ROM monitor prompt
  - command line input
  - command parse / dispatch
  - SDFS resident detection
  - SDFS API call

SDFS resident
  - SD/FAT service
  - candidate file read/write service
  - candidate BASIC SAVE/LOAD support
  - optional system image update candidate
```

v3では、ROMへFAT本体やDOS本体を戻さない。
ROMモニタに寄せるのは、コマンド入口、引数分解、dispatch、共通表示、resident API呼び出しまでを基本とする。
SD/FAT処理、SAVE/write、ファイルI/Oの実処理はRAM上のSDFS residentへ置く。

## 責務分担案

| レイヤ | v3で担う責務 | v3で担わない責務 |
| --- | --- | --- |
| ROMモニタ | 電源投入直後の復旧口、低レベルデバッグ、行入力、コマンド解釈、SDFS resident検出、SDFS API呼び出し、起動失敗時の復帰 | FAT本体、FAT write、directory walk本体、BASIC処理系固有のSAVE/LOAD実体 |
| SDFS resident | SD/FAT service、file open/read/write候補、loader補助、BASIC連携用サービス候補、system領域更新補助候補、必要なwork/buffer管理 | ROMモニタの低レベルデバッグ機能の再実装、独立シェルへの依存 |
| stage1 / system loader | v3 residentをRAMへ載せる初期導入経路。2段ロード継続または固定LBA system image一発ロードの比較対象 | 通常操作のUI、ユーザー向けDOSコマンド |
| BASIC連携層 | BASICテキストSAVE/LOAD、メモリ範囲SAVE、対象BASICごとの入口差分吸収 | 汎用FAT処理の重複実装 |
| PC側ツール | system image生成、SDイメージ生成、必要ならsystem領域更新用データ作成 | 実機での全操作代替 |

この分担は #256、#257、#258、#259、#260、#261 で詳細化する。
本Issueでは、v3でどの方向へ境界を動かすかだけを固定する。

MIKBUG互換の文字I/O固定入口は、v3でもROMモニタ側の互換面として残す。
既存BASICや移植候補が `INEEE`、`OUTEEE`、`OUTCH` などの入口へ依存する可能性があるため、SDFS resident APIとは別の安定入口として扱う。

## v2互換性の扱い

### 残すもの

- ROMモニタの低レベル操作、MIKBUG互換文字I/O入口、`BOOT` 失敗時にROMモニタへ戻れる復旧口。
- SDFS/68 v2の実装とsystem SD生成経路。v3検討中に既存SDFS/68を削除しない。
- `stage1` と `SDFS.BIN` の現行起動経路は、v3の設計が固まるまで旧本線として維持する。
- `.COM` ABI、`RUN`、`LOAD`、`DIR`、`EXIT` の既存仕様は、v2系の仕様として文書上残す。
- ROM常駐FAT `DIR` / `LF` は従来どおり直接指定互換構成の棚に残す。ただしv3本線にはしない。
- BASIC実行後にSDFSへ戻るABIを要求しない方針。既存BASICは制御を渡し切る対象として扱い、SAVE/LOAD連携は別入口で補助する。

### v3で切る可能性が高いもの

- `SDFS> ` 独立シェルを通常操作の唯一の入口にする前提。
- `BOOT -> stage1 -> FAT root SDFS.BIN` を唯一のsystem導入経路にする前提。
- SDFS/68本体が行入力、コマンド解釈、ファイル操作UIをすべて抱える前提。
- stage1 APIを、v3 residentの内部実装と外部ABIの両方に使い続ける前提。
- ユーザーRAM `$0000-$7FFF` を常に最大TPAとして扱う前提。v3のメモリマップではSDFS resident、VRAM、bank windowを含めて再評価する。

### 旧系統として温存するもの

v2系は、現行ハード構成と既存system SDで動く read-only 小型DOSとして温存する。
v3はv2を即時置換するのではなく、別アーキテクチャの検討線として進める。
そのため、v3実装Issueを切るまでは、v2のテスト、ドキュメント、`mk_sdfs_image.py`、stage1/SDFS.BINの生成を壊さない。

## 移行方針

v3の移行は、v2の破壊的変更として一括で入れない。
設計Issueで境界を固めた後、実装Issueは次のような段階へ分ける。

1. ROMモニタ側にresident検出とAPI呼び出し口を追加する。
2. SDFS residentの最小header/API tableだけを定義する。
3. 固定LBA system imageまたは現行stage1経由でresidentを載せるPoCを作る。
4. v2の `SDFS> ` シェルとは別に、ROMモニタ側コマンドからresident APIを呼ぶ。
5. BASIC SAVE/LOADやFAT writeは、resident APIとsystem更新方式が固まってから個別Issueへ分ける。

この段階では、v2の `BOOT` と `SDFS> ` を残したままv3入口を並走させる。
v3が安定してから、v2を互換系統として残すか、利用者向け本線を切り替えるか判断する。

## 後続Issueへの前提

### #256 ROMモニタ側command dispatch

ROMモニタは、v3でN-BASICの未定義命令hookに相当する「上位コマンド入口」の役割を担う候補である。
ここでいう相当は比喩であり、ROMモニタへBASIC風構文、高水準行編集、BASIC処理系の意味解析を載せるという意味ではない。
ただしROM空き容量は標準 `sbcio_vdg` / `k6802_vdg` 構成で約2.7KB程度であり、ROMへ置く処理はコマンド解釈とresident API呼び出しに限定する。
FAT本体やSAVE/write本体をROMへ戻す案は採らない。

### #257 固定LBA system image / 1発ロード

現行2段ロードは更新しやすいが、stage1とSDFS.BINの配置、API互換、失敗時復帰が複雑である。
v3では固定LBA system imageからresidentを一括ロードする案を比較対象にする。
ただし、現行stage1をすぐ撤去するのではなく、継続案と一発ロード案を並べて評価する。

### #258 system領域更新

固定LBA system imageを採る場合、SDカード全体やFAT rootの `SDFS.BIN` を毎回作り直す運用は重い。
v3では、FAT write本体とは独立に、固定sectorを更新対象にできるかを検討する。
固定sector更新も新しい書き込み機能であり、失敗時復旧、世代管理、誤書き込み防止、PC側ツールとの責務分担は #258 で判断する。

### #259 resident API

v3の外部ABIはstage1 APIをそのまま露出するのではなく、SDFS resident APIとして再定義する。
stage1 APIは、v2互換起動や内部実装部品として残す可能性はあるが、ROMモニタやBASIC連携層が直接依存する長期ABIにはしない方向で検討する。

### #260 メモリマップ / Bank RAM

v3では、SDFS residentをどこに固定的に存在させるか、または固定小residentとbank拡張へ分けるかを比較する必要がある。
`$4000-$7FFF` 16KB resident案、`$4000-$7FFF` 16KB bank windowを活かす旧バンクボード案、`$A000/$C000` 8KB bank window案、固定小resident + bank拡張案、bankなし縮退を比較する。
Bank RAMはv3の必須前提にせず、SAVE/writeやcacheを強化する任意拡張として扱えるか確認する。

### #261 BASIC SAVE/LOAD連携

BASIC SAVE/LOADは、SDFS独立シェルへコマンド追加するのではなく、ROMモニタ入口とSDFS resident APIを通じて実現できるかを検討する。
BASIC本体改造、ROMモニタコマンド、resident serviceの分担を分けて評価する。
既存BASICへ最初からSDFS復帰ABIを要求せず、BASIC側の入出力入口、未定義命令相当のhook可否、ROMモニタ経由の補助コマンドを比較する。

## 採用する初期判断

- v3は既存v2の単純な追加機能ではなく、互換性破壊を含む新アーキテクチャ検討とする。
- ROMモニタをv3のコマンド入口として使う方向を本命にする。
- SDFS/68は独立DOSシェルよりも、RAM residentのSD/FAT serviceとして再定義する。
- ROMへFAT本体やSAVE/write本体を戻さない。
- v2の現行起動経路と `SDFS> ` シェルは、v3検討中も旧系統として温存する。
- v3実装Issueは、#256から#261の設計が固まってから分割する。

## 対象外

- v3実装。
- FAT write / SAVE の実装。
- 既存SDFS/68 v2の削除。
- メモリマップの最終決定。
- stage1廃止の決定。
- BASIC本体改造。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前には `make test` を実行し、現行v2系のビルドとテストが壊れていないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #256: ROMモニタ側command dispatch設計。
- #257: 固定LBA system imageと1発ロード方式。
- #258: system領域更新方式。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
- #261: BASIC SAVE/LOAD連携方式。
- #136: 既存のROMモニタとSDFS/68責務境界。
- #137: SDFS/68 v2基本操作ロードマップ。
- #245: stage1 API拡張とSDFS/68 FATコードdedup。
