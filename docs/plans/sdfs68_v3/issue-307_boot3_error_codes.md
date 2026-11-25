# Issue #307 BOOT3 と WBOOT の失敗要因を識別できるエラーコードを出す

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 1-4（読み直しに失敗したら `?` とエラーコード）と決定 13（読み直しの間は何も出さず、失敗したときだけ `?` とコード）。#314 の 1 回読みと #301 の slot 選択の上に作った。

## 確認した事実

- cold（`CMD_BOOT3`）の失敗は、`?` と CR を出すだけだった。`BOOT3_TRY` はヘッダと和の失敗のときだけ `FAT_ERROR` に理由を入れ、SD の読み出しと `BB_STORE`（入口表・核の位置、`SDFS3API`）の失敗では何も入れなかった
- 両 slot が失敗したとき、`FAT_ERROR` には後に試した slot の理由だけが残る。今の開発用カード（marker なし、slot B は空）では、slot A の本当の理由が隠れ、いつも slot B の理由になる
- warm（`BIOS_WBOOT_IMPL`。WBOOT、モニタの `DOS`、`.COM` の戻り）の失敗も `?` だけだった。warm は `FAT_*` を使わない（#314）
- ヘッダ `+$09` は `abi_major`（#257）。今までは署名・版の不一致と同じ失敗にまとめていた
- `ldaa` は C を変えない。C=1 で戻る経路では、`bcs` のあとに `ldaa #コード` → `rts` でコードを渡せる
- エミュレータの失敗注入は CMD17 だけで、`SD_INIT` を失敗させる手段がなかった。`SD_INIT` は CMD0 の R1 が `$01` でなければすぐに C=1 で戻る

## 採用した判断

1. **コードは cold と warm で共通の 1 桁（`BT_ERR_*`）にした。** `1` SD の初期化、`2` 読み出し、`3` ヘッダ不正、`4` API の不一致、`5` 和の不一致、`6` BIOS 区画が無効（warm だけ）、`7` カードの差し替え（warm だけ）。`FAT_ERR_*` は v2 の stage1 と共有の番号で、SD の初期化と読み出しを分けられず、区画や差し替えの意味もないので使わない。BOOT3 は `FAT_ERROR` を書かなくなった（読む人はいない）
2. **cold は `?` のあとに slot A と slot B の理由を 1 桁ずつ出す（例 `?53`）。** 順は試した順ではなく、常に A → B。`SD_INIT` の失敗は両方 `1`（`?11`）
   - 却下: 最後に試した slot の理由だけ。今の開発用カードでは、A の理由が隠れていつも B の `3`（または `2`）になる
   - 却下: 先に試した slot の理由だけ。どちらを先に試したかは marker と世代で変わり、利用者には分からない
3. **warm は `?` のあとに 1 桁（例 `?7`）。** warm は起動した slot だけを読むので理由は 1 つ。桁の数で cold と warm を見分けられる。文字列は足さない
4. **ヘッダ `+$09`（abi_major）の不一致は `4` にした。** 古い resident（major 1）を置いたカードは、壊れたイメージ（`3`）ではなく版の不一致と分かる
5. **`BB_STORE` の `BB_CHECK_VALID` の失敗は `3` にした。** ここに来るのはヘッダの範囲検査を通ったあとで、外れるのは CCP 入口表と核の位置（ヘッダの欄）だけ。warm の `BB_CHECK_VALID` の失敗（区画が無効）は `6`
6. **cold の理由は `BOOT3_ERR`（cold だけの `FAT_VOLUME_LBA3`）に集める。** 上位 4bit が slot A、下位が slot B。`BOOT3_TRY` の直後に、`BB_SLOT_LBA` の下位が 64 かどうかで入れる桁を決める
7. **#301 の「他方を読む前の `SD_INIT` のし直し」が失敗したら、他方の slot の桁を `1` にする。** 桁が 0 のまま（`?30` など）残る経路を作らない。先に試した slot の理由はそのまま残る（例 `?31`）
8. **エミュレータに `--sd-fail-cmd0-after N` を足した。** CMD17 が N 回済んだあとの CMD0 を R1 エラー（`$04`）にする。CMD0 は記録に残らないので、回数を CMD17 で数えると、warm の読み直しの `SD_INIT` を既存の「読み直しの先頭の CMD17 の番号」から狙える。`--sd-log` の形式は変えていない

## 流れ

```
cold  BOOT3 ── SD_INIT ✗ ─────────────────────────────────────→ ?11
        └─ PICK → TRY(先) ✗ → 理由を slot の桁へ
                  SD_INIT ✗ → 他方の桁は 1 ─────────────────────→ ?<A><B>
                  TRY(他) ✗ → 理由を slot の桁へ ──────────────→ ?<A><B>
warm  WBOOT/DOS ─ 区画 ✗ ─────────────────────────────────────→ ?6
        └─ 和 ✗ → 読み直し ─ SD_INIT ✗ → ?1 ／ 読み出し ✗ → ?2 ／ +$18 ✗ → ?7
                      └─ 和 ✗ ──────────────────────────────────→ ?5
      （warm の ?6 以外は区画を無効にするので、続く DOS は ?6）
```

## 検証

`tests/test_sdfs68_v3_build.py`（sbcio_vdg・k6802_vdg の両方）に足したテスト:

- `test_boot3_error_codes_name_each_slot`
  - CMD0 が最初から失敗: `?11`、CMD17 は 0 回
  - CMD17 が最初から失敗: `?22`（marker と世代の 3 回のあと、A と B を 1 回ずつ）
  - A のヘッダ不正のあと、B の前の `SD_INIT` のし直しが失敗: `?31`（B は読まない）
  - A のヘッダ不正・和の不一致・ヘッダ `+$09` = 1、B は空: `?33`・`?53`・`?43`
  - marker は active=B、B はヘッダ不正、A は和の不一致: `?53`（B を先に試しても A → B の順）
  - どれも `DOS` は `?6`、`BB_MAGIC` = 0、resident は動かない
- `test_wboot_error_codes_name_the_cause`（`ZAPCCP.COM` で CCP を潰し、戻りの読み直しを狙う）
  - `BOOT3` の前の `DOS`: `?6`
  - 読み直しの `SD_INIT` が失敗: `?1`、CMD17 を出さない
  - 先頭セクタの読み出しが失敗: `?2`
  - CCP の 2 セクタ目の読み出しが失敗: `?2`
  - `+$18` の違うカードに差し替え: `?7`、先頭セクタだけ読む
  - `+$18` は同じで CCP の中身だけ違うカードに差し替え: `?5`、CCP の範囲だけ読む
  - どれも続く `DOS` は `?6`

書き換えたテスト（`?` の行をコード付きに）: `test_wboot_reload_fails_without_card_or_after_swap`（`?2`・`?7`）、`test_boot3_marker_slot_and_wboot_reload_from_it` のシナリオ 4（`?7`）、`test_boot3_falls_back_from_bad_active_slot` のシナリオ 9（`?35`）、`test_v2_boot_exit_returns_to_monitor_and_disables_dos`（`?6`）、`test_monitor_stack_fits_in_128_bytes`（偽の区画の読み直しは `?5`）、`test_dos_gate_rejects_unloaded_block_without_writing`（`?6`、形の正しい区画は `?7`）、`test_rom_boot3_rejects_bad_images`（ケースごとのコード。カードは LBA 96 の手前で終わるので B はいつも `2`）、`test_rom_bios_exec_returns_to_wboot`（`?6`）。

## 容量

#301 のあとの末尾の空きから、sbcio_vdg は 1289B → 1209B、k6802_vdg は 1275B → 1195B（どちらも +80B。見積りの +40〜60B を 20B 超えた）。経路ごとのコードの読み込み（`ldaa #コード` と `sec`／`rts` の組が 9 か所）、slot の桁へ入れる `BOOT3_NOTE`、表示の `BT_SHOW_ERR1`／`BT_SHOW_ERR2`、2 回目の `SD_INIT` の失敗の記録（10B）の分。SD=0 の ROM（base・sbcio）は #301 のビルドとバイト単位で一致する。

## 後続への引き継ぎ

- #318（実機）: 抜いたカード（`?11`）、片方の slot だけ読めないカード（`?2x`）、`.COM` の実行中のカードの差し替え（`?7`）で、コードが出ることを確かめる
- #302（PC 側の slot 更新）: 更新に失敗した slot は `3` か `5` で見える。両方の slot の理由が出るので、どちらを書き損じたか分かる
