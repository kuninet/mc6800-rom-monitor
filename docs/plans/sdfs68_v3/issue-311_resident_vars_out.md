# Issue #311 resident の書き換わる変数をイメージの外へ出し、核から CCP への参照をなくす

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 2-1・2-2・4-2。

## 確認した事実

- v3 のテストは `sbcio_4000`・`k6802_4000` と、`SDFS3_LOAD_BASE=0x5000` を上書きした `k6802_vdg` で動く。vdg 系の既定値は resident が窓に入らず、#313 で直す
- `SDFS3_WORK_BASE` は `MIKBUG_VAR_BASE+$20`（4000 work は `$4320`）。ROM モニタの変数は `$42F0` までなので重ならない
- `fat32.asm`・`sdcard.asm` は `SDFS3_*` を参照しないので、核の側へそのまま置ける
- 並べ替えた各ブロックは `rts` で終わるため、順序を入れ替えてもフォールスルーは壊れない

## 採用した判断

- 変数 7B（`LAST_ERROR`・`PARSE_PTR`・`PARSE_LEN`・`TOKEN_PTR`・`TOKEN_LEN`）は `SDFS3_WORK_BASE` からの `equ` にした（`hardware.inc` に `SDFS3_WORK_BASE` を追加）
- イメージの並びは「API ヘッダ・ジャンプテーブル → `SDFS3_CORE_START` → 核 → `SDFS3_CCP_START` → CCP」。配置（`org`・ヘッダの値）は変えていない
- 核: API スロット実装、パス解決、`TO_UPPER`、`PRINT*`・`PUTC`、`FAIL_A` 系、`sdcard.asm`・`fat32.asm`。CCP: それ以外（`INIT` と Welcome の文字列、`TXT_OK` を含む）
- `LAST_ERROR` はイメージの外で初期値がなくなるため、`SDFS3_INIT`（BOOT3 が呼ぶ）の先頭で 0 にする
- `SDFS3_PENDING_ERR` は使う Issue（#315）で足す
- 参照検査は `tools/lst_analyze.py --check-core-ccp <lst>`。核の範囲の行のオペランドの識別子が CCP 範囲のラベルを指していたら失敗する。境界直前の命令が `rts`/`jmp`/`bra`/`rti` でない場合（CCP へ落ち込む場合）も失敗する
- ジャンプテーブルは `CORE_START` の前にあるので検査の対象外。今の ROM が slot 1（`CMD_DISPATCH`）を呼ぶため、CCP を指す slot は 1 と 13（`INIT`）が残る。テストで「この 2 つだけ」を固定し、#313 で解消する

## 検証

- `test_sdfs3_mutable_vars_live_outside_image`: 変数の番地とイメージ外の確認
- `test_sdfs3_core_does_not_reference_ccp`: 参照 0 件、核が空でないこと、ジャンプテーブルの例外、`jmp`／`ldx #`／`fdb` を足した複製ソースで検査が失敗すること
- `test_sdfs3_resident_image_unchanged_after_commands`: 本物の `BOOT3` のあと `DIR`・`TYPE`・`LOAD`・`.COM`・失敗コマンドを実行し、RAM のイメージ範囲が SDFS3SYS のペイロードと一致すること、`GET_ERROR` が最後の失敗コードを返すこと
- `test_sdfs3_init_clears_last_error`: `LAST_ERROR` に `FF` を書いてから `BOOT3` し、`GET_ERROR` が 0 になること

## 後続への引き継ぎ

- #313: CCP を下へ動かし、ヘッダとジャンプテーブルを核の先頭に置く。slot 1・13 の例外をなくす。`INIT` の Welcome は CCP 入口へ移る
- #315: `SDFS3_PENDING_ERR` を `SDFS3_WORK_BASE+7` に足す
