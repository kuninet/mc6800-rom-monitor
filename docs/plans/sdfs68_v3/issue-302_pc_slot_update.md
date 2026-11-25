# Issue #302 PC 側ツールで SDFS/68 v3 system の非 active slot を更新する

親epic: #296。正の仕様は `issue-300_system_slot_layout.md`（LBA の配置、marker の形式、有効条件、選択の規則、更新時の世代の規約）と `issue-310_plan_b_abi.md` の 1-5（ヘッダの範囲検査、`+$10`・`+$12`、API major 2）。ROM 側の選択は `issue-301_boot3_slots.md`。ROM は変えていない。

## 使い方

```sh
python3 tools/sdfs3_slot_update.py --image sd.img --system build/SDFS3SYS-sbcio-vdg.BIN --dry-run
python3 tools/sdfs3_slot_update.py --image sd.img --system build/SDFS3SYS-sbcio-vdg.BIN
```

`--dry-run` は、marker と両 slot の状態、今起動する slot、更新先と新しい世代を表示するだけで、何も書かない。実カードは、イメージに吸い出してから更新し、書き戻す。

## 流れ

```
新しい SDFS3SYS ── 検査(ROM と同じ条件)─NG→ 終了(書かない)
SD イメージ ── 通常ファイルか(開いた fd の fstat)、128 セクタ以上か、MBR の 55AA、
               区画の開始が LBA 128 以上か ─NG→ 終了(書かない)
  │
  ▼ 今起動する slot = ROM の BOOT3 と同じ規則(marker 48、slot A 64、slot B 96)
  更新先 = その他方(どちらも無効なら A)、世代 = 有効な slot の世代の最大 + 1
  │
  1. 更新先の 32 セクタを書く(イメージ + 0 埋め) → fsync
  2. 読み戻して、書いたバイトと一致し、検査に通るか ─NG→ 終了(marker はそのまま)
  3. marker(active = 更新先、marker の世代 + 1)を書く → fsync
  4. 読み戻して、marker が有効で、ROM の規則で更新先が選ばれるか ─NG→ 失敗を報告
```

## 確認した事実

- ROM の `BOOT3_CHECK_HEADER` は flags を `== 1` で見る（bit0 だけではない）。header_size は `$0020` ちょうど。`BB_CHECK_VALID` は CCP 入口表を `[load, 核の先頭)`、核の先頭を `(load, load + payload - 1]` に収める。`BB_CHECK_API` は核の先頭から `SDFS3API` と major の 9 バイトがイメージに収まることを求める
- 既存の `parse_sdfs3sys_header`（`mk_sdfs3sys.py`）は ROM より緩い（header_size が 32 より大きくても通る、flags の bit0 が 0 なら和を見ない、API major を見ない）。slot の有効判定には使えない
- テストの `_marker`（#301）と、ツールの `build_marker` は同じバイトを作る
- 開発用イメージ（marker なし、slot A だけ、世代 0）から最初に更新すると、A は世代 0、B は世代 1 になる。ROM の世代の比較は「両方 0 以外」のときだけ働く

## 採用した判断

1. **書き込み先は通常ファイルだけ。** ブロックデバイスやキャラクタデバイスは、symlink 経由も含めて拒否する（開いた fd を `fstat` で見る）。Issue の「物理 SD への直接書き込みは必要に応じて別扱い」に従った。書き込みは LBA 48〜127 の外を拒む作りにもした（最後の砦）
2. **今起動する slot は、ROM と同じ規則で決める。** marker を盲信しない。marker が A を指していても A が無効で B が有効なら、ROM は B で起動するので、更新先は A になる
3. **両方の slot が無効なら A に書く**（初回の導入）
4. **slot の検査は 1 本の関数（`validate_system`）にまとめ**、新しいイメージ、読み戻し、既存の slot の判定の 3 か所で使う。ROM と同じ厳しさにした
5. **世代は「有効な slot の世代の最大 + 1」。** 無効な slot の世代は数えない（その slot は上書きする側か、起動しない側）
6. **世代が `$FFFF` なら書かずに失敗させる。** #300 は「`$FFFF` の次は 1」と書く一方で、「`$FFFF` と 1 が並ぶ状態はツールが作らない」とも書いている。1 に戻すと、marker が壊れたときに ROM は古い `$FFFF` の方を選ぶ。この端は #300 の中で両立しないので、拒否を選んだ。実用上は届かない（**#300 の文面との差**。#303 の実機側の更新も同じ規約を使うので、そこで決め直す）
7. **slot は 32 セクタを全部書く**（末尾は 0 埋め）。古いイメージの残りを slot に残さない
8. **marker の世代は、旧 marker が有効なら +1（`$FFFF` の次は 1）、無効なら 1。** ROM は marker の世代を比べないので、巻き戻りの問題はない
9. 失敗の注入は、テストで I/O 層（`SectorDevice`）を差し替えて行う。ツールにはテスト用のオプションを足していない

## 途中で止まったときに起動する slot

| 止まった所 | marker | ROM が起動する slot |
| --- | --- | --- |
| slot の書き込みの途中 | 旧のまま（有効） | 旧 slot（marker が指す） |
| slot の読み戻しが不一致・検査 NG | 旧のまま | 旧 slot |
| marker の書き込みの途中（marker が不正） | 不正 | 世代で選ぶ。両方の世代が 0 以外なら新しい slot。旧 slot が世代 0 なら旧 slot A |
| marker なしで、更新先の先頭だけが書けた（世代が大きい） | なし | 更新先を先に試し、和で落ちて旧 slot へ |

marker の書き込みの途中で止まったうえに旧 slot が世代 0 なら、新しい slot は起動しない。それでも旧 slot で起動はできる。ツールをもう一度動かせば、旧 slot（A）を今の起動先とみなし、B に世代 2 で書き直す。

## 検証

`tests/test_sdfs3_slot_update.py`（`make test` に追加）。前半は Python だけ、後半はツールで作ったイメージを ROM（sbcio_vdg・k6802_vdg）のエミュレータで BOOT3 し、**ツールが今起動するとみなす slot と ROM の `BB_SLOT_LBA` が一致すること**と、その slot のセクタを読んだことを確かめる。

- `test_validate_system_matches_rom_conditions`: magic、版、API major 1、flags 0・3、header_size 33、image_size 32・16385・ファイルより大きい、load < `$4000`、load + payload > `$8000`、`+$12` が 0・外、`+$10` ≧ `+$12`、SDFS3API が収まらない・署名・major、和を落とす。load + payload = `$8000` ちょうどは通す
- `test_marker_round_trip_and_validity`: `build_marker` が #301 のテストの `_marker` と同じバイト。#300 の marker の有効条件
- `test_select_boot_slot_follows_rom_rules`: #301 の「#300 の選択規則と同じ結果になる理由」の表
- `test_update_lifecycle_and_write_range`: 開発用イメージ → B に世代 1 → A に世代 2。変わるのは更新先の 32 セクタと LBA 48 だけ
- `test_update_targets_slot_rom_does_not_boot`: marker が A を指し A が壊れていれば A を更新する。両方無効なら A
- `test_failures_leave_marker_unchanged`: slot の途中で停止、読み戻し不一致、marker の途中で停止
- `test_rejects_bad_input_without_writing`: 新しいイメージの和・API major・余分なバイト・16KB 超、区画が LBA 64 から、55AA なし、128 セクタ未満、世代 `$FFFF`。どれもイメージは 1 バイトも変わらない。LBA 0・47・127〜128・2048 への書き込みを拒む
- `test_cli_dry_run_update_and_refuses_devices`: `--dry-run` は書かない。`/dev/null` と、それを指す symlink は拒む
- `test_rom_boots_updated_slot`（エミュ）: 開発用イメージ → A、更新 1 回目 → B、2 回目 → A
- `test_rom_boots_old_slot_after_failed_update`（エミュ）: slot の書きかけ（3 セクタ）と読み戻し不一致では旧 A。marker なしで B の書きかけ（世代 2）なら、ROM は B を全部読んでから A に戻る
- `test_rom_after_torn_marker`（エミュ）: 旧 slot が世代 0 なら A、世代 2/3 なら B

## 後続への引き継ぎ

- #303（実機側の更新）: 同じ手順（slot → 読み戻し → marker → 読み戻し）と、判断 2・5・6 を引き継ぐ。世代 `$FFFF` の扱いはここで決め直す
- #299（SD 生成ツールの正式化）: 生成時に slot A へ世代 1 と marker（active=A）を書いておけば、最初の更新のあとに marker が壊れても新しい slot から起動する（上の表の 3 行目）
- 物理 SD への直接書き込みは入れていない。入れるときは、対象のデバイスの確認（大きさ、MBR、既存の marker）を `--dry-run` と同じ報告で見せてから書く
