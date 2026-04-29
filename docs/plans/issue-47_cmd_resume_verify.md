# Issue #47 CMD_RESUME確認計画

## 目的

[Issue #47](https://github.com/kuninet/mc6800-rom-monitor/issues/47) では、PoC PR [#46](https://github.com/kuninet/mc6800-rom-monitor/pull/46) に含まれていた `CMD_RESUME` 修正と変数領域競合回避を確認する。

ただし、この作業は修正ありきでは進めない。現在の `main` で本当に不具合が残っているかを確認し、必要な場合だけ最小差分で修正する。
今回のテストでは変数領域競合回避の実装を追加するのではなく、モニタ作業領域と競合しない検証アドレスを使って `CMD_RESUME` の復帰動作を確認する。

## 現状確認

現在の `main` の `CMD_RESUME` は、`BRK_SAVE_*` に保存した CC/B/A/X/PC を `BRK_FRAME` が指す SWI フレームへ書き戻し、`txs` と `rti` で復帰する形になっている。

これは PoC PR #46 の「CMD_RESUME のレジスタ復元ロジック修正」後の方向と同じである。そのため、PoC ブランチから `src/main.asm` の SD/FAT 実装や大きな変数再配置を取り込む必要はない可能性が高い。

## 実装方針

- `src/main.asm` は追加テストで不具合が再現しない限り変更しない。
- PoC PR #46 から SD/FAT、PIA、`.DS_Store`、SDカードイメージ、PoC由来の大規模差分は取り込まない。
- `tests/test_smoke.py` に `CMD_RESUME` の不足観点を補う回帰テストを追加する。
- `AGENTS.md` と `docs/development/workflow.md` に、Issue単位の実装前計画を `docs/plans/` に残す運用を追記する。

## 追加する確認観点

- breakpoint resume 後に A/B/X が保持され、復元された元命令以降が実行されること。
- user SP が resume 後に復元され、`STS` で期待値を書けること。
- breakpoint停止中でない単独 `R` が `?` を返すこと。

user SP の確認値は `$1D00` とする。`$1E80` は現在の `MONITOR_RAM_BASE=$1E00` 配下のモニタ作業領域と重なり、SWI フレームやモニタ変数を壊すテストになるため、`CMD_RESUME` の純粋な回帰確認には使わない。

## 完了条件

- `make bin` が通る。
- `$env:REQUIRE_BUILD_ROM='1'; python tests/test_smoke.py` が通る。
- 追加テストが全て通る場合、#47 は「現行実装の確認と回帰テスト追加」として完了する。
- 追加テストで失敗した場合だけ、失敗内容を根拠に `CMD_RESUME` か SWI フレーム処理を最小修正する。

## 対象外

- SD/FAT本体。
- PIA/SPI実装。
- PoCブランチの不要ファイル整理。
- `docs/plans/phase5_sdcard.md` と `docs/plans/phase5_sdcard_codex_parallel.md` の編集。
- `docs/requirements/wk_問答.md` の編集。
