# 診断用S-Record

ROM容量を節約するため、周辺機能の固定診断はROMコマンドではなく、SD上のS-Recordとして実行する。

| ファイル | 用途 |
| --- | --- |
| `VDGA000.S` | K68-VDG VRAM `$A000` 構成向けの画面クリアと固定表示 |
| `VDGC000.S` | K68-VDG VRAM `$C000` 構成向けの画面クリアと固定表示 |
| `KEYTEST.S` | SBC-IO 2nd ACIA `$8094-$8095` の1文字受信確認 |

`.ASM` は元ソース、同名の `.S` はSDへそのまま置くためのS-Recordである。

SDFS/68から実行する例:

```text
SDFS> RUN VDGA000.S
SDFS> RUN KEYTEST.S
```
