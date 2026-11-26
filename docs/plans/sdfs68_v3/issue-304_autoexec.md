# Issue #304 AUTOEXEC.COM を CCP の cold 入口で自動実行する

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 2-4（cold 入口: INIT → Welcome → AUTOEXEC.COM → プロンプト）と、2026-11-25 に書き換えた Issue 本文の「案 B での変更」。#315（`LOAD_PATH`）・#316（CCP を `$6C00` の 1KB に戻した）の上に作った。

## 確認した事実

- 着手時（#316 のあと）は、CCP が `$6C00-$6FD5`（982B、1KB 枠の残り 42B）、核が `$7000-$7AD8`（2777B、4KB 枠の残り 1319B。#317 で SD ドライバを ROM へ寄せたあと）。`CCP_BASE` を下げると XLDR.OVL の区画（`$6800-$6BFF`）とかぶる
- 核の `LOAD_PATH`（flags bit0 = exec）は、成功すれば `BIOS_EXEC` で起動して戻らない。プログラムの `RTS` は ROM の WBOOT → CCP の warm に着く。読み込みの前の失敗は C=1 で戻り、途中の失敗は `PENDING_ERR` = 3 を立てて WBOOT へ飛ぶ
- コンソールの入力は ROM の `CONSOLE_GETC` で、キーボードの ACIA2（`$8094`）を先に、次に ACIA1（`$8018`）を見る。BIOS 入口表にコンソールの状態を返す入口はない。resident は `hardware.inc` を include しているので、ACIA の番地を持てる（両プロファイルで同じ番地）
- 6850 は受信データを読むと RDRF が落ち、戻せない。ROM の `READ_LINE` にも押し戻す口はない
- パス解析は `FAT_FIND_NAME0` に書くだけで、渡したパスの文字列には書かない（核のイメージ内の定数を渡してよい）
- エミュレータのスクリプト入力は「最初から全部届いている」扱いで、入力が尽きた状態で ACIA1 の状態を読むと終わる。既存のテストは、`BOOT3` の直後に次の入力が必ず届いている

## 採用した判断

- **探して起動する処理は核に置いた（`SDFS3_AUTOEXEC`）。** CCP の cold には `jsr SDFS3_AUTOEXEC` / `bcs SDFS3_CCP_ERROR` の 5B だけを足した。参照の向きは CCP → 核で、核から CCP は参照しない（`test_sdfs3_core_does_not_reference_ccp`）。API のスロットにはしない（cold 入口だけの内部の処理）
- **探すのはルートの `AUTOEXEC.COM` だけ。** `/BIN` は探さない。起動は CCP の `.COM` と同じ `LOAD_PATH` のブロック（load `$0100`、limit `GET_MEMTOP`、exec、引数なし）。ブロックとパス `AUTOEXEC.COM` は核のイメージ内の定数で、argptr はブロックの中の 0 のバイトを指す（B=0）
- **失敗の扱い**
  - 見つからない（コード 4）: 何も出さない。`LAST_ERROR` を 0 に戻す
  - 読み込みの前のほかの失敗（mount・SD の失敗 3、大きすぎる 8）: CCP がコマンドの失敗と同じく `?` を 1 回出してプロンプトへ。`LAST_ERROR` はそのコードのまま。FAT のないカードは mount の失敗なので、cold で `?` が 1 回出る（FAT を読めないことに気づける）
  - 読み込みの途中の失敗: `LOAD_PATH` のとおり WBOOT → warm が `?` を 1 回出す。warm は AUTOEXEC を探さないので、繰り返さない
- **抑止: AUTOEXEC を探す時点で、コンソールに受信済みの文字があれば飛ばす。** ACIA1 と、キーボードのある構成（`MONITOR_FEATURE_KEYBOARD`）では ACIA2 の RDRF を見るだけで、文字は読まない。文字はそのまま `SDFS3> ` の最初の入力になる。勧める操作は「`BOOT3` の Enter のあと、読み込みの数秒のあいだにもう一度 Enter」（空行になって何も起きない）。飛ばしたときは何も出さず、SD も読まない
  - 却下: 特定のキー（ESC など）だけで飛ばす。6850 は読まないと中身が分からず、違うキーだったときにその 1 文字が消える
  - 却下: BIOS の予約入口（14・15）にコンソールの状態を足す。ROM と #310 の ABI を変える。resident はもう `hardware.inc` の番地に依存しており、ACIA の番地は両プロファイルで同じ
  - 却下: 抑止を入れない。止まる AUTOEXEC.COM は RESET → `DOS`（warm）で逃げられるが、SD を PC で直すまで `BOOT3` のたびに踏む
- **既知の制約（抑止の誤動作）**: どちらも「AUTOEXEC が黙って動かない」形で出る
  - 端末が Enter で CR LF を送ると、`BOOT3` の行の LF が ACIA1 に残り、毎回飛ばされる。端末を CR だけにする
  - `k6802_vdg` をシリアルなしで使う（ACIA1 を配線しない）と、浮いた ACIA1 の RDRF で飛ばされることがある。初めのコマンドにゴミが混じる既知の症状と同じ根で、切り分けも同じ（ACIA1 に端末をつなぐと消える）
- **ROM は変えていない。** base・sbcio・sbcio_vdg・k6802_vdg の 4 本とも #316 のビルドとバイト単位で一致する
- **エミュレータに入力の保留を足した（既定はオフ）。**
  - `--input-hold-pc ADDR`: ACIA1 の入力で CR を渡したら、CPU が ADDR を実行するまで RDRF を立てない（その間は入力が尽きても終わらない）。テストでは ADDR を ROM の `CONSOLE_GETC` にする。人が「入力を求められてから次の行を打つ」形になり、cold だけでなく warm（`.COM` の戻り、`DOS`）でも入力が溜まっていない。このため「warm でも AUTOEXEC を探す」誤りが、抑止に隠れずに見える
  - `--key-input-hold-pc ADDR`: ACIA2 のキー入力を、CPU が ADDR を実行するまで見せない。テストでは CCP の cold 入口にする（読み込み中にキーボードを押した形）

## 将来の使い方（RTC の初期化など）

`AUTOEXEC.COM` は、RTC の初期化、表示の設定、環境の初期化などを、ROM を焼き直さずに SD のファイルの差し替えで足すための口にする。

- 中身は普通の `.COM`（`$0100` から、`$6F00` バイトまで）。API は `BIOS_GET_API` で引き、終わったら `RTS` で `SDFS3> ` に戻る
- cold（`BOOT3`）でだけ 1 回動く。warm では動かないので、`DOS` や `.COM` の戻りのたびに初期化し直すことはない。毎回の warm で要る処理は、ここには置けない
- RTC のような機器の初期化は、抑止されたときや AUTOEXEC.COM がないときにも DOS が動くように、DOS 側の動作の前提にしない
- 複数の初期化を並べたいときは、AUTOEXEC.COM から別の `.COM` を呼ぶ仕組み（バッチなど）が要る。今回は入れていない（元の本文の対象外「AUTOEXEC.S」）

## 流れ

```
モニタ  BOOT3 ─ ROM が SDFS3SYS を読む ─ CCP +0
CCP     cold: INIT → Welcome → jsr SDFS3_AUTOEXEC ─ C=1 → ? → SDFS3>
核      SDFS3_AUTOEXEC: ACIA1/ACIA2 に受信済み → C=0（抑止。SD は読まない）
                        LOAD_PATH(AUTOEXEC.COM, $0100〜$6FFF, exec)
                          ├ 見つからない → LAST_ERROR=0, C=0
                          ├ 読む前の失敗 → C=1
                          ├ 途中の失敗 → PENDING_ERR=3 → WBOOT → CCP +3 → ? → SDFS3>
                          └ BIOS_EXEC → AUTOEXEC.COM → RTS → WBOOT → CCP +3 → SDFS3>
CCP +3（warm: .COM の戻り・DOS）は AUTOEXEC を探さない
```

## 検証

`tests/test_sdfs68_v3_build.py` に足したテスト（sbcio_vdg・k6802_vdg の両方。入力は `--input-hold-pc` で 1 行ずつ保留する）:

- `test_autoexec_runs_once_on_cold_and_returns`（シナリオ 1・2）: `B` を `$0300` に書いて文字列を出し `RTS` する AUTOEXEC.COM が、Welcome とプロンプトの間に 1 回だけ出る。その間に FAT 側の読み出しがあり、SDFS3SYS は読み直さない。`$0300` は `$55` から 0 に（B=0）。続く `DIR`、`HELLO`（`.COM` の戻り）、`EXIT` → `DOS` のあとも文字列は 1 回のまま、門の注意も出ない
- `test_autoexec_absent_searches_quietly`（シナリオ 3）: AUTOEXEC.COM がなければ、Welcome の直後が `SDFS3> `。その間に FAT 側の読み出しがある（探した証拠）。cold の直後の `LAST_ERROR` は 0
- `test_autoexec_skipped_by_pending_key`（シナリオ 4・5）: `BOOT3` の直後に Enter が届いていれば（ACIA1、キーボードの ACIA2 の両方）、Welcome から最初のプロンプトまで SD を 1 セクタも読まず、文字列も出ない。Enter は空行になり、続く `DIR` が動く
- `test_autoexec_failures_show_one_error`（シナリオ 6）: `$6F01` バイトの AUTOEXEC.COM は、ファイルの中身を読まずに `?` が 1 回。4KB の AUTOEXEC.COM を読み込みの途中で 1 回だけ失敗させると、`?` が 1 回で `SDFS3> `、SDFS3SYS は読み直さず、Welcome も 1 回（繰り返さない）。どちらも続く `DIR` が動く

テストが空振りしないことを、わざと壊した resident で確かめた（コミットしていない）:

- 抑止の分岐を消すと、`test_autoexec_skipped_by_pending_key` が落ちる（ACIA1 の場合に AUTOEXEC が動く）
- warm の入口でも `SDFS3_AUTOEXEC` を呼ぶと、`test_autoexec_runs_once_on_cold_and_returns` が落ちる（AUTOEXEC の `RTS` のたびに warm から AUTOEXEC が動いて終わらず、エミュレータが時間切れになる）

## 容量

| | #316 のあと | #304 のあと |
| --- | --- | --- |
| CCP | `$6C00-$6FD5`（982B）。1KB 枠の残り 42B | `$6C00-$6FDA`（987B、+5B）。残り 37B |
| 核 | `$7000-$7AD8`（2777B）。4KB 枠の残り 1319B | `$7000-$7B0C`（2829B、+52B）。残り 1267B |
| SDFS3SYS | 3833B（8 セクタ） | 3885B（8 セクタ） |

ROM は変えていない。

## 後続への引き継ぎ

- RTC の初期化（#80 系）は AUTOEXEC.COM に載せられる。上の「将来の使い方」の前提を守る
- 抑止の誤動作（CR LF の端末、k6802_vdg の ACIA1 未配線）は、実機の確認（#318）で症状を見る。問題になれば、ROM を焼くときに BIOS の予約入口でコンソールの状態（LF を読み捨てるなど）を出す案を考える
- `SDFS3_AUTOEXEC` は ACIA の番地を直接読む。コンソールの I/O を変える Issue では、ここも一緒に直す
