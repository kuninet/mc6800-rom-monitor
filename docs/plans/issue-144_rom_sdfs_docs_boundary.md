# Issue #144 ROMモニタとSDFS/68責務境界のユーザー向け文書整理

## 背景

ROMモニタ、ROM常駐FAT、`BOOT`、stage1、SDFS/68の責務が、ユーザー向け文書を読んだときに混ざって見えやすくなっていた。
特に、ROMだけで何ができるか、SDFS/68を使うにはsystem SDが必要か、ROM常駐FAT `DIR` / `LF` が本線なのか互換なのかが分かりにくい。

## 採用方針

- ROMモニタは低レベル操作、復旧口、マシン語デバッガとして説明する。
- `BOOT` はSDFS/68起動入口であり、ROMにDOS機能を増やす入口ではない。
- stage1と `SDFS.BIN` はsystem SD側の成果物として説明する。
- SDFS/68は通常運用の第2段DOSとして説明する。
- ROM常駐FAT `DIR` / `LF` は `sbcio` profileの互換機能として扱い、本線は `BOOT + SDFS/68` へ寄せる。
- 図はGitHubで表示できるMermaid、一覧はMarkdown表で記録する。

## 更新対象

- `README.md`: レイヤー構成とSDFS/68の位置づけ。
- `docs/usage/build_commands.md`: profile別の位置づけ、成果物、SDFS/68起動フロー。
- `docs/usage/monitor_commands.md`: ROM視点のコマンド所属。
- `docs/usage/sdfs68_system_sd.md`: SDFS/68視点のsystem SD要否と操作フロー。
- `docs/README.md`: docs目次でのROM文書とSDFS/68文書の違い。
- `docs/plans/issue-sdfs68_responsibility_boundary.md`: #136方針の補強。
- `docs/plans/issue-128_rom_fat_cleanup.md`: ROM FAT互換扱いの補強。

## 対象外

- ROM実装、SDFS/68実装、Makefile、テストコードの変更。
- ROM常駐FAT `DIR` / `LF` の削除。
- SDFS/68 v2コマンドの実装。
- stage1 APIやSD/FAT処理の変更。

## 検証方針

- Markdownリンクを目視確認する。
- MermaidコードブロックがGitHub互換の `flowchart TD` になっていることを確認する。
- `DIR` / `LF` / `BOOT` / `RUN` / `EXIT` の説明が、ROM本線、ROM常駐FAT互換、SDFS/68の責務境界と矛盾しないことを確認する。
- 生成物や不要ファイルが差分に含まれていないことを確認する。
