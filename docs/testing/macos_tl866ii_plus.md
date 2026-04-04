# macOS で TL866II Plus を使って ROM を書き込む

## 目的

`TL866II Plus` を macOS から使い、ビルド結果から ROM ライタ向けバイナリを生成して `minipro` で書き込む。

## 前提

- `Homebrew` が使える
- ライタは `TL866II Plus`
- 書き込みツールは `minipro`

## インストール

```bash
brew install minipro
```

## 方針

このプロジェクトのビルド結果は CPU アドレス空間を持っている。

ROM ライタへ渡すときは、実際のチップ内アドレスに合わせたバイナリへ変換した方が安全である。

そのため、Makefile では次の流れにしている。

1. `make` で Intel HEX を生成する
2. `make rombin ROM_KIND=...` で `p2bin` を使ってチップ容量に合わせたバイナリを作る
3. `make program ROM_KIND=...` で `minipro` から書き込む

## 対応している ROM_KIND

| ROM_KIND | 容量 | 想定マップ | 生成されるバイナリ |
| --- | --- | --- | --- |
| `27C64` | 8KB | `E000-FFFF` | `build/mc6800-monitor-27C64.bin` |
| `27C128` | 16KB | `C000-FFFF` | `build/mc6800-monitor-27C128.bin` |
| `27C256` | 32KB | `8000-FFFF` | `build/mc6800-monitor-27C256.bin` |
| `28C256` | 32KB | `8000-FFFF` | `build/mc6800-monitor-28C256.bin` |
| `UPD28C256` | 32KB | `8000-FFFF` | `build/mc6800-monitor-UPD28C256.bin` |
| `W27C512` | 64KB | `0000-FFFF` | `build/mc6800-monitor-W27C512.bin` |

## 重要な注意

上の想定マップは、「その容量の ROM が CPU の上位アドレス空間へ素直に張られている」前提。

例えば `27C256` や `W27C512` を変換基板や配線で別の見せ方にしている場合は、Makefile の既定値のままでは合わない可能性がある。

その場合は次を上書きする。

- `ROM_KIND`
- `MINIPRO_DEVICE`
- 必要であれば `ROM_RANGE_START`
- 必要であれば `ROM_RANGE_END`

## 基本手順

### 1. W27C512 に書く

```bash
make clean
make
make rombin ROM_KIND=W27C512
make program ROM_KIND=W27C512
```

### 2. 27C256 に書く

```bash
make clean
make
make rombin ROM_KIND=27C256
make program ROM_KIND=27C256
```

### 3. 27C64 に書く

```bash
make clean
make
make rombin ROM_KIND=27C64
make program ROM_KIND=27C64
```

## 省略形ターゲット

よく使うものは専用ターゲットも用意してある。

```bash
make rombin-w27c512
make program-w27c512

make rombin-27c256
make program-27c256

make rombin-27c64
make program-27c64

make program-upd28c256
```

## verify と readback

書き込み後の比較:

```bash
make verify ROM_KIND=W27C512
```

読み出し:

```bash
make readback ROM_KIND=W27C512
```

読み出したファイルは次になる。

```text
build/mc6800-monitor-W27C512-readback.bin
```

## minipro のデバイス名が違う場合

`minipro` のデバイス名は手元の database に依存することがある。

もし既定値で合わない場合は、`MINIPRO_DEVICE` を明示して実行する。

```bash
make program ROM_KIND=W27C512 MINIPRO_DEVICE=W27C512@DIP28
```

## 実装メモ

Makefile では `p2bin` に対して次のような変換をかけている。

- `.p` オブジェクトを入力
- `ROM_RANGE_START-ROM_RANGE_END` を切り出す
- 未使用領域は `0xFF` で埋める
- ROM ライタ向けのバイナリとして出力する

これにより、CPU アドレス基準の出力から ROM ライタ向けのチップイメージを作っている。
