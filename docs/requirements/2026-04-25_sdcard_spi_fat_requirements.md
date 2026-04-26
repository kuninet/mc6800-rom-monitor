# SDカード / FAT 拡張調査 2026-04-25

## 目的

SBC66800 に SBC-IO を接続し、MC6821 PIA を使って SD カードを SPI モードで扱う案と、外付け小型マイコンを使って SD カードをメモリマップド I/O 風に扱う案を比較する。

ROM は 2KB にこだわらず、`$E000-$FFFF` の最大 8KB を上限とする。ただし FAT ファイルシステム全体を ROM に常駐させるのではなく、ROM は起動と最小 I/O に絞り、必要な機能を SD カードから RAM へロードする構成を優先して検討する。

## 結論

- MC6821 PIA のビットバング SPI でも、SD カードの SPI モード初期化と 512 バイト sector の read/write は実現可能と考えられる。
- MC6800+PIA でも、read-only に限定した FAT32 の DIR 表示と S-Record / Intel HEX ファイル LOAD は初期実装候補として残す。
- 初期実装は SDHC、FAT32、512 バイト sector、8.3 filename、単一 volume、root directory または固定 directory に限定する。
- `DIR` では FAT directory entry から 8.3 名、属性、ファイルサイズを表示し、LFN entry、削除 entry、volume label、subdirectory は初期対象外としてスキップする。
- `LOAD` では `.S`、`.HEX`、`.S19`、`.SREC` を stream read し、既存の S-Record / Intel HEX ローダへ渡す。
- SAVE は FAT 更新と flush 順序のリスクが大きいため、フェーズ2以降に分離する。
- 外付けマイコンは初期必須ではなく、将来の速度改善、安定化、SAVE 対応、block device MCU または FAT file server 化の候補として残す。
- ROM へ FAT read-only 操作を入れる案、FAT32 reserved sector の第1段から第2段を bootstrap する案、外部マイコンへ逃がす案にはそれぞれメリットとデメリットがある。
- Bootstrap 案は ROM を小さくし、`$C000-$DFFF` に SD buffer と FAT driver を置ける一方で、専用 SD 作成手順と復旧手順が必要になる。
- 現在の 8KB RAM だけでは FAT バッファ、sector バッファ、ディレクトリ処理、ロード先 RAM の同居が厳しい。SBC-IO で 32KB 以上へ拡張し、可能なら `$C000` 付近に 8KB 程度の sector/cache/bounce buffer を確保する。

## SDカード SPIモード要点

- SD カードは SPI Mode 0 で扱う。
- 初期化時の SPI クロックは 100kHz から 400kHz 程度に抑える。
- 電源投入後、CS を非選択にした状態で 74 クロック以上を供給してカードを SPI モードへ移行できる状態にする。
- 初期化の基本コマンドは `CMD0`, `CMD8`, `ACMD41`, `CMD58` を想定する。
- sector read は `CMD17`、sector write は `CMD24` を基本にする。
- SDHC 以降は block address 指定、古い SDSC は byte address 指定になるため、初期対象は SDHC に寄せる。
- データブロックは 512 バイトを基本単位にする。
- CS 解放後にもダミークロックを入れ、次コマンドへ移る前にカード側の出力状態を戻す。
- DO/MISO はプルアップを入れる。カード未挿入や応答なしを timeout で検出する。
- SD カードは 3.3V デバイスとして扱い、5V 系の MC6800/PIA とはレベル変換を入れる。

参考: [MMC/SDCの使いかた](https://elm-chan.org/docs/mmc/mmc.html)

## SBC-IO / MC6821 PIAでの実現性

SBC-IO は MC6821 PIA、MC6840 PTM、MC6850 ACIA、RAM 拡張を載せられる I/O 拡張基板であり、I/O 領域は SBC6800 系の既存 ACIA 配置と競合しにくいように設計されている。

PIA 直結で SPI を作る場合は、次の割り当てを第一候補にする。

| SPI 信号 | PIA 割り当て案 | 方向 |
| --- | --- | --- |
| SCLK | Port B bit 0 | 出力 |
| MOSI | Port B bit 1 | 出力 |
| MISO | Port B bit 2 | 入力 |
| CS | Port B bit 3 | 出力 |
| CARD_DETECT | Port B bit 4 | 入力 |
| WP | Port B bit 5 | 入力 |

この構成なら、Port A をデバッグ表示や将来の別 I/O に残せる。ただし実装上は 1 ビット転送ごとに PIA レジスタ read/write が発生するため、512 バイト sector を読むだけでも 4096 クロック分のビット操作とループ処理が必要になる。

PIA 直結方式では、まず SD カードを block device として読めることを確認する。

- SD カードが SPI モードに入るか。
- `CMD0` と `CMD8` の応答が読めるか。
- `ACMD41` で初期化完了まで到達できるか。
- `CMD58` で CCS を確認できるか。
- `CMD17` で固定 LBA の 512 バイトを読めるか。

固定 LBA の read が安定した後は、read-only FAT32 の DIR/LOAD までを PIA 直結の実用 PoC とする。FAT の write back、cluster 確保、複数ファイル open、subdirectory 再帰 traverse まで PIA 直結の初期実装に含めるのは避ける。

参考: [SBC-IO Rev02](https://sbc738827564.wordpress.com/page/12/)

## PIA直結FAT初期実装

PIA 直結の初期目標は、PC で通常の FAT32 として読める SD カードから、MC6800 側でファイル一覧を表示し、S-Record / Intel HEX をロードできることとする。PC 側の独自抽出ツールが必要になる raw 独自形式は採用しない。

初期対象は次に限定する。

- SDHC カード。
- FAT32。
- 512 バイト sector。
- 8.3 filename。
- 単一 volume。
- root directory、または固定 directory `/MC6800/`。
- read-only。
- 同時 open は 1 ファイルのみ。

`DIR` は FAT directory entry を sector 単位で読み、次の情報を表示する。

- 8.3 ファイル名。
- 属性。
- ファイルサイズ。

初期実装では次の entry はスキップする。

- LFN entry。
- 削除済み entry。
- volume label。
- subdirectory。
- system / hidden 属性の entry。

`LOAD` は対象ファイルを stream read し、既存の S-Record / Intel HEX ローダへ 1 文字ずつ渡す構成にする。対象拡張子は `.S`、`.HEX`、`.S19`、`.SREC` とする。形式判定は既存ローダと同様に、ファイル先頭の有効文字が `S` なら S-Record、`:` なら Intel HEX として扱う。

コマンド案は次の通り。

| コマンド | 用途 |
| --- | --- |
| `DIR` | SD カード上の対象 directory を表示する |
| `F` | `DIR` の短縮コマンド候補 |
| `LF filename` | SD カード上のファイルを S-Record / Intel HEX として LOAD する |

既存の `L` はシリアル受信 LOAD として維持する。`L filename` は入力互換性を崩す可能性があるため、初期候補は `LF filename` とする。

## 方式比較

SD/FAT 拡張は、ROM 直 FAT 案、FAT32 予約領域 bootstrap 案、外部マイコン案の 3 系統で比較する。

| 方式 | 概要 | メリット | デメリット | 位置づけ |
| --- | --- | --- | --- | --- |
| ROM 直 FAT | ROM 内に SD 初期化、sector read、read-only FAT DIR/LOAD を持つ | SD 準備が簡単、PC 互換が高い、外部部品が増えない | ROM/RAM を食う、PIA bit-bang が低速、SAVE 追加が重い | 初期実装の現実路線 |
| FAT32 reserved sector bootstrap | ROM は reserved sector 内の固定位置から第1段を `$C000` へ読むだけに寄せる | ROM を小さくできる、`$C000-$DFFF` に SD buffer/FAT driver を置ける | 専用 SD 作成が必要、format/修復で消える可能性がある | ROM 削減案 |
| 外部 block device MCU | MCU が SD 初期化、sector read/write、timeout を担当する | MC6800 側が SPI bit-bang から解放される、SAVE の土台になる | 部品と MCU firmware が増える、MC6800 側 FAT は残る | 性能改善案 |
| 外部 FAT MCU | MCU が `DIR/OPEN/READ/WRITE/CLOSE` を担当する | MC6800 側が最も軽い、SAVE と FAT 更新に強い | MCU 側 firmware が大きい、MC6800 とのプロトコル設計が必要 | 将来本命候補 |

初期は ROM 直 FAT read-only DIR/LOAD を優先する。ROM サイズが厳しい場合は bootstrap 案へ逃がし、SAVE や安定運用を重視する段階で外部 MCU 案を検討する。

## 外付けマイコン方式

将来の性能改善案として、外付け小型マイコンを SD カード制御と block device 制御に使う構成を残す。MC6800 側は低速な SPI ビット操作から解放され、I/O レジスタを読むだけで sector データを扱える。

MC6800 側のレジスタ案は 8 バイト幅に固定する。

| Offset | 名前 | 用途 |
| --- | --- | --- |
| `+0` | `CMD` | `INIT`, `READ`, `WRITE`, `STATUS`, `RESET` |
| `+1` | `STATUS` | busy, ready, error, card present, write protect |
| `+2` | `LBA0` | LBA bit 0-7 |
| `+3` | `LBA1` | LBA bit 8-15 |
| `+4` | `LBA2` | LBA bit 16-23 |
| `+5` | `LBA3` | LBA bit 24-31 |
| `+6` | `DATA` | sector data FIFO または window data |
| `+7` | `CTRL/IRQ` | FIFO reset, ack, optional IRQ control |

実アドレスは SBC-IO の競合確認後に決めるが、第一候補は `$8110-$8117` とする。既存 ACIA の `$8018-$8019` とは分離し、将来の PIA/PTM/ACIA 拡張とも衝突しないように定義値化する。

マイコン側は次の責務を持つ。

- SD カードの 3.3V SPI 制御。
- カード初期化とタイムアウト管理。
- 512 バイト sector read/write。
- 必要に応じた 512 バイト以上の内部バッファ。
- error code の保持。
- MC6800 側の低速 read/write に合わせた FIFO または window 制御。

FAT までマイコン側に持たせる案も可能だが、初期方針では PIA 直結の read-only FAT DIR/LOAD を先に検証する。外付けマイコンは、速度と安定性が不足した場合、または SAVE を実装する場合の拡張手段として扱う。

外部マイコン候補は次の通り。

| MCU | 特徴 | 向き不向き |
| --- | --- | --- |
| Raspberry Pi Pico / RP2040 | 264KB SRAM、SPI、PIO、安価で入手しやすい | FAT MCU 本命候補。FatFs、複数 sector buffer、MC6800 側ハンドシェイクを載せやすい |
| ATmega328P | 32KB Flash、2KB SRAM、SPI あり | block device MCU や簡易 read 補助なら候補。FAT server 本命には古く窮屈 |
| CH32V003 | 16KB Flash、2KB SRAM、SPI あり | block device 補助まで。FAT server には厳しい |

AVR ATmega328P は実績があり扱いやすいが、2KB SRAM では 512 バイト sector buffer、FAT 作業領域、MC6800 側通信 buffer を同時に持つ余裕が小さい。新規に FAT server を作るなら RP2040/Pico 系を優先する。

## FAT実装方針

ROM 常駐の本格 FAT read/write は避ける。`$E000-$FFFF` の 8KB ROM 上限では、モニタ本体、MIKBUG 互換入口、ローダ、エラー処理、SD 初期化、FAT directory/FAT chain/read/write を同居させる余裕が小さい。

ROM に置く候補は次に限定する。

- `sd_init`
- `sd_read_sector`
- `sd_boot_load`
- `sd_dir`
- `sd_load_file`
- FAT32 BPB 読み取りと基本パラメータ取得
- root directory または固定 directory の 8.3 entry 走査
- FAT chain をたどる read-only stream read

FAT I/O 本体を ROM に入れきれない場合は、SD カードから RAM へロードする。

- Petit FatFs 相当は ROM 常駐候補だが、MC6800 アセンブリ移植とサイズ見積もりが必要。
- 通常 FatFs 相当の read/write FAT は RAM ロード候補とする。
- 初期対象は FAT32、8.3 short filename、DIR 表示、単一ファイル open/read を基本にする。
- LFN、日本語ファイル名、Unicode 変換、exFAT、mkfs、複数同時 open、ディレクトリ作成は初期対象外にする。
- write / SAVE 対応は DIR/LOAD が安定してからフェーズ2として追加する。

標準対象メディアは SDHC 4GB から 32GB、FAT32、512 バイト sector とする。SDXC/exFAT/SDUC は対象外にする。

参考:

- [FatFs](https://elm-chan.org/fsw/ff/)
- [Petit FatFs](https://elm-chan.org/fsw/ff/00index_p.html)

## FAT32予約領域bootstrap案

FAT32 には reserved sectors があり、boot sector、FSInfo、backup boot sector などが置かれる。通常の Windows ファイルコピーでは reserved sectors はファイル領域として使われないため、専用作成ツールで確保・検証したカードに限り、この領域に第1段 bootstrap を固定配置する案は成立する。

ただし reserved sectors は標準的なアプリケーションデータ保存場所ではない。Windows や他ツールで再フォーマットした場合は消え、`chkdsk` などの修復、boot sector 更新、パーティション操作で書き換えられる可能性がある。そのため、更新頻度の高い本体やユーザファイルは FAT 上の通常ファイルに置く。

避ける sector は次の通り。

- volume 先頭の boot sector。
- FSInfo sector。
- boot code continuation に使われる sector。
- backup boot sector と backup FSInfo sector。

候補配置は、FAT32 BPB の `BPB_RsvdSecCnt`、`BPB_FSInfo`、`BPB_BkBootSec` を確認したうえで、reserved region 内の専用作成ツールが確保した固定位置にする。例として、`BPB_RsvdSecCnt >= 32` を要求し、boot sector、FSInfo、backup boot sector、backup FSInfo、boot continuation と衝突しない `volume_start + 16` 以降を第1段 bootstrap 候補にする。ただし実カードの reserved sector 数や衝突検査が条件を満たさない場合は bootstrap 案を使わない。

推奨運用は次の通り。

- 第1段 bootstrap は reserved sector に固定配置する。
- 第1段 bootstrap には signature と version を持たせる。
- ROM は SDHC 初期化、MBR/BPB 最小読取、reserved sector read、signature 検査、`$C000` jump に絞る。
- 第1段 bootstrap は `$C000-$DFFF` 上で動作し、FAT32 read-only の最小処理で第2段本体を読む。
- 第2段本体は FAT 上の通常ファイル `/MC6800/SDFS.BIN` または `/MC6800/BOOT.SYS` に置く。
- `$C000-$DFFF` は第1段 bootstrap、512 バイト sector buffer、SD/FAT driver、DIR/LF 処理、第2段 loader に使う。
- signature 不一致、reserved sector 不足、read error 時は、従来のシリアル `L` へ fallback する。

ROM 直 FAT fallback を持たせる場合、bootstrap 案は ROM 削減案ではなく冗長起動手段になる。そのため ROM 削減を目的とする bootstrap 案では、fallback はシリアル `L` のみに限定する。

SD 初期設定の面倒さは、PC 側スクリプトで吸収する。専用 SD イメージまたは専用作成ツールで FAT32 format、reserved sector への第1段書き込み、`/MC6800/SDFS.BIN` 配置、検証用 signature 確認までをまとめて行う。

## RAM配置方針

8KB RAM 構成では、既存モニタ作業領域、スタック、ロード先、sector buffer を同時に置く余裕が小さい。SD/FAT 拡張を実用化する場合は SBC-IO の RAM 拡張を前提にする。

候補配置は次の通り。

| 領域 | 用途 |
| --- | --- |
| `$0000-$1FFF` | 既存 8KB RAM、モニタ作業領域、互換用途 |
| `$2000-$7FFF` | ロード先プログラム、FAT I/O 本体 |
| `$8000-$BFFF` | I/O 領域、ボード依存領域 |
| `$C000-$DFFF` | 8KB sector/cache/bounce buffer、bootstrap 第2段、SD/FAT driver 候補 |
| `$E000-$FFFF` | ROM |

`$C000` の 8KB buffer は SBC-IO RAM 拡張時の候補であり、既存 8KB RAM 構成では必須要件にしない。Bootstrap 案では、`$C000-$DFFF` が RAM として実在し、ROM/I/O/アドレスデコードと衝突しないことを前提条件にする。この条件を満たす場合だけ、この領域を SD buffer と driver の退避先として優先的に使い、`$0000-$7FFF` の通常 RAM を圧迫しない構成にする。

## 段階的PoC

1. PIA 直結で SPI クロック、MOSI、CS を出し、MISO を読めることをロジックアナライザで確認する。
2. PIA 直結で `CMD0`, `CMD8`, `ACMD41`, `CMD58` の応答を確認する。
3. PIA 直結で `CMD17` により固定 LBA の 512 バイト sector read を確認する。
4. FAT32 BPB を読み、512 バイト sector、FAT32、root cluster などの基本パラメータを取得する。
5. root directory または固定 directory `/MC6800/` の entry を読み、8.3 ファイル名とサイズを `DIR` で表示する。
6. `TEST.S` と `TEST.HEX` を stream read し、既存ローダへ渡して RAM へロードする。
7. monitor command から `DIR` と `LF filename` を呼び出すインターフェースを追加する。
8. FAT32 reserved sector に signature 付き第1段 bootstrap を置き、`$C000` へ読み込めることを確認する。
9. `BPB_RsvdSecCnt` 不足、候補 sector 範囲不足、signature mismatch、read error でシリアル `L` fallback へ落ちることを確認する。
10. Windows で通常ファイルコピー、取り外し、再マウントを行い、raw sector の before/after 比較で第1段が変化しないことを確認する。
11. format、`chkdsk`、ディスク管理ツール操作は第1段を破壊し得る操作として扱い、専用作成ツールで再作成できることを確認する。
12. SAVE と外付けマイコン方式は将来フェーズで検討する。

## 実装時の受け入れ条件

- PIA 直結 PoC では、SD カード初期化と固定 LBA sector read が成功すること。
- FAT32 BPB を読み、FAT32 判定と基本パラメータ取得ができること。
- FAT32 SDHC カードに置いた 8.3 名の `TEST.S` と `TEST.HEX` が `DIR` に表示されること。
- `LF TEST.S` と `LF TEST.HEX` で既存ローダへ stream 入力し、RAM へロードできること。
- LFN 付きファイル、subdirectory、削除 entry、volume label は初期実装でスキップされること。
- Reserved sector bootstrap 案では、signature 付き第1段を `$C000` へ読み込み、signature 確認後に実行できること。
- Windows で通常ファイルコピーを行っても、reserved sector の第1段 bootstrap が変化しないこと。
- Reserved sector bootstrap 案では、`$C000-$DFFF` が RAM として使えることを起動前提として確認できること。
- Reserved sector bootstrap 案では、reserved sector 不足、候補 sector 範囲不足、signature mismatch、read error の negative test が通ること。
- write / SAVE 対応を入れる場合は、明示的な flush または close 後に PC 側で FAT32 として読めること。

## 将来構想

PIA 直結の DIR/LOAD が成立した後、速度、安定性、SAVE 対応のために外付けマイコン方式を検討する。

### Block device MCU

SD 初期化、sector read/write、timeout、busy 待ちを外付けマイコンへ逃がす方式。MC6800 側は FAT 処理を持つが、PIA bit-bang SPI から解放される。

CH32V003 は 2KB SRAM / 16KB Flash で制約が大きいため、FAT 処理を持たせるより block device MCU 候補として扱う。

ATmega328P も 2KB SRAM のため、block device MCU や簡易 read 補助の候補に留める。既存資産や書き込み環境を活かせる利点はあるが、FAT MCU として新規採用するなら余裕のある RP2040/Pico 系を優先する。

### FAT MCU

`DIR`、`OPEN`、`READ`、`WRITE`、`CLOSE` を外付けマイコンへ逃がす方式。MC6800 側は高レベルなファイル I/O コマンドを発行するだけになるため、SAVE 対応や複数ファイル操作を実装しやすい。

FAT MCU の本命候補は Raspberry Pi Pico / RP2040 系とする。RAM と Flash に余裕があり、FatFs、複数 sector buffer、MC6800 側ハンドシェイクを載せやすい。

## 未確定事項

- SBC66800 と SBC-IO を組み合わせた最終 I/O アドレスデコード。
- `$8110-$8117` を SD block device レジスタに使えるか。
- PIA 直結 DIR/LOAD を ROM に収めるか、一部を RAM ロードに分離するか。
- Bootstrap 案で reserved sector の固定位置をどこにするか。
- 専用 SD 作成スクリプトをどの環境向けに用意するか。
- 初期対象 directory を root に固定するか、`/MC6800/` に固定するか。
- FAT write 対応を初期実装に含めるか。
- 外付けマイコンを block device MCU とするか、FAT MCU とするか。

## 関連リンク

- [MMC/SDCの使いかた](https://elm-chan.org/docs/mmc/mmc.html)
- [FatFs](https://elm-chan.org/fsw/ff/)
- [Petit FatFs](https://elm-chan.org/fsw/ff/00index_p.html)
- [Microsoft FAT specification](https://download.microsoft.com/download/1/6/1/161ba512-40e2-4cc9-843a-923143f3456c/fatgen103.doc)
- [SBC-IO Rev02](https://sbc738827564.wordpress.com/page/12/)
- [RP2040 specifications](https://www.raspberrypi.com/products/rp2040/specifications/)
- [ATmega328P datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/Atmel-7810-Automotive-Microcontrollers-ATmega328P_Datasheet.pdf)
- [openwch/ch32v003](https://github.com/openwch/ch32v003)
- 関連 Issue: [#38](https://github.com/kuninet/mc6800-rom-monitor/issues/38)
