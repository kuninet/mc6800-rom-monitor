# docs 目次

`docs/` は、要件、設計、計画、進捗を分けて管理するためのディレクトリです。

## ディレクトリ構成

- [requirements/](requirements/): 何を作るか、どの制約があるかをまとめる
- [development/](development/): 開発運用、Issue/PR、引き継ぎコンテキストをまとめる
- [usage/](usage/): 実機やエミュレータでの使い方をまとめる
- [design/](design/): どう作るかをまとめる
- [plans/](plans/): 実装順序やフェーズ分割をまとめる
- [testing/](testing/): 実機確認や検証手順をまとめる
- [progress/](progress/): 日ごとの進捗を残す

## 運用ルール

- 要件変更は `requirements/` を更新する
- 開発運用や新規コンテキストへの引き継ぎ情報は `development/` を更新する
- 設計判断や配置案は `design/` を更新する
- 実装順序やフェーズ見直しは `plans/` を更新する
- 実機確認手順や検証観点は `testing/` を更新する
- 作業の区切りごとに `progress/YYYY-MM-DD.md` へ記録を残す
- 作業単位の正式な管理は GitHub Issue と PR を使う

## 現在の主要ドキュメント

- [requirements/monitor_requirements.md](requirements/monitor_requirements.md)
- [development/workflow.md](development/workflow.md): Issue/PR、テスト、レビューの開発運用ルール
- [development/project_context.md](development/project_context.md): 新規コンテキスト向けのプロジェクト引き継ぎ情報
- [usage/monitor_commands.md](usage/monitor_commands.md): ROM モニタのコマンドリファレンス
- [design/memory_map.md](design/memory_map.md)
- [design/architecture.md](design/architecture.md)
- [plans/implementation_plan.md](plans/implementation_plan.md)
- [testing/sbc6800_bringup.md](testing/sbc6800_bringup.md)
- [testing/sbc6800_datapack.md](testing/sbc6800_datapack.md): SBC6800 データパックの扱いと互換確認
- [testing/macos_tl866ii_plus.md](testing/macos_tl866ii_plus.md): UNIX 系環境で TL866II Plus を使う手順
- [testing/wsl2_tl866ii_plus.md](testing/wsl2_tl866ii_plus.md): WSL2 で TL866II Plus と minipro を試す手順
- [testing/windows_emulator_ci.md](testing/windows_emulator_ci.md): Windows エミュレータと GitHub Actions の手順
- [progress/2026-03-22.md](progress/2026-03-22.md)
- [progress/2026-04-05.md](progress/2026-04-05.md)
- [progress/2026-04-08.md](progress/2026-04-08.md)
- [progress/2026-04-14.md](progress/2026-04-14.md)
