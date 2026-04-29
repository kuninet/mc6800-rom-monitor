# プロジェクト引き継ぎコンテキスト

この文書は、新しい Codex や別の生成 AI がこのリポジトリだけを見て作業を始めるための入口である。作業前に [workflow.md](workflow.md) と合わせて読む。

## 現在の前提

- 対象 CPU は MC6800。
- 現在のターゲットボードは SBC6800。
- シリアル I/O は MC6850 ACIA。
- ROM は基本 `$E000-$FFFF`、最大 8KB を上限として扱う。
- 初期 RAM 想定は 8KB 以上だが、SD/FAT 拡張では SBC-IO による RAM 拡張も検討対象。
- モニタは MIKBUG 完全互換ではなく、BASIC が使う文字 I/O 入口互換を重視する。
- 既存コマンド、メモリマップ、I/O アドレスは、変更前に docs と smoke test の影響を確認する。

## 主要ドキュメントの読み順

1. [README.md](../../README.md): プロジェクト概要。
2. [workflow.md](workflow.md): Issue/PR、テスト、レビューの開発運用。
3. [docs/requirements/monitor_requirements.md](../requirements/monitor_requirements.md): ROM モニタ全体の要件。
4. [docs/usage/monitor_commands.md](../usage/monitor_commands.md): 現在のコマンド仕様。
5. [docs/design/memory_map.md](../design/memory_map.md): メモリマップ。
6. [docs/design/architecture.md](../design/architecture.md): 全体構成。
7. [docs/testing/windows_emulator_ci.md](../testing/windows_emulator_ci.md): エミュレータと CI の確認手順。
8. [docs/requirements/2026-04-25_sdcard_spi_fat_requirements.md](../requirements/2026-04-25_sdcard_spi_fat_requirements.md): SD/FAT 拡張の検討結果。

## テストとCI

現在の基本確認は Windows エミュレータ smoke test で行う。

```powershell
make bin
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
```

`REQUIRE_BUILD_ROM=1` を付けると、fixture ではなく最新ソースから生成した `build/mc6800-monitor.bin` を要求する。PR 前の確認ではこの経路を使う。

新しい振る舞いを実装する場合は、既存 smoke test が通るだけでは不十分である。追加した機能に対応するテストを追加し、入力と期待結果を固定する。

## SD/FAT検討の経緯

SD/FAT 拡張は、MC6821 PIA の bit-bang SPI で SDHC を読み、FAT32 read-only の `DIR` と `LF filename` を実装する方向で再設計している。

重要な経緯は次の通り。

- 検討 Issue: [#38](https://github.com/kuninet/mc6800-rom-monitor/issues/38)
- PoC PR: [#46](https://github.com/kuninet/mc6800-rom-monitor/pull/46)
- PoC 参照ブランチ: `feature/sdcard-spi-fat`
- 再実装 Issue: [#47](https://github.com/kuninet/mc6800-rom-monitor/issues/47) から [#54](https://github.com/kuninet/mc6800-rom-monitor/issues/54)

`feature/sdcard-spi-fat` は PoC 参照用として残す。不要ファイル混入、コマンド仕様ズレ、FAT32処理の未達点があるため、そのまま main へ統合しない。

PoC で確認された主な注意点は次の通り。

- `CMD_RESUME` と変数領域競合の修正は有望だが、SD/FAT本体とは分けて救出する。
- `DIR` 相当が `V` になっていたが、再実装では `DIR` を正式コマンドにする。
- `LF filename` は、コマンドとファイル名の間の空白を扱えるようにする。
- FAT32 は MBRあり/なし、`BPB_RootClus`、cluster chain、file size 終端を正しく扱う。
- root directory の先頭 1 sector だけを見る実装にはしない。
- `.DS_Store`、実験用 `.img`、個人メモを PR に含めない。

## SD/FAT再実装のIssue分割

- [#47](https://github.com/kuninet/mc6800-rom-monitor/issues/47): `CMD_RESUME` と変数領域修正の救出。
- [#48](https://github.com/kuninet/mc6800-rom-monitor/issues/48): SD/PIA エミュレータと FAT32 fixture 整備。
- [#49](https://github.com/kuninet/mc6800-rom-monitor/issues/49): PIA SPI 経由の SDHC sector read 最小実装。
- [#50](https://github.com/kuninet/mc6800-rom-monitor/issues/50): FAT32 BPB/MBR/RootClus 解析。
- [#51](https://github.com/kuninet/mc6800-rom-monitor/issues/51): FAT chain、file size、8.3検索。
- [#52](https://github.com/kuninet/mc6800-rom-monitor/issues/52): `DIR` / `LF filename` コマンド統合。
- [#53](https://github.com/kuninet/mc6800-rom-monitor/issues/53): FAT上の S-Record / Intel HEX LOAD。
- [#54](https://github.com/kuninet/mc6800-rom-monitor/issues/54): 実機PoCとSBC-IO PIAアドレス確定。

SD/FAT本体に入る前に、この開発運用文書を main へ入れる。その後、#47 から順に小さい PR で進める。

## Blogとの関係

Blogその13は、検討内容を読み物としてまとめた補助資料である。開発判断の正式な参照先は Git 管理下の docs、GitHub Issue、PR とする。

Blogにしか残っていない判断がある場合は、実装前に docs へ要点を移す。Issue/PR本文には、関連Issueへのリンクを必ず入れる。

## 変更対象外の扱い

既存の `docs/plans/phase5_sdcard.md` と `docs/plans/phase5_sdcard_codex_parallel.md` は、PoC前後の経緯を示す資料として残す。SD/FAT再実装で参照してよいが、別Issueで明示されていない限り、編集、整形、移動、削除をしない。
