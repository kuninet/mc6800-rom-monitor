# AGENTS.md

## 文書言語の統一

- ユーザーへの応答、GitHub Issue、Pull Request、コミットコメント、リポジトリ内ドキュメントは日本語で記載する。
- `docs/` 以下の計画書、設計書、要求メモ、進捗メモも日本語で記載する。
- 英語の識別子、コマンド名、ファイル名、CPU命令名、外部仕様名は必要に応じてそのまま使ってよいが、説明本文は日本語にする。

## Git操作の権限

- このプロジェクトで `git switch`、`git add`、`git commit`、`git push` などのGit操作を行う場合は、必ず権限昇格して実行する。
- Git操作がsandbox権限で失敗してから昇格するのではなく、最初から権限昇格を指定する。

## Issue close文言

- 対応IssueがそのPRで完了する場合、PR本文の対応Issue欄には `Closes #番号` を記載する。
- 参照だけで完了しないIssueには `Refs #番号` を使う。

## 親子Issue(sub-issue)

- 親子関係のあるIssueは、本文の `Refs` 表記だけで済ませず、GitHub の sub-issue として必ず正式に紐づける。
- `gh` CLI には sub-issue サブコマンドが無いため、GraphQL API で紐づける。
  ```sh
  P=$(gh issue view <親番号> --json id -q .id)
  C=$(gh issue view <子番号> --json id -q .id)
  gh api graphql -H "GraphQL-Features: sub_issues" \
    -f query='mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c}){subIssue{number}}}' \
    -F p="$P" -F c="$C"
  ```
- close済みのIssueも sub-issue として追加できる。

## 分割PRの紐づけ(パターンA)

GitHub Project の「Linked pull requests」列でPRを取りこぼさず追跡するための標準運用。

- 1つの作業を複数PRに分ける場合は、**PRステップごとに sub-issue を作り、各PRは `Closes #<そのstep-issue>`** を使う。これで全PRが該当Issueの「Linked pull requests」列に並び、取りこぼさない。
- 単一PRで完了する作業は、そのPRが対象Issueを `Closes` する。
- 親/アンブレラIssue(例 #216)は **close しない**。`Refs` と sub-issue ツリーで束ねる(`Closes` しない)。
- 注意: 「Linked pull requests」列はリンク(`Closes`/`Fixes`/`Resolves` または手動リンク)でのみ埋まり、`Refs` では出ない。そしてリンクはデフォルトブランチへのマージでIssueを自動closeする。「リンクするが閉じない」手段は無いため、閉じたくないIssueには上記のstep-issue分割で対応する。

## 生成AIの痕跡を残さない

- GitHub Issue、Pull Request、コミットメッセージに、生成AI由来であることを示す痕跡を一切残さない。
- コミットに `Co-Authored-By` の生成AI署名を付けない。PR本文に「Generated with ...」等のフッタを付けない。
- 道具名(解析ツール等)を手段として記載するのは痕跡ではないので可。

## テスト実行

- コード変更後と PR 作成前は、**必ず全テストを実行する**。正規手順は `make test`(ビルド前提込みで全テストを実行)。
- ドキュメントのみの変更では `make test` を省略してよい。その場合は PR 本文に「ドキュメントのみのためテスト省略」と明記する。
- 手順の詳細は `docs/development/workflow.md` の「テスト方針」を参照。
- テストは pytest ではなくスクリプト直実行。エミュテストは先に base profile をビルドしないと環境失敗する(`make test` が自動で満たす)。

## 改行コードを変更しない

- ファイルの既存の改行コードを変更しない(正規化しない)。`src/main.asm` は CRLF、その他は LF。
- 編集ツールは保存時に CRLF→LF 正規化することがあるため、CRLF ファイルはバイト保持の方法で編集する。
- コミット前に `git diff --numstat` と `git diff --ignore-all-space --numstat` が一致することを確認する(乖離=改行コードが壊れた合図)。

このリポジトリで Codex が作業する際のローカル運用ルールを定義する。

## 言語

- ユーザーへの応答は常に日本語で行う
- GitHub の Issue と Pull Request は日本語で記載する

## Git ワークフロー

- GitHub で管理されている作業は Issue に紐づけて進める
- 実装前に対応 Issue を確認し、作業ブランチを作成する
- 修正後は Pull Request を作成する
- マージは人間が行うため、Codex は絶対にマージしない

## 作業開始時の確認

- 作業前に `docs/development/workflow.md` を読み、このプロジェクトの Issue/PR、テスト、レビュー運用を確認する
- 新しいコンテキストで作業する場合は `docs/development/project_context.md` も読み、現在の制約、主要ドキュメント、SD/FAT 再実装の経緯を確認する
- Blog や過去会話だけにある判断は、必要に応じて Git 管理下の docs / Issue / PR に要点を残す

## Issue 単位の計画

- 実装前に Issue ごとの計画を立て、必要に応じて `docs/plans/` に残す
- `docs/plans/` には Issue 本文の丸写しではなく、確認した事実、採用した判断、検証方針、後続作業への引き継ぎを残す
- Issue はタスク管理、PR は変更説明、`docs/plans/` は将来の開発コンテキストとして使い分ける

## チーム運用

- 作業は基本的にエージェントチームで進める
- 標準の役割は `実装計画`、`実装者`、`批判的レビュー者` の 3 つとする
- 調査と実行の担当には軽いモデルを優先して使う

## レビュー運用

- 批判的レビュー者から指摘が出た場合は、まずユーザーに共有して対応判断を仰ぐ
- レビュー指摘をユーザー確認なしで黙って握りつぶさない
