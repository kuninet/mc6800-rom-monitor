# ビルド構成軸の設計方針

この文書は、ROMモニタのビルド構成を `MONITOR_PROFILE` だけで増やし続けないための設計方針を定義する。
今後のSD、VDG、2nd ACIAキーボード、I2Cなどの機能追加では、Issue計画時にこの文書を参照し、メモリ配置、外部I/F装備、機能フラグ、依存関係、条件アセンブル対象を分けて検討する。

## 基本方針

`MONITOR_PROFILE` は、互換用かつユーザー向けの完成品プリセット名として維持する。
一方で、新しい設計判断は profile 名そのものではなく、次の構成軸の組み合わせとして扱う。

| 軸 | 意味 |
| --- | --- |
| `MEMORY_CONFIG` | RAM容量、ユーザーRAM、モニタワークRAM、スタック、SD/FATワークの配置 |
| `BOARD_IO` | SBC-IOなど、外部I/O基板やI/Oデコードの有無 |
| `FEATURE_SD` | SD/FAT read-only機能をROMへ入れるか |
| `FEATURE_VDG` | K68-VDG表示機能をROMへ入れるか |
| `FEATURE_KEYBOARD` | 2nd ACIAキーボード入力機能をROMへ入れるか |
| `FEATURE_I2C` | PIA経由I2C機能をROMへ入れるか |

この分離により、たとえば「SBC-IOを装備しているがVDGはない」「K68-VDGを装備しているがワークRAMは `$A000-$BFFF`」「将来I2Cは使うがSDは使わない」といった組み合わせを、profile名の増殖ではなく構成軸で説明できるようにする。

## 構成軸の意味

`MEMORY_CONFIG` は外部I/F装備と独立したメモリ配置の軸である。
初期候補は次の通りとする。

| 値 | 意味 |
| --- | --- |
| `base8k` | SBC6800互換の8KB RAM配置。ワークRAMは低RAM内に置く |
| `ram64_c000_work` | 低位ユーザーRAM `$0000-$7FFF`、ワークRAM `$C000-$DFFF` |
| `ram64_a000_work` | 低位ユーザーRAM `$0000-$7FFF`、ワークRAM `$A000-$BFFF` |

`BOARD_IO` は外部I/O基板やI/Oデコードの軸である。
初期候補は `none` と `sbcio` とする。
SBC-IOを装備していてもメモリ配置は別軸で決めるため、`BOARD_IO=sbcio` だけで `$C000-$DFFF` ワークRAMと決めつけない。

`FEATURE_*` はROMへ機能コードを含めるかどうかの軸である。
非対応機能は実行時に `?` を返すだけでなく、可能な限り条件アセンブルでROMから除外する方針とする。

## 依存関係

機能軸には次の依存関係を置く。

| 機能 | 依存 |
| --- | --- |
| `FEATURE_SD=1` | `BOARD_IO=sbcio` が必要 |
| `FEATURE_KEYBOARD=1` | `BOARD_IO=sbcio` が必要 |
| `FEATURE_I2C=1` | `BOARD_IO=sbcio` が必要 |
| `FEATURE_VDG=1` | SBC-IOとは独立。K68-VDG装備とVRAM配置が必要 |

I2CはSBC-IOのPIAを前提にした将来機能として扱う。
VDGはSBC-IOとは独立した外部表示装備として扱い、VRAM範囲は `MEMORY_CONFIG` とは別に明示する。

## 既存profileの展開

既存の `MONITOR_PROFILE` は、当面は次のプリセットとして扱う。

| `MONITOR_PROFILE` | `MEMORY_CONFIG` | `BOARD_IO` | `FEATURE_SD` | `FEATURE_VDG` | `FEATURE_KEYBOARD` | `FEATURE_I2C` | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | `base8k` | `none` | `0` | `0` | `0` | `0` | SBC6800互換の最小構成 |
| `sbcio` | `ram64_c000_work` | `sbcio` | `1` | `0` | `1` | `0` | SBC-IO RAM拡張とSD/FAT、2nd ACIAキーボード |
| `sbcio_vdg` | `ram64_c000_work` | `sbcio` | `1` | `1` | `1` | `0` | SBC-IO構成でVRAM `$A000-$BFFF` |
| `k6802_vdg` | `ram64_a000_work` | `sbcio` | `1` | `1` | `1` | `0` | K6802-SBC向けにワークRAM `$A000-$BFFF`、VRAM `$C000-$DFFF` |

`FEATURE_KEYBOARD` は2nd ACIAキーボード入力PoCの構成軸であり、該当実装が未統合の時点では将来予定を含む扱いとする。
既存profile名はユーザー向け入口として残し、`MONITOR_PROFILE=base` などのビルド互換を壊さない。

## 将来のMake変数

将来的には、profileプリセットに加えて次のような直接指定を正式入口にできるようにする。

```sh
make bin MEMORY_CONFIG=ram64_a000_work BOARD_IO=sbcio FEATURE_SD=1 FEATURE_VDG=0
```

直接指定を実装する場合も、既存 `MONITOR_PROFILE` はプリセット展開として残す。
直接指定とprofile指定が競合する場合の優先順位、未対応の組み合わせ、出力ファイル名の規則は、実装Issueで明示してから変更する。

## 条件アセンブル方針

機能コードは、可能な限り構成軸に従って条件アセンブルする。

- `FEATURE_SD=0` では、`DIR`、`LF`、SD、FAT32関連コードと文字列をROMから除外する。
- `FEATURE_VDG=0` では、`VDGTEST`、VDG関連コード、VDG用文字列をROMから除外する。
- `FEATURE_KEYBOARD=0` では、2nd ACIA初期化、`KEYTEST`、関連文字列をROMから除外する。
- `FEATURE_I2C=0` では、I2Cドライバ、I2Cコマンド、関連文字列をROMから除外する。

ただし、条件アセンブルによるROMサイズ整理は段階的に行う。
既存コマンドの互換性、エミュレータテスト、実機確認手順を壊さないよう、機能ごとに小さいIssueへ分割する。

## MAP表示方針

`MAP` はprofile名だけでなく、構成軸の結果を説明できる表示へ拡張する。
将来の表示では、少なくとも次を確認できるようにする。

- メモリ構成。
- 外部I/O装備。
- 有効な機能。
- RAM、ワークRAM、SDバッファ、VRAM、主要I/Oアドレス、ROM範囲。

表示形式は実装Issueで決めるが、profile名だけを根拠に機能やメモリ配置を推測しない。
