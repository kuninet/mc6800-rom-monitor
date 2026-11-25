# Issue #313 v3 を案 B の配置へ切り替え、CCP を DOS のプロンプトとして独立させる

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-1〜1-7・2-2〜2-4・4-1・5 章。

## 確認した事実

- エミュレータは sbcio_vdg でも k6802_vdg でも、`BOOT3` から DOS のプロンプトまで動く（仕様 10 章の未確認点）
- LOAD/RUN を残した CCP は `$6400-$6C55`（2134B）で、仕様の見込み（約 1KB）を大きく超える。核は `$7000-$7C3E`（3135B、SD ドライバ込み）。SDFS3SYS は 6239B（ヘッダ 32B、CCP と核の間の空きを含む）
- `p2bin` は CCP の末尾と `$7000` の間の空きも出力に含める。BOOT3 はその空きも RAM にコピーするので、CCP の和はその空きを含めて取る（`[IMG_BASE, CORE_BASE)`）
- `READ_LINE` は大文字にしない。CCP は今までどおり語ごとに `TO_UPPER` で比べる
- `clr BB_MAGIC` は MAGIC の上位バイトだけを 0 にする。これで MAGIC が合わなくなり、区画は無効になる
- `src/main.asm` の CRLF の行は先頭の入口表のあたりなどに固まっている。BOOT3 以降の範囲は LF。編集はマッチした範囲の改行に合わせた

## 採用した判断

- 配置の定数は新しい `include/sdfs3_layout.inc` に置き、resident だけが include する（ROM は番地を持たない。仕様 1-7）。`SDFS3_RAM_FLOOR` は ROM も使うので `hardware.inc` のまま
- `SDFS3_CCP_BASE = $6400`（暫定）。`.COM` の上限は `CCP_BASE - $0100 = $6300` バイト。#316 で LOAD/RUN を外して `$6C00` に戻す
- 4000 work 構成では、Makefile の `check-sdfs3-config` が「v2 専用」と出して止める。inc 側にも `USER_RAM_END < $7FFF` のアサートを置いた
- BOOT3 の範囲検査は、大きさの上下限を確かめたあとに行う（`SDFS3_RAM_FLOOR ≦ load`、`load + payload ≦ USER_RAM_END+1`、桁あふれなし）。コピーより前に通すので、範囲の外の RAM には書かない。通ったら `load`・`load+entry_offset`・`load+api_table_offset` を区画に控える（コピーでヘッダが上書きされるため）
- BB_STORE は、和を 0 にしていったん CHECK を付け、`BB_CHECK_VALID` を通してから和を取って CHECK を付け直す。`BIOS_RAM_SUM` に区画の値を渡す前に必ず検査を通すため（#312 の m3）
- 核の署名を読む前に、核の先頭から 9 バイトがイメージの中にあることを確かめる。`CORE_BASE=$7FFF` のような壊れたヘッダで `$8000` 台の I/O を読まないため
- `BB_CHECK_VALID` は仕様どおり `IMG_BASE < CORE_BASE`、`CCP_VEC < CORE_BASE` に戻した（#312 の m1）。引く向きは今までと同じで、「借りが出なければ弾く」（`bcc`）にした
- `BIOS_WBOOT` は区画の自己検査と和 2 本の照合に通れば CCP の +3 へ、通らなければ `?` でモニタへ。`MAGIC`〜`CHECK` には書かない（`BB_WORK` だけ使う）。不一致でも `MAGIC` は消さない（`M` で戻せばまた入れる）。`STATE` への記録は #314 のモニタの門と一緒に入れる
- `BIOS_GET_API` は区画の自己検査を通せば `X = BB_CORE_BASE`。和は見ない（仕様の「検査はしない」）
- v2 の `BOOT` の冒頭で `clr BB_MAGIC`（仕様 1-3 のモード排他、#312 の m2）。#313 で DOS の門が本物になり、BOOT3 のあとに v2 を起動してから `DOS` と打つと古い区画を信じて飛ぶ経路ができるため、#314 を待たずに入れた
- API major 2・minor 0・16 スロット。SDFS3API ヘッダの `+$0E` は image の先頭（`CCP_BASE`）、`+$10` は image の最終番地、`+$12`（memtop）は `CORE_BASE-1`。SDFS3SYS ヘッダの `+$09`／`+$0A` はリスティングの `SDFS3_API_MAJOR`／`MINOR` から取る
- `SDFS3_PENDING_ERR` を `SDFS3_WORK_BASE+7`、`BIOS_EXEC` に渡すブロックを `+8..+$0B` に置いた（イメージの外）。#313 では立てる側がなく、warm の表示と INIT の消去だけ入れた
- CCP の `RUN addr`／`RUN file` も `BIOS_EXEC`（A=0、X=0、B=0）で起動する。プログラムの `RTS` は WBOOT を通って `SDFS3> ` に戻る
- 核→CCP の参照検査（`tools/lst_analyze.py --check-core-ccp`）は、範囲を `[CORE_START, END)` と `[CCP_START, CCP_END)` にした。ジャンプテーブルが核に入ったので、slot が CCP を指すと検査に掛かる。落ち込みの検査は「CCP の最後の命令（データ行を除く）が無条件の分岐」に変えた
- HELP の `CMD` を `DOS` に替えた

## 検証

`tests/test_sdfs68_v3_build.py` を sbcio_vdg・k6802_vdg に移し、`CMD xxx` の形を「`BOOT3` → `SDFS3> ` で入力」に書き直した。DOS で動いた証拠は、`SDFS3> <コマンド>` のエコーと、その出力のあとに次の `SDFS3> ` が出ること（`_dos()`）で取る。

- `test_rom_boot3_enters_dos_and_com_returns_through_wboot`（両プロファイル）: BOOT3 → Welcome → `SDFS3> ` → `DIR`・`TYPE`・`HELLO.COM`・`ARGS.COM AAA BBB`・`RETADDR.COM`・`LOAD`・`RUN RTS.S`・`RUN 0180`（BRK）→ `DOS` → `EXIT` → `D0200` → `DOS` → `DIR`。Welcome は 1 回だけ。`RETADDR.COM` がスタックから読んだ戻り番地が `$E0E6`（BIOS_WBOOT）
- `test_sdfs3_cmd_load_run_and_com_read_fat_files`: LOAD・RUN・`.COM` の失敗 4 件、`$6300` バイトの `.COM` は起動し `$6301` バイトは `?`
- `test_dos_gate_checks_ccp_and_core_sums`: CCP と核の 1 バイトを `M` で変えると `DOS` は `?`、戻すと入れる
- `test_dos_gate_rejects_unloaded_block_without_writing`: 区画が 0・ゴミ・形だけ正しい場合の `DOS` は `?` で、区画と CCP の場所に書かない。BOOT3 のあとに v2 の `BOOT` をすると `DOS` は `?`
- `test_rom_boot3_rejects_bad_images`: 古い resident（major 1、load `$5000`）、ヘッダ major 1、API major 1、署名違い、load が床より下、`$7FFF` を越える、核のオフセットがイメージの外、入口表が CCP の外、magic、チェックサム。どれも `?` で、区画は無効のまま
- `test_rom_bios_block_rejects_garbage`: `core=img` の 2 件が C=1 に反転。`CCP_VEC=CORE_BASE` を単独で突くケース（C=1）と、境界のすぐ内側（C=0）を足した
- `test_rom_drops_cmd_gateway_and_fixed_load_base`: ROM のリスティングと生成した `monitor_config.inc` に `SDFS3_LOAD_BASE`・`CMD_SDFS3`・`SDFS3_FIND_API`・`SDFS3_API_MIN_COUNT` などが残っていない
- `test_sdfs3_rejects_4000_work_profiles`: sbcio_4000・k6802_4000 の `make sdfs3sys` が分かるメッセージで失敗する
- #311・#312 のテスト（変数がイメージの外、核→CCP 参照 0、コマンド後もイメージ不変、INIT、BIOS 表、EXEC、区画）は新しい配置で生かした。固定 LBA ローダのハーネスは、`SDFS3_FIND_API` のかわりに核の先頭の署名を自分で確かめる形にした

## 後続への引き継ぎ

- #314: WBOOT の不一致で読み直す。`BIOS_WBOOT_IMPL` の `BIOS_WBOOT_FAIL` が差し替え先。`STATE` の記録と `CHECK` の付け直しもここで入れる。モニタ行きの門（`$E20D`、SWI、`G`）は未着手
- #315: `.COM` の読み込みを核の `LOAD_PATH` に移し、上限を `$6F00` バイトにする。`SDFS3_PENDING_ERR` を立てる側を作る
- #316: LOAD/RUN を CCP から外し、`SDFS3_CCP_BASE` を `$6C00` に戻す。そのとき `CCP_END ≦ $7000` のアサートが効く
- 注意: #316 までは `GET_MEMTOP`（`$6FFF`）が CCP（`$6400-$6FFF`）を含む。memtop を信じた `.COM` が CCP を潰すと、`RTS` のあと WBOOT の検査で `?` になりモニタに落ちる（#314 の読み直しで直る）
