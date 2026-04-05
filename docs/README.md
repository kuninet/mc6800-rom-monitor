# docs 目次

`docs/` は、要件、設計、計画、進捗を分けて管理するためのディレクトリです。

## ディレクトリ構成

- [requirements/](/Users/kuninet/git/MC6800_monitor/docs/requirements): 何を作るか、どの制約があるかをまとめる
- [design/](/Users/kuninet/git/MC6800_monitor/docs/design): どう作るかをまとめる
- [plans/](/Users/kuninet/git/MC6800_monitor/docs/plans): 実装順序やフェーズ分割をまとめる
- [testing/](/Users/kuninet/git/MC6800_monitor/docs/testing): 実機確認や検証手順をまとめる
- [progress/](/Users/kuninet/git/MC6800_monitor/docs/progress): 日ごとの進捗を残す

## 運用ルール

- 要件変更は `requirements/` を更新する
- 設計判断や配置案は `design/` を更新する
- 実装順序やフェーズ見直しは `plans/` を更新する
- 実機確認手順や検証観点は `testing/` を更新する
- 作業の区切りごとに `progress/YYYY-MM-DD.md` へ記録を残す
- 作業単位の正式な管理は GitHub Issue と PR を使う

## 現在の主要ドキュメント

- [requirements/monitor_requirements.md](/Users/kuninet/git/MC6800_monitor/docs/requirements/monitor_requirements.md)
- [design/memory_map.md](/Users/kuninet/git/MC6800_monitor/docs/design/memory_map.md)
- [plans/implementation_plan.md](/Users/kuninet/git/MC6800_monitor/docs/plans/implementation_plan.md)
- [testing/sbc6800_bringup.md](/Users/kuninet/git/MC6800_monitor/docs/testing/sbc6800_bringup.md)
- [testing/macos_tl866ii_plus.md](/Users/kuninet/git/MC6800_monitor/docs/testing/macos_tl866ii_plus.md): UNIX 系環境で TL866II Plus を使う手順
- [progress/2026-03-22.md](/Users/kuninet/git/MC6800_monitor/docs/progress/2026-03-22.md)
