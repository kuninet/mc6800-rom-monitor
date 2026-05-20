# Issue #82 SDFS/68 第2段ブート構想整理

## 関連リンク

- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #89: https://github.com/kuninet/mc6800-rom-monitor/issues/89
- Issue #81: https://github.com/kuninet/mc6800-rom-monitor/issues/81
- Issue #85: https://github.com/kuninet/mc6800-rom-monitor/issues/85
- Issue #107: https://github.com/kuninet/mc6800-rom-monitor/issues/107
- Issue #109: https://github.com/kuninet/mc6800-rom-monitor/issues/109

## 方針

第2段システムの名称は **SDFS/68** とし、SD カード上の実ファイル名は `SDFS.BIN` とする。`BOOT` は root の `AUTOEXEC.S` を直接 LOAD するコマンドではなく、SD上の第2段システムを起動する入口として扱う。

当初は **root directory の通常ファイル `SDFS.BIN` をROMが直接読む方式**を本線として整理した。しかし、8KB ROM内でKKBD-USB入力とVDG出力を重視する場合はFAT処理をROMに残す負担が大きい。#107 の評価を受け、現方針は **ROMが固定LBAからstage1 loaderを読み、stage1がFAT rootの `SDFS.BIN` を読む方式**へ寄せる。

`AUTOEXEC.S` は SDFS/68 が起動後に任意で処理する起動スクリプト相当とし、ROM 側 `BOOT` の直接責務には含めない。

責務は次のように分ける。

| 要素 | 責務 |
| --- | --- |
| ROM `BOOT` | 固定LBAからstage1 loaderをRAMへ LOAD/RUNするROM側の最小入口 |
| stage1 loader | FAT32 read-only最小実装でrootの `SDFS.BIN` を読み、boot servicesを公開するRAM常駐コード |
| `SDFS/68` (`SDFS.BIN`) | HEX/S-record ロード、DIR、TYPE、AUTOEXEC.S、将来の周辺機能を持つ第2段 |
| `AUTOEXEC.S` | RTC、VDG、キーボード、BASIC 起動などを行う任意の起動スクリプト |
| `mk-sdfs` | Mac / Windows / Linux で同じ結果を作るシステムSDイメージ生成ツール |
| fixed LBA boot area | stage1 loaderを置く固定領域。ROMはここだけを読む |

ROM容量は8KB互換を前提にすると既に余裕が小さいため、I2C、RTC、EEPROM、OLED/LCD、AUTOEXEC 処理をROMへ常駐させて肥大化させない。これらの周辺機能は、まずRAMロード可能なPoCとして煮詰め、最終的には `SDFS.BIN` または将来の M6800 DOS 相当の第2段機能へ寄せる。

## 方式比較

| 方式 | 位置づけ | 採用条件 |
| --- | --- | --- |
| root 通常ファイル `SDFS.BIN` をROMが読む方式 | 初期検討の履歴 | PCで通常ファイルとして配置できるが、ROMにFAT I/Oが残る |
| FAT32 reserved sector bootstrap | 将来の ROM 削減案 | 専用 SD 作成手順、signature 検査、復旧手順を用意できること |
| 固定物理LBA stage1 boot area | 現方針 | `mk-sdfs` 生成イメージを前提に、ROMからFATを外すこと |
| 外部 MCU 経由 | 将来の性能改善案 | SD/FAT 処理を外部 firmware に逃がす価値が実装コストを上回ること |

## ROM側 `BOOT` の境界

ROM 側には次だけを残す。

- SD 初期化。
- 固定LBAからstage1 loaderを固定RAMアドレスへ読み込む処理。
- stage1 header / signature / size / entry の最小検査。
- 成功時にstage1 entryへジャンプし、失敗時は必ず既存モニタの対話モードへ戻る処理。

ROM 側には次を入れない。

- FAT32 mount。
- root directory から 8.3 名 `SDFS    BIN` を探す処理。
- `SDFS.BIN` を直接読み込む処理。
- `AUTOEXEC.S` 直接処理。
- SDFS/68 シェル。
- サブディレクトリ、LFN、wildcard。
- FAT write / SAVE。
- 画像や大きなデータの direct access API。
- RTC / I2C / OLED / VDG高機能処理。

stage1 loader のロード先は、SBC-IO + VDG では **`$C400-$CFFF`**、K6802-SBC + VDG では **`$A400-$AFFF`** とする。`$C000/$A000` 先頭はsector buffer、`$C200/$A200` 以降はモニタ/stage1ワーク、`$D000-$DEFF` / `$B000-$BEFF` はSDFS/68本体ロード領域、`$DF00-$DFFF` / `$BF00-$BFFF` は当面stack余白として扱う。

stage1 loader には短い header と jump table を置く。初期案は次の最小情報にする。

| offset | 内容 |
| --- | --- |
| `+0` | signature: ASCII `S1API68` |
| `+7` | API version |
| `+8` | API count |
| `+9` | flags |
| `+16` | `jmp S1_INIT` |
| `+19` | `jmp S1_READ_SECTOR` |
| `+22` | `jmp S1_MOUNT` |
| `+25` | `jmp S1_FIND_83` |
| `+28` | `jmp S1_LOAD_FILE_83` |
| `+31` | `jmp S1_GET_ERROR` |

SDFS/68 本体の header は `SDFS.BIN` 側に残す。stage1 は `SDFS.BIN` を読み込んだ後、SDFS/68 signature、entry address、size が許容範囲内かを確認してから制御を渡す。checksum は v1 では必須にせず、必要なら v2 で追加する。

## SDFS/68 の段階

| 段階 | 内容 |
| --- | --- |
| v1 | ROM `BOOT`、stage1 loader、SDFS/68 最小シェル、`LF` 相当の HEX/S-record ロード、SDイメージ生成 |
| v2 | SDFS/68 側 `DIR`、`TYPE`、簡易ファイル情報、`AUTOEXEC.S` 相当 |
| v3 | サブディレクトリ、設定ファイル、I2C/RTC/VDG/キーボード連携 |
| v4 | 画像や固定バイナリデータの direct read API。ファイル全体LOADではなく sector / offset 単位で読む |
| v5 | bit-bang SPI の性能限界が問題になった時点で外部MCUや高速I/O案を再評価 |

v1 の優先機能は HEX / S-record ロードとする。既存 ROM の `DIR` / `LF` はすぐ削除せず、SDFS/68 v1 が通ってから ROM 削減 Issue で扱う。

## システムSDイメージ生成ツール

初期ツール名は `tools/mk_sdfs_image.py` とする。

初期スコープは **FAT32 SDイメージファイル生成**までに限定する。直接SDカードへ書き込む機能は、管理者権限、デバイス指定ミス、OS差分のリスクが大きいため対象外にする。

入力:

- `SDFS.BIN`
- stage1 loader binary
- 任意の `.S`
- 任意の `.HEX`
- 任意の `.BIN`
- 将来の画像や固定データファイル

出力:

- FAT32 形式の SDイメージファイル。
- 固定LBA boot area にstage1 loaderを配置する。
- root directory に `SDFS.BIN` と指定ファイルを 8.3 short filename で配置する。
- テスト用には既存 `tests/sd_fixtures.py` と同じく、小さい決定的イメージを生成できるようにする。

運用:

- Mac / Windows / Linux で同じ Python コードを使う。
- 実SDへの書き込みは、Mac / Linux では `dd` や OS 標準手段、Windows では既存イメージライタを使う手順を文書化する。
- 既存 FAT32 カードへファイルコピーする補助は後続候補にする。

## 後続Issue分割

#82 は設計親 Issue として扱い、実装は次の Issue に分ける。

| 候補 | 内容 | 備考 |
| --- | --- | --- |
| #101 ROM `BOOT` | 固定LBAからstage1を読み、header検査後にstage1へジャンプする | 失敗時は必ず既存モニタへ戻る |
| #102 SDFS/68 v1 | RAM上の第2段として、最小シェルと HEX/S-record ロードを実装する | ROM常駐ではなく `SDFS.BIN` |
| #103 `mk-sdfs` | Python製のシステムSDイメージ生成ツールを追加し、固定LBA stage1とroot `SDFS.BIN` を配置する | 直接SD書き込みは対象外 |
| #104 SDFS/68 data API | 画像/バイナリデータ direct read 用APIを設計する | VDG向けデータ利用を想定 |
| #105 SDFS/68 dirs | サブディレクトリ対応 | v2 以降 |
| #107 固定セクタBOOT評価 | ROMからFATを外す場合の削減効果と運用負荷を評価する | #101 実装前の判断材料 |
| #109 stage1 boot services | stage1常駐API、jump table、profile別配置を設計する | #101/#103/#107の前提を揃える |
| ROM削減 | SDFS/68 v1 が安定した後、ROM側 `DIR` / `LF` の削減を検討する | 互換性を確認してから |

## 検証方針

#82 では設計整理を成果物とし、実装テストは後続 Issue に分ける。後続 PoC では次を確認する。

- 固定LBAにstage1ありで signature 確認後にstage1へジャンプする。
- stage1がroot上の `SDFS.BIN` を読み、SDFS/68 signature確認後に第2段へジャンプする。
- stage1なし、stage1 signature不一致、stage1 read errorで安全に既存モニタへ戻る。
- `SDFS.BIN` なし、SDFS/68 signature不一致、size不正、FAT chain read errorでstage1またはSDFS/68がハングしない。
- SDFS/68 v1 で root 上の `.S` と `.HEX` をロードできる。
- 壊れた HEX、終端なしファイル、存在しないファイルでハングしない。
- `tools/mk_sdfs_image.py` が Mac / Windows / Linux で同一入力から同じ構造の FAT32 イメージを作れる。
- 既存 `test_smoke.py` と `test_sd_fixture.py` を維持する。
