# Issue #303 SDFS/68 v3 の核に SD raw write primitive を置く

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-6・2-3・決定 7 と、#300 の LBA 配置。#304 の上に作った。

## 確認した事実

- ROM の入口 8〜12（`BIOS_SD_SELECT` `$E0FE`、`DESELECT` `$E101`、`SEND_CMD` `$E104`、`XFER` `$E107`、`WAIT_R1` `$E10A`）は `src/sdcard.asm` への素の `jmp`。`SEND_CMD` は `SD_CMD_BYTE`・`SD_LBA0-3`（LBA0 が上位）・`SD_CRC_BYTE` を送って `WAIT_R1` に入り、R1 を A に返す（16 バイト待って来なければ C=1）。`SD_LBA*` は読むだけで変えない
- ROM の `SD_FAIL`（失敗時に DESELECT する）は入口に出ていない。SELECT のあとの失敗経路では、核が自分で `BIOS_SD_DESELECT` を呼ぶ
- 仕様 2-3 で slot 9〜12 は `SYS_UPDATE` と FAT write の 3 本、14・15 はディレクトリ列挙の予約。ROM は API の本数を見ない（major だけ）
- 読み取りストリーム（slot 3〜5）の状態は `FAT_*` と `SD_SECTOR_BUF` にある。`SD_LBA*` は毎回 `FAT_SECTOR_TO_SD_LBA` で作り直す
- `SD_INIT` は OCR の CCS を要求するので、扱うのは SDHC だけ。LBA をそのまま CMD24 の引数にできる
- 着手時の核は `$7000-$7D90`（3473B。#317 の前なので SD ドライバ 644B を含む）
- エミュレータは CMD24 を知らなかった。コマンドの頭を `value & $C0 == $40` で拾うので、データ区間を先に受けないと `$40-$7F` のデータが偽のコマンドになる

## 採用した判断

1. **slot 16 `SD_WRITE` を表の外に足した。** 仕様 2-3 の予約（9〜12・14・15）を保つため。後方互換の追加なので major 2 のまま `api_minor` を 1 に、本数を 17 にした。Welcome の表示は `02.01` になる
2. **書いてよい LBA は固定の 2 本で、呼び手は広げられない。**
   - flags bit0 = 0: データ領域 `LBA ≥ 128`（#300 の「FAT32 partition は 128 以上」）
   - flags bit0 = 1: system 領域 `48 ≤ LBA < 128`（active marker と slot A/B。#302・`SYS_UPDATE` の system install 用）
   - LBA 0〜47（MBR、予約、stage1）はどちらでも拒む。範囲外は SD に何も送らずコード 10
   - 上限は見ない（カードが R1 で拒む）。比較は上位 3 バイトの OR と下位 1 バイトで行い、`cpx` の大小は使わない
3. **パラメータブロックは `{buf(2), lba(4, 上位から), flags(1)}`。** bit1 = 読み戻し検証。ほかの bit は予約で見ない
4. **読み戻しは流しながら比べる。** CMD17 を低レベル入口で出し、受けたバイトを `buf` と 1 バイトずつ比べる。`SD_SECTOR_BUF` を使わないので、開いた取っ手と FAT の状態を壊さない。違っても 512B と CRC を読み切ってから DESELECT する
   - 違ったら数えずに 1 を立てる。1 周目のレビューで、1 バイトの `inc` で数えると 256 個・512 個違ったときに 0 に戻って一致と判定する誤りが見つかった（カードが書き込みを捨てた、全部 `$FF` が返った、という典型的な失敗を見逃す）
5. **C=1 のとき A = コード（`GET_ERROR` と同じ）、B = カードが返した生のバイト。** 実機で原因を絞るため

   | コード | 名前 | 条件 | B |
   | ---: | --- | --- | --- |
   | 10 | `SDFS3_ERR_WR_RANGE` | LBA が範囲外 | 0 |
   | 11 | `SDFS3_ERR_WR_CMD` | CMD24 の R1 が 0 でない、または来ない | R1（来なければ `$FF`） |
   | 12 | `SDFS3_ERR_WR_DATA` | データ応答が受理（`xxx00101`）でない | 応答（来なければ `$FF`） |
   | 13 | `SDFS3_ERR_WR_BUSY` | busy が上限回数のうちに解けない | `$00` |
   | 14 | `SDFS3_ERR_WR_VERIFY` | 読み戻しが書いた内容と違う | 0 |
   | 3 | `SDFS3_ERR_IO`（既存） | 読み戻しの CMD17 の R1・トークンの失敗 | ― |

6. **データ応答の前の `$FF` は 8 バイトまで読み飛ばす。** 仕様では CRC の直後に来るが、遅れるカードに備えた。`anda #$1F` で上位 3 bit を捨てて `$05` と比べる
   - 拒まれたとき（書き込みエラーなど）も、busy が解けるまで同じ上限で待ってから DESELECT する。ROM の `SD_READ_SECTOR` はコマンドの前にカードの準備を待たないので、待たずに離すと続く CMD17 が busy の `$00` を R1 = 0 と取り違える（1 周目のレビュー）
7. **busy の上限は XFER 2048 回。** busy を待つ 1 回は `SD_SPI_XFER` の 8 bit 分を含めて約 740 サイクル（命令の表から数えた）。2048 回で約 1.5M サイクル、E クロック 1MHz なら約 1.5 秒（推測）。SDHC の書き込み busy の上限 250ms、SDXC の 500ms より長くとった
8. **取っ手は閉じない。** installer の「ストリームで読みながらセクタを書く」をそのまま書ける。書いたセクタがいま読んでいるファイルのセクタなら、`SD_SECTOR_BUF` の中身は古いまま（FAT write の Issue で扱う）
9. **`SD_INIT` はしない。** BOOT3 と mount でカードは初期化済み。抜き差しのあとはカードが idle のままで R1 ≠ 0 になり、コード 11 で返る
10. **`GET_CAPS` の A の bit4（raw SD write）を立てた。** #259 の caps 表どおり。ほかの bit は変えていない
11. **CCP からは呼ばない。** CCP の範囲に `SDFS3_SD_WRITE`・`SDFS3_SDW_*`・`BIOS_SD_SELECT`〜`WAIT_R1`・`BIOS_SD_WRITE` への参照がないことを `tools/lst_analyze.py` の `check_ccp_sd_write_refs` で確かめる
12. `buf` は `$FE00` 以下から始める RAM の 512B とし、`SD_SECTOR_BUF` は指さない（規約。検査はしない）
13. コードは `include "sdcard.asm"` の行から離して置き（#317 とぶつからないように）、`BIOS_SD_*` の名前だけを呼ぶ。XFER が X・B を保つことは当てにせず、ポインタと回数は窓の resident ワーク（`W+$0320+$47`〜`+$50`、10B）に置いた
14. ROM の入口 13（`BIOS_SD_WRITE`）は予約のまま（決定 7）。ROM、`sdcard.asm`、`fat32.asm` は触らない

## 流れ

```
.COM ─ BIOS_GET_API → 表 +32 → SDFS3_SD_WRITE(X → {buf, lba, flags})
核   ブロックを写す → 範囲 ✗ → C=1, 10（SD に触らない）
     SELECT → CMD24 → R1 ✗ → DESELECT, 11
     $FF, $FE, 512B, CRC 2B → 応答（$FF は 8 回まで飛ばす）✗ → DESELECT, 12
     busy（$00 の間、2048 回まで）✗ → DESELECT, 13
     DESELECT → bit1 なら SELECT → CMD17 → $FE → 512B を比べる → CRC → DESELECT → ✗ 14 / 3
     C=0
ROM  BIOS_SD_SELECT/DESELECT/SEND_CMD/XFER/WAIT_R1 → sdcard.asm → PIA
```

## エミュレータ

`emu/sbc6800_emu.py` の `SDCard` に CMD24 を足した。

- データ区間（開始トークン待ちと 514 バイトの受信）は、コマンドの解析より先に受ける
- データ応答は CRC の 2 バイト目の直後のバイトで読める。受理は `$E5`、CRC エラーは `$EB`、書き込みエラーは `$ED`（上位 3 bit を立てて、マスク漏れを見つける）
- 受理と書き込みエラーのあと、busy（`$00`）を既定で 2 バイト返す（`--sd-cmd24-busy-bytes N`）。busy の残りは CS を上げても残り、その間はコマンドを受け付けない（実カードと同じ）
- カードの容量（イメージの大きさ）の外は R1 `$40`。イメージは伸ばさない
- データの途中で CS が上がったら書き込みを反映しない
- `--sd-save`（終わりのイメージを書き出す）、`--sd-write-log`（CMD24 ごとに「番号 LBA 結果」）。`--sd-log` の書式は変えていない
- 失敗の注入: `--sd-fail-cmd24 {r1,noresp,crc,wrerr,busy,corrupt,corrupt256,drop,readff}`（`corrupt256` は 256 バイト化ける、`drop` は受理して書かない、`readff` は読み戻しが全部 `$FF`）（`--sd-fail-cmd24-at N` で N 回目だけ）、`--sd-cmd24-resp-delay N`（応答の前に `$FF` を N 個）

## 検証

`tests/test_sdfs68_v3_build.py` に 4 本足した（ビルドの 2 本は数秒、エミュレータの 2 本は sbcio_vdg・k6802_vdg の両方）。

- `test_sd_write_writes_verifies_and_keeps_stream`（シナリオ 1・2・4）
  - `SDW.COM` が BIG.TXT（1500B）を開いて 600B 読んだところで、16 個のブロックを順に書き、残りを読み切る
  - LBA 400（データ領域、検証つき）、49（system、検証つき）、127（system）、128（データ領域の下端。今の VBR と同じ中身、検証つき）は C=0。データには 0〜255 を 2 周させた 512B（`$40-$7F`・`$FE`・`$FF` を含む）を使う
  - LBA 0・47（bit0 の有無の両方）、48・49・127（bit0 なし）、128・`$00010000`・`$00010030`（bit0 つき）は C=1・10・B = 0
  - `$00010000`・`$01000000`（bit0 なし）は範囲を通り、カードの R1 `$40` で 11・B = `$40`。最後の `GET_ERROR` は 11
  - CMD24 の記録は範囲を通った 6 回だけ。保存したイメージで変わったのは LBA 49・127・400 だけで、中身はパターンと一致する
  - 読み切ったストリームは BIG.TXT と一致する。続く `DIR` が動く
- `test_sd_write_failures_return_codes`（シナリオ 3）: LBA 400 を検証つきで 1 回書き、そのあと `DIR`

  | 注入 | 結果 |
  | --- | --- |
  | R1 `$04` | 11・`$04`、イメージ不変 |
  | R1 なし | 11・`$FF`、イメージ不変 |
  | CRC エラー | 12・`$EB`、イメージ不変 |
  | 書き込みエラー | 12・`$ED`、イメージ不変 |
  | busy の張り付き | 13・`$00` |
  | 黙って化ける | 14 |
  | 応答が 7 バイト遅れる | C=0、中身が一致 |
  | 応答が 8 バイト遅れる | 12・`$FF`（無応答） |
  | 256 バイト化ける | 14 |
  | 受理して書かない（前の中身はパターンと 512 バイトすべて違う） | 14、イメージ不変 |
  | 読み戻しが全部 `$FF` | 14 |
  | busy が 300 バイト続く | C=0、中身が一致 |
  | 書き込みエラーのあと busy が 300 バイト続く | 12・`$ED`、イメージ不変、続く `DIR` が動く |

  どれも `GET_ERROR` が同じコードで、続く `DIR` が動く（DESELECT 済み）
- `test_sd_write_slot_header_and_caps`（シナリオ 6）: ヘッダの本数 17・minor 1、slot 16 が `SDFS3_SD_WRITE`、1・9〜12・14・15 は `NOT_IMPLEMENTED` のまま
- `test_ccp_does_not_call_sd_write`（シナリオ 5）: CCP の範囲に参照がない。CCP に `jsr SDFS3_SD_WRITE`・`fdb SDFS3_SDW_CMD`・`jsr BIOS_SD_XFER` を足すと、それぞれ見つかる

書き換えたテスト: API の本数（17）と minor（1）、Welcome の版（`02.01`）、`GET_CAPS` のバイト列（A = `$10`）。

範囲の検査を `SYS_LO = 47` に変えた核では、シナリオ 1 が「LBA 47（bit0 つき）が範囲外にならない」で落ちることを確かめた。不一致を `inc` で数える前の核では `corrupt256` と `drop` が C=0 になって落ち、拒否のあとの busy を待たない核では、書き込みエラーと busy 300 バイトのあとの `DIR` が失敗して落ちる。

ROM（base・sbcio・sbcio_vdg・k6802_vdg）、stage1、v2 の SDFS は、着手前（#304 の 71c7e28）のビルドとバイト単位で一致する。

## 容量（sbcio_vdg・k6802_vdg で同じ）

| | 前 | 後 |
| --- | ---: | ---: |
| 核（`$7000` から） | 3473B（末尾 `$7D90`） | 3813B（末尾 `$7EE4`） |
| 4KB 枠の残り | 623B | 283B |

増えたのは 340B（`SD_WRITE` 本体と、ジャンプテーブルの 1 本 2B）。#317 で SD ドライバ 644B が抜けると、残りは約 927B になる（推測）。

## #318 で実機に確かめること

- busy の上限 2048 回が実カードで足りるか（XFER の実時間とカードの最大 busy から出した推測値）
- データ応答が CRC の直後に来るか、`$FF` を挟むか
- 拒まれた（CRC・書き込みエラー）あとのカードの状態と、次の読み出しが通るか（CMD13 で状態を見ていない）
- system 領域（予約の LBA 49 など）への書き込みと、そのあとの BOOT3
- 2 枚以上のカードで、書いて読み戻すこと
- 全バイトが違う書き込みで、読み戻しがコード 14 になること
- 書き込みの途中で電源を切るかカードを抜いたあと、そのカードで BOOT3 と `DIR` が通ること（system 領域を書く `SYS_UPDATE` の前提）

## 後続への引き継ぎ

- FAT write（slot 10〜12）: このプリミティブを使う。書いたセクタが `SD_SECTOR_BUF` にあるときの扱いはそちらで決める
- #302・`SYS_UPDATE`（slot 9）: system 領域は flags bit0 で書く。動いている slot を上書きしない判断はそちらで持つ
- #317 の rebase: 核の `include "sdcard.asm"` の置き換えとは別の場所なので、ぶつからない見込み。rebase のあとは上の容量を測り直す
