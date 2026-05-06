# Issue #70 次期モニタ拡張ロードマップ

## 関連リンク

- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- SD/FAT実機PoC Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- SBC-IO Rev02: https://sbc738827564.wordpress.com/2018/08/11/sbc-io-rev02/
- K68-VDG: https://github.com/kuninet/K68-VDG

## 背景

SBC-IO の MC6821 PIA 経由で SD/FAT read-only の `DIR` と `LF filename` が実機動作したため、次は単発機能を足す前にメモリマップと拡張ROM方針を整理する。

現行モニタは 8KB RAM 構成を前提に、SD sector buffer を `$1C00`、モニタワークを `$1E00` 付近に置いている。このままだと、電大版BASICのように低RAMを広く使うプログラムや、メモリサイズスキャンでRAMを壊すソフトと共存しにくい。

一方、SBC-IO には RAM 拡張、2つめの ACIA、PTM タイマなど未使用の機能があり、K68-VDG を組み合わせればスタンドアロン機に近づけられる。これらを同時に進めるとアドレス衝突しやすいため、まず次期メモリマップを決める。

## 採用方針

次期方針は **RAM整理 + ビルド分離** とする。

- 8KB互換ROMは維持し、現行の `$0000-$1FFF` RAM構成で動くことを守る。
- SBC-IO拡張ROMを別ビルドとして用意し、拡張RAM前提の機能をこちらへ寄せる。
- SBC-IO拡張ROMでは `$C000-$DFFF` をモニタワーク、SD sector buffer、将来のディスクI/Oワーク領域候補にする。
- `$A000-$BFFF` は K68-VDG の VRAM 候補として原則予約し、汎用RAMとしては使わない。
- 1st ACIA はPC接続用の保守コンソールとして維持し、2nd ACIA を将来のキーボード接続候補にする。

## ビルド分離の運用イメージ

ビルド分離は、単にRAM配置だけを切り替えるのではなく、将来のVRAM、キーボード、PTM、RTC、DOS相当機能を組み合わせられるようにするための土台として扱う。

初期案では、既定の `make bin` は現行互換の 8KB RAM ROM を作る。SBC-IO拡張構成は、たとえば `make bin MONITOR_PROFILE=sbcio` のようなプロファイル指定で作る候補とする。実際の変数名は実装時にMakefileの既存規約へ合わせる。

プロファイルは次のような粒度で考える。

- `base`: 現行互換。8KB RAM、1st ACIA、PIA SD/FAT read-only。
- `sbcio`: SBC-IO RAM拡張前提。モニタワークとSD bufferを `$C000-$DFFF` へ移す。
- `sbcio_vdg`: `sbcio` に K68-VDG を加える。`$A000-$BFFF` をVRAMとして予約する。
- `standalone`: VDG、2nd ACIAキーボード、PTM、AUTOEXECなどを含む将来候補。

機能が増えるとROM容量も厳しくなるため、プロファイルごとに有効機能を選べる構成を検討する。特に FAT read-only、VDG、キーボード、PTM、RTC、BOOT/DOS相当機能は、すべてを常に同居させる前提にしない。

## メモリマップ案

### 8KB互換ROM

現行互換を優先する。

- `$0000-$1FFF`: RAM
- `$1C00-$1DFF`: SD sector buffer
- `$1E00` 以降: モニタワーク
- `$1F00` 以降: MIKBUG互換ワーク
- `$8018-$8019`: 1st ACIA
- `$8050-$8053`: MC6821 PIA暫定アドレス
- `$E000-$FFFF`: ROM

### SBC-IO拡張ROM

低RAMをユーザープログラムやBASICへ返すことを優先する。

- `$0000-$7FFF`: ユーザープログラム、BASIC、ワークRAM候補
- `$8018-$8019`: 1st ACIA
- `$8050-$8053`: MC6821 PIA暫定アドレス
- `$A000-$BFFF`: K68-VDG VRAM候補として予約
- `$C000-$DFFF`: モニタワーク、SD sector buffer、FAT stream、将来のディスクI/Oワーク候補
- `$E000-$FFFF`: ROM

拡張ROMの初期候補は、`SD_SECTOR_BUF=$C000`、`MONITOR_RAM_BASE=$C200` 付近とする。最終値は実装時に変数量とスタック配置を見て決める。

## 次の実装候補

| 優先 | 候補 | 狙い | 主な注意点 |
| --- | --- | --- | --- |
| 1 | メモリ配置のビルド分離 | 8KB互換を残しつつSBC-IO拡張ROMの土台を作る | Makefileのプロファイル設計と既存smoke維持 |
| 2 | RAM確認コマンド | `$C000-$DFFF` の実機確認をしやすくする | 破壊範囲を明示し、I/OやROMを触らない |
| 3 | K68-VDG表示 | スタンドアロン機の画面出力へ進む | `$A000-$BFFF` VRAMとSBC-IO RAMの衝突回避 |
| 4 | 2nd ACIAキーボード | PC保守コンソールを残したままキーボード入力を追加 | PS/2かUSB+MCUかの選定 |
| 5 | PTMタイマ | timeout、tick、キー入力補助の土台を作る | 最初から割り込み前提にしない |
| 6 | PIA Port A I2C RTC | SDボード+RTCボード構想を検証する | PIA共有、I2Cプルアップ、レベル変換 |
| 7 | AUTOEXEC.S と BOOT | SDから起動時初期化やBASIC起動を自動化する | 自動実行アドレス規約を決める |
| 8 | SD bootstrap / M6800 DOS | ROM容量逼迫時に機能をRAM側へ逃がす | 専用SD作成手順が必要 |
| 9 | SAVE/write | スタンドアロン運用でSDへ保存できるようにする | FAT更新の安全性と電源断耐性 |

### 1. メモリ配置のビルド分離

最初に実施する候補。

- 8KB互換ROMとSBC-IO拡張ROMを別ビルドにする。
- 拡張ROMでは SD sector buffer とモニタワークを `$C000-$DFFF` へ移す。
- 既存の `DIR`、`LF HELLO.S`、`LF MICBAS13.S` が壊れないことを確認する。
- 電大版BASICのメモリスキャンで低RAMが壊れても、モニタ/SDワークが壊れにくい構成を目指す。

### 2. RAM確認コマンド

拡張ROMの実機確認をしやすくする。

- `MEM` または `MAP`: 想定メモリマップ表示。
- `RAMTEST`: `$C000-$DFFF` など範囲指定RAMテスト。
- 破壊テストは範囲を明示し、ROMやI/O領域を触らないようにする。

### 3. K68-VDG表示

スタンドアロン機への第一歩として扱う。

- `$A000-$BFFF` をVRAM優先候補にする。
- `$8110` のVDG設定用レジスタ候補は、SBC-IO側I/Oとの競合を確認してから採用する。
- 最初は `VDGTEST`、画面クリア、固定文字列表示程度に絞る。

### 4. 2nd ACIAキーボード

1st ACIAをPC接続用に残し、2nd ACIAをキーボード入力候補にする。

- 最初は `KEYTEST` で受信文字を表示するだけにする。
- 画面出力が入った後、コンソール入力を1st ACIA/2nd ACIAで切り替える。
- キーボード接続はスタンドアロン化の次段階として扱う。
- キーボードI/Fボードは別基板を想定する。
- PS/2キーボードは実装が比較的容易だが、入手性が今後悪くなる可能性がある。
- USBキーボードは将来性と入手性が高いが、MC6800直結では重いため、専用MCU付きキーボードI/Fとして検討する。
- 初期PoCはPS/2またはMCUでシリアル化したUSBキーボードを2nd ACIAへ接続する案を比較する。

### 5. PTMタイマ

PTMは最初から割り込み前提にせず、まずは待ち時間やtick用途で確認する。

- SD timeout の見直し。
- キー入力ポーリング補助。
- 簡易tickカウンタ。
- 将来の音、カーソル点滅、RTC風表示の土台。

### 6. PIA Port A I2C RTC

将来構想として、PIA Port A で I2C をbit-bangし、RTC時計ICを外付けする案を残す。

- SDボード + RTCボードとしてまとめる構成は、スタンドアロン機として実用性がある。
- SBC-IO上の既存PIAをSD SPIとRTC I2Cで共有するか、SD/RTC専用の独自I/O基板を作るかは検討課題とする。
- 既存PIAを共有する場合、Port BをSD SPI、Port AをI2C RTCに割り当てる候補とする。
- I2Cはopen-drain相当の扱いが必要なため、PIA出力方向、プルアップ、レベル変換、5V/3.3V混在を実機確認対象にする。
- RTCは `AUTOEXEC.S` や将来のDOS相当機能から時刻を読む用途を想定する。
- Port B の余りビット (bit 6/7) を I2C に流用する代替案と、RTC/EEPROM/OLED の同居検討は [i2c_bus_overlay_evaluation.md](i2c_bus_overlay_evaluation.md) にまとめてある。

### 7. AUTOEXEC.S と BOOT

SD LOADが実機動作したため、起動自動化は有力な次期機能。

- `BOOT` コマンドで root の `AUTOEXEC.S` を探してLOADする。
- 初期はS-Recordのみを対象にする。
- AUTOEXECからRTC初期化、VDG初期化、BASIC起動を行う構成にする。

### 8. SDシステム領域bootstrapとオリジナルDOS構想

ROM容量が FAT read-only と VDG 対応で厳しくなる場合、SDカードの予約領域や固定sectorを使ったbootstrap案を将来構想として残す。

- ROMにはSD初期化と第1段bootstrap readだけを残し、FAT/DIR/LF/VDG/キーボードなどをRAM上の第2段へ逃がす。
- 第2段はrootの `SDFS.BIN` など通常ファイルに置く案を優先し、固定sectorは最小bootstrapに限定する。
- SD予約領域を使う場合は、専用SD作成ツールとsignature検査が必要になる。
- 通常のモニタ拡張というより、M6800 DOS相当の別構想として扱う。
- 初期ロードマップでは実装対象外だが、ROM容量が逼迫した時の退避先として残す。

### 9. SAVE/write

FAT write は便利だが、実装ミスでSDカードを壊しやすい。VDG/キーボード/BOOTの後で検討する。

- 最初は新規ファイル作成ではなく、固定ファイルへの上書きやraw log保存から検討する。
- FAT更新、directory entry更新、flush、電源断耐性を別Issueで扱う。

## 推奨順序

1. メモリ配置のビルド分離。
2. `$C000-$DFFF` RAM確認とSD/FATワーク退避。
3. 電大版BASIC互換確認。
4. K68-VDGの画面テスト。
5. 2nd ACIAキーボード入力。
6. PTMタイマ。
7. PIA Port A I2C RTCのPoC。
8. `BOOT` / `AUTOEXEC.S`。
9. SDシステム領域bootstrapとオリジナルDOS構想の再評価。
10. SAVE/write。

## 検証方針

- 8KB互換ROMで既存 smoke test、SD fixture test、実機 `DIR` / `LF` が壊れないこと。
- SBC-IO拡張ROMで `$C000-$DFFF` のRAM testが通ること。
- 拡張ROMでSD bufferを移動しても `DIR`、`LF HELLO.S`、`LF MICBAS13.S` が通ること。
- BASICロード後にモニタワークやSD状態が低RAMスキャンで壊れにくいこと。
- VDG導入時は `$A000-$BFFF` と `$C000-$DFFF` の使い分けを文書とテストで確認すること。
- ビルド分離導入時は、少なくとも `base` と `sbcio` の両方でROM生成とsmoke testを通すこと。
- キーボードI/F検討時は、PS/2案とUSB+MCU案の部品入手性、実装規模、2nd ACIA接続方法を比較すること。

## 対象外

このIssueではロードマップ整理だけを扱う。以下は後続Issueで実装する。

- 実際のメモリ配置変更。
- ROMビルドターゲット追加。
- `MEM` / `MAP` / `RAMTEST` 実装。
- K68-VDG、2nd ACIA、PTM、RTC、AUTOEXEC、bootstrap/DOS、SAVE/write 実装。
