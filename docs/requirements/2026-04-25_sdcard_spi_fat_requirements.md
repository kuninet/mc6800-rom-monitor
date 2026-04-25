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

## RAM配置方針

8KB RAM 構成では、既存モニタ作業領域、スタック、ロード先、sector buffer を同時に置く余裕が小さい。SD/FAT 拡張を実用化する場合は SBC-IO の RAM 拡張を前提にする。

候補配置は次の通り。

| 領域 | 用途 |
| --- | --- |
| `$0000-$1FFF` | 既存 8KB RAM、モニタ作業領域、互換用途 |
| `$2000-$7FFF` | ロード先プログラム、FAT I/O 本体 |
| `$8000-$BFFF` | I/O 領域、ボード依存領域 |
| `$C000-$DFFF` | 8KB sector/cache/bounce buffer 候補 |
| `$E000-$FFFF` | ROM |

`$C000` の 8KB buffer は SBC-IO RAM 拡張時の候補であり、既存 8KB RAM 構成では必須要件にしない。

## 段階的PoC

1. PIA 直結で SPI クロック、MOSI、CS を出し、MISO を読めることをロジックアナライザで確認する。
2. PIA 直結で `CMD0`, `CMD8`, `ACMD41`, `CMD58` の応答を確認する。
3. PIA 直結で `CMD17` により固定 LBA の 512 バイト sector read を確認する。
4. FAT32 BPB を読み、512 バイト sector、FAT32、root cluster などの基本パラメータを取得する。
5. root directory または固定 directory `/MC6800/` の entry を読み、8.3 ファイル名とサイズを `DIR` で表示する。
6. `TEST.S` と `TEST.HEX` を stream read し、既存ローダへ渡して RAM へロードする。
7. monitor command から `DIR` と `LF filename` を呼び出すインターフェースを追加する。
8. SAVE と外付けマイコン方式は将来フェーズで検討する。

## 実装時の受け入れ条件

- PIA 直結 PoC では、SD カード初期化と固定 LBA sector read が成功すること。
- FAT32 BPB を読み、FAT32 判定と基本パラメータ取得ができること。
- FAT32 SDHC カードに置いた 8.3 名の `TEST.S` と `TEST.HEX` が `DIR` に表示されること。
- `LF TEST.S` と `LF TEST.HEX` で既存ローダへ stream 入力し、RAM へロードできること。
- LFN 付きファイル、subdirectory、削除 entry、volume label は初期実装でスキップされること。
- write / SAVE 対応を入れる場合は、明示的な flush または close 後に PC 側で FAT32 として読めること。

## 将来構想

PIA 直結の DIR/LOAD が成立した後、速度、安定性、SAVE 対応のために外付けマイコン方式を検討する。

### Block device MCU

SD 初期化、sector read/write、timeout、busy 待ちを外付けマイコンへ逃がす方式。MC6800 側は FAT 処理を持つが、PIA bit-bang SPI から解放される。

CH32V003 は 2KB SRAM / 16KB Flash で制約が大きいため、FAT 処理を持たせるより block device MCU 候補として扱う。

### FAT MCU

`DIR`、`OPEN`、`READ`、`WRITE`、`CLOSE` を外付けマイコンへ逃がす方式。MC6800 側は高レベルなファイル I/O コマンドを発行するだけになるため、SAVE 対応や複数ファイル操作を実装しやすい。

FAT MCU の本命候補は Raspberry Pi Pico / RP2040 系とする。RAM と Flash に余裕があり、FatFs、複数 sector buffer、MC6800 側ハンドシェイクを載せやすい。

## 未確定事項

- SBC66800 と SBC-IO を組み合わせた最終 I/O アドレスデコード。
- `$8110-$8117` を SD block device レジスタに使えるか。
- PIA 直結 DIR/LOAD を ROM に収めるか、一部を RAM ロードに分離するか。
- 初期対象 directory を root に固定するか、`/MC6800/` に固定するか。
- FAT write 対応を初期実装に含めるか。
- 外付けマイコンを block device MCU とするか、FAT MCU とするか。

## 関連リンク

- [MMC/SDCの使いかた](https://elm-chan.org/docs/mmc/mmc.html)
- [FatFs](https://elm-chan.org/fsw/ff/)
- [Petit FatFs](https://elm-chan.org/fsw/ff/00index_p.html)
- [SBC-IO Rev02](https://sbc738827564.wordpress.com/page/12/)
- [RP2040 specifications](https://www.raspberrypi.com/products/rp2040/specifications/)
- [openwch/ch32v003](https://github.com/openwch/ch32v003)
- 関連 Issue: [#38](https://github.com/kuninet/mc6800-rom-monitor/issues/38)
