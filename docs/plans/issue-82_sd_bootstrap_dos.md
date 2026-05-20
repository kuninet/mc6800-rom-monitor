# Issue #82 SDFS/68 第2段ブート構想整理

## 関連リンク

- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #89: https://github.com/kuninet/mc6800-rom-monitor/issues/89
- Issue #81: https://github.com/kuninet/mc6800-rom-monitor/issues/81
- Issue #85: https://github.com/kuninet/mc6800-rom-monitor/issues/85
- Issue #107: https://github.com/kuninet/mc6800-rom-monitor/issues/107

## 方針

第2段システムの名称は **SDFS/68** とし、SD カード上の実ファイル名は既存方針どおり `SDFS.BIN` とする。`BOOT` は root の `AUTOEXEC.S` を直接 LOAD するコマンドではなく、root directory の通常ファイル `SDFS.BIN` を RAM へ読み込んで起動する入口として扱う。

初期方式は **root directory の通常ファイル `SDFS.BIN` 起動**を本線として整理した。ただし、8KB ROM内でKKBD-USB入力とVDG出力を重視する場合はFAT処理をROMに残す負担が大きいため、#107 で固定セクタ版SDFS/68 loaderのROM削減効果を評価する。

`AUTOEXEC.S` は SDFS/68 が起動後に任意で処理する起動スクリプト相当とし、ROM 側 `BOOT` の直接責務には含めない。

責務は次のように分ける。

| 要素 | 責務 |
| --- | --- |
| `BOOT` | root の `SDFS.BIN` を探して RAM へ LOAD/RUN するROM側の最小入口 |
| `SDFS/68` (`SDFS.BIN`) | HEX/S-record ロード、DIR、TYPE、AUTOEXEC.S、将来の周辺機能を持つ第2段 |
| `AUTOEXEC.S` | RTC、VDG、キーボード、BASIC 起動などを行う任意の起動スクリプト |
| `mk-sdfs` | Mac / Windows / Linux で同じ結果を作るシステムSDイメージ生成ツール |
| reserved sector bootstrap | 将来の高速/小型ブート候補。初期実装では採らない |

ROM容量は8KB互換を前提にすると既に余裕が小さいため、I2C、RTC、EEPROM、OLED/LCD、AUTOEXEC 処理をROMへ常駐させて肥大化させない。これらの周辺機能は、まずRAMロード可能なPoCとして煮詰め、最終的には `SDFS.BIN` または将来の M6800 DOS 相当の第2段機能へ寄せる。

## 方式比較

| 方式 | 位置づけ | 採用条件 |
| --- | --- | --- |
| root 通常ファイル `SDFS.BIN` 起動 | 初期本線 | PC で通常ファイルとして配置でき、既存 FAT32 read-only 実装を活かせること |
| FAT32 reserved sector bootstrap | 将来の ROM 削減案 | 専用 SD 作成手順、signature 検査、復旧手順を用意できること |
| 固定物理LBA `SDFS.BIN` boot area | ROM 削減案 | `mk-sdfs` 生成イメージを前提に、ROMからFATを外す価値があること |
| 外部 MCU 経由 | 将来の性能改善案 | SD/FAT 処理を外部 firmware に逃がす価値が実装コストを上回ること |

## ROM側 `BOOT` の境界

ROM 側には次だけを残す。

- SD 初期化。
- FAT32 mount。
- root directory から 8.3 名 `SDFS    BIN` を探す処理。
- `SDFS.BIN` を固定RAMアドレスへ読み込む処理。
- SDFS/68 header / signature / size の最小検査。
- 成功時に SDFS/68 entry へジャンプし、失敗時は必ず既存モニタの対話モードへ戻る処理。

ROM 側には次を入れない。

- `AUTOEXEC.S` 直接処理。
- SDFS/68 シェル。
- サブディレクトリ、LFN、wildcard。
- FAT write / SAVE。
- 画像や大きなデータの direct access API。
- RTC / I2C / VDG / キーボードの高機能処理。

`SDFS.BIN` の初期ロード先は SBC-IO 拡張 RAM 前提で **`$C400` 以降**を候補にする。`$C000-$C1FF` は SD sector buffer、`$C200` 以降はモニタ/FATワークの候補があるため、実装Issueでは listing で実際のワーク終端を確認してから最終値を決める。

`SDFS.BIN` には短い header を置く。初期案は次の最小情報にする。

| offset | 内容 |
| --- | --- |
| `+0` | signature: ASCII `SDFS68` |
| `+6` | header version |
| `+7` | flags |
| `+8` | entry address high |
| `+9` | entry address low |
| `+10` | payload size high |
| `+11` | payload size low |

ROM 側は signature、header version、entry address、size が許容範囲内かだけを見る。checksum は v1 では必須にせず、必要なら v2 で追加する。

## SDFS/68 の段階

| 段階 | 内容 |
| --- | --- |
| v1 | ROM `BOOT`、SDFS/68 最小シェル、`LF` 相当の HEX/S-record ロード、SDイメージ生成 |
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
- 任意の `.S`
- 任意の `.HEX`
- 任意の `.BIN`
- 将来の画像や固定データファイル

出力:

- FAT32 形式の SDイメージファイル。
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
| #101 ROM `BOOT` | `SDFS.BIN` を root から読み、header 検査後に第2段へジャンプする | 失敗時は必ず既存モニタへ戻る |
| #102 SDFS/68 v1 | RAM上の第2段として、最小シェルと HEX/S-record ロードを実装する | ROM常駐ではなく `SDFS.BIN` |
| #103 `mk-sdfs` | Python製のシステムSDイメージ生成ツールを追加する | 直接SD書き込みは対象外 |
| #104 SDFS/68 data API | 画像/バイナリデータ direct read 用APIを設計する | VDG向けデータ利用を想定 |
| #105 SDFS/68 dirs | サブディレクトリ対応 | v2 以降 |
| #107 固定セクタBOOT評価 | ROMからFATを外す場合の削減効果と運用負荷を評価する | #101 実装前の判断材料 |
| ROM削減 | SDFS/68 v1 が安定した後、ROM側 `DIR` / `LF` の削減を検討する | 互換性を確認してから |

## 検証方針

#82 では設計整理を成果物とし、実装テストは後続 Issue に分ける。後続 PoC では次を確認する。

- `SDFS.BIN` ありで signature 確認後に第2段へジャンプする。
- `SDFS.BIN` なし、signature 不一致、size 不正、FAT chain read error で安全に既存モニタへ戻る。
- SDFS/68 v1 で root 上の `.S` と `.HEX` をロードできる。
- 壊れた HEX、終端なしファイル、存在しないファイルでハングしない。
- `tools/mk_sdfs_image.py` が Mac / Windows / Linux で同一入力から同じ構造の FAT32 イメージを作れる。
- 既存 `test_smoke.py` と `test_sd_fixture.py` を維持する。
