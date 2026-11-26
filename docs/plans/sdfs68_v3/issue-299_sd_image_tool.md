# Issue #299 SDFS/68 v3 system SD 生成ツールで案 B のイメージを正式化する

親epic: #296。正の仕様は `issue-300_system_slot_layout.md`（LBA の配置、marker の形式、重なり検出条件）と `issue-310_plan_b_abi.md` の決定 12（FAT32 の開始は 2048、128 はオプション）。#316（LOAD.COM・RUN.COM・XLDR.OVL）の上に作った。

## 確認した事実

- 着手時、`docs/usage/sdfs68_system_sd.md` は「`mk_sdfs_image.py` が LBA 64 に `SDFS3SYS` を置く」と書いていたが、コードにその機能はなかった。v3 のカードはテストの `_build_sdfs3sys_fat_sd_image`（FAT は LBA 128、256 セクタ）と手作業で作っていた
- FAT32 を LBA 2048 から置いた既定の大きさ（約 34MB、65525 クラスタ）のカードでも、両プロファイルの ROM と resident は変更なしで `BOOT3`・`DIR`・`LOAD`・`RUN`・`.COM` が通る
- #302 のレビューの残件: 世代 0 の slot A から最初に更新する途中で marker が壊れると、ROM は世代を比べず旧 slot A で起動する。slot A を世代 1 にして marker を書いておけば、最初の更新（B に世代 2）で marker が壊れても B を選ぶ。エミュレータで、世代 0 なら A、世代 1 なら B になることを確かめた

## 採用した判断

1. **新しいツール `tools/mk_sdfs3_image.py` にした。** `mk_sdfs_image.py`（v2）は `--stage1`・`--sdfs` が必須で、v3 のカードには要らない。FAT32 の組み立て（`fat32_image.py`）と 8.3 名の変換（`mk_sdfs_image.fat83_*`）は使い回した
2. **v2 の stage1・`SDFS.BIN` の同居は入れなかった。** 案 B の本文にない。LBA 16〜47 は 0 のまま、FAT にも割り当てない（#300）
3. **slot A を世代 1 にして和を付け直し、LBA 48 に marker（active=A、marker 世代 1）を書く。slot B は 0 のまま。** 空の slot B は magic 不一致で無効になり、#302 の最初の更新先になる
4. **marker の組み立てと `SDFS3SYS` の検査は、このツールにも持った。** 作った時点では #302（PR #328）がまだマージされていなかった。関数名と定数名は #302 の `sdfs3_slot_update.py` とそろえた（`build_marker`、`validate_system`、`MARKER_LBA` など）。#302 は main に入ったので、片方へ寄せるのは残件
5. **入力の `SDFS3SYS` を ROM の `BOOT3` と同じ厳しさで検査する**（magic、header version 1、API major 2、flags = 1、header size `$20`、大きさ 33〜16384、`$4000 ≦ load`・`load + payload ≦ $8000`、`+$12` の先の `SDFS3API` と major 2、和）。起動できないカードを PC 側で止める
6. **重なりの検出**: `--fat-start` が 128 未満なら拒否する（MBR・stage1・marker・slot と重なる）。組み立てたあと MBR を読み直して区画の開始を確かめ、marker・slot A・空の slot B・空の stage1 領域が置いたとおりかも確かめる
7. **ファイルの指定は `カード上のパス=ホストのパス`。** `=` がなければ `mk_sdfs_image.py` と同じく相対パスをそのまま使う。`--tools-dir` は `LOAD.COM`・`RUN.COM`・`XLDR.OVL` を `/BIN` に入れる（1 本でもなければエラー）
8. **Makefile に `sdfs3-image` を足した。** 出力は `build/SDFS3SD<suffix>.img`。中身はルートの `README.TXT`（`sdfs_tools/SDCARD.TXT` を CR LF にしたもの）・`HELLO.S`・`HELLO.COM`・`ARGS.COM` と `/BIN` の 3 本。`SDFS3_FAT_START`（既定 2048）で開始を変えられる
9. **`SDFS3_LOAD_BASE=$5000` の手順（Issue 本文の「削るもの」）は、`docs/testing/k6802_sdfs3_via_v2_bringup.md` に案 B より前の記録として残し、冒頭の注記に「今のビルドでは使えない」と新しいカードの作り方への参照を足した。** 今の使い方の文書（`docs/usage`）にはこの手順はもう無い
10. **実カードへは書かない**（今までの方針どおり）。Windows の手順は、書き込みソフトの使い方と書き込み先の取り違えの注意を `docs/usage/sdfs68_system_sd.md` に書いた

## 配置

```
physical LBA
0       MBR(区画 1: type 0C、開始 = --fat-start)
16-47   0(stage1 用に予約)
48      marker SDFS3MRK active=A gen=1
64-95   slot A = SDFS3SYS(+$1C = 1、和を付け直し)
96-127  0(slot B)
2048-   FAT32 /README.TXT /HELLO.S /HELLO.COM /ARGS.COM /BIN/LOAD.COM /BIN/RUN.COM /BIN/XLDR.OVL
```

## 検証

- `tests/test_mk_sdfs3_image.py`（エミュレータなし）: marker のバイト列と和、slot A の世代 1 と和（変わるのは `+$18`・`+$1C` の 4 バイトだけ）、slot B と LBA 1〜47 が 0、MBR の区画の開始（2048・128）。既定のイメージは 65525 クラスタ以上で、同じ入力から同じバイト列。`--fat-start` 0・1・16・47・48・64・95・96・127 は拒否（CLI は終了コード 2 で、出力を作らない）、128 は通る。壊れた `SDFS3SYS`（magic、和、header version、API major 1、flags、load の範囲、16385 バイト、`SDFS3API`、切り詰め）は拒否し、16384 バイトちょうどは通る。`カード上のパス=` と `--tools-dir`（足りなければエラー）。組み立てのあとの読み直しは、区画の開始が 64、区画がイメージの末尾を越える、55AA がない、marker・slot A・slot A の後ろ・slot B・stage1 領域に 1 バイトでも違いがあるイメージを拒否する
- `tests/test_sdfs68_v3_build.py`（sbcio_vdg・k6802_vdg）
  - `test_sd_image_tool_boots_and_runs_dos_commands`: `make sdfs3-image`（2048）と `--fat-start 128` のカードで、`BOOT3`→`DIR`→`DIR /BIN`→`TYPE README.TXT`→`LOAD HELLO.S`→`RUN HELLO.S`→`DOS`→`HELLO.COM`→`HELLO`→`ARGS AAA BBB` が通る。`BOOT3` は 48 と slot A の 9 セクタだけを読み、`BB_SLOT_LBA` = 64。marker と slot A は、テストの `_marker(0)`・`_slot_image(config, 1)` とバイト単位で一致する
  - `test_sd_image_tool_first_update_survives_marker_loss`: 生成したカードの 96 に世代 2 の slot B を置き、48 を 0 にする（最初の更新で marker の書き込みが途中で切れた状態）と、48・64・96 のあと B から起動する
- 一回きりの確認（コミットしていない）: #302 のブランチの `sdfs3_slot_update.py` を生成したカードにかけると、「marker active=A 世代 1、slot A 世代 1 有効、slot B 無効」と読み、B に世代 2 を書いて marker を世代 2 にした。更新後のカードはエミュレータで B から起動し、marker を 0 にしても B から起動した

ROM、`SDFS3SYS`、`.COM`、`XLDR.OVL` は変えていない（#316 のビルドとバイト単位で一致）。

## 後続への引き継ぎ

- #302 は main に入った。marker の組み立てと `SDFS3SYS` の検査を `sdfs3_slot_update.py` と共有するのは残件
- #304（AUTOEXEC.COM）: `sdfs3-image` にサンプルの `AUTOEXEC.COM` を入れるかは #304 で決める
- #318（実機確認）: FAT32 が LBA 2048 から始まるカードを実機で読めるか。Windows の書き込み手順（`docs/usage/sdfs68_system_sd.md`）を実際のカードで試す
