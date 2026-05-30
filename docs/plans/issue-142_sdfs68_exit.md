# Issue #142 SDFS/68 EXIT 実装

## 背景

SDFS/68は通常運用の第2段DOSとして扱い、メモリ変更、ブレークポイント、逆アセンブルなどの低レベルデバッグはROMモニタへ残す。
そのため、SDFS/68からROMモニタの `] ` プロンプトへ戻る明示的な出口が必要である。
起動メッセージは `SDFS/68 V1.2 #142` とする。
メジャー/マイナー番号はSDFS/68の機能世代、`#142` は元Issue番号をbuild番号相当として扱う。

## 採用仕様

- `SDFS> EXIT` でROMモニタへ戻る。
- `EXIT` は完全一致を基本とし、余分な引数は `?` にする。
- 小文字入力は既存コマンドと同じく大文字扱いで受け付ける。
- `EXIT` 後にROM側で再度 `BOOT` すれば、SDFS/68へ戻れる。

## 実装判断

ROM側 `CMD_BOOT` は stage1 entry へ `jmp` し、stage1もSDFS/68 entryへ `jmp` する。
そのため、SDFS/68には戻り番地がなく、`EXIT` を `rts` で実装することはできない。

`EXIT` は `MONITOR_REENTRY` へ `jmp` する。
`MONITOR_REENTRY` は現行ROMの `MONITOR_ENTRY_NO_KEYBOARD` に相当する `MONITOR_BASE+$000D` で、ACIA再初期化を避けて `MAIN_LOOP` へ戻る入口として扱う。
SDFS/68側で `STACK_TOP` を設定してから飛ぶため、SDFS/68内部の呼び出しstackは持ち越さない。
ROMモニタ状態の完全初期化は対象外で、必要ならリセット操作で行う。

## 確認内容

- `python3 tests/test_sdfs68_build.py`
- `MONITOR_PROFILE=sbcio_vdg make stage1 sdfs`
- `MONITOR_PROFILE=k6802_vdg make stage1 sdfs`

テストでは `BOOT -> EXIT -> BOOT` がタイムアウトせず、SDFS/68 bannerが2回表示されることを確認する。

## 実機確認手順

1. 新しい `SDFS.BIN` をsystem SDのrootへコピーする。
2. `] BOOT` でSDFS/68を起動する。
3. `SDFS> EXIT` でROMモニタの `] ` プロンプトへ戻ることを確認する。
4. `] BOOT` でもう一度SDFS/68を起動できることを確認する。

## 対象外

- ROMモニタ状態の完全初期化。
- ユーザープログラムからSDFS/68へ戻るABI。
- SDFS/68の常駐復帰機構。
