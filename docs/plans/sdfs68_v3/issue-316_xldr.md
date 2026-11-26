# Issue #316 LOAD.COM・RUN.COM・XLDR.OVL を作り、CCP から LOAD と RUN を外す

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 2-2・2-4・3 章、決定 5・6。#315（ファイル API と `LOAD_PATH`）の上に作った。

## 確認した事実

- 着手時（#315 のあと）は、CCP が `$6400-$6BF6`（2039B）、核が `$7000-$7D5C`（3421B。#317 のあとの main では `$7000-$7AD8`、2777B）。CCP の LOAD/RUN 関連（内蔵語 2 つ、`LOAD_FILE`、S-record と Intel HEX のローダ、16 進の解析、`OK` の文字列）は約 1.1KB
- LOAD/RUN を外して暗黙の `.COM` 検索を足しただけでは、CCP は 1127B で 1KB 枠を 103B 越えた
- 今のローダの作業変数（`LOADER_*`、`HEX_*`、`SDFS_RUN_ENTRY`）は ROM モニタページ（窓）にあり、番地はプロファイルで違う
- `READ_STREAM_GETC` は B と X を保ち、終わりは C=1・`GET_ERROR` = 0（#315）
- `LOAD_PATH` は読み込みの前に大きさを全部確かめ、`limit` が `GET_MEMTOP` を越えればコード 8 で C=1 を返す
- asl の `include` はソースの置き場所から探す。`sdfs_tools/LOAD_COM.ASM` から `XLDR_STUB.INC` を `-i` なしで読める
- macOS の GNU Make 3.81 は時刻を 1 秒単位で比べる。同じ秒に `.p` を作り直すと、`.BIN` と `SDFS3SYS` が古いまま残る（`test_sdfs3_core_does_not_reference_ccp` の後始末で、改変したイメージが `build/` に残ることがあった）

## 採用した判断

- **XLDR.OVL と入口はプロファイルによらない 1 本にした。** `hardware.inc` を include しない。ROM の固定番地（`BIOS_GET_API`・`BIOS_EXEC`・`PDATA1`）と API のスロットだけを使う。作業変数は本体の後ろ（`$6BBF-$6BD8`）に置く
- **入口は本体を核の `LOAD_PATH`（flags = 0、load = `$6800`、limit = `GET_MEMTOP`）で読む。** 仕様 3-2 の字面は `READ_STREAM_OPEN` だが、`LOAD_PATH` は大きさの検査（「本体の末尾が memtop を超えないか」）と読み込みの途中の失敗の扱い（WBOOT へ）を持っている。入口に同じ処理を書くより小さい（入口は 137B）。読み込んだあと、`$6803` の署名 `XLDR` を確かめる
- **`/BIN/XLDR.OVL` の読み込みが読み込みの前に失敗したら、理由によらずルートの `XLDR.OVL` を試す。** `LOAD_PATH` の失敗の種類を知るには `GET_ERROR` を呼ぶ必要があり、入口が大きくなる。SD の失敗ならルートも失敗する
- **失敗は XLDR と入口が自分で `?` CR LF を出して `RTS` する。** `.COM` には `PENDING_ERR` を立てる口がない。CCP の `?` と同じ並びにしたので、テストは CCP の失敗と同じ形で比べられる
- **書き込みの範囲は 1 バイトごとに、書く直前に確かめる。** 番地の上位バイトが `XLDR_BASE / $100`（`$68`）未満なら書く。`$67FE` からまたぐレコードも `$6800` の手前で止まる。`XLDR_BASE` が 256B 境界でないとアセンブルエラーにした。レコードの途中で止まったとき、それより前のバイトは書かれたまま残る（`$0000-$67FF` の中だけ）
- **形式はファイルの最初のレコードの先頭の文字で決める**（`S` なら S-record、`:` なら Intel HEX。今までのローダと同じ）。拡張子は見ない。途中で形式が変わるファイルは `?`
- **ローダの中身は今までのものを移した。** S0・S1・S2・S5・S8・S9 と Intel HEX の 00・01、チェックサム、行末の CR／LF の扱いは同じ。`LOADER_STAGE` の書き込み（使っていなかった）は消した。データの書き込みは `X_STORE` の 1 か所にまとめた
- **RUN の番地は「ちょうど 16 進 4 桁」**（今までの `RUN addr` と同じ）。そうでなければファイル名として読む
- **暗黙の `.COM` 検索（決定 5）**: 語に「.」がなければ、窓の resident ワーク（`SDFS3_COM_PATH`、40B）に `/BIN/<語>.COM` を組み、`+5`（`<語>.COM`）から `LOAD_PATH` を呼ぶ。戻ってきて `LAST_ERROR` が 4（見つからない）のときだけ、先頭（`/BIN/<語>.COM`）でもう一度呼ぶ。大きすぎる（8）や SD の失敗（3）では `/BIN` を探さない。語は 31 文字まで（越えたらコード 7）
- **「.」のある語は、最初の「.」から後ろがちょうど `.COM` のときだけ `.COM` として起動する。** `/BIN` は探さない。`HELLO.S`・`A.B.COM` は不明なコマンド（2）。`/BIN/LOAD`（「.」なし）は `/BIN/LOAD.COM`（ルートから見たパス）として読める
- **CCP を 1KB に収めるために縮めた。** 内蔵語（`DIR`・`TYPE`・`EXIT`）と `.COM` の照合を共通の `SDFS3_MATCH` にした。Welcome の行（版と `BASE=`・`END=`）はアセンブル時に 16 進の文字へ組み立てた文字列にした（`function` で数字を文字にする）。どちらも出力は今までと同じ
- **`SDFS3_CCP_BASE` を `$6C00` に戻した。** 試験用に `-D SDFS3_CCP_BASE_TEST=<値>` で下げられるようにし、Makefile の `SDFS3_ASL_DEFS` で渡す（シナリオ 4）。通常のビルドでは使わない
- **テストで resident を作り直すときは、先に `.BIN` と `SDFS3SYS` を消す**（`_remake_sdfs3`）。Make の 1 秒単位の比較で古いイメージが残らないようにした。既存の `test_sdfs3_core_does_not_reference_ccp` の後始末もこれに替えた

## 流れ

```
SDFS3> LOAD HELLO.S
CCP   語 LOAD に「.」なし → /BIN/LOAD.COM を組む → LOAD_PATH(LOAD.COM)✗4 → LOAD_PATH(/BIN/LOAD.COM, exec)
核    $0100 に読む → BIOS_EXEC(WBOOT を積む)
入口  BIOS_GET_API → major 2 → GET_MEMTOP → LOAD_PATH(/BIN/XLDR.OVL, $6800〜memtop)→ 署名 → jmp $6800(A=1)
XLDR  READ_STREAM_OPEN(HELLO.S)→ レコードごとに GETC → $0000-$67FF に書く → CLOSE → "OK" → RTS
ROM   WBOOT → 和の照合(CCP $6C00〜 は無傷)→ CCP +3 → SDFS3>
```

## 検証

`tests/test_sdfs68_v3_build.py` に足したテスト（`build/HELLO.S` など本物のサンプルを使う）:

- `test_xldr_load_run_and_write_range`（シナリオ 1〜3、sbcio_vdg・k6802_vdg）: `LOAD HELLO.S` → `EXIT` → `D0200-0220` が `HELLO.S` のデータと一致 → `DOS`。`RUN HELLO.S` は `HELLO SREC` のあと `BRK 0206`。`F0200-0220 00` で消してから `LOAD HELLO.HEX`（`HELLO.S` を写した Intel HEX）→ `RUN 0200` で同じく動く。`$7000`・`$6800`・`$67FE` からまたぐ・窓（`W+$0C00`）へのレコード、Intel HEX の `RUN`、ないファイル、引数なしの `RUN` は `?`。`$67FF` へは書ける。最後のレコードの後ろに行末がない S-record と Intel HEX も読める。窓の目印と核の先頭 16B は変わらない。本体・入口・resident が別々に持つ `$6800`・`$6C00`・API major が同じで、本体の変数が `$6C00` の手前で終わることも、各リスティングから確かめる。どの `LOAD`・`RUN` のあとも SDFS3SYS を読まず、モニタの門の注意も出ない
- `test_xldr_missing_or_in_root`（両プロファイル）: `XLDR.OVL` がない、署名が違う（`HELLO.COM` を置く）、memtop を 1 バイト越えるときは `LOAD`・`RUN 0300` が `?` で、続く `DIR` が動く。ルートにだけあれば使う
- `test_ccp_implicit_com_search`（両プロファイル）: `HELLO`・`hello` はルートの `HELLO.COM`（`/BIN` の同名より先）、`ARGS AAA BBB` は `/BIN` で引数付き、`/BIN/HELLO`・`BIN/HELLO` は `/BIN/HELLO.COM`。`NOSUCH` は `?`。ルートの `TOOBIG.COM`（`$6F01` バイト）は `?` で、`/BIN/TOOBIG.COM` を探さない（CMD17 の回数が `NOSUCH` より少ない）。`ONLYBIN.COM` は `/BIN` を探さない
- `test_xldr_overlapping_ccp_reloads_only_ccp`（シナリオ 4、両プロファイル）: `CCP_BASE=$6800` の試験用イメージ（Welcome は `BASE=6800`）で `LOAD HELLO.S` が `OK`、戻りで CCP のセクタだけを読み直し、続く `DIR` が動く。後始末で通常のイメージに戻ったことを確かめる

書き換えたテスト:

- `V3_CCP_BASE` を `$6C00` に。Welcome の `BASE=` も同じ
- LOAD・RUN を打つテストのカードに `/BIN` の 3 本を入れた
- `RUN addr` の番地を `$0110`・`$0180` から `$0300` へ、SWI のプログラムを `$0100` から `$0200` へ移した（`RUN.COM` の入口が `$0100-$0188` を上書きする。決定 6）
- `test_sdfs3_cmd_dispatch_parser_classifies_stub_commands`: `LOAD`・`RUN`・未知の語は暗黙の検索に入るので、FAT のないカードではマウントの失敗（3）。`HELLO.S`・`A.COMX`・`A.B.COM` は不明なコマンド（2）、31 文字の語は 3、32 文字は 7 を足した
- `_system_sectors` は CCP の先頭を引数で受ける
- `test_rom_boot3_rejects_bad_images` の「`USER_RAM_END` を越える」: load を `$6C00` 決め打ちから「最後のバイトが `$8000` に来る番地」に変えた（イメージが 4.4KB になり、`$6C00` は正しい load になったため）

## 容量

| | #315 のあと | #316 のあと |
| --- | --- | --- |
| CCP | `$6400-$6BF6`（2039B） | `$6C00-$6FD5`（982B）。1KB 枠の残り 42B |
| 核 | `$7000-$7AD8`（2777B。#317 のあと） | 変わらない。4KB 枠の残り 1319B |
| SDFS3SYS | 5881B（12 セクタ。#317 のあと） | 3833B（8 セクタ） |
| LOAD.COM・RUN.COM | ― | 137B ずつ（`$0100-$0188`） |
| XLDR.OVL | ― | 959B（`$6800-$6BBE`、変数は `$6BBF-$6BD8`）。一時区画の残り 39B |

ROM は変えていない。SD=0 の ROM（base・sbcio）も v3 の ROM（sbcio_vdg・k6802_vdg）も、main（#315 と #317 のマージ後、867c87c）のビルドとバイト単位で一致する。大きさは #317 のあとの main の上に載せ直して測った。

## 後続への引き継ぎ

- #299（SD 生成ツール）: `build/LOAD.COM`・`build/RUN.COM`・`build/XLDR.OVL` を `/BIN` に入れる。プロファイルによらず 1 本
- CCP の残りは 42B。内蔵語を足すと 1KB を越えやすい。越えたら `SDFS3_CCP_BASE` を下げるより先に、CCP の中の共通ルーチンを核へ移すことを考える（`$6C00` を下げると XLDR の区画とかぶり、LOAD のたびに CCP を読み直す）
- 仕様 3-2・決定 6 の入口の大きさ「約 80B」「`$0100-$014F`」（推測）は、実測で 137B・`$0100-$0188` になった
- XLDR の一時区画の残りは 39B。ローダの機能（S3 レコードなど）を足すときは、変数を含めて `$6C00` の手前に収める（アセンブル時に検査する）
