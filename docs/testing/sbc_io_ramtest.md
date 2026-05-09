# SBC-IO拡張RAM RAMTEST確認手順

## 目的

SBC-IO拡張ROM profileで、拡張RAM候補の `$2000-$7FFF` と `$C000-$DFFF` が実機で読み書きできることを確認する。
`RAMTEST` は破壊系コマンドであり、実行中は対象範囲へ `$55` / `$AA` を書き込む。
各バイトの元値は復元するが、実行中に電源断やリセットが発生した場合の内容保持は保証しない。

## 前提

- `sbcio` profile のROMを書き込んでいること。
- `MAP` で `MAP SBCIO`、`WORK C000-DFFF`、`SD C000`、`MON C200` が表示されること。
- `$A000-$BFFF` は K68-VDG VRAM 候補なので、`RAMTEST` の対象にしない。
- `RAMTEST` 自身はゼロページ `$00F0-$00F5` を一時ワークに使い、実行中のスタックもゼロページ直下へ移すため、`$0000-$00FF` は検査対象外にする。
- ゼロページの作業領域と一時スタック領域は指定範囲外でも書き換わるため、`RAMTEST` 前後で `$0000-$00FF` の内容保持は確認対象にしない。
- `base` profileでは `0100-1BFF` 内だけを許可し、`2000-7FFF` や `C000-DFFF` は `?` を返す。

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

2. 標準RAM側の安全範囲を確認する。

   ```text
   ] RAMTEST 0100-1BFF
   RAMTEST 0100-1BFF
   OK
   ]
   ```

3. SBC-IO拡張RAMを含む `$0100-$7FFF` 内を確認する。
   まずは短い範囲で試し、必要なら全域へ広げる。

   ```text
   ] RAMTEST 0100-7FFF
   RAMTEST 0100-7FFF
   OK
   ]
   ] RAMTEST 2000-3FFF
   RAMTEST 2000-3FFF
   OK
   ]
   ] RAMTEST 4000-7FFF
   RAMTEST 4000-7FFF
   OK
   ]
   ```

4. SBC-IO拡張work領域の `$C000-$DFFF` 内を確認する。

   ```text
   ] RAMTEST C200-C2FF
   RAMTEST C200-C2FF
   OK
   ]
   ] RAMTEST C000-DFFF
   RAMTEST C000-DFFF
   OK
   ]
   ```

5. 成功後、通常コマンドが復帰していることを確認する。

   ```text
   ] H
   ] MAP
   ] D0100
   ```

6. SDカードを接続している場合は、SD/FAT workが復帰していることも確認する。

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
] RAMTEST 0000-00FF
?
] RAMTEST 1BFF-2000
?
] RAMTEST E000-FFFF
?
] RAMTEST DFFF-E000
?
```

任意の許可領域追加、RAM容量自動検出、長時間バーンインは別Issueで扱う。
