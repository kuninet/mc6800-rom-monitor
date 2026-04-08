# WSL2 で TL866II Plus と minipro を試す

## 目的

Windows 上の WSL2 から `TL866II Plus` を認識させ、Linux 版 `minipro` で書き込み確認するための手順と確認結果を残す。

## 2026-04-08 時点の確認結果

- Windows 側の WSL は `Ubuntu 22.04.5 LTS`、`WSL version 2`
- Windows 側では TL866II Plus が `XGecu WinUSB Device` として見えている
- `usbipd-win 5.3.0` は導入済み
- TL866II Plus を WSL2 へ attach できた
- WSL 側で `lsusb` に `TL866II Plus Device Programmer [MiniPRO]` が見えた
- WSL 側で `minipro --version` が `Found TL866II+` を返した
- `make program-w27c512` で `W27C512@DIP28` への書き込みと検証が成功した

今回の確認で、WSL2 経由の `minipro` 書き込みは少なくとも `W27C512` で実用になることを確認した。

## Windows 側で見えた TL866II Plus

`usbipd-win` 導入後、次のように TL866II Plus が列挙された。

```text
BUSID  VID:PID    DEVICE                STATE
2-3    a466:0a53  XGecu WinUSB Device   Not shared
```

`VID:PID a466:0a53` と `XGecu WinUSB Device` は TL866II Plus と見てよい。

## 前提

- Windows 11
- WSL2 の Ubuntu
- `TL866II Plus`
- Windows 側に `usbipd-win`
- WSL 側に `minipro`

## 実施した確認

### 1. WSL の状態

```powershell
wsl --status
wsl -l -v
```

確認できた内容:

- 既定ディストリビューションは `Ubuntu`
- `Ubuntu` は `Running`
- WSL バージョンは `2`

### 2. usbipd-win の導入

未導入なら Windows 側で次を実行する。

```powershell
winget install --exact dorssel.usbipd-win
```

今回の確認では `usbipd.exe` は次に入った。

```text
C:\Program Files\usbipd-win\usbipd.exe
```

## 実施手順

### 1. Windows 側で TL866II Plus を列挙する

```powershell
& 'C:\Program Files\usbipd-win\usbipd.exe' list
```

TL866II Plus が `XGecu WinUSB Device` として見えることを確認する。

### 2. 管理者 PowerShell で bind する

```powershell
& 'C:\Program Files\usbipd-win\usbipd.exe' bind --busid 2-3
```

管理者権限がない場合は次のエラーになる。

```text
usbipd: error: Access denied; this operation requires administrator privileges.
```

管理者 PowerShell で実行できれば、この手順は成功する。

### 3. 通常権限の PowerShell で WSL に attach する

`bind` が済んだ後で次を実行する。

```powershell
& 'C:\Program Files\usbipd-win\usbipd.exe' attach --wsl --busid 2-3
```

`bind` 前に実行すると次のように失敗する。

```text
usbipd: error: Device is not shared; run 'usbipd bind --busid 2-3' as administrator first.
```

Windows 側でデバイスがまだ占有されている場合は、次のように失敗することがある。

```text
WSL usbip: error: Attach Request for 2-3 failed - Device busy (exported)
usbipd: warning: The device appears to be used by Windows; stop the software using the device, or bind the device using the '--force' option.
```

この場合は TL866 系の Windows アプリを閉じて再試行する。必要なら管理者 PowerShell で次を実行する。

```powershell
& 'C:\Program Files\usbipd-win\usbipd.exe' bind --busid 2-3 --force
```

### 4. WSL 側で USB 認識を確認する

```bash
lsusb
```

attach 後は、少なくとも次のように TL866II Plus が見える。

```text
Bus 001 Device 002: ID a466:0a53 Haikou Xingong Electronics Co.,Ltd TL866II Plus Device Programmer [MiniPRO]
```

### 5. WSL 側で minipro を入れる

`Ubuntu 22.04` では `apt-get install minipro` は通らなかった。

```text
E: Unable to locate package minipro
```

そのため、この環境ではソースから導入した。

依存パッケージを入れる。

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config git libusb-1.0-0-dev usbutils
```

ソースを取得してビルドする。

```bash
cd ~
git clone https://gitlab.com/DavidGriffith/minipro.git
cd ~/minipro
make
sudo make install
```

udev ルールは今回の取得物では `udev/60-minipro.rules` に入っていた。

```bash
cd ~/minipro
sudo cp udev/60-minipro.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo usermod -a -G plugdev $USER
```

グループ反映のため、一度 WSL を再起動する。

```powershell
wsl --shutdown
```

### 6. WSL 側で minipro を確認する

```bash
minipro --version
minipro -l | grep -E '27C64|27C128|27C256|28C256|UPD28C256|W27C512'
```

TL866II Plus が正常に渡っていれば、`minipro --version` でプログラマ認識が見えるはず。

今回の確認では次のように認識できた。

```text
Found TL866II+ 04.2.132 (0x284)
minipro version 0.7.4
```

## 確認できた成功例

`W27C512` では、WSL 側で次の実行が成功した。

```bash
cd /mnt/c/Users/kuninet/git/MC6800_monitor
make program-w27c512
```

結果:

```text
Chip ID: 0xDA08  OK
Erasing... 204 ms  OK
Writing Code...  29.87 Sec  OK
Reading Code...  1.11 Sec  OK
Verification OK
```

このため、少なくとも `W27C512@DIP28` では `usbipd-win + WSL2 + minipro` の構成で消去、書き込み、検証まで通る。

## 次にやること

1. 書き込み済み ROM を SBC6800 実機で確認する
2. 必要なら `verify` と `readback` も WSL 側で試す
3. `27C64`、`27C256`、`28C256` 系でも同様に通るか確認する

## 実機書き込みまで進めるときのコマンド例

attach と `minipro` 導入が済んだ後は、WSL 側で次を試す。

```bash
cd /mnt/c/Users/kuninet/git/MC6800_monitor
make clean
make
make rombin ROM_KIND=27C64
make program ROM_KIND=27C64
```

別 ROM を使う場合は `ROM_KIND` と、必要なら `MINIPRO_DEVICE` を上書きする。

## 補足

- WSL に USB を attach している間は Windows ネイティブ側からそのデバイスは使えない
- `usbipd` が PATH に出ない場合でも、`C:\Program Files\usbipd-win\usbipd.exe` を直接呼べばよい
- `Ubuntu 22.04` では `apt` パッケージ名 `minipro` が見つからなかったため、ソースビルド前提で考える方が早い
- まずは `minipro --version` と `lsusb` の確認を優先し、いきなり書き込みに進まない方が切り分けしやすい
