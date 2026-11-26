# Issue #315 v3 のファイル API（slot 2〜5）を実装し、`.COM` の起動を核へ移す

親epic: #296。正の仕様は `issue-310_plan_b_abi.md` の 2-3・2-4・4-1。#313・#314・#307 の上に作った。

## 確認した事実

- 着手時（main 5d6b194）は、CCP が `$6400-$6C55`（2134B）、核が `$7000-$7C3E`（3135B）、SDFS3SYS が 6239B。slot 2〜5 は `SDFS3_NOT_IMPLEMENTED` を指していた
- `.COM` の起動は CCP の中で、パス解析 → mount → 解決 → 拡張子 → 大きさ（`$6300` バイトまで）→ 生ロード → `BIOS_EXEC` だった
- 行バッファ `LINE_BUF` は窓（`MONITOR_RAM_BASE`）にある。`.COM` の引数の文字列は、TPA を潰しても残る
- `FAT32_STREAM_GETC` は `SD_SECTOR_BUF` に今のセクタを持ち、次の呼び出しでもそれを当てにする
- `.COM` のコマンドでは、mount（LBA 0 と BPB）とルートのディレクトリで CMD17 が 3 回あり、ファイルの中身はその後に読む。Issue のシナリオ 3 の「3 回目の CMD17」は、ディレクトリの読み出し（読み込みの前）に当たる
- `BIOS_GET_API` は区画の自己検査に通れば C=0・X = 核の先頭（SDFS3API ヘッダ）を返す

## 採用した判断

- **`LOAD_PATH` はブロックを最初に窓のワークへ写す。** 読み込みでブロックが潰れても、起動の引数（entry・argptr・arg_len）は残る。entry と argptr は `SDFS3_EXEC_BLOCK` にそのまま入れる
- **大きさの検査は読み込みの前に全部行う。** 0 バイト、`$10000` バイト以上、`limit > GET_MEMTOP`、`limit < load`、`size-1 > limit-load` はコード 8（新設 `SDFS3_ERR_TOO_BIG`）で C=1。`limit` を `GET_MEMTOP` までにしたのは、核の中のローダが自分を潰さないため（窓や I/O にも書かない）
- **読み込みの途中の失敗は flags によらず WBOOT へ。** 仕様 2-3 の文のとおり。核には、呼び手の場所が読み込みで潰れたかどうかが分からない。`LAST_ERROR` と `SDFS3_PENDING_ERR` に 3 を入れて `jmp BIOS_WBOOT`。WBOOT は壊れた区画を読み直し、CCP の warm 入口が `?` を 1 回出して `PENDING_ERR` を消す。読み込みのループに入ったあと（`FAT32_STREAM_GETC` の失敗）を「途中」とした
- **mount し直すのはパスを取る API（`LOAD_PATH`・`OPEN`）。** Issue の「どの API も mount し直す」をこう読んだ。`GETC` で mount すると読みかけの位置を失う
- **取っ手は 1 本で、窓のワーク（`SDFS3_STREAM_OPEN`）に置く。** `LOAD_PATH`・`OPEN`・`INIT`・CCP の warm 入口で閉じる。前のプログラムの取っ手を次のプログラムへ持ち越さない（CCP の `DIR`・`TYPE` も `FAT_*` と `SD_SECTOR_BUF` を使うため）。閉じた取っ手の `GETC` はコード 9（新設 `SDFS3_ERR_NOT_OPEN`）
- **`GETC` は B と X を保つ。** #316 の XLDR が 1 バイトずつ読むときに扱いやすい。終わりは C=1・`LAST_ERROR` = 0、SD の失敗は C=1・3（`FAT_BYTES_REMAIN` で見分ける）
- **`LOAD_PATH`（bit0 = 0）は C=0・X = 読み込んだ末尾の次の番地を返す。** 呼び手が読み込んだ大きさを知るため
- **`SDFS3_EXEC`（`BIOS_EXEC` を呼ぶ部分）を CCP から核へ移した。** 核から CCP を参照しないため。CCP の `RUN` も核のこれを使う（CCP → 核の参照はよい）
- **CCP の `.COM` は、パスと引数を解析してブロックを組み、`LOAD_PATH` へ `jmp` するだけにした。** 戻ってくるのは読み込みを始める前の失敗だけで、`LAST_ERROR` は核のコード（見つからない 4、大きすぎる 8 など）を残す。`SDFS3_ERR_COM`（7）はパスの解析の失敗だけになった。`SDFS3_COM_CHECK_SIZE`・`SDFS3_COM_LOAD_RAW`・`SDFS3_PARSE_COM_CHECK_EXT` は消した（拡張子は語の照合 `SDFS3_IS_COM_TOKEN` が見ている）
- `SDFS3_COM_MAX` は `SDFS3_CORE_BASE - $0100`（`$6F00`）。`SDFS3_CCP_BASE` は #316 まで `$6400` のままなので、`$6300` バイトを超える `.COM` は CCP を潰し、戻りで CCP が読み直される
- CCP の `LOAD`・`RUN` は変えていない（#316 で外す）

## 流れ

```
CCP  SDFS3_CMD_COM ─ パス・引数を解析 ─ ブロック（load=$0100, limit=$6FFF, bit0）─ jmp LOAD_PATH
核   LOAD_PATH ─ ブロックを写す → 取っ手を閉じる → MOUNT → 解決 → 大きさ ✗ → C=1（CCP が ?）
                 └ 読み込み ✗ → PENDING_ERR=3 → jmp BIOS_WBOOT
                 └ bit0 → SDFS3_EXEC → BIOS_EXEC（戻らない）／ bit0=0 → C=0, X=末尾+1
ROM  BIOS_WBOOT → 和の照合 → 壊れた区画だけ読み直す → CCP +3 → PENDING_ERR なら ? → SDFS3>
```

## 検証

エミュレータに `--sd-fail-cmd17-count N` を足した。`--sd-fail-cmd17-from` の番号から N 回だけ失敗させる（一時的な読み出しの失敗。続く読み直しは成功する）。

`tests/test_sdfs68_v3_build.py`（sbcio_vdg・k6802_vdg の両方）に足したテスト:

- `test_com_max_size_runs_and_returns_through_reload`（シナリオ 1〜3）
  - `$6F00` バイト（NOP の並び、`$6FFF` が RTS）は何も出さずに戻り、戻りで CCP のセクタだけを読み直す。CCP の先頭は SD と同じに戻り、続く `DIR` が動く
  - `$6F01` バイトは `?`。CMD17 は mount とディレクトリの 3 回以下で、SDFS3SYS は読まない。`$0100` の目印は残る
  - 4KB の `.COM` を読み込みの 3 回目の CMD17 から失敗させる: `?` が 1 回で `SDFS3> `。`$0100` はファイルの中身に替わっている（読み込みが始まっていた）。CCP は無傷で読み直さない。`PENDING_ERR` は 0
  - Issue の字面どおりコマンドの頭から 3 回目（ディレクトリ）で 1 回だけ失敗: `?` が 1 回、`$0100` の目印は残る（読み込みの前の C=1）
  - `$6F00` バイトの `.COM` を最後のデータのセクタで 1 回だけ失敗: WBOOT が CCP のセクタを読み直し、`?` が 1 回で `SDFS3> `、続く `DIR` が動く
- `test_read_stream_api_from_com`（シナリオ 4）: `BIOS_GET_API` で表を引く `STREAM.COM` が、slot 3〜5 で `/HELLO.S` を 1 バイトずつ読む（`GETC` が B と X を保つことも確かめる）。終わりで C=1・`GET_ERROR` = 0、`CLOSE` のあとの `GETC` は C=1・9、`MISSING.S` の `OPEN` は C=1・4。`LOAD_PATH`（bit0 = 0）で README を `$0500` にちょうど読めて C=0・X = 末尾+1、1 バイト足りない `limit` と `GET_MEMTOP` を越える `limit` はコード 8

書き換えたテスト:

- `test_sdfs3_profiles_build_and_match_header`: slot 2〜5 が `NOT_IMPLEMENTED` ではないこと。`INIT` のバイト列に `clr SDFS3_STREAM_OPEN` を足した
- `test_sdfs3_cmd_load_run_and_com_read_fat_files`: 大きさの境界（`BIG.COM`・`MAX.COM`）を上の新しいテストへ移した
- `test_sdfs3_resident_image_unchanged_after_commands`: `NOFILE.COM` のあとの `LAST_ERROR` は 4（見つからない）
- `test_sdfs3_cmd_dispatch_parser_classifies_stub_commands`: FAT のないカードで `FOO.COM` を打ったときのコードは 3（マウントの失敗。今までは CCP が 7 に置き換えていた）

## 容量

| | main（#317 のあと、97794b7） | #315 のあと |
| --- | --- | --- |
| CCP | `$6400-$6C55`（2134B） | `$6400-$6BF6`（2039B、−95B） |
| 核 | `$7000-$79BA`（2491B） | `$7000-$7AD8`（2777B、+286B）。4KB 枠の残り 1319B |
| SDFS3SYS | 5595B（11 セクタ） | 5881B（12 セクタ） |

#317（SD ドライバを ROM の BIOS 入口へ寄せた）の上に載せ直して測った。#317 の前（main 5d6b194）の上では、核は `$7000-$7D5C`（3421B）だった。ROM は変えていない（ROM のソースに差分がない）。SD=0 の ROM（base・sbcio）も v3 の ROM（sbcio_vdg・k6802_vdg）も main と同じになる。

## 後続への引き継ぎ

- #316: XLDR.OVL の入口は `READ_STREAM_OPEN`／`GETC`／`CLOSE` で `/BIN/XLDR.OVL` を `$6800` から読む。`GETC` は B と X を保つ。`LOAD_PATH`（bit0 = 0、`load` = `$6800`、`limit` = `$6BFF`）でも読める。CCP から `LOAD`・`RUN` を外したら `SDFS3_CCP_BASE` を `$6C00` に戻す。そのとき `.COM` の上限（`$6F00`）は変わらない
- #316: 核の 4KB 枠の残りは 1319B（#317 のあと）
- `LOAD_PATH` の読み込みは、今までの CCP の生ロードと同じく 1 バイトずつ `FAT32_STREAM_GETC` を呼ぶ。実機で `$6F00` バイトが遅ければ、セクタ単位の写しに替える余地がある
