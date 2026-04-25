# SDカード / FAT 拡張調査 2026-04-25

## 目的

SBC66800 に SBC-IO を接続し、MC6821 PIA を使って SD カードを SPI モードで扱う案と、外付け小型マイコンを使って SD カードをメモリマップド I/O 風に扱う案を比較する。

ROM は 2KB にこだわらず、`$E000-$FFFF` の最大 8KB を上限とする。ただし FAT ファイルシステム全体を ROM に常駐させるのではなく、ROM は起動と最小 I/O に絞り、必要な機能を SD カードから RAM へロードする構成を優先して検討する。

## 結論

- MC6821 PIA のビットバング SPI でも、SD カードの SPI モード初期化と 512 バイト sector の read/write は実現可能と考えられる。
- ただし、PIA アクセスとビットシフトを MC6800 がすべて担当するため低速で、カード初期化、busy 待ち、タイムアウト処理、FAT 処理まで載せると実用性は低い。
- 3.3V 電源、信号レベル変換、DO ラインのプルアップ、カード挿抜時の保護も必要であり、PIA 直結は PoC 向きと位置づける。
- 本命は外付け小型マイコンを SD カード制御専用にし、MC6800 側には sector block device をメモリマップド I/O 風に見せる方式とする。
- FAT ファイルシステムを ROM 常駐で本格実装するのは現実的ではない。ROM には boot/bootstrap と sector I/O の最小機能を置き、FAT I/O は SD カードから RAM へロードする構成を推奨する。
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

PIA 直結方式で確認する価値がある範囲は次に限定する。

- SD カードが SPI モードに入るか。
- `CMD0` と `CMD8` の応答が読めるか。
- `ACMD41` で初期化完了まで到達できるか。
- `CMD58` で CCS を確認できるか。
- `CMD17` で固定 LBA の 512 バイトを読めるか。

FAT の directory traverse、FAT chain 追跡、write back、複数ファイル操作まで PIA 直結で行うのは避ける。

参考: [SBC-IO Rev02](https://sbc738827564.wordpress.com/page/12/)

## 外付けマイコン方式

推奨方式は、外付け小型マイコンを SD カード制御と block device 制御に使う構成とする。MC6800 側は低速な SPI ビット操作から解放され、I/O レジスタを読むだけで sector データを扱える。

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

FAT までマイコン側に持たせる案も可能だが、初期方針ではマイコンは block device に限定する。これにより、MC6800 側の OS/monitor から見たファイルシステム方針を後で変更しやすくする。

## FAT実装方針

ROM 常駐の本格 FAT は避ける。`$E000-$FFFF` の 8KB ROM 上限では、モニタ本体、MIKBUG 互換入口、ローダ、エラー処理、SD 初期化、FAT directory/FAT chain/read/write を同居させる余裕が小さい。

ROM に置く候補は次に限定する。

- `sd_init`
- `sd_read_sector`
- `sd_boot_load`
- 固定 LBA から RAM へロードする最小 bootstrap
- 可能なら 8.3 固定名の boot file 検索

FAT I/O 本体は SD カードから RAM へロードする。

- Petit FatFs 相当は ROM 常駐候補だが、MC6800 アセンブリ移植とサイズ見積もりが必要。
- 通常 FatFs 相当の read/write FAT は RAM ロード候補とする。
- 初期対象は FAT32、8.3 short filename、単一ファイル open/read を基本にする。
- LFN、日本語ファイル名、Unicode 変換、exFAT、mkfs、複数同時 open、ディレクトリ作成は初期対象外にする。
- write 対応は read boot が安定してから追加する。

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
4. 外付けマイコン方式で固定 LBA の 512 バイト read/write を確認する。
5. MCU block device の status、timeout、card absent、write protect を確認する。
6. ROM から固定 LBA bootstrap を RAM へロードして実行する。
7. RAM ロード型 FAT I/O で 8.3 名の単一ファイル open/read を確認する。
8. monitor command から SD/FAT I/O を呼び出すインターフェースを追加する。

## 実装時の受け入れ条件

- PIA 直結 PoC では、SD カード初期化と固定 LBA sector read が成功すること。
- MCU 方式では、固定 LBA の 512 バイト read/write、連続 sector read、busy/status timeout、カード未挿入が確認できること。
- FAT 段階では、8.3 名の単一ファイル open/read、連続読み込み、RAM への bootstrap load が確認できること。
- write 対応を入れる場合は、明示的な flush または close 後に PC 側で FAT32 として読めること。

## 未確定事項

- SBC66800 と SBC-IO を組み合わせた最終 I/O アドレスデコード。
- `$8110-$8117` を SD block device レジスタに使えるか。
- PIA 直結をどこまで残し、MCU 方式へ移行するか。
- FAT I/O を MC6800 側 RAM に置くか、MCU 側へ寄せるか。
- SD bootstrap の検索方式を固定 LBA にするか、8.3 固定名にするか。
- FAT write 対応を初期実装に含めるか。

## 関連リンク

- [MMC/SDCの使いかた](https://elm-chan.org/docs/mmc/mmc.html)
- [FatFs](https://elm-chan.org/fsw/ff/)
- [Petit FatFs](https://elm-chan.org/fsw/ff/00index_p.html)
- [SBC-IO Rev02](https://sbc738827564.wordpress.com/page/12/)
- 関連 Issue: [#38](https://github.com/kuninet/mc6800-rom-monitor/issues/38)
