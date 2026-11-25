# Issue #301 BOOT3 を system slot A/B と active marker 対応ローダへ拡張する

親epic: #296。正の仕様は `issue-300_system_slot_layout.md`（marker の形式、有効条件、選択の優先順位）と `issue-310_plan_b_abi.md`（1-3〜1-5、1-7 の slot と marker の LBA）。slot の選択は #314 の 1 回読み（`BB_READ_RANGE`）の上に作った。

## 流れ

```
BOOT3
  clr BB_MAGIC → SD_INIT ─NG→ ?
  │
  ▼ BOOT3_PICK(先に試す slot を決める)
  LBA 48 を読む ─ marker 有効 ─→ first = active_slot(A=64 / B=96)
        │ 読めない・無効
        ▼
  LBA 64 と 96 の先頭セクタの +$1C(slot_generation)を読む
  両方 0 でなく B > A なら first = B、それ以外は first = A
  │
  ▼
  BOOT3_TRY(first) ─成功→ BIOS 区画(BB_SLOT_LBA = first)→ CCP +0(戻らない)
  │失敗(ヘッダ・大きさ・範囲・和・SD)
  ▼
  SD_INIT ─NG→ ?
  BOOT3_TRY(first eor $20) ─成功→ 同上(BB_SLOT_LBA = 他方)
  │失敗
  ▼
  clr BB_MAGIC → ? → モニタ(DOS も ?)

warm(#314 のまま): WBOOT は marker を読まない。BB_SLOT_LBA の先頭セクタの +$18 を
BB_IMG_SUM と照合し、違えば中止して ?。同じなら壊れた区画を BB_SLOT_LBA から読み直す。
```

## 確認した事実

- slot A（64）と B（96）の LBA は下位 8bit の bit 5 だけが違う。`eora #$20` で入れ替えられる（アセンブル時に確かめる）
- 「試す」（ヘッダの検査 → `BB_READ_RANGE` → `BB_STORE` → 全体の和の照合）は `BB_WORK` を全部使う。試行をまたいで残す値（先に試した slot）は、cold だけが使う `FAT_*`（`BOOT3_HEADER_SUM` と同じ流儀）に置いた。CCP は起動後に mount し直す
- 既存の SD 生成（テストの `_build_sdfs3sys_fat_sd_image`、`tools/mk_sdfs_image.py`）は LBA 48 と 96〜127 を 0 のままにする。LBA 48 は magic 不一致で marker 無効、slot B は magic 不一致で無効になる
- エミュレータは、イメージの範囲外の LBA の CMD17 を R1 エラーで返す。slot B の手前で切ったイメージで「active の slot が読めない」を確かめられた
- SDFS3SYS の CCP の末尾 `$6FFF` は埋め草（`$FF`）で、和の範囲に入る。テストでは slot B のここに `$B0` を入れ、和を付け直して slot を区別した

## 採用した判断

1. **既存の単一 LBA 開発用イメージ（marker なし、LBA 64 だけ）は残す。** #300 の「既存の単一 LBA image との互換」が、そのまま slot A として起動すると決めている。SD 生成ツールの正式化（#299）は未着手で、今のテストとツールもこの形を作る。marker と世代を書くのは PC 側の slot 更新（#302）の役目なので、この Issue ではテストの補助だけで作った
2. **選んでから読むのではなく、読んで確かめ、だめなら他方を読む。** slot の有効条件のうち「イメージ全体の和」は全部読まないと分からない。先に両方を検査すると全体の和の照合を 2 か所に持つことになる。下の表のとおり、#300 の選択規則と同じ結果になる
3. **marker が有効で active が失敗したら、世代を読まずに他方を試す。** active が無効と分かった時点で、候補は他方だけになる
4. **世代は slot が有効か確かめずに、生の値で比べる。** 無効な slot を先に選んでも、試して失敗し他方へ進むだけで結果は変わらない（時間だけかかる）。巻き戻りは判定しない（`$FFFF` と `1` なら `$FFFF` が新しい。#300 のとおり）
5. **最後の失敗の理由が `FAT_ERROR` に残る**（後に試した slot の理由）
6. **`BB_CHECK_VALID` に slot の LBA の検査は足さない。** `BB_MAGIC` と `BB_CHECK` でゴミは弾ける。LBA を書くのは BOOT3 だけ
7. **#300 の容量削減の優先順位（世代比較 → marker の slot 欄 → slot_count）は使わず、全部の条件を見る。** 空きが十分ある
8. **他方を試す前に `SD_INIT` をし直す（5B）。** 実機のカードは、R1 エラーやトークンの時間切れのあとビジーのままになり、次の CMD17 も失敗し続けることがある。そうなると「active の slot は読めないが他方は正常」のカードで fallback が効かない。初期化の時間は、先の slot が失敗したときだけかかる。`BOOT3_PICK` の中（marker・世代の読み出し）の失敗のあとには入れていない
9. **magic の照合は `BOOT3_CHECK_HEADER` と共用しなかった。** 共用の部品にしても 15B ほどしか減らず、#314 のヘッダ検査に手が入る

### #300 の選択規則と同じ結果になる理由

| 状況 | #300 の規則 | この実装 |
| --- | --- | --- |
| marker 有効、active が有効 | active（規則 1） | active を試して成功 |
| marker 有効、active が無効 | 両方を検査 → 有効なのは他方だけ | active が失敗 → 他方を試す |
| marker 無効、両方有効、世代が両方 0 以外で違う | 世代の大きい方 | 世代の大きい方を先に試して成功 |
| marker 無効、片方だけ有効 | 有効な方 | 無効な方が先なら失敗して、他方で成功 |
| marker 無効、両方有効、世代で決まらない | A | A が先 |
| 両方無効 | `?` | 2 つとも失敗して `?` |

## 読み出し回数（今のイメージは 13 セクタ）

| カード | #314 | #301 |
| --- | --- | --- |
| marker あり、active が正常 | ― | 48 ＋ slot の 13 回（+1 回） |
| marker なし（今の開発用イメージ） | 64〜76 の 13 回 | 48、64、96 ＋ 64〜76（+3 回） |
| marker あり、active の和が不一致 | ― | 48 ＋ active の 13 回 ＋ 他方の 13 回 |

## ROM の容量

#314 のあとの末尾の空きから、sbcio_vdg は 1575B → 1289B、k6802_vdg は 1561B → 1275B（どちらも +286B。他方を試す前の `SD_INIT` の 5B を含む）。見積り（仕様 1-8 の +150〜250B）を 36B 超えた。marker の有効条件を全部見たこと（magic 8B の照合だけで 48B）と、世代の比較・試行の出入口の分。MIKBUG の隙間の使用は変わらない。SD=0 の ROM（base・sbcio）は #314 のビルドとバイト単位で一致する。

## 検証

`tests/test_sdfs68_v3_build.py`（sbcio_vdg・k6802_vdg の両方）。SD は marker（48）＋ slot A（64）＋ slot B（96）＋ FAT32（128）。CMD17 の記録で読んだ LBA を確かめる。

- `test_boot3_marker_slot_and_wboot_reload_from_it`（シナリオ 1〜4）
  - active=A なら 48 と A の 13 セクタだけを読み、`$6FFF` は `$FF`
  - active=B なら 48 と B の 13 セクタだけを読み、`BB_SLOT_LBA` = 96。`ZAPCCP.COM` の戻りは何も出さずに B の CCP（96〜102）だけを読み直し、`DIR` が動き、`$6FFF` = `$B0`
  - 読み直しの先頭の CMD17 から marker を active=A に戻したカード（B はバイト一致）に替えても、読むのは B の CCP だけ。48 は読まない
  - 差し替え先の B の `+$18` が違えば、B の先頭セクタだけを読んで `?`、`DOS` も `?`。CCP は `$00` のまま
- `test_boot3_invalid_marker_falls_back_to_generation`（シナリオ 5）: A（世代 3）と B（世代 4）、marker は active=A。欄を 1 つずつ壊して和を付け直す（magic、version、active=2、slot_count、flags bit0、slot_max・slot_a・slot_b の下位と上位、size 31・513・`$0300`）と、和だけを壊したものは、48・64・96 のあと B から起動する。size 32・`$0100`・512 と壊さない marker は A から起動する
- `test_boot3_generation_picks_first_slot`（シナリオ 6）: marker なしで、A/B の世代が 3/2 → A、3/4 → B、0/5 → A、5/0 → A、5/5 → A、`$0100`/`$00FF` → A、`$00FF`/`$0100` → B、`$FFFF`/`1` → A、A が空（0 埋め）/0 → A の先頭だけ読んで B
- `test_boot3_falls_back_from_bad_active_slot`（シナリオ 7〜9）
  - active=B の和が不一致（ペイロードだけ壊す）: B の 13 セクタのあと A の 13 セクタを読んで A から起動。`ZAPCCP.COM` の読み直しは A の CCP
  - active=A のヘッダ不正: A の先頭セクタだけ読んで B から起動
  - active=B が読めない（カードが 96 の手前で終わる）: 96 の R1 エラーのあと A から起動
  - marker なしで B の先頭が読めない: 48・64・96（R1 エラー）のあと A から起動
  - 両方だめ: `BOOT3` も `DOS` も `?`、`BB_MAGIC` = 0
- `test_rom_boot3_reads_image_once`（シナリオ 10）: marker なしの今のイメージは、48・64・96 のあと 64〜76 を 1 回ずつ読む

## 後続への引き継ぎ

- #302（PC 側の slot 更新）: #300 の slot 有効条件のうち `load_address` の一致は、案 B では #310 の 1-5 の範囲の検査（`$4000 ≦ load`、`load + payload ≦ $8000`）で読み替える。marker の和は「`+$18` を 0 にした 512B の 16bit 加算」。`marker_size` は 32〜512（上位バイト 1 も有効）。ROM は `slot_max_sectors`・`slot_a_lba`・`slot_b_lba` の上位バイトが 0、下位が 32・64・96 であることも見る。テストの補助 `_marker`・`_slot_image` が組み立ての手本になる
- #307（エラーコード）: 両 slot が失敗したとき、`FAT_ERROR` には後に試した slot の理由が残る。どちらの理由を出すか（または両方か）は #307 で決め直す
- #318（実機確認）: 片方の slot だけが読めないカードで fallback することを試す。エミュレータは失敗の次の CMD17 にも普通に答えるので、他方の前の `SD_INIT` が要るかどうかは実機でしか分からない。`BOOT3_PICK` の中の読み出しの失敗のあとは `SD_INIT` をし直さない
- #299（SD 生成ツールの正式化）: 今のツールは marker を書かず、slot A だけを置く。BOOT3 はこれを slot A として起動する（+3 回の読み出し）
