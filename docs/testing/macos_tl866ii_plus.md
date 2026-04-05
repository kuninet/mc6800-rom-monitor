# UNIX 系環境で TL866II Plus を使って ROM を書き込む

## 目的

`TL866II Plus` を UNIX 系環境から使い、ビルド結果から ROM ライタ向けバイナリを生成して `minipro` で書き込む。

## 前提

- `minipro` が動く UNIX 系環境がある
- ライタは `TL866II Plus`
- 書き込みツールは `minipro`

## 想定する環境

- macOS
- Linux
- Windows 上の WSL 2

Makefile の `rombin` / `program` / `verify` / `readback` ターゲットは、`minipro` と `p2bin` が使える UNIX 系環境であれば基本的に同じ手順で使える。

## macOS でのインストール

```bash
brew install minipro
```

## Linux でのインストール例

ディストリビューションごとにパッケージ名は異なるが、少なくとも `minipro` と `libusb` 系が必要になる。

例:

```bash
sudo apt install minipro
```

## WSL 2 での参考手順

WSL 2 では USB デバイスをそのまま Linux 側から使えないため、`usbipd-win` を使って TL866II Plus を WSL へアタッチする必要がある。

公式:
- [Microsoft Learn: USB デバイスを接続する](https://learn.microsoft.com/ja-jp/windows/wsl/connect-usb)

大まかな流れは次の通り。

1. Windows 側で `usbipd-win` を入れる
2. `wsl --update` で WSL を最新化する
3. 管理者権限の PowerShell で `usbipd list` を実行する
4. TL866II Plus の bus id を確認して `usbipd bind --busid <busid>` を実行する
5. 通常権限の PowerShell で `usbipd attach --wsl --busid <busid>` を実行する
6. WSL 側で `lsusb` や `minipro --version` で認識を確認する

例:

```powershell
winget install --interactive --exact dorssel.usbipd-win
wsl --update
usbipd list
usbipd bind --busid 4-4
usbipd attach --wsl --busid 4-4
```

WSL 側:

```bash
lsusb
minipro --version
```

WSL にアタッチしている間、その USB デバイスは Windows ネイティブ側からは使えない点に注意する。

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

## macOS での実績

確認できている実績は次の通り。

- `minipro --version` で `TL866II+` を認識
- `minipro -t` の自己診断は成功
- `minipro -r` の読み出しは成功
- `make program-w27c512` で `W27C512` の erase / write / read / verify が成功

成功時の条件:

- `TL866II Plus` を `セルフパワーUSBハブ` 経由で接続
- `W27C512@DIP28`
- `make program-w27c512`

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

まず使えるデバイス名を確認するには次を使う。

```bash
minipro -l | rg '27C64|27C256|28C256|W27C512|UPD28C256'
```

プログラマの接続状況確認は次でよい。

```bash
minipro --version
```

接続されていれば `Found TL866II+` のように表示される。

## 既知の制約

macOS で `minipro` を使った書き込みでは、少なくとも一部の環境で次の現象を確認している。

- `minipro --version` では TL866II Plus を認識する
- `minipro -t` の自己診断は成功する
- `minipro -r` の読み出しは成功する
- 消去も成功する
- しかし書き込みだけ途中で `LIBUSB_TRANSFER_TIMED_OUT` になることがある

一方で、同じ macOS 環境でも `セルフパワーUSBハブ` を経由させたところ、`W27C512` の書き込みは成功した。

そのため、macOS で timeout が出る場合は次を優先して試す。

- `TL866II Plus` をセルフパワーUSBハブ経由で接続する
- USB ポートを変える
- 直結とハブ経由を入れ替えて比較する
- `minipro --version`、`minipro -t`、`minipro -r` の順で切り分ける

この現象は `W27C512` だけでなく `28C256` 系でも確認した。少なくともこのリポジトリの確認環境では、`macOS + minipro + TL866II Plus` の組み合わせで書き込みが安定しない場合がある。

そのため、現時点では次の運用が現実的である。

- UNIX 系環境ではビルドと ROM イメージ生成を行う
- macOS ではセルフパワーUSBハブ経由を優先して試す
- それでも不安定なら Windows の純正ソフトを使う
- もしくは WSL 2 側の Linux `minipro` を試す

## 実装メモ

Makefile では `p2bin` に対して次のような変換をかけている。

- `.p` オブジェクトを入力
- `ROM_RANGE_START-ROM_RANGE_END` を切り出す
- 未使用領域は `0xFF` で埋める
- ROM ライタ向けのバイナリとして出力する

これにより、CPU アドレス基準の出力から ROM ライタ向けのチップイメージを作っている。
