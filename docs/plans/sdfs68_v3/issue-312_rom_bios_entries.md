# Issue #312 ROM に BIOS 入口表・RAM の和のルーチン・BIOS 区画を追加する

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-1〜1-3・1-6・1-8・4-2・決定 16。

## 確認した事実

- MIKBUG の隙間 `$E0E6-$E1AB`（198B）は空いていた。入口表 48B（`$E0E6-$E115`）の後ろに、小さな本体と RAM の和を置いて `$E163` まで使った（126B）
- `make test` が作る SD=1 の構成は、どれも KEYBOARD=1（`$E20D` が `jmp MAIN_LOOP`）、`S1_SUPPORTED=1`、窓あり。このため `if MONITOR_FEATURE_SD` で囲めば足りる
- `READ_LINE` は X と B を返さないので、`BIOS_READ_LINE` は 3 命令の包みにした
- 今の resident は「API ヘッダ → 核 → CCP」の並びで、SDFS3API ヘッダは `SDFS3_LOAD_BASE` にある。SDFS3SYS ヘッダの `+$10`・`+$12` は v1 の意味のまま
- vdg 系の既定の `SDFS3_LOAD_BASE`（`$D000`／`$B000`）は窓の中にあり、自己検査の範囲（`$4000`〜`USER_RAM_END`）から外れる。既定の構成では BOOT3 のあとも自己検査は「未ロード」になる。#313 で resident が低位 RAM に移れば解消する
- `BOOT3_DST_PTR`・`BOOT3_EXPECTED_SUM` は `FAT_*` の別名なので、INIT を呼ぶ前に区画の欄へ控える
- `src/main.asm` は CRLF と LF の行が混在している。編集では、周りの行の改行に合わせた

## 採用した判断（2026-11-25、オーナー承認）

| # | 論点 | 決定 |
| --- | --- | --- |
| Q1 | 今の配置での区画の中身 | `CORE_BASE` は仕様どおり SDFS3API ヘッダの番地（今は `IMG_BASE` と同じ）、和は `SUM_CORE` の 1 本、`SUM_CCP=0`、`CCP_VEC=IMG_BASE`。自己検査は `IMG_BASE ≦ CORE_BASE`、`IMG_BASE ≦ CCP_VEC ≦ CORE_BASE` に緩める（#313 で `<` に戻す） |
| Q2 | 和のルーチンの終端 | `BB_WORK` に「最後のバイトの次の番地」を入れる（`[X, 終端)` の和）。長さ 0 なら即座に戻る |
| Q3 | `BIOS_INFO` | A = `BIOS_VERSION`（1）、B = 16 |
| Q4 | `BIOS_MONITOR` | `lds #STACK_TOP` / `jmp MONITOR_REENTRY`（`$E20D`） |
| Q5 | BOOT3 の冒頭 | `BB_MAGIC` を消す。途中で失敗したときに古い区画が有効のまま残らない |

- `BIOS_WBOOT` は #312 では `lds #STACK_TOP` / `jmp MAIN_LOOP_ERROR`（`?` とプロンプト）
- `BIOS_EXEC` は、X が指すブロックをスタックを切り替える前に読む。呼び手のブロックが新しいスタックの位置（`W+$1F7C-$1F7F`）と重なっても壊さないため
- 区画の自己検査 `BB_CHECK_VALID` は区画にも RAM にも書かない。16bit の大小は `suba`/`sbca` の借りで判定する（6800 の `cpx` は Z しか当てにならない）

## 検証

`tests/test_sdfs68_v3_build.py` に 6 本足した。

- `test_rom_bios_entry_table_layout`: sbcio_vdg・k6802_vdg で、16 本の番地と ROM バイナリ上の `jmp` の飛び先、隙間の末尾、`$E20D`
- `test_rom_bios_read_line_and_sd_match_internal`: `BIOS_READ_LINE` と `READ_LINE`、`BIOS_SD_INIT`／`BIOS_SD_READ` と `SD_INIT`／`SD_READ_SECTOR` が同じ結果
- `test_rom_bios_exec_returns_to_wboot`: entry で A=0・B=引数長・X=argptr・SP=`W+$1F7D`・一番上が `BIOS_WBOOT`。`RTS` のあと `?` とプロンプト
- `test_rom_bios_info_and_reserved`: `BIOS_INFO`、予約 13〜15 が C=1、BOOT3 前の `BIOS_GET_API` が C=1
- `test_rom_bios_block_rejects_garbage`: 擬似乱数の区画 8 通りが C=1、正しい区画 4 通りが C=0、欄を 1 つずつ範囲外にして `CHECK` を付け直した 10 通りと、1 バイト変えた区画が C=1。区画と区画の外の RAM は変わらない
- `test_rom_boot3_writes_bios_block`: k6802_vdg＋`SDFS3_LOAD_BASE=$5000` で本物の BOOT3。区画の各欄、`SUM_CORE` ＝ RAM の和 ＝ ペイロードの和、`M` で 1 バイト変えると C=1、`CMD DIR` は今までどおり

SD=0 の ROM（base・sbcio）は main のビルドとバイト単位で一致することを確かめた。

## 容量

増えたのは隙間 126B と末尾 195B の計 321B。末尾の空きは sbcio_vdg が 1943B から 1748B に、k6802_vdg が 1929B から 1734B に減った。

## 後続への引き継ぎ

- #313: 自己検査の `IMG_BASE ≦ CORE_BASE` と `CCP_VEC ≦ CORE_BASE` を、仕様 1-3 どおり `<` に戻す。`BB_STORE` で `CORE_BASE` をヘッダ `+$12` から、`CCP_VEC` をヘッダ `+$10` から取り、和を 2 本に分ける。`BIOS_WBOOT` を本物にする
- #314: `BIOS_MONITOR` は `$E20D` 経由なので、`$E20D` の命令を門へ変えれば足りる。BOOT3 を 1 回読みに作り替えるとき、`BB_WORK` に終端を控える流れを引き継ぐ
