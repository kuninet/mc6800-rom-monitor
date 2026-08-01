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

ROMモニタとSDFS/68は別レイヤーとして読む。
[usage/monitor_commands.md](usage/monitor_commands.md) はROMモニタの `] ` プロンプトで使うコマンド、[usage/sdfs68_system_sd.md](usage/sdfs68_system_sd.md) はSDFS/68の `SDFS> ` プロンプトとsystem SDの方針を扱う。
標準profileではROM常駐FAT `DIR` / `LF` を本線から外し、`BOOT + SDFS/68` を通常運用の本線にする。
ROM常駐FATを確認したい場合は、profileではなく直接構成軸で `FEATURE_SD=1 FEATURE_FAT=1` を指定する。

- [requirements/monitor_requirements.md](requirements/monitor_requirements.md)
- [development/workflow.md](development/workflow.md): Issue/PR、テスト、レビューの開発運用ルール
- [development/project_context.md](development/project_context.md): 新規コンテキスト向けのプロジェクト引き継ぎ情報
- [usage/monitor_commands.md](usage/monitor_commands.md): ROM モニタのコマンドリファレンス
- [usage/sdfs68_system_sd.md](usage/sdfs68_system_sd.md): SDFS/68 と system SD の初期方針
- [design/memory_map.md](design/memory_map.md)
- [design/architecture.md](design/architecture.md)
- [design/sdfs68_com_abi.md](design/sdfs68_com_abi.md): SDFS/68 `.COM` トランジェントコマンドABI
- [plans/implementation_plan.md](plans/implementation_plan.md)
- [plans/issue-103_mk_sdfs_image.md](plans/issue-103_mk_sdfs_image.md): SDFS/68 システムSDイメージ生成ツールの実装計画
- [plans/issue-101_rom_stage1_boot.md](plans/issue-101_rom_stage1_boot.md): ROM固定LBA stage1 BOOT
- [plans/issue-102_sdfs68_minimal.md](plans/issue-102_sdfs68_minimal.md): SDFS/68最小本体とboot services接続
- [plans/issue-107_fixed_sector_boot_eval.md](plans/issue-107_fixed_sector_boot_eval.md): 固定セクタ版SDFS/68 loaderのROM削減評価
- [plans/issue-109_stage1_boot_services.md](plans/issue-109_stage1_boot_services.md): SDFS/68 stage1 boot services設計
- [plans/issue-113_stage1_header_build.md](plans/issue-113_stage1_header_build.md): SDFS/68 stage1 header / jump table とビルド基盤
- [plans/issue-115_stage1_sd_read.md](plans/issue-115_stage1_sd_read.md): SDFS/68 stage1 SD raw sector read boot services
- [plans/issue-117_stage1_fat_mount.md](plans/issue-117_stage1_fat_mount.md): SDFS/68 stage1 FAT32 mount boot service
- [plans/issue-119_stage1_find_83.md](plans/issue-119_stage1_find_83.md): SDFS/68 stage1 root 8.3 find boot service
- [plans/issue-121_stage1_load_file_1sector.md](plans/issue-121_stage1_load_file_1sector.md): SDFS/68 stage1 1-sector file load boot service
- [plans/issue-123_stage1_memory_3kb.md](plans/issue-123_stage1_memory_3kb.md): SDFS/68 stage1 3KB配置
- [plans/issue-125_stage1_sdfs_entry.md](plans/issue-125_stage1_sdfs_entry.md): SDFS/68 stage1 header検査とentry jump
- [plans/issue-128_rom_fat_cleanup.md](plans/issue-128_rom_fat_cleanup.md): SDFS/68移行後のROM常駐FAT DIR/LF整理
- [plans/issue-129_sdfs68_migration_roadmap.md](plans/issue-129_sdfs68_migration_roadmap.md): SDFS/68 v1移行とROM FAT整理ロードマップ
- [plans/issue-130_sdfs68_loader.md](plans/issue-130_sdfs68_loader.md): SDFS/68 v1 HEX/S-recordロード
- [plans/issue-sdfs68_responsibility_boundary.md](plans/issue-sdfs68_responsibility_boundary.md): SDFS/68とROMモニタの責務境界
- [plans/issue-sdfs68_v2_roadmap.md](plans/issue-sdfs68_v2_roadmap.md): SDFS/68 v2 第2段DOS基本操作ロードマップ
- [plans/sdfs68_v3/README.md](plans/sdfs68_v3/README.md): SDFS/68 v3 設計メモ
- [plans/sdfs68_v3/issue-255_boundary.md](plans/sdfs68_v3/issue-255_boundary.md): SDFS/68 v3 責務境界とv2互換性方針
- [plans/issue-141_sdfs68_load.md](plans/issue-141_sdfs68_load.md): SDFS/68 LOAD正式化
- [plans/issue-149_sdfs68_run_addr.md](plans/issue-149_sdfs68_run_addr.md): SDFS/68 RUN addr
- [plans/issue-150_sdfs68_run_file.md](plans/issue-150_sdfs68_run_file.md): SDFS/68 RUN filename
- [plans/issue-153_sdfs68_dir_run_polish.md](plans/issue-153_sdfs68_dir_run_polish.md): SDFS/68 DIR/RUN表示改善
- [plans/issue-155_sdfs68_line_input.md](plans/issue-155_sdfs68_line_input.md): SDFS/68 行入力改善
- [plans/issue-167_vdg_console_output.md](plans/issue-167_vdg_console_output.md): VDG console出力
- [plans/issue-175_rom_size_audit.md](plans/issue-175_rom_size_audit.md): ROM容量削減とデッドコード探索
- [plans/issue-177_sbcio_profile_cleanup.md](plans/issue-177_sbcio_profile_cleanup.md): sbcio profileのSD/FAT整理
- [plans/issue-144_rom_sdfs_docs_boundary.md](plans/issue-144_rom_sdfs_docs_boundary.md): ROMモニタとSDFS/68責務境界のユーザー向け文書整理
- [../diagnostics/README.md](../diagnostics/README.md): SDからロードして使う診断用S-Record
- [../sdfs_tools/README.md](../sdfs_tools/README.md): SDFS/68向け S-Record / `.COM` ツールサンプル
- [testing/sbc6800_bringup.md](testing/sbc6800_bringup.md)
- [testing/sbc_io_sd_bringup.md](testing/sbc_io_sd_bringup.md): SBC-IO と microSD SPI モジュールで SD/FAT を実機確認する手順
- [testing/sbc6800_datapack.md](testing/sbc6800_datapack.md): SBC6800 データパックの扱いと互換確認
- [testing/macos_tl866ii_plus.md](testing/macos_tl866ii_plus.md): UNIX 系環境で TL866II Plus を使う手順
- [testing/wsl2_tl866ii_plus.md](testing/wsl2_tl866ii_plus.md): WSL2 で TL866II Plus と minipro を試す手順
- [testing/windows_emulator_ci.md](testing/windows_emulator_ci.md): Windows エミュレータと GitHub Actions の手順
- [progress/2026-03-22.md](progress/2026-03-22.md)
- [progress/2026-04-05.md](progress/2026-04-05.md)
- [progress/2026-04-08.md](progress/2026-04-08.md)
- [progress/2026-04-14.md](progress/2026-04-14.md)
