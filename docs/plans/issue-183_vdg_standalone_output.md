# Issue #183 VDGスタンドアロン出力方針

## 背景

VDG + 2nd ACIAキーボードでスタンドアロン運用する場合、1st ACIAが未接続でも起動表示まで進む必要がある。
従来の `ACIA_PUTC` は 1st ACIA の `TDRE` を無限待ちするため、UART送信レディが立たない環境では VDG への表示も止まる。

## 採用方針

- `FEATURE_VDG=0` では従来どおり `ACIA_PUTC` が送信レディを待つ。
- `FEATURE_VDG=1` では、1st ACIA が送信レディならUARTへ出し、送信レディでなければUART出力だけを捨てて先へ進む。
- VDG出力、2nd ACIAキーボード入力、UART入力fallbackの入口は変更しない。
- UARTが正常な場合は従来どおりUARTにも出る。

## 検証方針

- エミュレータに 1st ACIA `TDRE=0` 固定の再現オプションを追加する。
- `FEATURE_VDG=1` のROMで、UART出力が止まってもVRAM上に起動メッセージとプロンプトが出ることを確認する。
- 既存のUART正常時 smoke test を維持する。

## 対象外

- UART接続有無の自動検出。
- UART送信の再送やバッファリング。
- #182 のSDFS/68改行整理。
- #179 の `DS` 短幅ダンプ。
