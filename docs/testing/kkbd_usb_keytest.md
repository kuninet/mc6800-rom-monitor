# KKBD-USB 2nd ACIA実機確認手順

## 目的

SBC-IOの2nd ACIA `$8094/$8095` にKKBD-USBを接続し、SDからロードする `diagnostics/KEYTEST.S` でUSBキーボード由来のUART入力を確認する。

## 前提

- 1st ACIA `$8018/$8019` はPC保守コンソールとして接続済みであること。
- SBC-IOの2nd ACIAは `$8094/$8095` としてデコードされていること。
- KKBD-USBはUSBキーボード入力をASCIIへ変換し、UART TXへ送信できる状態であること。
- KKBD-USBは `9600 bps`、`8N1`、行末コード `CR` に設定すること。
- KKBD-USBのUART出力レベルとSBC-IO側入力レベルが安全に接続できること。

## ROM作成

SBC-IO RAM拡張profileで確認する。ROM常駐の `KEYTEST` コマンドは容量節約のため外している。

```sh
MONITOR_PROFILE=sbcio make bin
```

VDG構成と併用する場合は、対象構成に合わせて次のどちらかを使う。

```sh
MONITOR_PROFILE=sbcio_vdg make bin
MONITOR_PROFILE=k6802_vdg make bin
```

ROMライタ用イメージが必要な場合は、使用するROM種別に合わせて `rombin` ターゲットを使う。

```sh
MONITOR_PROFILE=sbcio make rombin ROM_KIND=W27C512
```

## 配線

- KKBD-USB UART TX を SBC-IO 2nd ACIA RX へ接続する。
- GNDを共通にする。
- KKBD-USBからSBCへ送信する単方向PoCのため、SBC-IO 2nd ACIA TXからKKBD-USB RXへの接続は不要。

## 確認手順

1. 対象profileのROMで起動し、1st ACIAの保守コンソールに `MC6800 MONITOR` とプロンプト `]` が出ることを確認する。
2. `MAP` を実行し、SBC-IO系profileで `KEY 8094-8095` が表示されることを確認する。

```text
] MAP
...
KEY 8094-8095
ROM E000-FFFF
]
```

3. `diagnostics/KEYTEST.S` をsystem SDへコピーする。
4. `BOOT` でSDFS/68を起動し、`RUN KEYTEST.S` を実行する。
5. USBキーボードで `A` を押し、次のように表示されることを確認する。

```text
SDFS> RUN KEYTEST.S
KEY WAIT
KEY 41 A
```

6. 必要に応じて再実行して `Enter` を押し、制御文字が `.` として表示されることを確認する。

```text
SDFS> RUN KEYTEST.S
KEY WAIT
KEY 0D .
```

## 追加確認

- 診断用S-Record実行後、SWIでROMモニタへ戻ること。
- ROMモニタで `KEYTEST` を入力すると `?` を返すこと。
- VDG有効profileでは、`KEYTEST.S` の表示が1st ACIAとVDG画面へ複製されること。

## 記録する内容

- 使用したROM profileとROM種別。
- KKBD-USBのファームウェア版またはコミット。
- KKBD-USBのジャンパー設定。
- SBC-IO 2nd ACIAの配線。
- `MAP` 出力。
- `RUN KEYTEST.S` の表示結果。
