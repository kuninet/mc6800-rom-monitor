# ビルド構成軸の設計方針

この文書は、ROMモニタのビルド構成を `MONITOR_PROFILE` だけで増やし続けないための設計方針を定義する。
今後のSD、VDG、2nd ACIAキーボード、I2Cなどの機能追加では、Issue計画時にこの文書を参照し、メモリ配置、外部I/F装備、機能フラグ、依存関係、条件アセンブル対象を分けて検討する。

## 基本方針

`MONITOR_PROFILE` は、互換用かつユーザー向けの完成品プリセット名として維持する。
一方で、新しい設計判断は profile 名そのものではなく、次の構成軸の組み合わせとして扱う。

| 軸 | 意味 |
| --- | --- |
| `MEMORY_CONFIG` | RAM容量、ユーザーRAM、モニタワークRAM、スタック、SD workの配置 |
| `BOARD_IO` | SBC-IOなど、外部I/O基板やI/Oデコードの有無 |
| `FEATURE_SD` | raw SD sector readと固定LBA stage1 `BOOT` をROMへ入れるか |
| `FEATURE_FAT` | ROM常駐のFAT32 `DIR` / `LF` を入れるか |
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
| `ram64_4000_work` | 低位ユーザーRAM `$0000-$3FFF` (16KB TPA)、SDFS固定領域 `$4000-$7FFF` (16KB)。SDセクタバッファはバンク窓 `$C000` または `$A000` に残す |

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
| `FEATURE_FAT=1` | `FEATURE_SD=1` が必要 |
| `FEATURE_KEYBOARD=1` | `BOARD_IO=sbcio` が必要 |
| `FEATURE_I2C=1` | `BOARD_IO=sbcio` が必要 |
| `FEATURE_VDG=1` | SBC-IOとは独立。K68-VDG装備とVRAM配置が必要 |

I2CはSBC-IOのPIAを前提にした将来機能として扱う。
VDGはSBC-IOとは独立した外部表示装備として扱い、VRAM範囲は `MEMORY_CONFIG` とは別に明示する。

ただし、I2CはRTC、EEPROM、OLED/LCDなど個別デバイス処理を含めるとROM容量を急速に消費する。8KB ROM互換を維持する間は、`FEATURE_I2C=1` を「I2C関連コードを無条件にROMへ押し込む入口」として使わない。ROM側へ入れる場合でも、最小BOOTや診断用の薄い入口に限定し、I2Cバスドライバ本体や個別デバイス機能はシリアル `L`、ROM常駐FATがある構成の `LF`、または `SDFS.BIN` など第2段のRAMロード機能として検証する。

`FEATURE_SD=1` はraw SD sector readと固定LBA stage1 `BOOT` の前提を表す。ROM常駐のFAT32 `DIR` / `LF` は `FEATURE_FAT=1` として分ける。標準profileではROM容量確保と責務整理のため `FEATURE_FAT=0` を基本にし、`base` / `sbcio` は `FEATURE_SD=0`、VDG付きprofileは `FEATURE_SD=1` / `FEATURE_FAT=0` にする。
ただし、stage1 / SDFS/68生成可否はprofile名ではなく構成軸で判断する。`BOARD_IO=sbcio`、`FEATURE_SD=1`、`MEMORY_CONFIG=ram64_c000_work` または `ram64_a000_work` の組み合わせなら、VDGなしのSBC-IO構成でも `BOOT + SDFS/68` 用のROM、stage1、`SDFS.BIN` を生成できる。

## 既存profileの展開

既存の `MONITOR_PROFILE` は、当面は次のプリセットとして扱う。

| `MONITOR_PROFILE` | `MEMORY_CONFIG` | `BOARD_IO` | `FEATURE_SD` | `FEATURE_FAT` | `FEATURE_VDG` | `FEATURE_KEYBOARD` | `FEATURE_I2C` | 補足 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `base` | `base8k` | `none` | `0` | `0` | `0` | `0` | `0` | SBC6800互換の最小構成 |
| `sbcio` | `ram64_c000_work` | `sbcio` | `0` | `0` | `0` | `1` | `0` | SBC-IO RAM拡張と2nd ACIAキーボード。SDなし |
| `sbcio_vdg` | `ram64_c000_work` | `sbcio` | `1` | `0` | `1` | `1` | `0` | SBC-IO構成でVRAM `$A000-$BFFF`、ROM FATなし |
| `k6802_vdg` | `ram64_a000_work` | `sbcio` | `1` | `0` | `1` | `1` | `0` | K6802-SBC向けにワークRAM `$A000-$BFFF`、VRAM `$C000-$DFFF`、ROM FATなし |
| `sbcio_4000` | `ram64_4000_work` | `sbcio` | `1` | `0` | `0` | `1` | `0` | SBC-IO 16KB固定領域構成、VRAM `$A000-$BFFF` 想定 (SDバッファ `$C000` 配置) |
| `k6802_4000` | `ram64_4000_work` | `sbcio` | `1` | `0` | `0` | `1` | `0` | K6802-SBC向け16KB固定構成、VRAM `$C000-$DFFF` 想定 (SDバッファ `$A000` 配置) |

`FEATURE_KEYBOARD` は2nd ACIAキーボード入力PoCの構成軸であり、SBC-IOの2nd ACIA `$8094-$8095` を前提にする。
既存profile名はユーザー向け入口として残し、`MONITOR_PROFILE=base` などのビルド互換を壊さない。

## Make変数

profileプリセットに加えて、構成軸の直接指定を正式入口として使える。

```sh
make bin MEMORY_CONFIG=ram64_a000_work BOARD_IO=sbcio FEATURE_SD=1 FEATURE_FAT=0 FEATURE_VDG=0
```

`MONITOR_PROFILE` は既存互換のプリセット入口として残し、指定されたprofileから次の既定値を展開する。
コマンドラインまたは環境変数で構成軸を指定した場合は、その値でprofile既定値を上書きする。

| 変数 | 値 | 意味 |
| --- | --- | --- |
| `MEMORY_CONFIG` | `base8k` / `ram64_c000_work` / `ram64_a000_work` / `ram64_4000_work` | メモリ配置 |
| `BOARD_IO` | `none` / `sbcio` | 外部I/O装備 |
| `FEATURE_SD` | `0` / `1` | raw SD sector readと固定LBA `BOOT` をROMへ入れるか |
| `FEATURE_FAT` | `0` / `1` | ROM常駐のFAT32 `DIR` / `LF` を入れるか |
| `FEATURE_VDG` | `0` / `1` | K68-VDG機能をROMへ入れるか |
| `FEATURE_KEYBOARD` | `0` / `1` | 2nd ACIAキーボード機能をROMへ入れるか |
| `FEATURE_I2C` | `0` / `1` | I2C機能をROMへ入れるか。現時点では依存関係だけを検査する |
| `VDG_VRAM_CONFIG` | `a000` / `c000` | VDG有効時のVRAM配置 |
| `BUILD_CONFIG_NAME` | 任意の短い名前 | 直接指定ビルドの出力名suffixを明示する |

既存profileの出力名は互換のため維持する。
直接指定ビルドでは、`BUILD_CONFIG_NAME` があれば `build/mc6800-monitor-<BUILD_CONFIG_NAME>.bin` を生成し、未指定の場合は `MEMORY_CONFIG`、`BOARD_IO`、各 `FEATURE_*`、`VDG_VRAM_CONFIG` から一意なsuffixを生成する。

```sh
make bin MEMORY_CONFIG=ram64_a000_work BOARD_IO=sbcio FEATURE_SD=1 FEATURE_FAT=0 FEATURE_VDG=1 FEATURE_KEYBOARD=1 VDG_VRAM_CONFIG=c000 BUILD_CONFIG_NAME=axis-k6802
```

上の例では `build/mc6800-monitor-axis-k6802.bin` を生成する。

不正な組み合わせはMake時に失敗させる。
`FEATURE_SD=1`、`FEATURE_KEYBOARD=1`、`FEATURE_I2C=1` は `BOARD_IO=sbcio` を必須とする。
`FEATURE_VDG=1` は `VDG_VRAM_CONFIG` の明示的な配置を使う。
`make stage1` / `make sdfs` は `FEATURE_SD=1`、`BOARD_IO=sbcio`、stage1対応RAM配置を必須にする。
標準 `sbcio` profileはSDなしのまま維持し、VDGなしSDFS/68構成を試す場合は次のように軸指定で有効化する。

```sh
MONITOR_PROFILE=sbcio FEATURE_SD=1 FEATURE_FAT=0 BUILD_CONFIG_NAME=sbcio-sdfs make bin stage1 sdfs
```

アセンブル時には、Makefileが `build/monitor_config.inc` を生成し、ROM本体はこの生成ファイルだけをincludeする。
過去の `include/profiles/*.inc` はprofileプリセットのコピー元としては使わない。
テスト互換と段階的移行のため、`MONITOR_PROFILE_*` と `MONITOR_FEATURE_*` の既存シンボルは当面生成し続ける。

## 条件アセンブル方針

機能コードは、構成軸に従ってASLの `if` / `else` / `endif` で条件アセンブルする。

- `FEATURE_SD=0` では、`DIR`、`LF`、SD、FAT32関連コードと文字列をROMから除外する。
- `FEATURE_VDG=1` では、通常出力のVDG複製だけをROMへ入れる。固定表示確認は `diagnostics/VDGA000.S` / `VDGC000.S` をSDから実行する。
- `FEATURE_KEYBOARD=1` では、2nd ACIA初期化とMAP表示だけをROMへ入れる。受信確認は `diagnostics/KEYTEST.S` をSDから実行する。
- `FEATURE_I2C=0` では、I2Cドライバ、I2Cコマンド、関連文字列をROMから除外する。

無効な機能はdispatch上で未定義コマンドになり、従来どおり `?` を返す。
同時に、コマンド本体、内部ルーチン、関連文字列はROMから除外する。
listingのsymbol tableでも、無効機能の内部ラベルは原則として出ないことを期待する。

I2C本体は未実装であり、現時点では構成軸と `BOARD_IO=sbcio` 依存関係だけを導入する。実装Issueを切る場合も、まずRAMロード可能なPoCとして作り、ROM常駐化はサイズ見積もりと第2段ロード方針を確認してから判断する。

## MAP表示方針

`MAP` はprofile名互換の見出しを維持しつつ、構成軸の結果を表示する。
少なくとも次を確認できるようにする。

- メモリ構成。
- 外部I/O装備。
- 有効な機能。
- RAM、ワークRAM、SDバッファ、VRAM、主要I/Oアドレス、ROM範囲。

`FEATURE_SD=0` では `SD xxxx` 行を表示しない。
`FEATURE_VDG=0` では `VRAM xxxx-yyyy` と `VDG xxxx` 行を表示しない。
`FEATURE_KEYBOARD=0` では `KEY 8094-8095` 行を表示しない。

後続Issueで、見出しを `MEM` / `IO` / `FEAT` 形式へ拡張できるようにする。
ただし、profile名だけを根拠に機能やメモリ配置を推測する設計へ戻さない。
