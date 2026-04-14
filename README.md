# mc6800-rom-monitor

MC6800 向けの小型 ROM モニタプロジェクトです。

初版は USB シリアル接続された端末を前提に、MC6850 ACIA 経由で対話する ROM モニタを目指します。ROM 容量 2KB を主目標に置き、メモリダンプ、メモリ変更、指定アドレス実行、S-Record / Intel HEX のロードを段階的に実装します。

MIKBUG 全体の完全互換は狙いませんが、電大版 BASIC が利用する文字入出力エントリーポイント互換は重視します。

## 現在の前提

- CPU: MC6800
- ターゲットボード: SBC6800
- シリアル I/O: MC6850 ACIA
- ACIA クロック: 153.6 kHz
- ボーレート: 9600 bps
- 文字コード: ASCII
- 入力行終端: 既定は `CR`
- 出力行終端: `CRLF`
- アセンブラ: Macro Assembler AS
- 初版 ROM サイズ目標: 2KB
- 初版 RAM 想定: 8KB 以上

当面の動作確認ターゲットは SBC6800 とし、ROM 差し替えで起動確認できる状態を目標にします。MINIBUG 互換ボード向けの配置検討は別課題として保留します。

## ドキュメント

- [docs/README.md](/Users/kuninet/git/MC6800_monitor/docs/README.md): docs 全体の目次
- [docs/requirements/monitor_requirements.md](/Users/kuninet/git/MC6800_monitor/docs/requirements/monitor_requirements.md): 要件定義
- [docs/design/memory_map.md](/Users/kuninet/git/MC6800_monitor/docs/design/memory_map.md): 初版メモリマップ案
- [docs/design/architecture.md](/Users/kuninet/git/MC6800_monitor/docs/design/architecture.md): モニタ全体のアーキテクチャ
- [docs/plans/implementation_plan.md](/Users/kuninet/git/MC6800_monitor/docs/plans/implementation_plan.md): 実装計画
- [docs/progress/2026-03-22.md](/Users/kuninet/git/MC6800_monitor/docs/progress/2026-03-22.md): 初期進捗ログ
- [docs/progress/2026-04-05.md](/Users/kuninet/git/MC6800_monitor/docs/progress/2026-04-05.md): WSL2 minipro 検証ログ
- [docs/progress/2026-04-08.md](/Users/kuninet/git/MC6800_monitor/docs/progress/2026-04-08.md): WSL2 minipro 書き込み成功ログ
- [docs/progress/2026-04-14.md](/Users/kuninet/git/MC6800_monitor/docs/progress/2026-04-14.md): フェーズ4 ローダ実装と実機確認ログ
- [docs/testing/sbc6800_bringup.md](/Users/kuninet/git/MC6800_monitor/docs/testing/sbc6800_bringup.md): SBC6800 実機確認手順
- [docs/testing/macos_tl866ii_plus.md](/Users/kuninet/git/MC6800_monitor/docs/testing/macos_tl866ii_plus.md): UNIX 系環境で TL866II Plus を使う手順
- [docs/testing/wsl2_tl866ii_plus.md](/Users/kuninet/git/MC6800_monitor/docs/testing/wsl2_tl866ii_plus.md): WSL2 で TL866II Plus と minipro を試す手順

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

## ビルド

現在のフェーズ1では GNU make から次の生成物を作れるようにしています。

- `make srec`: Motorola S-record を生成
- `make ihex`: Intel HEX を生成
- `make bin`: ROM イメージのバイナリを生成
- `make`: S-record と Intel HEX をまとめて生成

SBC6800 前提の現在値:

- ROM: `$E000-$FFFF`
- RAM: `$0000-$1FFF`
- ACIA control/status: `$8018`
- ACIA data: `$8019`

前提ツール:

- `asl`
- `p2bin`
- `p2hex`
- `minipro`

## 想定ディレクトリ構成

- `src/`: モニタ本体
- `src/platform/`: ボード依存部
- `include/`: 定義値やアドレス設定
- `docs/requirements/`: 要件定義
- `docs/design/`: 設計資料
- `docs/plans/`: 実装計画
- `docs/progress/`: 進捗ログ

実装前段階のため、現時点ではドキュメント整備を優先しています。
