# SBC-IO 拡張RAM RAMTEST確認手順

## 目的

SBC-IO拡張ROM profileで、拡張RAM候補の `$C000-$DFFF` が実機で読み書きできることを確認する。

`RAMTEST` は破壊系コマンドであり、実行中は対象範囲へ `$55` / `$AA` を書き込む。
各バイトの元値は復元するが、実行中に電源断やリセットが発生した場合の内容保持は保証しない。

## 前提

- `sbcio` profile のROMを書き込んでいること。
- `MAP` で `MAP SBCIO`、`WORK C000-DFFF`、`SD C000`、`MON C200` が表示されること。
- `$A000-$BFFF` は K68-VDG VRAM 候補なので、`RAMTEST` の対象にしない。
- `base` profileでは `RAMTEST C000-DFFF` は実行対象外で、`?` を返す。

## 実行手順

1. 起動後、`MAP` でprofileを確認する。

   ```text
   ] MAP
   MAP SBCIO
   RAM 0000-7FFF
   USER 0000-7FFF
   WORK C000-DFFF
   SD C000
   MON C200
   MIK 1F00
   STK 1F42
   ROM E000-FFFF
   ]
   ```

2. `RAMTEST C000-DFFF` を実行する。

   ```text
   ] RAMTEST C000-DFFF
   RAMTEST C000-DFFF
   OK
   ]
   ```

3. 成功後、通常コマンドが復帰していることを確認する。

   ```text
   ] H
   ] MAP
   ] D0100
   ```

4. SDカードを接続している場合は、SD/FAT workが復帰していることも確認する。

   ```text
   ] DIR
   ] LF HELLO.S
   ] D0100
   ```

## 失敗時

失敗した場合は、`NG xxxx` の形式で失敗アドレスを表示する。

```text
] RAMTEST C000-DFFF
RAMTEST C000-DFFF
NG C234
]
```

この場合は、SBC-IO RAM拡張の実装、アドレスデコード、ジャンパ設定、バス配線、該当アドレスが他デバイスと競合していないかを確認する。

## 拒否される入力

初期実装では安全側に倒し、次のような入力は `?` を返す。

```text
] RAMTEST
?
] RAMTEST A000-BFFF
?
] RAMTEST E000-FFFF
?
] RAMTEST 8000-80FF
?
```

任意範囲指定、RAM容量自動検出、長時間バーンインは別Issueで扱う。
