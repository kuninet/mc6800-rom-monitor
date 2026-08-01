# ROMモニタ コマンドリファレンス

この文書は、SBC6800 実機またはエミュレータ上で ROM モニタを操作するときの使い方をまとめる。
要件や設計判断ではなく、端末から何を入力し、どのような結果を確認するかを中心に書く。

## 前提

- 端末設定は `9600 8N1` とする。
- 入力行終端は `CR` とする。
- 起動時に `MC6800 MONITOR` を表示する。
- モニタのプロンプトは `] ` とする。
- アドレスと値は 16 進数で入力する。
- コマンド名は英大文字で入力する。

## コマンド一覧

この一覧はROMモニタのプロンプト `] ` で使うコマンドである。
SDFS/68 起動後の `SDFS> ` で使う `DIR`、`TYPE`、`RUN`、`LOAD`、`EXIT` は別レイヤーのコマンドであり、このROMコマンド一覧には含めない。

### ROM本線コマンド

ROM単体で使える低レベル操作、復旧口、マシン語デバッグ用のコマンドである。

| コマンド | 用途 |
| --- | --- |
| `D` | 継続アドレスから 64 バイト分をダンプする |
| `Dssss` | `ssss` から 64 バイト分をダンプする |
| `Dssss-eeee` | `ssss` から `eeee` までをダンプする |
| `Mssss` | `ssss` からメモリを変更する |
| `MAP` | 現在のビルドが想定する主要メモリ配置を表示する |
| `RAMTEST ssss-eeee` | 許可された明示範囲のRAMを破壊テストする |
| `Gssss` | `ssss` へジャンプして実行する |
| `L` | S-Record または Intel HEX をロードする |
| `H` | コマンド一覧を表示する |
| `Fssss-eeee vv` | `ssss` から `eeee` までを `vv` で埋める |
| `B` | 現在のブレークポイント状態を表示する |
| `Bssss` | RAM 上の `ssss` に SWI ブレークポイントを設定する |
| `C` | 現在のブレークポイントを解除する |
| `Cssss` | `ssss` のブレークポイントを解除する |
| `R` | SWI ブレーク停止後に再開する |
| `Ussss` | `ssss` から簡易逆アセンブル表示する |
| `UW` | VDG有効ROMで、UART送信待ち状態を表示する |
| `UW ON` | VDG有効ROMで、UART送信時にTDREを待つ |
| `UW OFF` | VDG有効ROMで、UART送信不可なら捨ててVDG出力を優先する |

### SDFS/68起動入口

`BOOT` はROM上のファイル操作コマンドではなく、system SD上のstage1を起動してSDFS/68へ制御を渡す入口である。

| コマンド | 用途 |
| --- | --- |
| `BOOT` | 固定LBAからSDFS/68 stage1 loaderを読み込んで、第2段システムへ移行する。`FEATURE_SD=1` かつ stage1対応RAM構成のROMで有効 |
| `CMD <tail>` | RAM上のSDFS/68 v3 resident APIを検出し、slot 1 `SDFS3_CMD_DISPATCH` へ `tail` を渡す。`FEATURE_SD=1` かつ stage1対応RAM構成のROMで有効 |

### ROM常駐FAT互換コマンド

`DIR` / `LF` は `FEATURE_FAT=1` を直接指定したROMだけに残す互換機能である。
標準profileではROMに入れず、SD上ファイルの通常操作はSDFS/68側で行う。

| コマンド | 用途 |
| --- | --- |
| `DIR` | SDカード上のroot directoryにある8.3通常ファイルを表示する。`FEATURE_FAT=1` のROMだけで有効 |
| `LF filename` | SDカード上の8.3名ファイルを検索して開く。`FEATURE_FAT=1` のROMだけで有効 |

### コマンドの所属

| 所属 | コマンド | 位置づけ |
| --- | --- | --- |
| ROM本線 | `D`、`M`、`G`、`L`、`B`、`C`、`R`、`U`、`UW` など | ROM単体で使う低レベル操作とデバッグ |
| ROM常駐FAT互換 | `DIR`、`LF filename` | `FEATURE_SD=1 FEATURE_FAT=1` を直接指定したときだけ使う互換入口 |
| SDFS/68起動入口 | `BOOT` | system SD上のstage1と `SDFS.BIN` へ渡す入口 |
| SDFS/68 | `DIR`、`TYPE`、`RUN`、`LOAD`、`EXIT` | `SDFS> ` で使う第2段DOSのコマンド |
| stage1内部 | boot services | ユーザーが直接入力しないSDFS/68起動用サービス |

## メモリダンプ

`D` コマンドはメモリ内容を 16 バイト単位で表示する。

```text
] D0100
0100 CE 01 07 BD E0 7E 3F 0D 0A 48 45 4C 4C 4F 2C 20  .....~?..HELLO,
0110 57 4F 52 4C 44 0D 0A 04 08 00 08 0D 00 03 05 0F  WORLD...........
0120 ...
0130 ...
]
```

`Dssss` は指定アドレスから 64 バイト分を表示する。

```text
] D0100
```

`Dssss-eeee` は開始アドレスから終了アドレスまでを表示する。終了アドレスは表示範囲に含まれる。

```text
] D0100-011F
0100 ...
0110 ...
]
```

引数なしの `D` は、前回の続きから 64 バイト分を表示する。

```text
] D0100
...
] D
0140 ...
]
```

開始アドレスが終了アドレスより大きい場合や、範囲指定が欠けている場合は `?` を表示する。

```text
] D0110-0100
?
] D0100-
?
```

`$FFFF` 付近を指定した場合は `$FFFF` までを表示し、`$0000` へラップして表示しない。

## メモリ変更

`Mssss` は指定アドレスから 1 バイトずつメモリを書き換える。
各行で現在アドレス、現在値、入力待ちが表示される。

```text
] M0100
0100: CE - 86
0101: 01 - 42
0102: 07 - .
]
```

値は 1 桁または 2 桁の 16 進数で入力する。
`.` を入力するとメモリ変更を終了する。
不正な値や 3 桁以上の値を入力すると `?` を表示して終了する。

## メモリマップ表示

`MAP` は現在のROMビルドが想定する主要メモリ配置を表示する。RAMを書き換えず、実機上にRAMが存在するかの破壊テストもしない。

```text
] MAP
MAP BASE
RAM 0000-1FFF
USER 0000-1FFF
WORK 1C00-1FFF
MON 1E00
MIK 1F00
STK 1F42
ROM E000-FFFF
]
```

`base` profileは `FEATURE_SD=0`、`FEATURE_VDG=0`、`FEATURE_KEYBOARD=0` のため、SD、VDG、KEYの行を表示しない。

SBC-IO拡張ROMでは `MAP SBCIO` と表示され、`WORK C000-DFFF`、`MON C200`、`MIK C300`、`STK DFFF` などの拡張RAM前提の配置になる。標準の `sbcio` profileはSDなし、ROM常駐FATなしであり、`DIR` / `LF` / `BOOT` は有効にならない。
`FEATURE_KEYBOARD=1` のROMでは、2nd ACIAキーボード入力候補として `KEY 8094-8095` も表示する。

K68-VDG表示PoC用の `sbcio_vdg` profileでは、SBC-IO拡張ROMの配置に加えて K68-VDG 用の VRAM と設定レジスタを表示する。ROM容量をVDG/キーボード/BOOTへ寄せるため、ROM常駐FATの `DIR` / `LF` は無効で、SDからの第2段起動は `BOOT` を使う。

```text
] MAP
MAP SBCIO VDG
RAM 0000-7FFF
USER 0000-7FFF
WORK C000-DFFF
SD C000
MON C200
MIK C300
STK DFFF
VRAM A000-BFFF
VDG 8110
KEY 8094-8095
ROM E000-FFFF
]
```

K6802-SBCでK68-VDGのVRAMを `$C000-$DFFF` に置く `k6802_vdg` profileでは、SD/FATとモニタのワーク領域を `$A000-$BFFF` に移す。

```text
] MAP
MAP K6802 VDG
RAM 0000-7FFF
USER 0000-7FFF
WORK A000-BFFF
SD A000
MON A200
MIK A300
STK BFFF
VRAM C000-DFFF
VDG 8110
KEY 8094-8095
ROM E000-FFFF
]
```

新SDFS/68固定領域（16KB級拡張）の `ram64_4000_work` 構成では、TPA（ユーザーRAM）が `$3FFF` 上限へ下がり、作業領域が `$4000-$7FFF` に移るため、次のような表示になります（VDG無効・SD有効の例）。

```text
] MAP
MAP SBCIO
RAM 0000-7FFF
USER 0000-3FFF
WORK 4000-7FFF
SD C000
MON 4200
MIK 4300
STK 7FFF
KEY 8094-8095
ROM E000-FFFF
]
```

SDセクタバッファの番地は、S1/SDFS固定領域 `$4000-$7FFF` の中ではなく、ジャンパ選択されたバンク窓（上の例では `$C000`）へ正しく残されます。

## K68-VDG表示

`FEATURE_VDG=1` のROMでは、起動メッセージ、プロンプト、通常の文字出力をUARTとK68-VDG画面の両方へ出す。
K68-VDG の設定レジスタは `$8110`、VRAMは `sbcio_vdg` で `$A000-$BFFF`、`k6802_vdg` で `$C000-$DFFF` を使う。

VDG有効ROMでは、32桁画面向けの短幅ダンプ `DS` も使える。
`DS`、`DS0100`、`DS0100-011F` の形式で、1行はアドレスと8 byte分のHEXだけを表示し、ASCII欄は出さない。
表示は `0100 00 01 02 03 04 05 06 07` のように32桁以内へ収める。

VDG有効ROMでは、1st ACIA UART出力を補助コンソールとして扱う。
デフォルトの `UW OFF` では、1st ACIA の `TDRE` が立っていない文字は捨てて、VDG画面とキーボード操作を止めない。
Mac側でUSBシリアルログを確実に取りたい場合は `UW ON` を実行すると、従来どおり `TDRE` を待って送信する。
ただし `UW ON` は、USBシリアル未接続、制御線の状態異常、またはACIA送信不可の状態では停止し得る。

ROM容量を節約するため、画面クリアと固定文字列表示だけの `VDGTEST` コマンドはROMから外した。
必要な場合は `diagnostics/VDGA000.S` または `diagnostics/VDGC000.S` をSDへ置き、SDFS/68から `RUN` する。

```text
SDFS> RUN VDGA000.S
```

## 2nd ACIAキーボード入力

SBC-IOの2nd ACIA `$8094-$8095` は、KKBD-USBなどのUARTキーボードI/F接続先として扱う。
ROM容量を節約するため、受信確認だけの `KEYTEST` コマンドはROMから外した。
必要な場合は `diagnostics/KEYTEST.S` をSDへ置き、SDFS/68から `RUN` する。

```text
SDFS> RUN KEYTEST.S
KEY 41 A
```

通常のモニタ入力、MIKBUG互換 `INEEE`、BASIC入力は、まだ2nd ACIAへ切り替えない。これは後続Issueで扱う。

## RAM確認

`RAMTEST ssss-eeee` は、許可された範囲内のRAMを確認する破壊系コマンドである。
実行中は対象範囲へ `$55` / `$AA` を書き込み、読出し確認後に元値へ戻す。

```text
] RAMTEST C000-DFFF
RAMTEST C000-DFFF
OK
]
```

安全のため、指定範囲全体がビルドプロファイルで有効化された単一の許可領域に完全包含される場合だけ実行する。
`RAMTEST` 自身はゼロページ `$00F0-$00F5` を一時ワークに使い、実行中のスタックもゼロページ直下へ移すため、`$0000-$00FF` は検査対象外にする。
ゼロページの作業領域と一時スタック領域は指定範囲外でも書き換わるため、`RAMTEST` 前後で `$0000-$00FF` の内容保持は保証しない。
`base` profileでは `0100-1BFF` 内の範囲だけを許可する。
`sbcio` / `sbcio_vdg` profileでは `0100-7FFF`、`C000-DFFF` 内の範囲を許可する。
`k6802_vdg` profileでは `0100-7FFF`、`A000-BFFF` 内の範囲を許可する。
たとえば `sbcio` では `RAMTEST 2000-3FFF` や `RAMTEST C200-C2FF` は実行できる。
無引数、片側欠落、5桁以上、余分な文字、開始 > 終了、`0000-00FF` や `7FFF-C000` のように許可領域外を含む範囲は `?` を返す。
`sbcio_vdg` の `$A000-$BFFF` や `k6802_vdg` の `$C000-$DFFF` はK68-VDG VRAMなので触らない。

失敗時は `NG xxxx` の形式で失敗アドレスを表示する。

```text
] RAMTEST C000-DFFF
RAMTEST C000-DFFF
NG C234
]
```

電源断やリセットが途中で発生した場合の内容保持は保証しない。

## 実行

`Gssss` は指定アドレスへジャンプして実行する。

```text
] G0100
```

モニタへ戻るには、実行先のプログラムが `SWI` などでモニタへ戻る必要がある。
戻らないプログラムを実行した場合、端末操作だけでは復帰できないことがある。

## ロード

`L` はローダモードに入り、S-Record または Intel HEX を受信する。
最初の有効レコードの先頭が `S` なら S-Record、`:` なら Intel HEX として扱う。

```text
] L
L
S1060200010203F1
S9030000FC
OK
]
```

正常終了すると `OK` を表示する。
異常時は `?S1` から `?S5`、または `?I1` から `?I5` のようなデバッグ表示を返す。

ロード処理はレコードを受信しながら解析する。
ロード中の進捗表示は速度を優先して行わず、正常終了時は `OK`、異常時は `?S1` から `?S5`、または `?I1` から `?I5` を表示する。

`LF filename` は `FEATURE_FAT=1` のROMで、SDカード上のroot directoryから8.3 short filenameのファイルを検索し、S-RecordまたはIntel HEXとしてロードする。
既存の `L` とは別の入口だが、レコード解析とRAM書き込みは同じローダ処理を使う。

```text
] LF TEST.S
OK
]
```

ファイル名の前後の空白は無視する。subdirectory、LFN、wildcardは対象外である。
LOAD後の自動実行は行わない。必要に応じて `Gssss` で開始アドレスへジャンプする。
`FEATURE_FAT=0` のROMでは `LF` のコマンド本体をROMに入れず、未対応コマンドとして `?` を返す。
標準profileでは、SD上ファイルの通常ロードはROMでは行わない。
`BOOT` でSDFS/68を起動してから、SDFS/68側の `L filename` または `LOAD filename` を使う。

SDFS/68はROMモニタとは別の第2段システムとして扱う。SDFS/68側の `DIR`、`TYPE`、`RUN`、`LOAD`、`EXIT` は [SDFS/68 システムSDカード方針](sdfs68_system_sd.md) に記載する。

## SD directory

`DIR` は `FEATURE_FAT=1` のROMで、SDカード上のroot directoryにある8.3通常ファイルを表示する。
LFN、削除entry、volume label、subdirectoryは表示しない。
ROM側の `DIR` とSDFS/68側の `DIR` は名前が同じでも別機能である。
ROM側 `DIR` は `FEATURE_SD=1 FEATURE_FAT=1` を直接指定したときだけ使う互換機能、SDFS/68側 `DIR` は `SDFS> ` で使う通常運用コマンドとして扱う。

```text
] DIR
TEST.S A 0000001E
TEST.HEX A 00000020
MULTI.BIN A 00000400
]
```

サイズは8桁16進で表示する。`DIR` は `D` dumpとは別コマンドであり、従来の `D0100` や `D0100-011F` はそのまま使える。
`FEATURE_FAT=0` のROMでは `DIR` のコマンド本体をROMに入れず、`D` dump以外の未対応入力として `?` を返す。

## ヘルプ

`H` は短いコマンド一覧を表示する。

```text
] H
D M MAP RAMTEST G L B C R U H F
]
```

`FEATURE_SD=1` かつ `FEATURE_FAT=0` のROMでは、固定LBA stage1起動用の `BOOT` を含めて表示する。

```text
] H
D M MAP RAMTEST G L BOOT CMD B C R U H F
]
```

`FEATURE_FAT=1` のROMでは、ROM常駐FAT互換機能として `DIR` と `LF` を含めて表示する。

```text
] H
D DIR M MAP RAMTEST G L LF BOOT CMD B C R U H F
]
```

`FEATURE_SD=1` かつ `FEATURE_FAT=0` のROMでは、ROM側FAT互換コマンドではなく `BOOT` を含める。VDG/キーボード診断はROMコマンドではなく、SD上の診断用S-Recordから実行する。

```text
] H
D M MAP RAMTEST G L BOOT CMD B C R U H F
]
```

## メモリフィル

`Fssss-eeee vv` は開始アドレスから終了アドレスまでを `vv` で埋める。
終了アドレスは範囲に含まれる。

```text
] F0100-01FF 00
]
```

主用途は RAM 領域の初期化である。
開始アドレスが終了アドレスより大きい場合、範囲指定や値が欠けている場合、値が 3 桁以上の場合は `?` を表示する。

## SWIブレーク

`Bssss` は RAM 上の指定アドレスへ SWI 命令 `$3F` を書き込み、ソフトウェアブレークポイントを設定する。
設定時に元の 1 バイトはモニタ内部へ保存される。

```text
] B0105
]
```

`B` は現在のブレークポイント状態を表示する。

```text
] B
BP NONE
]
] B0105
] B
BP 0105
]
```

ブレークポイント v1 は単一箇所のみ対応する。
別の `Bssss` を設定すると、現在のブレークポイントを復元してから新しい場所へ設定する。
ROM 領域への `B` は対象外で、`?` を表示する。

```text
] BE200
?
]
```

ブレークポイントに到達すると、モニタは元バイトを復元し、ブレークポイントを自動解除する。
停止時はレジスタを短い形式で表示する。

```text
BRK 0105 A=12 B=34 X=2000 SP=1F20 CC=C0
]
```

表示する `BRK` のアドレスは、SWI 命令の次ではなく、停止したブレークアドレスである。

`R` は保存済みの SWI フレームを使って、復元済みの元命令から再開する。
同じ場所で再び止めたい場合は、再開後または停止後にもう一度 `Bssss` を設定する。

```text
] R
```

`C` は現在のブレークポイントを解除する。
`Cssss` は指定アドレスのブレークポイントだけを解除する。

```text
] C
]
] C0105
]
```

## 簡易逆アセンブル

`Ussss` は指定アドレスから 8 命令分を簡易逆アセンブル表示する。

```text
] U0100
0100 86 LDAA #$12
0102 B7 STAA $0120
0105 3F SWI
0106 FF DB $FF
]
```

対応命令は主要命令と、現在のモニタや SBC6800 データパック確認でよく使う命令に限定する。
未対応 opcode は `DB $xx` と表示し、1 バイト進める。

簡易アセンブラは未実装である。
短いパッチは `M` コマンド、まとまったコードは PC 側でアセンブルして `L` コマンドでロードする。

## 小さいプログラムでの確認例

次の例は、`$0120` に `$42`、`$0121` に `$99` を書き込む短いプログラムを RAM に入れ、2 回目のストア直前で止める。

```text
] M0100
0100: .. - 86
0101: .. - 42
0102: .. - B7
0103: .. - 01
0104: .. - 20
0105: .. - 86
0106: .. - 99
0107: .. - B7
0108: .. - 01
0109: .. - 21
010A: .. - 3F
010B: .. - .
]
] B0105
] G0100
BRK 0105 A=42 B=.. X=.... SP=.... CC=..
] D0120-0121
0120 42 00  B.
] R
] D0120-0121
0120 42 99  B.
]
```

この例では、`B0105` で `$0105` の `LDAA #$99` の位置にブレークを置く。
ブレーク停止時点では `$0120` だけが更新され、`R` で再開すると元命令から実行されて `$0121` も更新される。
