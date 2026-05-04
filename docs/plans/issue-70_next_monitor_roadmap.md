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

### 5. PTMタイマ

PTMは最初から割り込み前提にせず、まずは待ち時間やtick用途で確認する。

- SD timeout の見直し。
- キー入力ポーリング補助。
- 簡易tickカウンタ。
- 将来の音、カーソル点滅、RTC風表示の土台。

### 6. AUTOEXEC.S と BOOT

SD LOADが実機動作したため、起動自動化は有力な次期機能。

- `BOOT` コマンドで root の `AUTOEXEC.S` を探してLOADする。
- 初期はS-Recordのみを対象にする。
- AUTOEXECからRTC初期化、VDG初期化、BASIC起動を行う構成にする。

### 7. SAVE/write

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
7. `BOOT` / `AUTOEXEC.S`。
8. SAVE/write。

## 検証方針

- 8KB互換ROMで既存 smoke test、SD fixture test、実機 `DIR` / `LF` が壊れないこと。
- SBC-IO拡張ROMで `$C000-$DFFF` のRAM testが通ること。
- 拡張ROMでSD bufferを移動しても `DIR`、`LF HELLO.S`、`LF MICBAS13.S` が通ること。
- BASICロード後にモニタワークやSD状態が低RAMスキャンで壊れにくいこと。
- VDG導入時は `$A000-$BFFF` と `$C000-$DFFF` の使い分けを文書とテストで確認すること。

## 対象外

このIssueではロードマップ整理だけを扱う。以下は後続Issueで実装する。

- 実際のメモリ配置変更。
- ROMビルドターゲット追加。
- `MEM` / `MAP` / `RAMTEST` 実装。
- K68-VDG、2nd ACIA、PTM、AUTOEXEC、SAVE/write 実装。
