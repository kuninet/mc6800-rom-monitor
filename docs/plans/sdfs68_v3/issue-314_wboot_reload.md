# Issue #314 戻り口の検査と静かな再ロードを ROM に入れ、BOOT3 を 1 回読みにする

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-1〜1-5・4-2・決定 1・4・13・16。

## 確認した事実

- `$E20D` の命令を `jmp MON_GATE` に変えれば、`CONTRL`（`MONITOR_ENTRY` を通る）、v2 の `EXIT`、`BIOS_MONITOR` の 3 つが門を通る。`RESET` は `MAIN_LOOP` へ落ちるので通らない
- `SWI_HANDLER` は `lds #STACK_TOP` してからモニタのコードを動かす。`BIOS_EXEC` と `G` のプログラムのスタックは `W+$1F7F` から下なので、SWI のフレームはモニタの 128B（`W+$1F80-$1FFF`）の外にある。`SWI_HANDLER` 自身は変えなくてよかった
- モニタの SWI はブレークポイントとして扱われ、`R` は SWI の番地から再開する（`B` で置いた SWI だけが元の命令に戻る）。プログラムに直に書いた SWI は、`R` で同じ SWI をもう一度実行する。このため、シナリオ 5 は `B` で置いた SWI で確かめた
- `RAMTEST` は 1 バイトごとに元の値を書き戻す。正常な RAM では CCP も核も壊れないので、`RAMTEST 0100-7FFF` のあとの `DOS` は読み直さずに入る。CCP と核を潰す操作の例には `F0100-7FFF 00` を使った
- `SD_READ_SECTOR` は `SD_LBA0-3` を変えない。`SD_INIT` は `SD_LBA0-3` を 0 にする。`SD_SECTOR_BUF`（`W+$0000`）は 512B 境界にある（アセンブル時に確かめる）
- 今のイメージ（6239B、CCP `$6400-$6FFF` は空きを含めて 3072B）では、CCP はファイル上 `$0020-$0C1F`（LBA 64〜70）、核は `$0C20-$185E`（LBA 70〜76）。LBA 70 には CCP の末尾と核の先頭が入る
- エミュレータの出力は、Python の text モードで受けると `\r\n` が `\n` に変わる。SD の記録の「送信済みバイト数」と出力の位置を突き合わせるには、バイトのまま受け取る

## 採用した判断

- 読み込みは `BB_READ_RANGE` の 1 本にまとめた。`BB_WORK` に `OFF`（ファイル上のオフセット）・`END`・`DST`・`TMP` を置き、セクタは `BB_SLOT_LBA + OFF/512`。`SD_LBA` が今のバッファのセクタと同じなら読まないので、ヘッダの照合で読んだ先頭セクタと、CCP と核の境目のセクタは 1 回しか読まない。`FAT_*` は使わない
- **BOOT3 の和は「コピーしながら」ではなく「コピーした RAM で」取る**（Issue の「読みながら足す」から変えた）。ヘッダの 32B は `+$18` を 0 にしてバッファで足し、ペイロードは `BB_STORE` が取る CCP と核の和 2 本をそのまま足す。SD の読み出しは 1 回のままで、RAM に置いた中身そのものを確かめるので、RAM への書き込みの失敗も見つかる。コピーのループに和を混ぜると、6800 のレジスタが足りず、ROM も時間も増える
- `BIOS_WBOOT`: 自己検査に通らなければ区画に書かずに `?`。通ったら和 2 本を照合して `STATE` に記録し（`CHECK` を付け直す）、0 なら CCP の +3 へ。0 でなければ `SD_INIT` → 先頭セクタ → `+$18` と `BB_IMG_SUM` の照合（違えば RAM に書く前にやめる）→ 壊れた区画だけ読む → 和を取り直して `STATE` を書く。失敗はすべて `clr BB_MAGIC` → `?`。エラーコードは #307
- `MON_GATE` は `lds #STACK_TOP` → `MON_CHECK` → `MAIN_LOOP`。`MON_CHECK` は自己検査に通ったときだけ和を照合して `STATE` を記録し、壊れていれば `*SDFS3 CCP`／`*SDFS3 CORE`／`*SDFS3 CCP CORE` の 1 行を出す。読み直さない（決定 1）
- SWI は、BRK の行を出したあとに `MON_GATE` へ飛ぶ（退避は済んでいる）。注意の行は BRK の行の下に出る（Issue の「退避直後」から表示の順だけ変えた）
- `G` は `MON_GATE` を `BIOS_PROG_STACK-1..0` に積み、`lds #BIOS_PROG_STACK-2` してから飛ぶ（決定 4・16）
- `$E20D`・SWI・`G` の変更は `if MONITOR_FEATURE_SD` の中だけ。SD=0 の ROM（base・sbcio）は #313 のビルドとバイト単位で一致する
- 2 回読みの部品（`BOOT3_SUM_*`、`BOOT3_COPY_*`、`BOOT3_SET_*COUNT*`、`BOOT3_DEC_*`、`BOOT3_SET_LBA`、`BOOT3_READ_SECTOR`）は消した
- v2 の `CMD_BOOT` の `clr BB_MAGIC`（#312 の m2）は #313 で入っている。この Issue ではテストで固定した

## 検証

エミュレータ（`emu/sbc6800_emu.py`）に足したもの:

- `--sd-log FILE`: CMD17 ごとに「番号 LBA R1 送信済みバイト数」
- `--sd-fail-cmd17-from N`: N 回目以降の CMD17 を R1 エラー（SD を抜いた代わり）
- `--sd-swap-image FILE --sd-swap-at N`: N 回目の CMD17 からイメージを差し替える
- `--stack-watch FLOOR`: `lds`／`txs` で SP が FLOOR 以上になった区間（モニタのスタック）の最小 SP を、ROM の命令と RAM の命令に分けて出す

`tests/test_sdfs68_v3_build.py` に足したテスト（sbcio_vdg・k6802_vdg の両方）:

- `test_rom_boot3_reads_image_once`: BOOT3 の CMD17 が LBA 64〜76 の 13 回（2 回読みなら 26 回）
- `test_wboot_reloads_only_broken_parts`: 健全な `HELLO.COM` の戻りで SD を読まない。CCP を潰す `.COM` のあとは LBA 64〜70 だけ、核を壊す `.COM` のあとは LBA 64 と 70〜76 だけを、何も出さずに読み直す。`B` で止めたプログラムは BRK の行と `*SDFS3 CCP` が出て、読み直さない。`R` のあとのプログラムは CCP に置いた値を読め、終わりの `RTS` で CCP を読み直して `SDFS3> ` に戻る
- `test_wboot_reload_fails_without_card_or_after_swap`: 読み直しの先頭の CMD17 から失敗させると `?`、`DOS` も `?`。`+$18` の違うカードに差し替えると、先頭セクタだけ読んで `?`。CCP は `$00` のまま、核も変わらない
- `test_monitor_gate_warns_and_dos_after_reset_and_ramtest`: `G E20D` と `G` のプログラムの `RTS` で注意と `STATE`（1、3、0）、`CHECK` が合う。門は SD を読まない。リセット（`G` でリセットの番地）と `RAMTEST 0100-7FFF` のあとの `DOS` は読み直さない。`F0100-7FFF 00` のあとは LBA 64〜76 を 1 回ずつ読む
- `test_v2_boot_exit_returns_to_monitor_and_disables_dos`: v3 のあとに v2 の `BOOT`、v2 の `EXIT` で注意なしにモニタ、`DOS` は `?`、`BB_MAGIC` は 0
- `test_monitor_stack_fits_in_128_bytes`: 下の計測

書き換えたテスト: `test_rom_bios_entry_table_layout`（`$E20D` は `jmp MON_GATE`）、`test_dos_gate_rejects_unloaded_block_without_writing`（形の正しい区画は `STATE` を記録して読み直しに進み、`+$18` の不一致で `MAGIC` を消す。CCP の目印は変わらない）。`test_dos_gate_checks_ccp_and_core_sums` は読み直しのテストに置き換えた。

## 計測（決定 16）

モニタのスタックの最深（`--stack-watch W+$1F80`）:

| 経路 | sbcio_vdg | k6802_vdg |
| --- | --- | --- |
| モニタ（`B` で止めたまま `H`・`D`・`DS`・`U`・`MAP`・`B`・`UW`・`F`・`RAMTEST`・`L`、`R`、門の注意、DOS の読み直しの失敗） | 19B（最小 SP `$DFED`） | 19B（`$BFED`） |
| DOS を含む（BOOT3、`DIR`・`TYPE`・`.COM`、CCP と核の読み直し） | 23B（`$DFE9`） | 23B（`$BFE9`） |

128B に十分収まる。

## 容量

#313 のあとの末尾の空きから、sbcio_vdg は 1681B → 1575B、k6802_vdg は 1667B → 1561B（どちらも +106B）。範囲の読み込み・WBOOT の読み直し・モニタの門・`G` の戻り番地を足し、2 回読みの部品を消した差し引き。MIKBUG の隙間の使用は変わらない（`$E15E` まで）。

## 後続への引き継ぎ

- #301: slot を選ぶときは `BB_SLOT_LBA` を書けば、cold も warm も `BB_READ_HEADER`／`BB_READ_RANGE` がその slot から読む。今は `CMD_BOOT3` の頭で `SDFS3SYS_FIXED_LBA` を入れている
- #307: 失敗の経路は `CMD_BOOT3_ERROR`（`FAT_ERROR` にヘッダ・和の失敗の種類が入る）と `BIOS_WBOOT_FAIL`／`BIOS_WBOOT_REJECT`。warm 側は `FAT_*` を使わない約束なので、コードを残す場所は `BB_WORK` か予約の `+$1C-$1F` から選ぶ
- #315: 核のファイル API は、今までどおり `SD_SECTOR_BUF` と `FAT_*` が上書きされても困らない作りにする（ROM の読み直しが `SD_SECTOR_BUF` を使うため）
- docs の仕様 1-1 は「`RAMTEST1` で壊れることがある」としているが、`RAMTEST` は値を書き戻すので、壊れるのは RAM が故障したときだけ。仕様の本文は書き換えず、ここに残す
