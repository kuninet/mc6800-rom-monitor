# Issue #107 固定セクタ版 SDFS/68 loader ROM削減評価

## 関連リンク

- Issue #107: https://github.com/kuninet/mc6800-rom-monitor/issues/107
- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #101: https://github.com/kuninet/mc6800-rom-monitor/issues/101
- Issue #103: https://github.com/kuninet/mc6800-rom-monitor/issues/103

## 結論

スタンドアロン機として **KKBD-USB入力 + VDG出力 + UART fallback** をROM側の主役にするなら、SDFS/68 boot は FAT版より固定セクタ版を本線にする価値が高い。

現行の `FEATURE_SD=1` は、SD sector read だけでなく FAT32 mount、root directory scan、cluster chain、`DIR`、`LF` までROMに含める。listing で見ると、KBD+VDGのみ構成から KBD+VDG+現行SD/FAT構成への増分は約 **2.9KB** ある。8KB ROMでこの増分は大きく、VDGコンソールやKKBD-USB入力の常駐余地を圧迫する。

今後の方針は、ROM側を **raw SD sector boot + SDFS/68 header確認 + fallback** に寄せ、FAT操作はSDFS/68側へ逃がすのがよい。

## 試算

`build/*.bin` は固定ベクタまで含むため、構成差の見積りには使わない。ここでは listing の実質コード終端を見る。`build/monitor_config.inc` は共有されるため、構成別ビルドは逐次実行した。

| 構成 | 確認コマンド | 実質コード終端 | 備考 |
| --- | --- | --- | --- |
| KBD+VDGのみ | `make bin MEMORY_CONFIG=ram64_c000_work BOARD_IO=sbcio FEATURE_SD=0 FEATURE_VDG=1 FEATURE_KEYBOARD=1 FEATURE_I2C=0 VDG_VRAM_CONFIG=a000 BUILD_CONFIG_NAME=sbcio-vdg-nosd ROM_CODE_LIMIT=20000` | `F13F` | `acia6850.asm` 終端直後 |
| KBD+VDG+現行SD/FAT | `make bin MONITOR_PROFILE=sbcio_vdg ROM_CODE_LIMIT=20000` | `FC8A` | `fat32.asm` 終端直後 |

差分は `FC8A - F13F = 0x0B4B`、約 **2891 bytes**。

現行SD/FAT構成の内訳の目安:

| 範囲 | 内容 | 目安 |
| --- | --- | --- |
| `F3BC` - `F640` | `SD_INIT`、`SD_READ_SECTOR`、bit-bang SPI | 約644 bytes |
| `F640` - `FC8A` | FAT32 mount、8.3検索、file read、cluster chain | 約1610 bytes |
| 先行部の増分 | `DIR` / `LF` 連携、FAT loader入力、表示補助など | 約637 bytes |

raw固定セクタBOOTは、SD初期化とsector readの下回りを残すため、SD部分をゼロにはできない。ただし FAT32処理、root検索、cluster chain、`DIR`、`LF` をROMから外せるため、現行SD/FAT構成から **おおむね2KB前後** のROM削減余地がある。

実際の固定セクタBOOTでは、連続sector load、SDFS/68 header確認、entry range確認、fallback表示が追加されるため、raw SD readだけとの差分は増える。それでもFAT版BOOTより小さくなる見込みが高い。

## 方式比較

| 方式 | ROM量 | SD作成負荷 | 復旧性 | 評価 |
| --- | --- | --- | --- | --- |
| FAT版BOOT | 大きい | 低い。rootへ `SDFS.BIN` を置ける | FATが読めないと起動不可 | 開発初期は楽だが、8KB ROMでは重い |
| 固定物理LBA版BOOT | 小さい | 高い。`mk-sdfs` 生成イメージ必須 | FATが壊れても固定boot areaが読めれば起動可能 | スタンドアロン機の本線候補 |
| FAT32 reserved sector版BOOT | 中程度 | 中から高。FAT32 layout確認が必要 | reserved regionが壊れると起動不可 | 説明はしやすいが、ROM側検査が増えやすい |

## 推奨仕様

固定セクタ版の初期候補は **固定物理LBA版** とする。

- `mk-sdfs` 生成イメージでは、MBR partitionの外側にSDFS/68 boot areaを置く。
- 初期候補は physical LBA `16` 以降とする。
- ROMはFATを見ず、固定LBAからheader sectorを読み、signatureとsizeを確認してからpayloadを連続sectorとしてRAMへ読む。
- root directory には確認用として同じ `SDFS.BIN` を置く。
- `mk-sdfs` は root `SDFS.BIN` と固定boot areaの内容が一致するように生成する。
- 手動コピーだけでは固定boot areaは更新されないため、起動用SDは `mk-sdfs` で作る運用にする。

SDFS/68 headerは #82 の案を維持し、固定セクタBOOTでは少なくとも次を確認する。

- signature: `SDFS68`
- header version
- entry address
- payload size
- payloadがSDFS/68ロード領域内に収まること

checksumはv1では必須にしない。必要ならSDFS/68 v2以降で追加する。

## ROM責務

ROMに残す:

- UART fallback。
- KKBD-USB入力。
- VDG最小出力または診断。
- monitor core。
- SD初期化とraw sector read。
- 固定LBAからSDFS/68をRAMへロードする最小 `BOOT`。
- SDFS/68 signature / size / entry確認。

ROMから外す:

- FAT32 mount。
- root directory探索。
- 8.3 filename検索。
- cluster chain。
- `DIR`。
- `LF`。
- I2C、RTC、EEPROM、OLED。
- 画像やバイナリデータのdirect read API。

## 失敗時動作

固定セクタBOOTは、次の失敗時に既存monitorへ戻る。

- SD init失敗。
- 固定LBA read失敗。
- signature不一致。
- header version不正。
- payload size不正。
- entry address不正。
- payload途中read失敗。

FATが壊れていても、固定boot areaが読めてheaderが正しければSDFS/68起動を試みる。SDFS/68起動後にFAT mountへ失敗した場合は、SDFS/68側の対話モードまたはROM fallback方針で扱う。

## 後続方針

#101 は、評価完了までFAT版BOOTとして実装へ進めない。固定セクタ案を採用する場合は、#101を固定セクタBOOTへ再定義するか、FAT版BOOTを別Issueへ退避する。

推奨する後続分割:

- 固定セクタBOOT実装: ROM側に `BOOT` を追加し、physical LBA `16` からSDFS/68をロードする。
- `mk-sdfs` 固定boot area対応: root `SDFS.BIN` と固定boot areaを同期してイメージ生成する。
- SDFS/68 v1: 起動後にFATをmountし、HEX/S-recordロードを提供する。
- ROM削減: SDFS/68 v1が成立した後、ROM側 `DIR` / `LF` を削る。

## 検証方針

このIssueでは実装コードを入れない。PRでは次を確認する。

- `git diff --check`
- `make bin`
- `REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `REQUIRE_BUILD_ROM=1 python3 tests/test_sd_fixture.py`

固定セクタBOOT実装Issueでは、SD fixtureに固定boot areaを持つイメージを追加し、正常起動、signature不一致、size不正、途中read失敗を確認する。
