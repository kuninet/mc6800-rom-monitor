# Issue #317 v3 resident の SD ドライバを ROM の BIOS 入口へ寄せる

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-6 と決定 8。

## 確認した事実

- resident が参照していた `sdcard.asm` のラベルは `SD_INIT` と `SD_READ_SECTOR` の 2 つだけ（`fat32.asm` と `resident_stub.asm`）
- ROM の入口 `BIOS_SD_INIT`（`$E0F8`）と `BIOS_SD_READ`（`$E0FB`）は素の `jmp`。飛び先は ROM が include する同じ `src/sdcard.asm` で、中に条件アセンブルはない。レジスタの使い方と壊すレジスタは今までと同じ
- `SD_ERROR`・`SD_LBA0-3`・`SD_PORTB_SHADOW` などの変数は、ROM と resident が同じ `hardware.inc` と `monitor_config.inc` から番地を取る。PIA の影の値も今までどおり共有する

## 採用した判断

- `include "sdcard.asm"` の行を、その場で `SD_INIT equ BIOS_SD_INIT`・`SD_READ_SECTOR equ BIOS_SD_READ` に置き換えた。呼ぶ側（`fat32.asm`、resident）は変えない
- ROM、`sdcard.asm`、`fat32.asm` は触らない

## 大きさ（sbcio_vdg・k6802_vdg で同じ）

| | 前 | 後 |
| --- | ---: | ---: |
| 核（`$7000` から） | 3135B（末尾 `$7C3E`） | 2491B（末尾 `$79BA`） |
| `SDFS3.BIN` | 6207B | 5563B |
| `SDFS3SYS` | 6239B（13 セクタ） | 5595B（11 セクタ） |

減ったのは 644B。核の 4KB 枠の残りは 1605B になる。

## 検証

`tests/test_sdfs68_v3_build.py` に 3 本足した（どれも sbcio_vdg・k6802_vdg）。

- `test_sdfs3_resident_calls_rom_sd_entries`: `SD_INIT`・`SD_READ_SECTOR` が `$E0F8`・`$E0FB`、ドライバのラベルがリスティングに無い
- `test_sdfs3_commands_match_output_with_rom_sd_driver`: `DIR`・`TYPE HELLO.S`・`HELLO.COM`・`LOAD HELLO.S` の出力と、ロードされた中身
- `test_sdfs3_sd_access_goes_through_bios_table`: ROM の入口表の 1 本だけを失敗にすると、BOOT3 は通り `DIR` が `?` になる

外す前（main）と後で同じ入力を流して出力を比べた。違いは Welcome が表示する核の末尾番地（`END=7C3E` → `END=79BA`）だけだった。

ROM（base・sbcio・sbcio_vdg・k6802_vdg）、stage1、v2 の SDFS は main のビルドとバイト単位で一致する。

## 後続への引き継ぎ

- resident は #312 以降の ROM（BIOS 入口表を持つもの）が前提。それより古い ROM は major 2 の resident を BOOT3 で受け付けないので、組み合わせは起きない（仕様 5-3）
- SD write（#303）を resident に足すときは、低レベルの入口 8〜12（`BIOS_SD_SELECT` 〜 `BIOS_SD_WAIT_R1`）を使う
- #318: 実機でも resident の SD 読み出しは ROM のドライバを通る
