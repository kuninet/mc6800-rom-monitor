# K68-VDG表示PoC 実機確認手順

## 目的

`sbcio_vdg` または `k6802_vdg` profile の ROM で、K68-VDG の VRAM と `$8110` 設定レジスタを使い、画面クリアと固定文字列表示ができることを確認する。

## 前提

- SBC6800 と SBC-IO の組み合わせで、1st ACIA のシリアルコンソールが使えること。
- `sbcio_vdg` profileでは、K68-VDG は VRAM `$A000-$BFFF` 設定で接続すること。
- `k6802_vdg` profileでは、K68-VDG は VRAM `$C000-$DFFF` 設定で接続すること。
- K68-VDG の VDG設定用レジスタは `$8110` として接続すること。
- SD/FAT ワーク領域と K68-VDG VRAM が重ならないこと。

## ROM作成

```sh
MONITOR_PROFILE=sbcio_vdg make bin
```

K6802-SBCでVRAMを `$C000-$DFFF` に置く場合は `k6802_vdg` profileを使う。

```sh
MONITOR_PROFILE=k6802_vdg make bin
```

ROMライタ用イメージが必要な場合は、使用するROM種別に合わせて `rombin` ターゲットを使う。

```sh
MONITOR_PROFILE=sbcio_vdg make rombin ROM_KIND=27C64
```

```sh
MONITOR_PROFILE=k6802_vdg make rombin ROM_KIND=27C64
```

## 確認手順

1. 対象profileの ROM で起動し、シリアルコンソールに `MC6800 MONITOR` とプロンプト `]` が出ることを確認する。
2. K68-VDG の画面にも `MC6800 MONITOR` とプロンプトが表示されることを確認する。
3. `H` を実行し、シリアルコンソールとK68-VDG画面の両方にヘルプが表示されることを確認する。
4. `MAP` を実行し、次の行が表示されることを確認する。

`sbcio_vdg` profileの場合:

```text
MAP SBCIO VDG
WORK C000-DFFF
SD C000
MON C200
MIK C300
STK DFFF
VRAM A000-BFFF
VDG 8110
ROM E000-FFFF
```

`k6802_vdg` profileの場合:

```text
MAP K6802 VDG
WORK A000-BFFF
SD A000
MON A200
MIK A300
STK BFFF
VRAM C000-DFFF
VDG 8110
ROM E000-FFFF
```

5. 必要に応じて、SDへ診断用S-Recordを置き、SDFS/68から実行する。

`VDGTEST` 相当の固定表示確認はROMコマンドではなく、Git管理下の `diagnostics/VDGA000.S` / `VDGC000.S` を使う。
`sbcio_vdg` では `VDGA000.S`、`k6802_vdg` では `VDGC000.S` をSDへコピーする。

```text
SDFS> RUN VDGA000.S
```

必要に応じて `sbcio_vdg` では `D A000-A017`、`k6802_vdg` では `D C000-C017` を実行し、VRAM先頭にMC6847向けの文字コードが入ることを確認する。
ASCII `$20-$3F` の空白、数字、記号は、表示可能な `$60-$7F` 側へ変換して書く。
ただし、`D` コマンドの出力自体もVDGへ書かれるため、実機画面はダンプ表示で進む。

```text
A000 4B 76 78 6D 56 44 47 60 41 70 70 70
```

```text
C000 4B 76 78 6D 56 44 47 60 43 70 70 70
```

## 追加確認

- SDFS/68併用構成では、診断用S-Record実行後も `DIR` / `LOAD` / `RUN` が動作することを確認する。
- `sbcio_vdg` では `RAMTEST C000-DFFF` がSD/FATワーク領域の破壊テストであり、`$A000-$BFFF` は K68-VDG VRAM のため対象にしない。
- `k6802_vdg` では `RAMTEST A000-BFFF` がSD/FATワーク領域の破壊テストであり、`$C000-$DFFF` は K68-VDG VRAM のため対象にしない。

## 記録する内容

- 使用した ROM profile と ROM 種別。
- K68-VDG のジャンパまたは配線設定。
- `MAP` 出力。
- 起動直後のVDG画面表示。
- `H` / `MAP` のVDG画面表示。
- 診断用S-Recordの実行結果。
- 画面表示結果。
- SD/FAT を併用した場合は `DIR` / `LF` の結果。
