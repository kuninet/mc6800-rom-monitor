# Issue #182 VDG SDFS/68 CR/LF整理

## 背景

SDFS/68 は行入力に `MIKBUG_INCH` を使う。`MIKBUG_INCH` は入力文字を echo するため、Enter 入力時に `CR` が一度 VDG へ出る。
その後、SDFS/68 の `SDFS_READ_LINE_DONE` でも行入力完了として `CR` を出し、`SDFS_PUTC` が `CR/LF` を補う。

UART側では従来から許容されていたが、VDG console は `CR` を即改行として扱うため、`DIR` や `RUN` の直後に余計な空行が見える。

## 採用方針

- SDFS/68 の行編集ルーチンは変更しない。
- UARTの出力仕様は変更しない。
- VDG console 側で直前 `CR` 状態を見て、連続 `CR` を追加改行として扱わない。
- `CR/LF` の `LF` 抑止、通常文字での `VDG_LAST_CR` リセット、BS/DELでの状態リセットは維持する。

## 検証方針

- `sbcio_vdg` の system SD 起動後に `DIR` を実行し、VRAM dump上で `SDFS> DIR` の直後行が空行にならないことを固定する。
- 既存の VDG CR/LF、BS、scroll smoke test を維持する。
- UART側のSDFS/68既存テストを維持する。

## 対象外

- #183 の 1st ACIA 未接続時スタンドアロン出力。
- #179 の `DS` 短幅ダンプ。
- SDFS/68 行編集仕様の作り直し。
