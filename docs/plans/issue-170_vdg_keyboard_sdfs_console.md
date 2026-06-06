# Issue #170 VDG+keyboard SDFS/68統合確認

## 背景

#167、#168、#169 により、ROMモニタのVDG表示、行制御、2nd ACIAキーボード入力は段階的に整った。
#170 では、その入口をSDFS/68起動後にも使い、スタンドアロンパソコン的に操作できることを確認する。

## 前提PR

- #197: SDFS/68のVDG余分改行を抑止する。
- #198: VDG有効時、1st ACIA送信待ちで停止しない。
- #199: VDG 32桁向けの `DS` を追加する。

## 採用方針

- SDFS/68の行編集ルーチンは当面そのまま使う。
- 入力入口は `MIKBUG_INCH` 経由の2nd ACIA優先/UART fallbackを使う。
- 出力入口は `MIKBUG_OUTCH` / `OUTEEE` 経由でVDGとUARTを併用する。
- UARTはデバッグ用に残すが、VDG+keyboardだけでも起動表示とSDFS操作に到達できる状態を目標にする。

## 検証方針

- 自動テストでは、#197、#198、#199 の各PRで個別の再現条件を固定する。
- #170 では実機確認手順を `docs/testing/vdg_keyboard_sdfs68_console.md` に残す。
- #170 をcloseする判断は、実機で `BOOT`、`DIR`、`LOAD`、`RUN`、`EXIT` を確認してから行う。

## 対象外

- SDFS/68の高度な行編集。
- UARTを完全に削除するprofile。
- VDGカーソルの点滅や画面属性制御。
- `.COM` ABIの変更。
