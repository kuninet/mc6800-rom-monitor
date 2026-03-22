# mc6800-rom-monitor

MC6800 向けの小型 ROM モニタプロジェクトです。

初版は USB シリアル接続された端末を前提に、MC6850 ACIA 経由で対話する ROM モニタを目指します。ROM 容量 2KB を主目標に置き、メモリダンプ、メモリ変更、指定アドレス実行、S-Record / Intel HEX のロードを段階的に実装します。

MIKBUG 全体の完全互換は狙いませんが、電大版 BASIC が利用する文字入出力エントリーポイント互換は重視します。

## 現在の前提

- CPU: MC6800
- シリアル I/O: MC6850 ACIA
- ACIA クロック: 153.6 kHz
- ボーレート: 9600 bps
- 文字コード: ASCII
- 入力行終端: 既定は `CR`
- 出力行終端: `CRLF`
- アセンブラ: Macro Assembler AS
- 初版 ROM サイズ目標: 2KB
- 初版 RAM 想定: 8KB 以上

## ドキュメント

- [requirements.md](/Users/kuninet/git/MC6800_monitor/requirements.md): 要件定義
- [memory_map.md](/Users/kuninet/git/MC6800_monitor/memory_map.md): 初版メモリマップ案

## 初版スコープ

初版の必須機能は次を想定しています。

- ACIA 初期化
- 1 文字入力
- 1 文字出力
- 1 行入力
- 16 進入力変換
- メモリダンプ
- メモリ変更
- 指定アドレス実行
- Motorola S-Record ロード
- Intel HEX ロード
- MIKBUG 互換 I/O エントリーポイント

次フェーズ以降で検討する機能は次です。

- S-Record / Intel HEX 保存
- レジスタ表示と変更
- ソフトウェアブレーク
- ハード支援デバッグ
- ビデオ出力対応

## 開発方針

- デバイス依存部とモニタ本体を分ける
- メモリマップと I/O アドレスは定義切り替えで再ビルド可能にする
- 2KB ROM 制約を優先し、初版では保存やデバッグ機能を削る
- MIKBUG 互換は BASIC が使う I/O 入口に限定する

## 想定ディレクトリ構成

- `src/`: モニタ本体
- `src/platform/`: ボード依存部
- `include/`: 定義値やアドレス設定
- `docs/`: 将来の補足資料

実装前段階のため、現時点ではドキュメント整備を優先しています。
